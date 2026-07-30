# Make.com Build Guide — Silent Failure Monitor

Build time: ~90 minutes. Keep this open on one screen, Make on the other.

Make has no code node on the free tier, so this version uses a **rolling baseline sheet**
instead of computing medians in JavaScript. Same idea, simpler mechanics.

---

## Before you start

1. A Google Sheet where your events land (form responses, orders, bookings) with a
   **timestamp column**. Call this tab `Events`.
2. Add a second tab called `Baseline` with headers:
   `weekday | window | expected_count`
   Fill it once from your own history (see Step 0), or start with rough numbers and tune.
3. A third tab called `State` with headers: `last_alert_at`
4. An **Anthropic API key** (console.anthropic.com) for the diagnosis step.

### Step 0 — Build the baseline once
In your `Events` tab, add a pivot table: rows = weekday, columns = 4-hour block,
values = COUNT, then divide each cell by the number of weeks of history.
Copy those numbers into the `Baseline` tab. That's your "normal".
Re-do this monthly, or automate it later.

---

## The scenario

### Module 1 — Schedule
Set the scenario to run **every 4 hours** (clock icon, bottom-left).

### Module 2 — Google Sheets → Search Rows (`Events`)
- Spreadsheet: your sheet · Sheet: `Events`
- Filter: `timestamp` **greater than** `{{addHours(now; -8)}}`
- This pulls only the last two 4-hour windows.

### Module 3 — Tools → Aggregator (Numeric)
- Source module: Module 2
- Aggregate function: **count**
- Result: how many events actually arrived. Call this `actual`.

### Module 4 — Google Sheets → Search Rows (`Baseline`)
- Sheet: `Baseline`
- Filter: `weekday` equals `{{formatDate(now; "dddd")}}`
  AND `window` equals `{{floor(formatDate(now; "H") / 4)}}`
- Returns the expected count for right now.

### FILTER A — "Is this a window we can judge?"
On the line after Module 4:
- Condition: `expected_count` **greater than** `1.5`
  (skips windows that are normally quiet — no false alarms at 8am)
- AND: `{{formatDate(now; "H")}}` **greater than or equal to** `9`
- AND: `{{formatDate(now; "H")}}` **less than** `18`

### FILTER B — "Has it actually stopped?"
Add a second condition on the same line:
- `{{3.result}}` **less than** `{{4.expected_count * 0.25}}`
  (fires only if actual is under 25% of expected)

### Module 5 — Google Sheets → Search Rows (`State`)
- Sheet: `State` — reads `last_alert_at`

### FILTER C — Cooldown
- Condition: `{{5.last_alert_at}}` **does not exist**
  OR `{{5.last_alert_at}}` **earlier than** `{{addHours(now; -12)}}`
- Stops the monitor nagging every 4 hours about the same outage.

### Module 6 — HTTP → Make a request (AI diagnosis)
- URL: `https://api.anthropic.com/v1/messages`
- Method: `POST` · Body type: `Raw` · Content type: `JSON (application/json)`
- Headers:
  - `x-api-key` : `YOUR_ANTHROPIC_API_KEY`
  - `anthropic-version` : `2023-06-01`
- Request content (replace the two mapped values):
```json
{"model":"claude-sonnet-4-6","max_tokens":400,"messages":[{"role":"user","content":"You are writing to a non-technical small business owner. Their contact form submissions have stopped. Expected about <<EXPECTED>> in the last 8 hours; <<ACTUAL>> arrived. Write a short alert (max 120 words) that states plainly what stopped, lists the 3 most likely causes in plain English most likely first, and gives one specific first thing to check. Calm and factual. Do not invent details. Plain text only, no markdown."}]}
```
- Map `<<EXPECTED>>` to Module 4's `expected_count` and `<<ACTUAL>>` to Module 3's result.
- Parse response: **Yes**
- Right-click the module → **Add error handler → Resume**, with fallback text
  `"Your form submissions have stopped. Please check that your form is working."`
  (An API outage must not block the alert.)

### Module 7 — Email → Send an email
- To: the business owner
- Subject: `Alert: form submissions have stopped`
- Content: map the AI text from Module 6
  (`Data > content[] > text`), then append the raw numbers underneath.

### Module 8 — Google Sheets → Update a Row (`State`)
- Set `last_alert_at` to `{{now}}` — this arms the cooldown.

---

## Test it

1. **Healthy test:** run the scenario now. With normal event volume it should stop at
   Filter B and do nothing. That's success.
2. **Failure test:** temporarily set the sensitivity in Filter B from `0.25` to `5`
   (so it fires even when healthy). Run once. You should get an email. Set it back.
3. Screenshot the scenario canvas and one alert email for your portfolio.

---

## Common snags

- **Filter never passes:** check your `Baseline` tab actually has a row matching today's
  weekday and window number. Window = `hour ÷ 4`, rounded down (9am → 2).
- **AI returns markdown fences:** add "no markdown, no code fences" to the prompt.
- **Mapped fields show as plain text:** always drag from the right-hand panel, never type.
- **Alert fires on a public holiday:** add the date to a `Holidays` tab and a filter that
  excludes it. Worth doing before selling this to a real client.
