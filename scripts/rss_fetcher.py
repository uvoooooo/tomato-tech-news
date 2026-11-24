"""
RSS Fetcher and Parser Module
Responsible for downloading RSS XML and extracting content for the target date.
"""
import os
import feedparser
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse
import re
from config import COMPANY_FEEDS, COMPANY_POSTS_PER_FEED, RSS_URL, RSS_TIMEOUT

TWITTER_RECAP_LIMIT = 6500
COMPANY_SUMMARY_LIMIT = 500

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

    def fetch_company_posts(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Official lab posts published from start through end, inclusive."""
        posts: List[Dict[str, Any]] = []
        for feed in company_feeds():
            name = feed["name"]
            url = feed["url"]
            print(f"📥 Pulling {name}: {url}")
            try:
                resp = requests.get(
                    url,
                    timeout=self.request_timeout,
                    headers={"User-Agent": "TomatoNews/2.0 (compatible; NewsBot/1.0)"},
                )
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
            except Exception as err:
                print(f"⚠️ {name} feed failed: {err}")
                continue
            matched = []
            for item in parsed.entries:
                day = self._published_day(item)
                if not day or day < start or day > end:
                    continue
                matched.append(self._company_post(item, name, day))
            matched.sort(key=lambda post: post["date"], reverse=True)
            kept = matched[: max(COMPANY_POSTS_PER_FEED, 1)]
            print(f"   {name}: {len(kept)} post(s) in {start} → {end}")
            posts.extend(kept)
        posts.sort(key=lambda post: (post["date"], post["source"]), reverse=True)
        print(f"✅ Lab posts kept: {len(posts)}")
        return posts

    def _published_day(self, item) -> Optional[str]:
        parsed = getattr(item, "published_parsed", None) or getattr(item, "updated_parsed", None)
        if not parsed:
            return None
        return datetime(*parsed[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")

    def _company_post(self, item, source: str, day: str) -> Dict[str, Any]:
        summary = html_to_text(item.get("summary") or item.get("description") or "")
        return {
            "source": source,
            "title": html_to_text(str(item.get("title") or "")).strip(),
            "url": str(item.get("link") or "").strip(),
            "date": day,
            "summary": summary[:COMPANY_SUMMARY_LIMIT],
        }


def company_feeds() -> List[Dict[str, str]]:
    """Default lab feeds, or COMPANY_RSS_URLS when that env var is set."""
    raw = os.getenv("COMPANY_RSS_URLS", "").strip()
    if not raw:
        return list(COMPANY_FEEDS)
    feeds = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "|" in part:
            name, url = part.split("|", 1)
            feeds.append({"name": name.strip(), "url": url.strip()})
        else:
            host = urlparse(part).netloc or part
            feeds.append({"name": host, "url": part})
    return feeds or list(COMPANY_FEEDS)


def company_window(target_day: str) -> tuple:
    """
    Dates whose lab posts belong in this report.

    A Monday report includes Saturday and Sunday, because those days have
    no report of their own. Every other target day covers only itself.
    """
    target = datetime.strptime(target_day, "%Y-%m-%d").date()
    previous = target - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    start = previous + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), target.strftime("%Y-%m-%d")


def html_to_text(html: str) -> str:
    """Flatten a feed snippet, keeping linked URLs."""
    text = html or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)<h[1-6][^>]*>", "\n## ", text)
    text = re.sub(r'(?i)<a [^>]*href="([^"]+)"[^>]*>', r" \1 ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for src, dst in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&#39;", "'"),
        ("&quot;", '"'),
    ):
        text = text.replace(src, dst)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    return text.strip()


def extract_twitter_recap(html: str, limit: int = TWITTER_RECAP_LIMIT) -> str:
    """
    The AINews 'AI Twitter Recap' section, as plain text with tweet URLs.

    The full roundup is too long to send, and the tweet section is the part
    that carries company posts from X.
    """
    match = re.search(r"AI Twitter Recap(.*?)(?:AI Reddit Recap|$)", html or "", re.S | re.I)
    chunk = match.group(1) if match else (html or "")
    text = html_to_text(chunk)
    if len(text) <= limit:
        return text
    trimmed = text[:limit].rsplit(" ", 1)[0]
    return trimmed + "…"


def fetch_rss_content(target_date: str) -> Optional[Dict[str, Any]]:
    """Legacy helper for backward compatibility"""
    loader = NewsLoader()
    data = loader.pull_feed()
    return loader.fetch_by_day(target_date, data)
