"""
RSS Fetcher and Parser Module
Responsible for downloading RSS XML and extracting content for the target date.
"""
import feedparser
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
import re
from config import RSS_URL, RSS_TIMEOUT

class NewsLoader:
    """Handles fetching and parsing of news from RSS feeds"""
    
    def __init__(self, source_url: str = None):
        """
        Initialize the news loader
        Args:
            source_url: URL of the RSS feed. Defaults to RSS_URL from config.
        """
        self.url = source_url or RSS_URL
        self.request_timeout = RSS_TIMEOUT
        self.cache = None

    def pull_feed(self) -> feedparser.FeedParserDict:
        """Retrieve and parse the remote RSS feed"""
        print(f"📥 Pulling RSS data: {self.url}")
        try:
            resp = requests.get(
                self.url,
                timeout=self.request_timeout,
                headers={"User-Agent": "TomatoNews/2.0 (compatible; NewsBot/1.0)"}
            )
            resp.raise_for_status()
            parsed_data = feedparser.parse(resp.content)
            
            if parsed_data.bozo:
                print(f"⚠️ Feed parsing issue: {parsed_data.bozo_exception}")
                
            print(f"✅ Feed loaded: {len(parsed_data.entries)} items found")
            self.cache = parsed_data
            return parsed_data
        except requests.RequestException as err:
            raise RuntimeError(f"Failed to download feed: {err}")
        except Exception as err:
            raise RuntimeError(f"Failed to process feed: {err}")

    def fetch_by_day(self, date_str: str, feed_data: feedparser.FeedParserDict = None) -> Optional[Dict[str, Any]]:
        """
        Locate news entry matching a specific calendar day
        Args:
            date_str: Target date in YYYY-MM-DD format
            feed_data: Existing feed data. If None, it will be pulled.
        Returns:
            Processed entry or None if missing.
        """
        if feed_data is None:
            feed_data = self.pull_feed()
            
        try:
            target_obj = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Date format mismatch: {date_str} (use YYYY-MM-DD)")

        print(f"🔍 Locating content for: {date_str}")
        for item in self._candidate_entries(feed_data.entries):
            if self._entry_day(item) == target_obj.strftime("%Y-%m-%d"):
                formatted = self._format_item(item)
                print(f"✅ Matched: {formatted['title']} ({formatted['link']})")
                return formatted

        print(f"❌ No matching content for {date_str}")
        return None

    def _candidate_entries(self, entries) -> List[Any]:
        """
        Prefer weekday AINews roundups when the feed mixes them with other posts.

        Latent Space's feed also carries essays and podcasts. Those are skipped
        once any entry is tagged `ainews` or titled `[AINews]`. A feed with no
        such entries (the old smol.ai issue feed) is searched as-is.
        """
        ainews = [item for item in entries if self._is_ainews(item)]
        if ainews:
            print(f"📰 AINews entries: {len(ainews)} (other feed items ignored)")
            return ainews
        return list(entries)

    def _is_ainews(self, item) -> bool:
        """True for Latent Space weekday roundups."""
        title = str(item.get("title", "")).strip()
        if title.lower().startswith("[ainews]"):
            return True
        for tag in getattr(item, "tags", None) or []:
            term = tag.get("term", "") if isinstance(tag, dict) else getattr(tag, "term", "")
            if term and "ainews" in str(term).lower():
                return True
        return False

    def _entry_day(self, item) -> Optional[str]:
        """
        Calendar day used to match a report.

        Legacy smol.ai issue URLs (`/issues/YY-MM-DD-`) win over pubDate, because
        those feeds sometimes republish with a stale timestamp. Latent Space
        permalinks have no date, so the UTC publish date is used.
        """
        link = item.get("link", "") or ""
        url_date = self._parse_url_date(link)
        if url_date:
            return url_date
        parsed = getattr(item, "published_parsed", None)
        if parsed:
            pub_time = datetime(*parsed[:6], tzinfo=timezone.utc)
            return pub_time.strftime("%Y-%m-%d")
        return None

    def _parse_url_date(self, url: str) -> Optional[str]:
        """Extract YYYY-MM-DD from URL path segments"""
        patterns = [
            r'/issues/(\d{2})-(\d{2})-(\d{2})-',            
            r'/issues/(\d{4})-(\d{2})-(\d{2})-',              
        ]
        for p in patterns:
            found = re.search(p, url)
            if found:
                y, m, d = found.groups()
                full_y = f"20{y}" if len(y) == 2 else y
                return f"{full_y}-{m}-{d}"
        return None

    def _format_item(self, raw_item) -> Dict[str, Any]:
        """Clean and structure raw RSS entry data"""
        title = str(raw_item.get("title", "") or "")
        title = re.sub(r"(?i)^\[AINews\]\s*", "", title).strip()
        out = {
            "title": title,
            "link": raw_item.get("link", ""),
            "guid": raw_item.get("id", raw_item.get("guid", raw_item.get("link", ""))),
            "description": raw_item.get("description", ""),
            "content": "",
            "pubDate": raw_item.get("published", raw_item.get("updated", ""))
        }
        
        # Priority for full content
        if hasattr(raw_item, 'content') and raw_item.content:
            out["content"] = raw_item.content[0].get('value', '')
        elif hasattr(raw_item, 'summary'):
            out["content"] = raw_item.summary
        else:
            out["content"] = out["description"]
            
        # Unescape HTML entities
        out["content"] = out["content"].replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        return out

    def get_latest_timestamp(self, feed_data: feedparser.FeedParserDict = None) -> Optional[str]:
        """Identify the date of the most recent item in the feed"""
        if feed_data is None:
            feed_data = self.pull_feed()
        if not feed_data.entries:
            return None
            
        dates = [
            day for day in (
                self._entry_day(item) for item in self._candidate_entries(feed_data.entries)
            ) if day
        ]
        return max(dates) if dates else None

    def get_available_range(self, feed_data: feedparser.FeedParserDict = None) -> tuple:
        """Determine the start and end dates present in the feed"""
        if feed_data is None:
            feed_data = self.pull_feed()
        if not feed_data.entries:
            return None, None
            
        found_dates = [
            day for day in (
                self._entry_day(item) for item in self._candidate_entries(feed_data.entries)
            ) if day
        ]
        if not found_dates:
            return None, None
        return min(found_dates), max(found_dates)

def fetch_rss_content(target_date: str) -> Optional[Dict[str, Any]]:
    """Legacy helper for backward compatibility"""
    loader = NewsLoader()
    data = loader.pull_feed()
    return loader.fetch_by_day(target_date, data)
