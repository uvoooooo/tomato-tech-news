"""
arXiv fetcher for the focus topics.

One query per topic, limited to a lookback window ending on the report date.
The same paper can match more than one topic; those matches are merged.
"""
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import feedparser
import requests

from config import (
    ARXIV_API_URL,
    ARXIV_MAX_RESULTS,
    ARXIV_TIMEOUT,
    FOCUS_LOOKBACK_DAYS,
    FOCUS_TOPICS,
)


class PaperLoader:
    """Pull recent arXiv papers that match the configured focus topics."""

    def __init__(self, source_url: str = None):
        self.url = source_url or ARXIV_API_URL
        self.timeout = ARXIV_TIMEOUT

    def fetch_for_date(self, date_str: str, lookback_days: int = None) -> List[Dict[str, Any]]:
        """
        Papers submitted in the inclusive window ending on date_str.

        Args:
            date_str: Report date, YYYY-MM-DD.
            lookback_days: Window length. Defaults to FOCUS_LOOKBACK_DAYS.
        """
        end = datetime.strptime(date_str, "%Y-%m-%d")
        span = lookback_days if lookback_days is not None else FOCUS_LOOKBACK_DAYS
        if span < 1:
            span = 1
        start = end - timedelta(days=span - 1)
        start_stamp = start.strftime("%Y%m%d") + "0000"
        end_stamp = end.strftime("%Y%m%d") + "2359"
        print(
            f"📚 arXiv window {start.strftime('%Y-%m-%d')} → {date_str} "
            f"({len(FOCUS_TOPICS)} topics)"
        )

        merged: Dict[str, Dict[str, Any]] = {}
        for index, topic in enumerate(FOCUS_TOPICS):
            if index:
                time.sleep(6)
            found = self._query_topic(topic, start_stamp, end_stamp, start, end)
            print(f"   {topic['key']}: {len(found)}")
            for paper in found:
                existing = merged.get(paper["id"])
                if existing is None:
                    merged[paper["id"]] = paper
                    continue
                for key in paper["topics"]:
                    if key not in existing["topics"]:
                        existing["topics"].append(key)

        papers = sorted(merged.values(), key=lambda item: item.get("published", ""), reverse=True)
        print(f"✅ arXiv papers kept: {len(papers)}")
        return papers

    def _get_with_retry(self, params: Dict[str, Any], topic_key: str):
        """GET the arXiv API, backing off on rate limits and timeouts."""
        delay = 5
        last_err = None
        attempts = 3
        for attempt in range(attempts):
            try:
                resp = requests.get(
                    self.url,
                    params=params,
                    timeout=self.timeout,
                    headers={"User-Agent": "TomatoNews/2.0 (mailto:local)"},
                )
                if resp.status_code == 429:
                    last_err = "rate limited"
                    if attempt == attempts - 1:
                        break
                    print(f"⚠️ arXiv {topic_key} rate limited, retry in {delay}s")
                    time.sleep(delay)
                    delay = min(delay * 2, 20)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as err:
                last_err = err
                print(f"⚠️ arXiv {topic_key} request failed ({attempt + 1}/{attempts}): {err}")
                if attempt == attempts - 1:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 20)
        print(f"⚠️ arXiv query failed for {topic_key}: {last_err or 'rate limited'}")
        return None

    def _query_topic(
        self,
        topic: Dict[str, Any],
        start_stamp: str,
        end_stamp: str,
        start: datetime,
        end: datetime,
    ) -> List[Dict[str, Any]]:
        terms = " OR ".join(f"({clause})" for clause in topic["queries"])
        # Date stays in the query so backfills do not only see the newest papers.
        # Category is applied locally; a long cat: OR list makes arXiv reject the call.
        query = f"({terms}) AND submittedDate:[{start_stamp} TO {end_stamp}]"
        resp = self._get_with_retry(
            {
                "search_query": query,
                "start": 0,
                "max_results": ARXIV_MAX_RESULTS,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            topic["key"],
        )
        if resp is None:
            return []

        parsed = feedparser.parse(resp.content)
        papers = []
        for entry in parsed.entries:
            if not self._in_scope(entry):
                continue
            paper = self._format_entry(entry, topic["key"])
            if paper is None:
                continue
            published = datetime.strptime(paper["published"], "%Y-%m-%d")
            if published < start or published > end:
                continue
            papers.append(paper)
        return papers

    def _in_scope(self, entry) -> bool:
        """Keep cs, math, and stat papers. Uncategorized entries are kept."""
        terms = []
        for tag in getattr(entry, "tags", None) or []:
            term = tag.get("term", "") if isinstance(tag, dict) else getattr(tag, "term", "")
            if term:
                terms.append(str(term))
        if not terms:
            return True
        return any(
            term.startswith("cs.") or term.startswith("math.") or term.startswith("stat.")
            for term in terms
        )

    def _format_entry(self, entry, topic_key: str) -> Optional[Dict[str, Any]]:
        published = self._published_day(entry)
        if not published:
            return None
        arxiv_id = self._arxiv_id(entry.get("id", "") or entry.get("link", ""))
        if not arxiv_id:
            return None
        url = f"https://arxiv.org/abs/{arxiv_id}"
        return {
            "id": arxiv_id,
            "title": _plain(entry.get("title", "")),
            "summary": _plain(entry.get("summary", "")),
            "url": url,
            "published": published,
            "topics": [topic_key],
        }


    def _published_day(self, entry) -> Optional[str]:
        parsed = getattr(entry, "published_parsed", None)
        if parsed:
            return datetime(*parsed[:3]).strftime("%Y-%m-%d")
        raw = str(entry.get("published", "") or "")
        if len(raw) >= 10:
            return raw[:10]
        return None

    def _arxiv_id(self, value: str) -> Optional[str]:
        match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", value or "")
        return match.group(1) if match else None


def _plain(text: str) -> str:
    """Collapse markup and whitespace from an arXiv field."""
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()
