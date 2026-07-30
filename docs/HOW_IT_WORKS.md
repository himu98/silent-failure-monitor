# How It Works — Detection Logic

This document explains the reasoning behind the detection engine. If you're going to
demo or defend this project, read this one.

## The core insight

Conventional monitoring is **error-driven**: something throws a 500, an exception fires,
a health check fails, an alert goes out. It answers "did something go wrong?"

Silent failures don't throw anything. The form submits, the page returns 200, the server
is healthy — the submission just never reaches a human. There is no error to catch.

So the question has to change from "did something go wrong?" to
**"did something stop happening that should have happened?"**

That reframing is the whole project. Everything below is implementation.

## Step 1 — Establish rhythm, not average

A flat average is useless for a business. A plumber gets twelve enquiries on a Monday
morning and zero on a Sunday night; averaging those produces a number that describes neither.

So the baseline is keyed on **(weekday, 4-hour window)**:

```
(Thursday, window 3)  ->  [3, 4, 2, 3, 5, 3, 2, 4]   median = 3
```

Each number is one historical Thursday's 12:00–16:00 count. The **median** is used rather
than the mean because one viral day or one spam flood would drag a mean upward and desensitise
the monitor permanently.

### The zero-window bug

The first version only recorded windows that *had* events. That silently excluded all the
zeros, so a slot that was empty half the time looked twice as busy as it really was — and the
monitor under-reacted to genuine outages.

The fix: enumerate every historical date and window explicitly, and record a `0` where nothing
happened. Absence has to be counted, in a tool about absence.

### Excluding today

The baseline stops 24 hours before "now". If an outage started this morning and today's zeros
fed the baseline, the tool would gradually learn that zero is normal — and stop alerting on
exactly the failure it was built to catch.

## Step 2 — Compare, don't assume

For each recent window the engine computes `actual / expected`. A window is anomalous when
that ratio falls below `sensitivity` (default `0.25`, i.e. under 25% of normal).

Windows are **skipped, not failed**, when they can't be judged fairly:

| Skip reason | Why |
|---|---|
| Outside business hours | 3am silence is not a signal |
| Fewer than 2 historical samples | No basis for comparison |
| Expected < 1.5 events | A normally-quiet slot proves nothing by being quiet |

Skipped windows don't count toward the confirmation requirement — the engine keeps walking
backwards (up to a generous lookback) until it finds enough comparable windows. Without this,
a Monday-morning check would find only weekend windows, skip them all, and conclude
"insufficient data" forever. This was a real bug caught in testing: the broken sample data
failed to alert because the second window fell outside business hours.

## Step 3 — Confirm before shouting

One bad window is noise. The engine requires **two consecutive judgeable windows** to both look
anomalous before it alerts.

This is standard practice in alerting design — requiring consecutive anomalous intervals rather
than a single one filters transient noise without losing sensitivity to sustained problems. The
cost is a delay of one window (four hours); the benefit is that the alert is trustworthy, which
is the only property that matters in monitoring. A tool that cries wolf gets muted, and a muted
monitor is worse than no monitor at all.

## Step 4 — Diagnose in the reader's language

Detection is only half the product. "Form submissions have dropped 100%" is useless to a bakery
owner who doesn't know what a form handler is.

The AI step takes the facts — event type, silence duration, expected vs actual — and produces a
short, calm, plain-English explanation with the three most likely causes and one concrete first
action. The prompt explicitly forbids inventing details, because a confidently wrong diagnosis
is worse than none.

If the AI call fails, a rule-based fallback produces a serviceable alert instead. **A monitoring
tool must not go silent when a dependency breaks** — that would reproduce the exact failure mode
it exists to detect.

## Step 5 — Don't nag

Once an alert fires, a 12-hour cooldown suppresses repeats. The outage is already known;
re-alerting every four hours trains the owner to ignore the emails.

## Tuning for a real client

| Setting | Default | Raise it when | Lower it when |
|---|---|---|---|
| `sensitivity` | 0.25 | Volume is spiky; you want fewer alerts | Volume is steady; you want earlier warning |
| `consecutive_windows_required` | 2 | False alarms are annoying the client | Every hour of downtime is expensive |
| `check_window_hours` | 4 | Low-volume business | High-volume business wanting fast detection |
| `min_expected_to_alert` | 1.5 | Business is very quiet generally | Business is busy and every lead matters |

A reasonable rule: log two weeks of data before enabling alerts, look at the actual variance,
then set thresholds from what you observe rather than from a default.

## Known limitations (be honest about these)

- **Public holidays look like outages.** A holiday calendar is the obvious next feature.
- **Seasonal businesses** with long quiet periods need a longer baseline window than 90 days.
- **Very low-volume businesses** (under ~1 event/day) can't be monitored this way — there's no
  rhythm to detect a break in. Synthetic testing is the right tool for them.
- **A partial failure** (form works for some browsers) shows as a dip, not a stop, and may sit
  above the sensitivity threshold. Severity tiers would address this.
