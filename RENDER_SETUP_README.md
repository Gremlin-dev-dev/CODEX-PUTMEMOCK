# CodexHub — Render Setup & Environment Variables

Reference doc for everything configured on Render. Keep this updated whenever you add a new variable.

---

## Services on Render

| Service | Type | Purpose |
|---|---|---|
| `codexhub-putme` (or similar) | Web Service (Python/Flask) | The backend API |
| `codexhub-putme-1` (or similar) | Static Site | The frontend (HTML/CSS/JS) |
| Postgres database | PostgreSQL | Stores users, questions, results |

---

## Environment Variables (set on the **backend** Web Service → Environment tab)

| Variable | Example value | What it does |
|---|---|---|
| `ALLOWED_EMAILS` | `aspirant1@gmail.com,aspirant2@gmail.com` | Comma-separated whitelist. Only these emails can sign up. **Append new aspirant batches here — never remove old ones once they've signed up, or they'll be locked out of login.** |
| `ADMIN_EMAILS` | `youremail@gmail.com` | Emails allowed to view `/admin.html` — the question-review panel showing every question across all days/subjects with correct answers, for checking MathJax rendering etc. |
| `JWT_SECRET_KEY` | (long random string) | Signs login tokens. Never change this once live — it would log everyone out instantly. |
| `FRONTEND_ORIGIN` | `https://codexhub-putme-1.onrender.com` | Tells the backend which frontend URL is allowed to call it (CORS). Must match your actual frontend URL exactly. |
| `DATABASE_URL` | (auto-filled by Render) | Connection string to Postgres. **Set automatically when you attach a database — don't type this by hand except when recreating a database (see below).** |
| `EXAM_DATES` | `2026-08-25,2026-08-26,2026-08-27` | Three comma-separated dates (Day 1, Day 2, Day 3). Controls when the exam window opens. **Leave this unset entirely while testing** — without it, days just unlock the next calendar day after finishing the previous one (test mode). |

### The "same date" trick
If you want aspirants to go through all 3 days **back-to-back in one sitting** instead of waiting a day between each, set all three `EXAM_DATES` values to the **same date**, e.g.:
```
2026-08-27,2026-08-27,2026-08-27
```
Day 2 and Day 3 will unlock immediately after finishing the previous day, since the "has today reached this day's date" check is already true for all three.

---

## Hardcoded settings (in `backend/app.py`, not env vars — edit the code to change these)

| Setting | Current value | Where in code |
|---|---|---|
| Exam duration per day | 30 minutes | `EXAM_DURATION_MINUTES` |
| Max attempts per day | 2 | `MAX_ATTEMPTS_PER_DAY` |
| Questions per subject per exam | 10 (randomly drawn if pool is bigger) | `QUESTIONS_PER_SUBJECT` |
| Result release delay | 4 hours after first attempt on that day | `RESULT_DELAY_HOURS` |
| Department subject lists | Science/Commercial/Art elective lists | `DEPARTMENT_ELECTIVES` dict |

---

## ⚠️ IMPORTANT: Free Postgres databases expire after 30 days

Render's **free-tier Postgres databases are automatically deleted 30 days after creation** — no warning beyond an eventual connection failure. This has already happened once (caught via a Render email: *"server failure... Exited with status 1"*, logs showed `could not translate host name ... Name or service not known`).

**When this happens, everything in the database is gone — permanently.** All signups, results, department/subject choices. No recovery.

### What to do when it happens again:
1. Render → **New +** → **PostgreSQL** → create a fresh one
2. Copy its **Internal Database URL**
3. Backend service → **Environment** → update `DATABASE_URL` → Save
4. Questions auto-reload from `questions_data/*.json` on the next deploy (no action needed)
5. **Every aspirant must sign up again from scratch** — there's no way around this on free tier

### Longer-term options:
- **Stay free**: recreate the database every ~30 days, accept the data wipe
- **Upgrade to Render's paid Postgres plan** (a few dollars/month): database never expires, data stays permanent — worth it once this is a real paid product people return to

---

## Repo structure reminder

```
CODEX-PUTMEMOCK/ (or whatever the repo is named)
├── frontend/
│   ├── index.html, login.html, department.html, subjects.html,
│   │   dashboard.html, exam.html, results.html, profile.html, admin.html
│   ├── blogo.png, slogo.jpg  (logos)
│   ├── manifest.json, sw.js, icons/  (PWA)
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   ├── questions_data/day1.json, day2.json, day3.json
└── RENDER_SETUP_README.md  (this file)
```

---

## Adding more questions later

1. Edit `backend/questions_data/day{1,2,3}.json` on GitHub (or upload a replacement file)
2. Each question needs a **unique** `external_id` — reusing one updates that question instead of duplicating it
3. Math/science notation: wrap in `\(...\)` (not `$...$` — MathJax here is only configured for the backslash-parenthesis style)
4. Push → Render auto-redeploys → questions reload automatically (no manual seed step needed)
5. Check `/admin.html` afterward to visually confirm rendering looks right — it auto-flags any leftover `$` signs

---

## Adding a new aspirant batch / cohort

1. Append new emails to `ALLOWED_EMAILS` (comma-separated, no spaces)
2. Decide the new cohort's 3 dates, update `EXAM_DATES`
3. **Watch out**: if some aspirants from a previous batch haven't finished all 3 days yet, changing `EXAM_DATES` to new dates can re-lock their remaining days until the new dates arrive. Best to confirm stragglers are done first, or keep dates set to cover both groups.

---

*Last updated: reflects the setup as of early October 2026.*
