# Automated Micro-Influencer Outreach System

EDXSO AI Engineer Intern: Assignment 1

A Python pipeline that discovers fitness micro-influencers on YouTube, enriches their profiles with real public data, filters them with explainable PASS/FAIL reasons, writes a personalized email and Instagram DM for each one with Gemini, and sends or simulates outreach with duplicate protection and an outreach log.

```
YouTube Data API → Discovery → Enrichment → Filtering → AI Personalization → Sending → Tracker (CSV)
```

## Results of the test run

| Stage | Count |
|---|---|
| Channels discovered | 309 |
| Enriched | 309 |
| Public emails found (all channels) | 79 |
| Passed filtering | 36 |
| Passed and have a public email | 9 |
| Messages generated (email + DM) | 36 |
| Emails sent to a test inbox | 8 |
| Instagram DMs queued for manual sending | 4 |

All files are in `output/`.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Data source | YouTube Data API v3 (REST, via `requests`) |
| LLM | Google Gemini (`gemini-3.5-flash-lite`) via the `google-genai` SDK |
| Storage | SQLite (`outreach.db`) |
| Email | Gmail SMTP (`smtplib`, App Password) |
| Output | CSV files |

**APIs used:** YouTube `search.list`, `channels.list`, `playlistItems.list`, `videos.list`; Gemini `generate_content`; Gmail SMTP.

**Data source:** only public YouTube data. Instagram and website links are taken from links that creators publish in their own descriptions. No login-walled scraping and no captcha bypass.

## How each stage works

### 1. Discovery (`discovery.py`)
- Runs the fitness search queries in `config.py` (e.g. "calisthenics progress update", "home workout hindi") until `TARGET_CANDIDATES` channels are collected.
- Searches **videos** published in the last 120 days rather than channels. Video search surfaces smaller, active creators; channel search mostly returns big brands.
- `INSERT OR IGNORE` on `channel_id` (primary key) removes duplicate channels automatically.
- Long-tail queries were added in a second round because generic queries returned mostly channels over 100K subscribers.

### 2. Enrichment (`enrichment.py`)
| Field | How it is obtained |
|---|---|
| Followers | `statistics.subscriberCount`. Stored as NULL if the creator hides it |
| Engagement rate | Last 10 uploads: `(likes + comments) / views × 100`. Videos with hidden likes are skipped |
| Last upload | Days since the most recent video |
| Email | Regex over channel and video descriptions. Handles `name [at] gmail [dot] com`. Otherwise **"Not Found"**, never guessed |
| Instagram / Website | Links in the creator's own descriptions |
| Content themes | Most frequent words and 2-word phrases in recent titles (hashtags used only as a fallback) |
| Fitness relevance | Share of recent titles that contain a fitness keyword |
| Audience age / gender | **Not Available**: the public API does not expose them |

`channels.list` is batched 50 IDs per call. Each channel is wrapped in try/except, so one failure is recorded in the `error` column and the run continues.

### 3. Filtering (`filtering.py`)
Complete filter category: **Fitness**. All thresholds are in `config.py`.

| Rule | Threshold | Example FAIL reason |
|---|---|---|
| Followers | 5,000 – 100,000 | `Followers 312,000 > 100,000 (not micro)` |
| Engagement | ≥ 2% | `Engagement 1.1% < 2.0%` |
| Activity | Last upload ≤ 60 days ago | `Inactive: last upload 143 days ago` |
| Content relevance | ≥ 30% fitness titles | `Low fitness relevance (0.1)` |
| Geography | Optional allow-list | `Country US not targeted` |
| Brand safety | Blocklist (betting, casino, steroid…) | `Brand-safety flag: betting` |

Every influencer gets a status and a plain-English reason. A missing email does **not** fail a creator; it is marked "DM/manual outreach only".

Fail reasons in the test run (one creator can fail several rules): followers out of range 212, engagement 149, relevance 71, inactive 6, enrichment error 3.

### 4. AI personalization (`personalize.py`)
- **Collaboration angle is rule-based**, from size and engagement:
  - under 15K followers → barter or UGC
  - 15K–50K → affiliate or paid placement
  - 50K–100K → ambassador or sponsored integration
- Gemini receives **only verified facts**: channel name, 3 most recent video titles, content themes, country, brand and angle.
- The prompt forbids invented numbers, invented first names and adding deal types beyond the chosen angle.
- **Validation in code** checks three things:
  - email is 60–90 words
  - DM is 15–30 words
  - the message mentions at least one word from the creator's real titles or themes (anti-generic check)

  A failing draft is sent back to Gemini with the exact errors, up to 3 attempts.
- Emojis and hashtags are stripped from names and titles before prompting.
- Only creators without a message are processed, so a failed creator is retried on the next run.
- 503 and rate-limit errors are retried with back-off.

### 5. Sending (`sender.py`)
- Only valid emails are selected. `Not Found` is skipped.
- **Dry run by default** (logged as `simulated`). `--send` sends through Gmail SMTP.
- `TEST_RECIPIENT` (set in `.env`) redirects every email to a test inbox, so **no real creator was emailed**.
- **Duplicate prevention:**
  - `UNIQUE(channel_id, channel)` on `outreach_log`
  - a check that the same email address was not already contacted

  A second run reports `duplicate` instead of sending again.
- Other safeguards: a daily send limit (counted from the log), a delay between sends, an opt-out line, per-email failure logging, and a clean stop if SMTP login fails.
- **Instagram DMs are not automated**, because Meta does not allow cold DMs via API. They are queued as `pending_manual` and marked `sent_manual` with `python sender.py --dm-sent <channel_id>` after sending by hand.

### 6. Export (`export.py`)
| File | Contents |
|---|---|
| `influencer_dataset.csv` | All discovered creators with metrics, email, themes, PASS/FAIL and reason |
| `shortlisted_influencers.csv` | PASS only |
| `personalized_messages.csv` | Subject, email pitch, DM, word counts, collab angle |
| `outreach_tracker.csv` | Influencer, email, message generated, sent, date, status |

## Setup

```bash
git clone <repo-url>
cd influencer-outreach
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in:
```
YOUTUBE_API_KEY=...
GEMINI_API_KEY=...
SMTP_USER=you@gmail.com          # only for --send
SMTP_PASSWORD=gmail_app_password # only for --send
TEST_RECIPIENT=you@gmail.com     # every email goes here instead of the creator
```

- **YouTube key:** Google Cloud Console → enable *YouTube Data API v3* → Credentials → API key.
- **Gemini key:** https://aistudio.google.com/apikey
- **Gmail App Password:** turn on 2-Step Verification, then go to https://myaccount.google.com/apppasswords

## Running

```bash
python main.py                    # full pipeline, dry-run sending
python main.py --skip-discovery   # rerun without spending search quota
python main.py --send             # real send (set TEST_RECIPIENT in .env first)
python peek.py                    # print 3 generated messages for a quick quality check
```

Each stage can also be run alone (`python discovery.py`, `python filtering.py`, …). Every stage is resumable: it skips work that is already done.

## Project structure
```
config.py        settings: queries, thresholds, brand, model
db.py            SQLite schema (influencers, messages, outreach_log)
discovery.py     YouTube search -> candidate channels
enrichment.py    metrics, email, links, themes
filtering.py     PASS/FAIL with reasons
personalize.py   Gemini email + DM with validation
sender.py        dry run / SMTP send, dedupe, Instagram DM queue
export.py        CSV deliverables
main.py          runs every stage in order
peek.py          prints sample messages
output/          generated CSVs
```

## Scalability (50 → 500+)
- **Quota:** a search costs 100 units; enriching a channel costs about 2–3 units. The free quota is 10,000 units/day, so 500+ channels fit in one or two days, and runs are resumable.
- Batched API calls (50 channels per call). SQLite can be swapped for Postgres without changing the logic.
- A new niche only needs new queries and keywords in `config.py`.
- Gemini calls are independent per creator, so they can be parallelised on a paid tier.

## Limitations
- **Email coverage is limited.** Many creators hide their email behind YouTube's captcha-protected button, which is not bypassed.
- **Audience age, gender and location** are not available from the public API. `Country` is the channel's self-declared country.
- **Engagement is view-based** (standard for YouTube), so it is not directly comparable to Instagram's follower-based engagement.
- **Themes and relevance are keyword-based:** fast and explainable, but they can miss unusual titles.
- **Instagram DMs are manual** by design (platform policy).
- **FitFuel is a fictional demo brand** used for the pitches.

## Data integrity
No influencer data is fabricated. Every metric comes from the YouTube API at run time. Missing values are written as `Not Found`, `Not Available` or `Hidden by creator`.
