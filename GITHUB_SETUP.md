# Publishing this to GitHub

*Delete this file after you've published — it's instructions for you, not part of the project.*

## 1. Create the repository

1. Go to https://github.com/new
2. **Repository name:** `silent-failure-monitor`
3. **Description:** `Detects when business events stop arriving — silent failure monitoring with AI diagnosis`
4. **Public** (it has to be public to share as a portfolio link)
5. Do **not** tick "Add a README" — this project already has one.
6. Create repository.

## 2. Push the code

Unzip this folder, open a terminal inside it, then:

```bash
git init
git add .
git commit -m "Silent Failure Monitor: detect when business events stop arriving"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/silent-failure-monitor.git
git push -u origin main
```

If GitHub asks for a password, it wants a **Personal Access Token**, not your account
password: Settings → Developer settings → Personal access tokens → Tokens (classic) →
Generate new token → tick `repo` → copy it and paste it as the password.

## 3. Finish the repo page

- Edit `README.md` and replace `YOUR_USERNAME` in the clone URL with your GitHub username.
- On the repo page, click the gear beside "About" and add topics:
  `monitoring` `automation` `n8n` `make` `ai` `small-business` `anomaly-detection` `python`
- Paste the same one-line description in the About box.

## 4. Before you share the link — check these

- [ ] No API keys anywhere. Search the repo for `sk-`, `api_key`, `x-api-key`.
      The n8n JSON and Make guide should say `YOUR_ANTHROPIC_API_KEY`, never a real key.
- [ ] `monitor_state.json` is not committed (`.gitignore` handles it).
- [ ] The demo commands in the README actually run on a fresh clone.
- [ ] This `GITHUB_SETUP.md` file is deleted.

## 5. Where to use the link

- The Process Street application ("share a link to a public AI project")
- Your LinkedIn **Featured** section
- Your CV, under Selected Projects
- Any automation or technical-support application from here on

---

## Before an interview — make it yours

You need to be able to explain every part of this. Work through it in this order:

1. **Run both demos** and watch the difference in output.
2. **Read `docs/HOW_IT_WORKS.md`** — that's the reasoning, and it's what you'll be asked about.
3. **Break it on purpose:** open `engine/monitor.py`, change `sensitivity` from `0.25` to `0.9`,
   re-run the healthy data, and watch it produce a false alarm. That single experiment teaches
   you more about threshold tuning than reading ever will.
4. **Change something real:** adjust the business hours, add a new event type to the fallback
   diagnosis, or add a `--json` output flag. Commit it. Now the repo has your fingerprints on it.
5. **Build the n8n or Make version** so you can demo it live. The Make build guide is the
   easier of the two to finish in an evening.

### Questions you should be able to answer

- *Why median instead of average?* One freak busy day would drag an average up and permanently
  desensitise the monitor.
- *Why two consecutive windows?* One quiet afternoon isn't an outage. False alarms get a
  monitoring tool muted, and a muted monitor is worthless.
- *Why exclude the last 24 hours from the baseline?* Otherwise an in-progress outage teaches the
  system that zero is normal.
- *Why not just synthetic-test the form?* It needs site access, creates fake leads in the CRM,
  and only tests what you configured. Watching where results land needs none of that.
- *What breaks it?* Public holidays, very low-volume businesses, and partial failures that dip
  but don't stop. All three are in the limitations section — say so openly.
