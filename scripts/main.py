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
    OUTPUT_DIR,
    languages_for_pipeline,
    get_news_timezone,
    NEWS_DATE_TZ,
)
from rss_fetcher import NewsLoader
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
    args = cli.parse_args()

    # Weekends: no scheduled work unless backfilling (--date) or --force / SKIP_WEEKENDS=false
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

    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY not found.")
        sys.exit(1)

    langs = languages_for_pipeline(args.language)
    target_day = args.date or resolve_date(args.days)
    print(f"📅 Target: {target_day} | Report language(s): {', '.join(langs)}")

    alerts = AlertManager()
    builder = PageBuilder()

    try:
        print("\n[1/5] Fetching RSS...")
        loader = NewsLoader()
        feed = loader.pull_feed()

        print("[2/5] Locating content...")
        raw_news = loader.fetch_by_day(target_day, feed)

        if not raw_news:
            print("⚠️ No content found. Generating empty page(s).")
            builder.write_styles()
            for lang in langs:
                builder.build_empty(
                    target_day,
                    EMPTY_RSS_MSG.get(lang, EMPTY_RSS_MSG["en"]),
                    lang,
                )
            if alerts._is_ready():
                reason = "RSS feed returned no entries for this date."
                for lang in langs:
                    if alerts.recipients_for_locale(lang):
                        alerts.notify_empty(target_day, reason, mail_locale=lang)
            return

        ai = ContentProcessor()
        builder.write_styles()

        for lang in langs:
            print(f"\n========== Language: {lang} ==========")
            print(f"[3/5] AI Analysis ({lang})...")
            report = ai.process_news(raw_news, target_day, lang)

            if report.get("status") == "empty":
                print(f"⚠️ AI returned empty analysis for {lang}.")
                builder.build_empty(
                    target_day,
                    report.get("reason", "AI analysis empty"),
                    lang,
                )
                if alerts._is_ready() and alerts.recipients_for_locale(lang):
                    alerts.notify_empty(
                        target_day,
                        report.get("reason", "AI analysis empty"),
                        mail_locale=lang,
                    )
                continue

            print("[4/5] Generating HTML...")
            html_file = builder.build_daily(report)

            print("[5/5] Finalizing exports...")
            pdf_file = str(Path(OUTPUT_DIR) / f"{target_day}-{lang}.pdf")
            try:
                await capture_screenshot(html_file, pdf_file)
            except Exception as e:
                print(f"⚠️ PDF export failed: {e}")

            total = sum(
                len(c.get("items", [])) for c in report.get("categories", [])
            )
            if alerts._is_ready():
                alerts.notify_success(target_day, total, mail_locale=lang)

            print(f"\n✨ Done ({lang}): processed {total} items for {target_day}.")

    except Exception as e:
        print(f"\n💥 Pipeline Error: {e}")
        if alerts._is_ready():
            for lang in langs:
                if alerts.recipients_for_locale(lang):
                    alerts.notify_failure(target_day, str(e), mail_locale=lang)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
