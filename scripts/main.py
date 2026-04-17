"""
AI Daily Generator - Main Entry Point
Orchestrates the news collection, analysis, and publishing workflow.
"""
import sys
import os
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Setup path for local imports
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config import OPENROUTER_API_KEY, OUTPUT_DIR, ENABLE_IMAGE_GENERATION
from rss_fetcher import NewsLoader
from llm_analyzer import ContentProcessor
from html_generator import PageBuilder
from notifier import AlertManager
from pdf_generator import capture_screenshot

def show_welcome():
    """Print application banner"""
    print("""
    ========================================
    🍅 Tomato AI Daily Pipeline
    ========================================
    """)

def resolve_date(offset: int = 1) -> str:
    """Calculate target date string"""
    target = datetime.now(timezone.utc) - timedelta(days=offset)
    return target.strftime("%Y-%m-%d")

async def run_pipeline():
    """Execute the full automation sequence"""
    show_welcome()
    
    # CLI Args
    cli = argparse.ArgumentParser(description='Tomato AI Daily')
    cli.add_argument('--days', type=int, default=1, help='Lookback days')
    cli.add_argument('--date', type=str, help='Specific date (YYYY-MM-DD)')
    cli.add_argument('--language', type=str, default='zh', choices=['zh', 'en'], help='Language')
    args = cli.parse_args()

    if not OPENROUTER_API_KEY:
        print("❌ Error: OPENROUTER_API_KEY not found.")
        sys.exit(1)

    # Components
    alerts = AlertManager()
    builder = PageBuilder()
    
    target_day = args.date or resolve_date(args.days)
    print(f"📅 Target: {target_day} | Mode: {args.language}")

    try:
        # 1. Fetch
        print("\n[1/5] Fetching RSS...")
        loader = NewsLoader()
        feed = loader.pull_feed()
        
        # 2. Extract
        print("[2/5] Locating content...")
        raw_news = loader.fetch_by_day(target_day, feed)
        
        if not raw_news:
            print("⚠️ No content found. Generating empty page.")
            builder.write_styles()
            builder.build_empty(target_day, "No news available in RSS feed.", args.language)
            if alerts._is_ready():
                alerts.notify_empty(target_day, "RSS feed returned no entries for this date.")
            return

        # 3. Analyze
        print(f"[3/5] AI Analysis ({args.language})...")
        ai = ContentProcessor()
        report = ai.process_news(raw_news, target_day, args.language)
        
        if report.get("status") == "empty":
            print("⚠️ AI returned empty analysis.")
            if alerts._is_ready():
                alerts.notify_empty(target_day, report.get("reason", "AI analysis empty"))
            return

        # 4. Build
        print("[4/5] Generating HTML...")
        builder.write_styles()
        html_file = builder.build_daily(report)
        
        # 5. Export & Notify
        print("[5/5] Finalizing exports...")
        pdf_file = str(Path(OUTPUT_DIR) / f"{target_day}-{args.language}.pdf")
        try:
            await capture_screenshot(html_file, pdf_file)
        except Exception as e:
            print(f"⚠️ PDF export failed: {e}")

        # Count items
        total = sum(len(c.get('items', [])) for c in report.get('categories', []))
        
        if alerts._is_ready():
            alerts.notify_success(target_day, total, args.language)

        print(f"\n✨ Done! Processed {total} items for {target_day}.")
        
    except Exception as e:
        print(f"\n💥 Pipeline Error: {e}")
        if alerts._is_ready():
            alerts.notify_failure(target_day, str(e))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
