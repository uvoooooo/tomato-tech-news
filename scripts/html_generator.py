"""
HTML Generation Module
Responsible for creating the daily news report in HTML format and updating the index page.
"""
import json
import re
from datetime import datetime, timedelta
from html import escape, unescape
from html.parser import HTMLParser
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from config import (
    OUTPUT_DIR,
    THEMES,
    SITE_META,
    GITHUB_PAGES_URL,
    I18N,
    FOCUS_LOOKBACK_DAYS,
    WEEKLY_WINDOW_DAYS,
)

# daily: 2026-11-20-zh.html   weekly: week-2026-11-20-zh.html
_REPORT_FILE = re.compile(r"^(week-)?(\d{4}-\d{2}-\d{2})-(zh|en)\.html$")
_ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.I)

class _DailyCardParser(HTMLParser):
    """Pull news cards out of a generated daily page."""

    def __init__(self):
        super().__init__()
        self.section = ""
        self.items: List[Dict[str, Any]] = []
        self._current = None
        self._buf: List[str] = []
        self._in_h2 = False
        self._in_h3 = False
        self._in_summary = False
        self._in_tag = False
        self._skip_section = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = attr.get("class", "")
        if tag == "section" and "summary-card" in classes:
            self._skip_section = True
        elif tag == "section" and "category-section" in classes:
            self._skip_section = False
        elif tag == "h2" and "section-title" in classes and not self._skip_section:
            self._in_h2 = True
            self._buf = []
        elif tag == "article" and not self._skip_section:
            self._current = {
                "category": self.section,
                "title": "",
                "summary": "",
                "url": "",
                "tags": [],
            }
        elif tag == "h3" and self._current is not None:
            self._in_h3 = True
            self._buf = []
        elif tag == "p" and "news-summary" in classes and self._current is not None:
            self._in_summary = True
            self._buf = []
        elif tag == "a" and "item-link" in classes and self._current is not None:
            self._current["url"] = attr.get("href", "")
        elif tag == "span" and "tag" in classes.split() and self._current is not None:
            self._in_tag = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "h2" and self._in_h2:
            self.section = unescape("".join(self._buf).strip())
            self._in_h2 = False
        elif tag == "h3" and self._in_h3 and self._current is not None:
            self._current["title"] = unescape("".join(self._buf).strip())
            self._in_h3 = False
        elif tag == "p" and self._in_summary and self._current is not None:
            self._current["summary"] = unescape("".join(self._buf).strip())
            self._in_summary = False
        elif tag == "span" and self._in_tag and self._current is not None:
            text = unescape("".join(self._buf).strip())
            if text:
                self._current["tags"].append(text)
            self._in_tag = False
        elif tag == "article" and self._current is not None:
            if self._current["title"]:
                self.items.append(self._current)
            self._current = None

    def handle_data(self, data):
        if self._in_h2 or self._in_h3 or self._in_summary or self._in_tag:
            self._buf.append(data)


class PageBuilder:
    """Handles construction of HTML reports and index maintenance"""
    
    def __init__(self, root: str = None):
        """
        Initialize the page builder
        Args:
            root: Output root directory
        """
        self.root = Path(root or OUTPUT_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        self._init_assets()

    def _init_assets(self):
        """Prepare asset directories"""
        (self.root / "css").mkdir(parents=True, exist_ok=True)

    def reported_arxiv_ids(self, start: str, before: str) -> Set[str]:
        """
        arXiv ids already linked from dailies in [start, before).

        The report day itself is excluded, so a rerun can still choose the
        same papers. Later dailies are ignored, so a backfill is not affected
        by reports published after that day.
        """
        start_day = datetime.strptime(start, "%Y-%m-%d").date()
        before_day = datetime.strptime(before, "%Y-%m-%d").date()
        found: Set[str] = set()
        day = start_day
        while day < before_day:
            stamp = day.strftime("%Y-%m-%d")
            for lang in ("zh", "en"):
                path = self.root / f"{stamp}-{lang}.html"
                if not path.exists():
                    continue
                found.update(_ARXIV_ID.findall(path.read_text(encoding="utf-8", errors="replace")))
            day += timedelta(days=1)
        return found

    def collect_week_items(self, start: str, end: str, lang: str) -> List[Dict[str, Any]]:
        """Unique news cards from the weekday dailies in an inclusive date window."""
        start_day = datetime.strptime(start, "%Y-%m-%d").date()
        end_day = datetime.strptime(end, "%Y-%m-%d").date()
        merged: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        day = start_day
        while day <= end_day:
            if day.weekday() < 5:
                path = self.root / f"{day.strftime('%Y-%m-%d')}-{lang}.html"
                for card in self._read_daily_cards(path):
                    key = card.get("url") or card["title"].casefold()
                    if key in merged:
                        if day.isoformat() not in merged[key]["dates"]:
                            merged[key]["dates"].append(day.isoformat())
                    else:
                        card["dates"] = [day.isoformat()]
                        merged[key] = card
                        order.append(key)
            day += timedelta(days=1)
        items = []
        for index, key in enumerate(order, 1):
            card = merged[key]
            card["id"] = str(index)
            items.append(card)
        return items

    def _read_daily_cards(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        parser = _DailyCardParser()
        parser.feed(path.read_text(encoding="utf-8"))
        return parser.items

    def build_daily(self, data: Dict[str, Any]) -> str:
        """Create a new daily report page"""
        day = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        # Prioritize 'lang' from AI response, then 'language' from main.py, default to 'zh'
        lang = data.get("lang") or data.get("language") or "zh"
        theme_id = data.get("theme", "blue")
        style = THEMES.get(theme_id, THEMES["blue"])
        
        print(f"📄 Building report: {day} ({lang})")
        
        # Inject the resolved lang back into data for _assemble_html to use
        data["lang"] = lang
        
        content = self._assemble_html(data, style)
        fname = self._report_filename(day, lang, data.get("kind") or "daily")
        fpath = self.root / fname
        
        fpath.write_text(content, encoding='utf-8')
        print(f"✅ Report saved: {fname}")
        
        self.sync_index(day, data, lang)
        return str(fpath)

    def _report_filename(self, day: str, lang: str, kind: str = "daily") -> str:
        """Weekly pages use a separate name so they do not replace that Friday's daily."""
        if kind == "weekly":
            return f"week-{day}-{lang}.html"
        return f"{day}-{lang}.html"

    def build_empty(self, day: str, msg: str = "No data", lang: str = "zh", kind: str = "daily") -> str:
        """Create a placeholder page for missing data"""
        ui = I18N.get(lang, I18N["zh"])
        title = ui.get("weekly_title", ui["title"]) if kind == "weekly" else ui["title"]
        html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} · {day}</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-icon">🍅</div>
            <h1>{title}</h1>
            <div class="date-badge">{self._pretty_date(day, lang)}</div>
        </header>
        <main class="main-content" style="text-align: center; padding: 100px 0;">
            <div style="font-size: 50px;">📭</div>
            <h2>{ui['empty_title']}</h2>
            <p style="color: #888;">{msg}</p>
            <br>
            <a href="index.html" class="item-link">{ui['back_to_home']}</a>
        </main>
    </div>
</body>
</html>"""
        fpath = self.root / self._report_filename(day, lang, kind)
        fpath.write_text(html, encoding='utf-8')
        return str(fpath)

    def _assemble_html(self, data: Dict[str, Any], style: Dict[str, str]) -> str:
        """Generate the full HTML structure for a report"""
        day = data.get("date", "")
        # Use safe get with default to avoid KeyError
        lang = data.get("lang") or data.get("language") or "zh"
        ui = I18N.get(lang, I18N["zh"])
        kind = data.get("kind") or "daily"
        page_title = ui.get("weekly_title", ui["title"]) if kind == "weekly" else ui["title"]
        if kind == "weekly" and data.get("window_start"):
            date_label = f"{data['window_start']} – {data.get('window_end', day)}"
            focus_line = ""
            highlights_label = ui.get("weekly_highlights", ui["highlights"])
        else:
            date_label = self._pretty_date(day, lang)
            focus_line = escape(ui.get("focus", "").format(n=FOCUS_LOOKBACK_DAYS))
            highlights_label = ui["highlights"]
        
        # Highlights
        highlights_section = ""
        if data.get("summary"):
            items = "\n".join([
                f'<li class="summary-item">{escape(str(s))}</li>' for s in data["summary"]
            ])
            highlights_section = f"""
            <section class="summary-card">
                <h2 class="section-title">{highlights_label}</h2>
                <ul class="summary-list">
                    {items}
                </ul>
            </section>"""

        # Categorized News
        news_sections = ""
        for cat in data.get("categories", []):
            if not cat.get("items"): continue
            
            cards = ""
            for item in cat["items"]:
                tags = "".join([
                    f'<span class="tag">{escape(str(t))}</span>'
                    for t in item.get("tags", [])[:3]
                ])
                link = ""
                if item.get("url"):
                    href = escape(item["url"], quote=True)
                    link = f'<a href="{href}" class="item-link" target="_blank">{ui["read_more"]}</a>'
                cards += f"""
                <article class="news-card">
                    <h3 class="news-title">{escape(item['title'])}</h3>
                    <p class="news-summary">{escape(item['summary'])}</p>
                    {link}
                    <div class="item-tags">{tags}</div>
                </article>"""
            
            heading = escape(f"{cat.get('icon', '')} {cat['name']}".strip())
            news_sections += f"""
            <section class="category-section">
                <h2 class="section-title">{heading}</h2>
                <div class="news-grid">{cards}</div>
            </section>"""

        # Keywords
        keywords_bar = ""
        if kind != "weekly" and data.get("keywords"):
            keywords_bar = f"""
            <footer class="keywords-footer">
                <p>{ui['keywords']}: {escape(' / '.join(str(k) for k in data['keywords']))}</p>
            </footer>"""

        return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title} · {date_label}</title>
    <meta name="description" content="{SITE_META['description']}">
    <link rel="stylesheet" href="css/styles.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-icon">🍅</div>
            <h1>{page_title}</h1>
            <div class="date-badge">{date_label}</div>
            {f'<p class="focus-line">{focus_line}</p>' if focus_line else ''}
        </header>
        <main class="main-content">
            {highlights_section}
            {news_sections}
            {keywords_bar}
        </main>
        <footer class="footer">
            <p>© {datetime.now().year} {ui['title']} · {ui['footer_text']}</p>
        </footer>
    </div>
</body>
</html>"""

    def _index_date(self, entry: Dict[str, Any]) -> str:
        """Archive label. Weeklies show their range so they stay distinct from a Friday daily."""
        lang = entry.get("lang", "zh")
        if (entry.get("kind") or "daily") == "weekly":
            start = entry.get("window_start") or ""
            end = entry.get("window_end") or entry.get("date", "")
            if start and end:
                return f"Week · {start} – {end}"
            return f"Week · {self._pretty_date(entry.get('date', ''), lang)}"
        return self._pretty_date(entry.get("date", ""), lang)

    def _pretty_date(self, dstr: str, lang: str) -> str:
        """Format date for human reading"""
        try:
            dt = datetime.strptime(dstr, "%Y-%m-%d")
            ui = I18N.get(lang, I18N["zh"])
            day_name = ui['weekdays'][dt.weekday()]
            if lang == "zh":
                return dt.strftime(ui['date_format']) + f" {day_name}"
            return f"{day_name}, " + dt.strftime(ui['date_format'])
        except:
            return dstr

    def sync_index(self, day: str, data: Dict[str, Any], lang: str):
        """Update the central archive page from this report plus every issue on disk."""
        summary = (data.get("summary") or [""])[0]
        kind = data.get("kind") or "daily"
        entry = {
            "date": day,
            "url": self._report_filename(day, lang, kind),
            "summary": summary[:120],
            "lang": lang,
            "kind": kind,
            "window_start": data.get("window_start", ""),
            "window_end": data.get("window_end", ""),
            "ts": datetime.now().isoformat(),
        }
        log = [
            e for e in self._load_index()
            if not (
                e.get("date") == day
                and e.get("lang", "zh") == lang
                and (e.get("kind") or "daily") == kind
            )
        ]
        log.append(entry)
        self._write_archive(self._merge_archive(log), lang)

    def rebuild_archive(self, lang: str = "en") -> int:
        """Rewrite index.html from published HTML, in date order, grouped by month."""
        log = self._merge_archive(self._load_index())
        self._write_archive(log, lang)
        return len(log)

    def _load_index(self) -> List[Dict[str, Any]]:
        db_path = self.root / ".index.json"
        if not db_path.exists():
            return []
        try:
            log = json.loads(db_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return log if isinstance(log, list) else []

    def _entry_key(self, entry: Dict[str, Any]):
        return (
            entry.get("date") or "",
            entry.get("lang") or "zh",
            entry.get("kind") or "daily",
        )

    def _is_empty_page(self, path: Path) -> bool:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "No News Today" in text

    def _blurb_from_html(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'class="summary-item">(.*?)</li>', text, re.S)
        if not match:
            match = re.search(r'class="news-summary">(.*?)</p>', text, re.S)
        if not match:
            return ""
        raw = re.sub(r"<[^>]+>", "", match.group(1))
        return unescape(re.sub(r"\s+", " ", raw)).strip()[:120]

    def _entry_from_filename(self, name: str) -> Optional[Dict[str, Any]]:
        match = _REPORT_FILE.match(name)
        if not match:
            return None
        weekly, day, lang = match.groups()
        kind = "weekly" if weekly else "daily"
        entry = {
            "date": day,
            "url": name,
            "summary": "",
            "lang": lang,
            "kind": kind,
            "window_start": "",
            "window_end": "",
        }
        if kind == "weekly":
            end = datetime.strptime(day, "%Y-%m-%d").date()
            start = end - timedelta(days=max(WEEKLY_WINDOW_DAYS, 1) - 1)
            entry["window_start"] = start.strftime("%Y-%m-%d")
            entry["window_end"] = day
        return entry

    def _merge_archive(self, log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """One row per published issue that actually has news. Newest month first."""
        by_key = {}
        for entry in log:
            if entry.get("date") and entry.get("url"):
                by_key[self._entry_key(entry)] = entry

        merged: List[Dict[str, Any]] = []
        for path in self.root.glob("*.html"):
            scanned = self._entry_from_filename(path.name)
            if not scanned or self._is_empty_page(path):
                continue
            existing = by_key.get(self._entry_key(scanned))
            summary = (existing or {}).get("summary") or self._blurb_from_html(path)
            if not summary:
                continue
            row = dict(existing or scanned)
            row["date"] = scanned["date"]
            row["url"] = scanned["url"]
            row["lang"] = scanned["lang"]
            row["kind"] = scanned["kind"]
            row["summary"] = summary[:120]
            if scanned["kind"] == "weekly":
                row["window_start"] = row.get("window_start") or scanned["window_start"]
                row["window_end"] = row.get("window_end") or scanned["window_end"]
            merged.append(row)

        merged.sort(key=lambda e: 0 if (e.get("lang") or "zh") == "zh" else 1)
        merged.sort(key=lambda e: 0 if (e.get("kind") or "daily") == "weekly" else 1)
        merged.sort(key=lambda e: e.get("date") or "", reverse=True)
        return merged

    def _month_label(self, month: str) -> str:
        try:
            return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        except Exception:
            return month

    def _write_archive(self, log: List[Dict[str, Any]], lang: str):
        db_path = self.root / ".index.json"
        db_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

        sections = ""
        month = None
        rows = ""
        for entry in log:
            entry_month = (entry.get("date") or "")[:7]
            if entry_month != month:
                if month is not None:
                    sections += self._month_section(month, rows)
                month = entry_month
                rows = ""
            rows += f"""
            <article class="index-entry">
                <a href="{escape(entry.get('url') or '#')}" class="entry-link">
                    <span class="entry-date">{escape(self._index_date(entry))}</span>
                    <p class="entry-summary">{escape(entry.get('summary') or '')}</p>
                </a>
            </article>"""
        if month is not None:
            sections += self._month_section(month, rows)

        ui = I18N.get(lang, I18N["zh"])
        html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ui['title']} - Archive</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-icon">🍅</div>
            <h1>{ui['title']}</h1>
            <p class="subtitle">{ui['subtitle']}</p>
        </header>
        <main class="main-content">
            {sections}
        </main>
    </div>
</body>
</html>"""
        (self.root / "index.html").write_text(html, encoding="utf-8")

    def _month_section(self, month: str, rows: str) -> str:
        return f"""
        <section class="index-month">
            <h2 class="section-title">{escape(self._month_label(month))}</h2>
            <div class="index-entries">{rows}</div>
        </section>"""

    def write_styles(self):
        """Generate the CSS stylesheet (preserved layout)"""
        css = """/* ========================================
   Tomato AI Daily - Modern Minimalist Dark Mode Stylesheet
   ======================================== */
:root {
    --bg-color: #000000;
    --card-bg: #000000;
    --title-color: #ffffff;
    --text-color: #cccccc;
    --accent-color: #ffffff;
    --secondary-color: #888888;
    --border-color: #222222;
    --tag-bg: #111111;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Inter', sans-serif;
    background: var(--bg-color);
    color: var(--text-color);
    line-height: 1.6;
}
.container { max-width: 720px; margin: 0 auto; padding: 80px 24px; }
.header { margin-bottom: 80px; }
.logo-icon { font-size: 32px; margin-bottom: 16px; }
.header h1 { font-size: 48px; font-weight: 800; color: var(--title-color); letter-spacing: -0.04em; }
.date-badge { font-size: 14px; color: var(--secondary-color); text-transform: uppercase; letter-spacing: 0.1em; }
.focus-line { margin-top: 12px; font-size: 14px; color: var(--secondary-color); }
.section-title { font-size: 13px; font-weight: 700; color: var(--secondary-color); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 24px; padding-bottom: 8px; border-bottom: 1px solid var(--border-color); }
.summary-card { margin-bottom: 64px; }
.summary-list { list-style: none; }
.summary-item { font-size: 18px; font-weight: 500; color: var(--title-color); margin-bottom: 16px; padding-left: 24px; position: relative; }
.summary-item::before { content: "→"; position: absolute; left: 0; color: var(--secondary-color); }
.category-section { margin-bottom: 64px; }
.news-grid { display: flex; flex-direction: column; gap: 40px; }
.news-card { padding-bottom: 40px; border-bottom: 1px solid var(--border-color); }
.news-title { font-size: 20px; font-weight: 700; color: var(--title-color); margin-bottom: 8px; }
.news-summary { font-size: 16px; color: var(--text-color); margin-bottom: 16px; }
.item-link { font-size: 14px; font-weight: 600; color: var(--title-color); text-decoration: none; }
.item-link::after { content: " ↗"; }
.item-tags { display: flex; gap: 8px; margin-top: 16px; }
.tag { font-size: 12px; color: var(--secondary-color); background: var(--tag-bg); padding: 4px 10px; border-radius: 4px; }
.keywords-footer { margin-top: 80px; padding-top: 40px; border-top: 1px solid var(--border-color); color: var(--secondary-color); font-size: 14px; }
.footer { margin-top: 40px; color: var(--secondary-color); font-size: 12px; }
.index-month { margin-bottom: 56px; }
.index-month .section-title { margin-bottom: 16px; }
.index-entries { display: flex; flex-direction: column; gap: 24px; }
.index-entry { padding: 24px; border: 1px solid var(--border-color); border-radius: 8px; }
.entry-link { text-decoration: none; }
.entry-date { font-size: 18px; font-weight: 700; color: var(--title-color); display: block; }
.entry-summary { font-size: 14px; color: var(--secondary-color); }
"""
        (self.root / "css" / "styles.css").write_text(css, encoding='utf-8')

# Compatibility aliases
class HTMLGenerator(PageBuilder):
    def generate_daily(self, d): return self.build_daily(d)
    def generate_empty(self, d, r, l): return self.build_empty(d, r, l)
    def update_index(self, d, r, lang): return self.sync_index(d, r, lang)
    def generate_css(self): self.write_styles()

def generate_daily_html(res):
    b = PageBuilder()
    b.write_styles()
    return b.build_daily(res)
