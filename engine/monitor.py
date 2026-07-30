"""
Silent Failure Monitor - core detection engine
==============================================

Detects when an expected stream of business events STOPS arriving
(form submissions, orders, bookings, report deliveries) and explains
the likely cause in plain English.

Traditional monitoring watches for errors. This watches for absence.

Usage:
    python monitor.py sample_data/form_submissions.csv
    python monitor.py sample_data/form_submissions.csv --config config.json

Set ANTHROPIC_API_KEY for AI-written diagnosis; otherwise a rule-based
fallback is used so the tool always runs.
"""

import argparse
import csv
import json
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_CONFIG = {
    "event_name": "contact form submission",
    "business_name": "the business",
    "timezone_note": "local time",
    "business_hours": {"start": 9, "end": 18},
    "business_days": [0, 1, 2, 3, 4],          # Mon=0 ... Sun=6
    "check_window_hours": 4,                    # size of each evaluation window
    "min_history_days": 14,                     # refuse to judge without this much data
    "sensitivity": 0.25,                        # alert if actual < 25% of expected
    "min_expected_to_alert": 1.5,               # ignore windows that are normally quiet
    "consecutive_windows_required": 2,          # confirm before alerting (kills noise)
    "alert_cooldown_hours": 12,                 # don't re-alert constantly
}


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def load_events(path):
    """Read a CSV with a timestamp column. Returns a sorted list of datetimes."""
    events = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        ts_field = None
        for candidate in ("timestamp", "date", "datetime", "created_at", "time"):
            if reader.fieldnames and candidate in [c.lower() for c in reader.fieldnames]:
                ts_field = [c for c in reader.fieldnames if c.lower() == candidate][0]
                break
        if ts_field is None:
            raise ValueError("CSV needs a timestamp/date/datetime/created_at column")

        for row in reader:
            raw = (row.get(ts_field) or "").strip()
            if not raw:
                continue
            dt = parse_timestamp(raw)
            if dt:
                events.append(dt)
    return sorted(events)


def parse_timestamp(raw):
    """Tolerant timestamp parsing - real client data is messy."""
    raw = raw.replace("T", " ").replace("Z", "").strip()
    raw = re.sub(r"[+-]\d{2}:?\d{2}$", "", raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------------
# Baseline: what does "normal" look like for this business?
# ----------------------------------------------------------------------

def build_baseline(events, cfg, now):
    """
    Businesses have weekly rhythms, not flat averages. A Tuesday 10am is not a
    Sunday 10am. So the baseline is keyed on (weekday, window-of-day) and we take
    the MEDIAN of historical windows - medians ignore one freak busy day.

    Important: windows that historically saw ZERO events must count as zeros,
    otherwise the median is biased upward and the monitor under-reacts.
    """
    window = cfg["check_window_hours"]
    history_start = now - timedelta(days=90)
    if events:
        history_start = max(history_start, events[0])

    # exclude the most recent day so an in-progress failure can't poison its own baseline
    history_end = now - timedelta(days=1)

    counts = defaultdict(int)                      # (date, key) -> count
    for ev in events:
        if ev < history_start or ev >= history_end:
            continue
        counts[(ev.date(), (ev.weekday(), ev.hour // window))] += 1

    # enumerate every historical date so empty windows are represented
    per_key = defaultdict(list)
    day = history_start.date()
    last_day = history_end.date()
    windows_per_day = 24 // window
    while day < last_day:
        for w in range(windows_per_day):
            key = (day.weekday(), w)
            per_key[key].append(counts.get((day, key), 0))
        day += timedelta(days=1)

    return {
        key: {"median": statistics.median(vals), "samples": len(vals)}
        for key, vals in per_key.items()
    }


def expected_for(window_start, baseline, cfg):
    key = (window_start.weekday(), window_start.hour // cfg["check_window_hours"])
    entry = baseline.get(key)
    if not entry or entry["samples"] < 2:
        return None                      # not enough history to judge this slot
    return entry["median"]


def in_business_hours(dt, cfg):
    bh = cfg["business_hours"]
    return dt.weekday() in cfg["business_days"] and bh["start"] <= dt.hour < bh["end"]


# ----------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------

def evaluate(events, cfg, now=None):
    """Return a result dict describing the current health of the event stream."""
    now = now or datetime.now()
    window = cfg["check_window_hours"]

    if not events:
        return {"status": "no_data", "message": "No events found in the source."}

    history_days = (now - events[0]).days
    if history_days < cfg["min_history_days"]:
        return {
            "status": "learning",
            "message": (f"Only {history_days} days of history. "
                        f"Need {cfg['min_history_days']} to establish a reliable baseline."),
            "history_days": history_days,
        }

    baseline = build_baseline(events, cfg, now)

    # Walk backwards through recent windows, newest first. Windows that can't be
    # judged (closed hours, no history, normally quiet) are skipped WITHOUT
    # counting toward the requirement - so we keep going back until we have
    # enough comparable windows, or hit the lookback limit.
    findings = []
    judged_count = 0
    needed = cfg["consecutive_windows_required"]
    max_lookback = needed * 12          # generous: covers nights and weekends

    for i in range(max_lookback):
        if judged_count >= needed:
            break

        w_end = now - timedelta(hours=window * i)
        w_start = w_end - timedelta(hours=window)

        if not in_business_hours(w_start, cfg):
            findings.append({"window_start": w_start, "skipped": "outside business hours"})
            continue

        expected = expected_for(w_start, baseline, cfg)
        if expected is None:
            findings.append({"window_start": w_start, "skipped": "insufficient history"})
            continue
        if expected < cfg["min_expected_to_alert"]:
            findings.append({"window_start": w_start, "skipped": "normally quiet window"})
            continue

        actual = sum(1 for e in events if w_start <= e < w_end)
        ratio = actual / expected if expected else 1.0
        findings.append({
            "window_start": w_start,
            "window_end": w_end,
            "expected": round(expected, 1),
            "actual": actual,
            "ratio": round(ratio, 2),
            "anomalous": ratio < cfg["sensitivity"],
        })
        judged_count += 1

    judged = [f for f in findings if "anomalous" in f]
    if not judged:
        return {"status": "unknown", "message": "No comparable windows to evaluate right now.",
                "findings": findings}

    all_anomalous = all(f["anomalous"] for f in judged)
    confirmed = all_anomalous and len(judged) >= cfg["consecutive_windows_required"]

    last_event = events[-1]
    silent_hours = round((now - last_event).total_seconds() / 3600, 1)

    return {
        "status": "alert" if confirmed else "healthy",
        "confirmed": confirmed,
        "silent_hours": silent_hours,
        "last_event": last_event.isoformat(sep=" "),
        "total_expected": round(sum(f["expected"] for f in judged), 1),
        "total_actual": sum(f["actual"] for f in judged),
        "windows_checked": len(judged),
        "findings": findings,
    }


# ----------------------------------------------------------------------
# Diagnosis
# ----------------------------------------------------------------------

DIAGNOSIS_PROMPT = """You are a technical assistant writing to a non-technical small business owner.

Their "{event_name}" stream has stopped. Facts:
- Last one received: {last_event} ({silent_hours} hours ago)
- Expected in this period: about {total_expected}
- Actually received: {total_actual}

Write a short alert (max 120 words) that:
1. States plainly what has stopped and for how long.
2. Lists the 3 most likely causes, most likely first, in plain English (no jargon).
3. Gives one specific first thing to check.

Be calm and factual, not alarming. Do not invent details you weren't given.
Return plain text only - no markdown, no headings."""


def diagnose_ai(result, cfg):
    from anthropic import Anthropic
    client = Anthropic()
    prompt = DIAGNOSIS_PROMPT.format(
        event_name=cfg["event_name"],
        last_event=result["last_event"],
        silent_hours=result["silent_hours"],
        total_expected=result["total_expected"],
        total_actual=result["total_actual"],
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def diagnose_fallback(result, cfg):
    """Rule-based diagnosis so the tool works with no API key."""
    name = cfg["event_name"]
    causes = {
        "contact form submission": [
            "the form plugin or website was updated recently and broke the form",
            "notification emails are being blocked or sent to an old address",
            "the form provider or hosting had an outage",
        ],
        "order": [
            "the payment provider is rejecting or failing transactions",
            "the checkout page has an error after a recent site change",
            "order notification emails have stopped being delivered",
        ],
        "booking": [
            "the booking calendar is full or misconfigured",
            "the booking widget failed to load after an update",
            "confirmation emails are not being delivered",
        ],
    }
    likely = causes.get(name, [
        "a recent change to the system that produces these events",
        "a delivery or notification failure between systems",
        "an outage at a third-party provider",
    ])
    return (
        f"No {name}s have been received for {result['silent_hours']} hours. "
        f"Around {result['total_expected']} were expected in this period; "
        f"{result['total_actual']} arrived.\n\n"
        f"Most likely causes:\n"
        f"1. {likely[0].capitalize()}.\n"
        f"2. {likely[1].capitalize()}.\n"
        f"3. {likely[2].capitalize()}.\n\n"
        f"First thing to check: submit one yourself and confirm it arrives where it should."
    )


# ----------------------------------------------------------------------
# Alert state (so it doesn't nag)
# ----------------------------------------------------------------------

STATE_FILE = Path("monitor_state.json")


def should_send(result, cfg, now):
    if result["status"] != "alert":
        return True
    if not STATE_FILE.exists():
        return True
    try:
        state = json.loads(STATE_FILE.read_text())
        last = datetime.fromisoformat(state["last_alert"])
    except Exception:
        return True
    return (now - last) >= timedelta(hours=cfg["alert_cooldown_hours"])


def record_alert(now):
    STATE_FILE.write_text(json.dumps({"last_alert": now.isoformat()}))


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Detect silent failures in a business event stream.")
    ap.add_argument("events_csv", help="CSV file with a timestamp column")
    ap.add_argument("--config", help="Optional JSON config file")
    ap.add_argument("--now", help="Override current time (YYYY-MM-DD HH:MM) for testing")
    args = ap.parse_args()

    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text()))

    now = parse_timestamp(args.now) if args.now else datetime.now()
    events = load_events(args.events_csv)
    result = evaluate(events, cfg, now)

    print("=" * 62)
    print(f"  SILENT FAILURE MONITOR - {cfg['business_name']}")
    print(f"  Watching: {cfg['event_name']}s   |   Checked: {now:%Y-%m-%d %H:%M}")
    print("=" * 62)
    print(f"Status: {result['status'].upper()}")

    if result["status"] in ("no_data", "learning", "unknown"):
        print(result["message"])
        return

    print(f"Events loaded: {len(events)}   Last event: {result['last_event']}")
    print(f"Windows checked: {result['windows_checked']}  "
          f"Expected ~{result['total_expected']}  Actual {result['total_actual']}")

    if result["status"] == "healthy":
        print("\nEverything looks normal. No alert sent.")
        return

    if not should_send(result, cfg, now):
        print("\nAnomaly still active, but an alert was already sent recently (cooldown).")
        return

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("\nDiagnosis mode: AI\n")
        message = diagnose_ai(result, cfg)
    else:
        print("\nDiagnosis mode: rule-based fallback (set ANTHROPIC_API_KEY for AI)\n")
        message = diagnose_fallback(result, cfg)

    print("-" * 62)
    print(message)
    print("-" * 62)
    record_alert(now)


if __name__ == "__main__":
    main()
