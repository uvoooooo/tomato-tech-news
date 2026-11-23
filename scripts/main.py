"""
AI Daily Generator - Main Entry Point
Orchestrates the news collection, analysis, and publishing workflow.
"""
import os
import sys
import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Setup path for local imports
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config import (
    OPENROUTER_API_KEY,
    languages_for_pipeline,
    get_news_timezone,
    NEWS_DATE_TZ,
    I18N,
    FOCUS_LOOKBACK_DAYS,
    WEEKLY_WINDOW_DAYS,
)
from rss_fetcher import NewsLoader
from arxiv_fetcher import PaperLoader
from llm_analyzer import ContentProcessor
from html_generator import PageBuilder
from notifier import AlertManager
from pdf_generator import capture_screenshot

EMPTY_RSS_MSG = {
    "zh": "RSS 中未找到该日期的条目。",
    "en": "No news available in RSS feed for this date.",
}


def show_welcome():
    """Print application banner"""
    print("""
    ========================================
    🍅 Tomato AI Daily Pipeline
    ========================================
    """)


def resolve_date(offset: int = 1) -> str:
    """
    Target calendar date for the report.

    Uses **NEWS_DATE_TZ** from config (see **DEFAULT_NEWS_DATE_TZ** / env **NEWS_DATE_TZ**).

    offset == 1: **previous business day** (Mon–Fri). Monday → Friday; Tue–Fri → yesterday.

    offset >= 2: **calendar** days ago in the same timezone.
    """
    tz = get_news_timezone()
    today = datetime.now(tz).date()
    if offset == 1:
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        out = d.strftime("%Y-%m-%d")
        print(
            f"📅 Date anchor: TZ={NEWS_DATE_TZ} local_today={today} → target={out} (previous weekday)"
        )
        return out
    anchor = datetime.now(tz)
    target_dt = anchor - timedelta(days=offset)
    out = target_dt.strftime("%Y-%m-%d")
    print(f"📅 Date anchor: TZ={NEWS_DATE_TZ} local_today={today} → target={out} (calendar -{offset}d)")
    return out


def _is_weekend_in_news_tz() -> bool:
    """Sat/Sun in NEWS_DATE_TZ (weekend skip)."""
    tz = get_news_timezone()
    return datetime.now(tz).weekday() >= 5


def _skip_weekends_enabled() -> bool:
    return os.getenv("SKIP_WEEKENDS", "true").lower() in ("1", "true", "yes")


def completed_week_end(today):
    """Friday that closes the latest finished work week."""
    weekday = today.weekday()
    if weekday >= 5:
        return today - timedelta(days=weekday - 4)
    if weekday == 4:
        return today
    return today - timedelta(days=weekday + 3)


def week_window(end_day):
    """Inclusive window of WEEKLY_WINDOW_DAYS ending on end_day."""
    span = max(WEEKLY_WINDOW_DAYS, 1)
    return end_day - timedelta(days=span - 1), end_day


async def _emit(builder, alerts, report, lang: str, kind: str = "daily"):
    """Write one language of a report and notify when mail is configured."""
    day = report.get("date", "")
    if report.get("status") == "empty":
        print(f"⚠️ Empty analysis for {lang}.")
        builder.build_empty(
            day,
            report.get("reason", "AI analysis empty"),
            lang,
            kind=kind,
        )
        print(f"📭 Empty for {lang} — skipping email notification.")
        return

    print("[4/5] Generating HTML...")
    html_file = builder.build_daily(report)

    print("[5/5] Finalizing exports...")
    pdf_file = str(Path(html_file).with_suffix(".pdf"))
    try:
        await capture_screenshot(html_file, pdf_file)
    except Exception as err:
        print(f"⚠️ PDF export failed: {err}")

    total = sum(len(c.get("items", [])) for c in report.get("categories", []))
    if alerts._is_ready():
        alerts.notify_success(
            day,
            total,
            mail_locale=lang,
            kind=kind,
            window_start=report.get("window_start") or "",
            window_end=report.get("window_end") or "",
        )
    print(f"\n✨ Done ({lang}): processed {total} items for {day}.")


async def run_weekly(args):
    """One report covering the week that ends on the latest finished Friday."""
    langs = languages_for_pipeline(args.language)
    if args.date:
        end = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        end = completed_week_end(datetime.now(get_news_timezone()).date())
    start, end = week_window(end)
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    print(f"📅 Week: {start_s} → {end_s} | Report language(s): {', '.join(langs)}")

    alerts = AlertManager()
    builder = PageBuilder()

    try:
        await _run_weekly_body(langs, start_s, end_s, alerts, builder)
    except Exception as err:
        print(f"\n Pipeline Error: {err}")
        sys.exit(1)


async def _run_weekly_body(langs, start_s, end_s, alerts, builder):
    print("\n[1/4] Reading this week's dailies...")
    builder.write_styles()
    collected = {
        lang: builder.collect_week_items(start_s, end_s, lang)
        for lang in langs
    }
    for lang, items in collected.items():
        print(f"   {lang}: {len(items)} unique items")

    if not any(collected.values()):
        print("⚠️ No daily items in this week. Generating empty page(s).")
        for lang in langs:
            builder.build_empty(
                end_s,
                I18N.get(lang, I18N["zh"]).get("weekly_empty", EMPTY_RSS_MSG["en"]),
                lang,
                kind="weekly",
            )
        return

    ai = ContentProcessor()
    for lang in langs:
        items = collected[lang]
        print(f"\n========== Language: {lang} ==========")
        if not items:
            builder.build_empty(
                end_s,
                I18N.get(lang, I18N["zh"]).get("weekly_empty", EMPTY_RSS_MSG["en"]),
                lang,
                kind="weekly",
            )
            print(f"📭 No {lang} dailies in this week — skipping email notification.")
            continue
        print(f"[2/4] Ranking {len(items)} items ({lang})...")
        report = ai.rank_week(items, end_s, lang)
        report["kind"] = "weekly"
        report["window_start"] = start_s
        report["window_end"] = end_s
        await _emit(builder, alerts, report, lang, kind="weekly")


async def run_pipeline():
    """Execute the full automation sequence"""
    show_welcome()

    cli = argparse.ArgumentParser(description="Tomato AI Daily")
    cli.add_argument(
        "--days",
        type=int,
        default=1,
        help="1 = previous weekday in NEWS_DATE_TZ; 2+ = calendar days back in that TZ",
    )
    cli.add_argument("--date", type=str, help="Specific date (YYYY-MM-DD)")
    cli.add_argument(
        "--language",
        type=str,
        default="zh",
        choices=["zh", "en"],
        help="Report language when using legacy NOTIFICATION_TO (single list)",
    )
    cli.add_argument(
        "--force",
        action="store_true",
        help="Run even on Sat/Sun (NEWS_DATE_TZ) when SKIP_WEEKENDS is on",
    )
    cli.add_argument(
        "--weekly",
        action="store_true",
        help="Weekly brief for the 7 days ending the latest finished Friday. --date sets that end day.",
    )
    args = cli.parse_args()

    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY not found.")
        sys.exit(1)

    if args.weekly:
        await run_weekly(args)
        return

    # Weekends: no scheduled daily unless backfilling (--date) or --force / SKIP_WEEKENDS=false
    if (
        _skip_weekends_enabled()
        and not args.force
        and not args.date
        and _is_weekend_in_news_tz()
    ):
        print(
            f"⏭️ Skip: today is weekend ({NEWS_DATE_TZ}). "
            "Use --date YYYY-MM-DD to backfill, --force, or set SKIP_WEEKENDS=false."
        )
        return

    langs = languages_for_pipeline(args.language)
    target_day = args.date or resolve_date(args.days)
    print(f"📅 Target: {target_day} | Report language(s): {', '.join(langs)}")

    alerts = AlertManager()
    builder = PageBuilder()

    try:
        print("\n[1/5] Fetching sources...")
        loader = NewsLoader()
        feed = loader.pull_feed()
        raw_news = loader.fetch_by_day(target_day, feed)

        print("[2/5] Fetching arXiv...")
        papers = []
        try:
            papers = PaperLoader().fetch_for_date(target_day)
        except Exception as err:
            print(f"⚠️ arXiv fetch failed: {err}")

        if not raw_news and not papers:
            print("⚠️ No roundup and no papers. Generating empty page(s).")
            builder.write_styles()
            for lang in langs:
                builder.build_empty(
                    target_day,
                    I18N.get(lang, I18N["zh"]).get("empty_focus", EMPTY_RSS_MSG["en"]),
                    lang,
                )
            print("📭 Nothing on focus for this date — skipping email notification.")
            return

        window_end = datetime.strptime(target_day, "%Y-%m-%d").date()
        window_start = window_end - timedelta(days=max(FOCUS_LOOKBACK_DAYS, 1) - 1)
        bundle = {
            "title": (raw_news or {}).get("title") or "Focus digest",
            "link": (raw_news or {}).get("link") or "",
            "content": (raw_news or {}).get("content") or "",
            "papers": papers,
            "window_start": window_start.strftime("%Y-%m-%d"),
            "window_end": target_day,
        }

        ai = ContentProcessor()
        builder.write_styles()

        for lang in langs:
            print(f"\n========== Language: {lang} ==========")
            print(f"[3/5] AI Analysis ({lang})...")
            report = ai.process_news(bundle, target_day, lang)
            report["kind"] = "daily"
            report["window_start"] = bundle["window_start"]
            report["window_end"] = bundle["window_end"]
            await _emit(builder, alerts, report, lang, kind="daily")

    except Exception as e:
        print(f"\n Pipeline Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
