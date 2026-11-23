"""
HTML Generation Module
Responsible for creating the daily news report in HTML format and updating the index page.
"""
import os
import json
from datetime import datetime
from html import escape
from typing import Dict, Any, List
from pathlib import Path
from config import (
    OUTPUT_DIR,
    THEMES,
    SITE_META,
    GITHUB_PAGES_URL,
    I18N,
    FOCUS_LOOKBACK_DAYS,
)

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
        fname = f"{day}-{lang}.html"
        fpath = self.root / fname
        
        fpath.write_text(content, encoding='utf-8')
        print(f"✅ Report saved: {fname}")
        
        self.sync_index(day, data, lang)
        return str(fpath)

    def build_empty(self, day: str, msg: str = "No data", lang: str = "zh") -> str:
        """Create a placeholder page for missing data"""
        ui = I18N.get(lang, I18N["zh"])
        html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ui['title']} · {day}</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-icon">🍅</div>
            <h1>{ui['title']}</h1>
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
        fpath = self.root / f"{day}-{lang}.html"
        fpath.write_text(html, encoding='utf-8')
        return str(fpath)

    def _assemble_html(self, data: Dict[str, Any], style: Dict[str, str]) -> str:
        """Generate the full HTML structure for a report"""
        day = data.get("date", "")
        # Use safe get with default to avoid KeyError
        lang = data.get("lang") or data.get("language") or "zh"
        ui = I18N.get(lang, I18N["zh"])
        date_label = self._pretty_date(day, lang)
        focus_line = escape(ui.get("focus", "").format(n=FOCUS_LOOKBACK_DAYS))
        
        # Highlights
        highlights_section = ""
        if data.get("summary"):
            items = "\n".join([
                f'<li class="summary-item">{escape(str(s))}</li>' for s in data["summary"]
            ])
            highlights_section = f"""
            <section class="summary-card">
                <h2 class="section-title">{ui['highlights']}</h2>
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
        if data.get("keywords"):
            keywords_bar = f"""
            <footer class="keywords-footer">
                <p>{ui['keywords']}: {escape(' / '.join(str(k) for k in data['keywords']))}</p>
            </footer>"""

        return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ui['title']} · {date_label}</title>
    <meta name="description" content="{SITE_META['description']}">
    <link rel="stylesheet" href="css/styles.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-icon">🍅</div>
            <h1>{ui['title']}</h1>
            <div class="date-badge">{date_label}</div>
            <p class="focus-line">{focus_line}</p>
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
        """Update the central archive page"""
        db_path = self.root / ".index.json"
        log = []
        if db_path.exists():
            try:
                log = json.loads(db_path.read_text(encoding='utf-8'))
            except:
                log = []
            
        summary = data.get("summary", [""])[0]
        entry = {
            "date": day,
            "url": f"{day}-{lang}.html",
            "summary": summary[:120],
            "lang": lang,
            "ts": datetime.now().isoformat()
        }
        
        # Merge: one row per (date, lang) so zh/en on the same day both appear
        log = [
            e for e in log
            if not (e.get("date") == day and e.get("lang", "zh") == lang)
        ]
        log.insert(0, entry)
        log = log[:50]
        
        db_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
        
        # Rebuild index.html
        rows = ""
        for e in log:
            e_lang = e.get("lang", "zh")
            rows += f"""
            <article class="index-entry">
                <a href="{e.get('url', '#')}" class="entry-link">
                    <span class="entry-date">{self._pretty_date(e.get('date', ''), e_lang)}</span>
                    <p class="entry-summary">{e.get('summary', '')}</p>
                </a>
            </article>"""
            
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
            <div class="index-entries">{rows}</div>
        </main>
    </div>
</body>
</html>"""
        (self.root / "index.html").write_text(html, encoding='utf-8')

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
