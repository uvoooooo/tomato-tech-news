**Language / 语言**: **English** | [简体中文](README.zh.md)

# TomatoNews (Tomato AI Daily)

Fetches the day’s items from **RSS**, classifies and summarizes them with a **large language model (OpenRouter)**, and produces **static HTML / PDF**; optional deployment to **GitHub Pages** via **GitHub Actions**; optional **SMTP** email notifications.

---

## Overview

| Capability | Description |
|------------|-------------|
| Data source | Default `news.smol.ai` RSS; override with `RSS_URL` |
| Processing | OpenRouter-compatible API for categorization, takeaways, and keywords |
| Outputs | Daily HTML under `docs/`, archive `index.html`, styles in `css/styles.css`; **PDF** (Playwright) locally or in CI |
| Automation | `.github/workflows/daily.yml`: scheduled pipeline and Pages deploy |
| Notifications | HTML + plain-text email on success / empty / failure (requires SMTP) |

---

## What the report looks like

A fixed sample lives in `docs/` (same layout as CI). **No extra screenshots needed**: open these in the repo to preview the full page.

| Type | File | Notes |
|------|------|--------|
| **PDF** (best as a “full-page” view) | [`docs/2026-04-16-zh.pdf`](./docs/2026-04-16-zh.pdf) | Same as Playwright PDF in CI; paginated preview on the file view |
| **HTML** | [`docs/2026-04-16-zh.html`](./docs/2026-04-16-zh.html) | Chinese daily: dark minimal layout, **Today's Highlights**, cards by “Model / Product / Research”, links and keyword footer |
| **Archive index** | [`docs/index.html`](./docs/index.html) | Dated list linking to each HTML issue |

> To refresh the sample after cloning, run `scripts/main.py` once and commit the updated files under `docs/` (`.gitignore` whitelists the sample above and `docs/css/`; other dates stay ignored).

---

## Usage

### 1. Clone and Python environment

```bash
git clone https://github.com/<your-username>/TomatoNews.git
cd TomatoNews
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For **PDF** export, install the browser once:

```bash
playwright install chromium
```

### 2. Environment variables

Copy the example and fill in values:

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | **Yes** | Model API |
| `OPENROUTER_BASE_URL` | No | Default `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | No | Default `openai/gpt-4o` |
| `RSS_URL` | No | RSS feed URL |
| `OUTPUT_DIR` | No | Output directory, default `docs` |
| `SKIP_WEEKENDS` | No | Default `true`: skip the main run on **Saturday and Sunday** in **`NEWS_DATE_TZ`** (override with `--date` / `--force` or set to `false`) |
| `NEWS_DATE_TZ` | No | If unset, uses **`DEFAULT_NEWS_DATE_TZ`** in **`scripts/config.py`** (template default is UK **`Europe/London`**). After fork, change the default or set this (e.g. **`Asia/Shanghai`**, **`Etc/UTC`**) without editing app code. CI can set the same name under **Repository variables** |
| `GITHUB_PAGES_URL` | No | Site root URL for “open report” links in email; Actions injects it—usually leave empty |
| `SMTP_*` | No | Mail account; omit to skip email |
| `NOTIFICATION_TO` | No | **Classic**: single recipient list (comma-separated); body language follows `--language` |
| `NOTIFICATION_TO_ZH` / `NOTIFICATION_TO_EN` | No | **Split**: Chinese vs English recipients (comma-separated). **At least one side** enables split mode: **zh + en** reports (two model calls); Chinese list gets Chinese email + `…-zh.html`, English list gets English email + `…-en.html`; **`NOTIFICATION_TO` is not used for routing** in that mode. If both are empty, falls back to a single report from `--language` and `NOTIFICATION_TO` |
| `ENABLE_IMAGE_GENERATION` | No | If `true`, configure `FIREFLY_API_KEY` etc. (see `scripts/config.py`) |

### 3. Generate one issue locally

```bash
export PYTHONPATH="$(pwd)/scripts${PYTHONPATH:+:$PYTHONPATH}"
python scripts/main.py --days 1          # default: “previous business day” (tz: config.DEFAULT_NEWS_DATE_TZ or NEWS_DATE_TZ)
# python scripts/main.py --days 2        # count back calendar days in UTC (not a business calendar)
# python scripts/main.py --date 2026-04-16 --language zh
# python scripts/main.py --language en
```

Check `docs/` for new `YYYY-MM-DD-<lang>.html` and optional PDF.

### 4. GitHub Actions daily run

1. Push this repo to GitHub.  
2. Under **Settings → Secrets and variables → Actions**, set at least **`OPENROUTER_API_KEY`**; other secrets should match `env` in `daily.yml`.  
3. **Settings → Pages**  
   - **Build and deployment → Source**: choose **GitHub Actions** (this repo uses `upload-pages-artifact` + `deploy-pages`, not the old `gh-pages` branch flow).  
4. In **Actions**, run **Tomato Tech News Daily Automation** once and confirm `build` and `deploy` succeed.  
5. The site is usually at `https://<owner>.github.io/<repo>/` (from `GITHUB_REPOSITORY`). The workflow injects `GITHUB_PAGES_URL` for emails to match.  
6. After a successful run, the workflow **commits** updated `docs/` (daily HTML, `index.html`, `.index.json`, CSS) to **`main` / `tomatonewsdaily`**, so **older “open report” links in email keep working** on GitHub Pages (each deploy still ships the full `docs/` tree from the branch). If **branch rules** block direct pushes, add an allow rule for **`github-actions[bot]`** (or relax rules for that path) so this step can succeed.

Schedule: **weekdays only (Mon–Fri UTC) at 08:00** (16:00 Beijing); no weekend cron. Default **`--days 1`** uses the **previous business day (UTC)**: e.g. **Monday** builds **Friday**’s RSS date, **Tuesday** builds **Monday**, and so on. Manual **Run workflow** or **push** runs on weekends are also skipped by default (see `SKIP_WEEKENDS`); to backfill, set **`SKIP_WEEKENDS=false`**, use **`--force`**, or **`--date YYYY-MM-DD`** (not treated as the “daily” run).

---

## Repository layout (brief)

```
scripts/           # Pipeline: RSS, LLM, HTML, PDF, email
docs/              # Site; daily HTML + archive tracked in git (CI commit) for stable URLs
.github/workflows/ # daily.yml: scheduled build and Pages
requirements.txt
.env.example
```
