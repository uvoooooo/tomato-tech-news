"""
AI Analysis Module
Uses OpenRouter (OpenAI-compatible API) to analyze, classify, and summarize news.
"""
import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from config import (
    OPENROUTER_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    CLAUDE_MAX_TOKENS,
    DEFAULT_THEME,
    FIXED_THEME,
    FOCUS_TOPICS,
    I18N,
)

class ContentProcessor:
    """Orchestrates AI-driven news analysis and summarization"""
    
    def __init__(self, key: str = None, endpoint: str = None):
        """
        Initialize the processor with API credentials
        Args:
            key: OpenRouter API key. Defaults to config.
            endpoint: API base URL. Defaults to config.
        """
        self.api_key = key or OPENROUTER_API_KEY
        self.api_url = endpoint or OPENROUTER_BASE_URL
        self.engine = OPENROUTER_MODEL
        self.token_limit = CLAUDE_MAX_TOKENS
        
        if not self.api_key:
            raise EnvironmentError("Missing OPENROUTER_API_KEY in environment")
            
        try:
            self.api_client = OpenAI(base_url=self.api_url, api_key=self.api_key)
            print(f"✅ AI Engine ready: {self.engine}")
        except Exception as err:
            raise RuntimeError(f"AI Client initialization failed: {err}")

    def process_news(self, raw_data: Dict[str, Any], date_tag: str, language: str = "zh") -> Dict[str, Any]:
        """
        Perform deep analysis on news content via LLM
        Args:
            raw_data: Input news dictionary
            date_tag: Target date string
            language: Desired output language
        Returns:
            Structured analysis result
        """
        has_roundup = bool(raw_data and raw_data.get("content"))
        has_papers = bool(raw_data and raw_data.get("papers"))
        if not has_roundup and not has_papers:
            return self._generate_empty_state(
                date_tag,
                I18N.get(language, I18N["zh"]).get("empty_focus", "No content provided"),
                language,
            )

        print(f"🤖 Requesting AI analysis ({language})...")
        instruction = self._compose_instruction(raw_data, date_tag, language)
        
        try:
            chat_response = self.api_client.chat.completions.create(
                model=self.engine,
                max_tokens=self.token_limit,
                temperature=0.25,
                messages=[{"role": "user", "content": instruction}]
            )
            raw_output = chat_response.choices[0].message.content
            print(f"✅ AI analysis complete ({len(raw_output)} chars)")
            return self._decode_ai_output(raw_output, date_tag, language)
        except Exception as err:
            print(f"❌ AI processing error: {err}")
            return self._create_emergency_fallback(raw_data, date_tag)

    def _compose_instruction(self, data: Dict[str, Any], date: str, lang: str) -> str:
        """Build the structured prompt for the AI"""
        lang_label = "中文" if lang == "zh" else "English"
        topic_list = "\n".join([
            f"- {topic['key']} {topic['icon']} {topic['name']['en']}: "
            f"{topic['description'].get(lang, topic['description']['en'])}"
            for topic in FOCUS_TOPICS
        ])
        keys = " / ".join(topic["key"] for topic in FOCUS_TOPICS)
        papers = self._format_papers(data.get("papers") or [])
        roundup = (data.get("content") or "").strip()
        roundup_block = roundup[:8000] if roundup else "(none for this date)"

        return f"""You write a narrow research brief. Keep only items that are clearly about the topics below.
Target Language: {lang_label}. Write titles, summaries, highlights, and keywords in {lang_label}. Keep topic keys and proper nouns as given.

[Topics]
{topic_list}

Drop general model launches, funding, product news, and policy unless they are specifically about one of these topics.

[Target Date]
{date}
Paper window: {data.get('window_start', date)} through {data.get('window_end', date)}

[arXiv papers]
{papers}

[Industry roundup]
Title: {data.get('title', 'Unknown')}
URL: {data.get('link', '') or '(none)'}
Body:
{roundup_block}

---

[Tasks]
1. status is "success" when you keep at least one item, otherwise "empty".
2. summary: up to 5 highlights, each under 50 words, drawn only from kept items. Cover more than one topic when several topics have items. Do not pad.
3. categories: one bucket per topic that has clear matches. key must be one of: {keys}.
   Judge each topic on its own. When a topic's shortlist has clear papers, keep 3 to 4 of the strongest. Do not drop a topic because another topic has more papers.
   Omit a topic only when nothing in its shortlist is actually about it.
   A paper goes in exactly one bucket, the best fit among its topic hints.
   Each item needs title, summary (under 60 words), url copied from the source, and up to 3 tags.
   Tag arXiv items "arXiv" and roundup items "AINews".
   From the roundup, keep only on-topic developments and link them to the roundup URL.
   Do not invent papers, titles, or URLs.
4. keywords: 5-8 specific terms that appear in the kept items.
5. theme: "blue".

[Output Format]
Strict JSON only:
```json
{{
  "status": "success",
  "date": "{date}",
  "lang": "{lang}",
  "theme": "blue",
  "summary": ["Point 1", "Point 2"],
  "keywords": ["KW1", "KW2"],
  "categories": [
    {{
      "key": "coding_agent",
      "name": "Coding Agent",
      "icon": "💻",
      "items": [
        {{
          "title": "Short Title",
          "summary": "Brief summary",
          "url": "https://arxiv.org/abs/0000.00000",
          "tags": ["arXiv", "SWE-bench"]
        }}
      ]
    }}
  ]
}}
```
"""

    def _format_papers(self, papers: list) -> str:
        """Render a balanced arXiv shortlist, capped per topic."""
        if not papers:
            return "(none)"
        per_topic = 5
        chosen = []
        seen = set()
        for topic in FOCUS_TOPICS:
            kept = 0
            for paper in papers:
                if paper.get("id") in seen or topic["key"] not in (paper.get("topics") or []):
                    continue
                seen.add(paper.get("id"))
                chosen.append(paper)
                kept += 1
                if kept >= per_topic:
                    break
        blocks = []
        for index, paper in enumerate(chosen, 1):
            topics = ", ".join(paper.get("topics") or [])
            abstract = (paper.get("summary") or "")[:400]
            blocks.append(
                f"{index}. topics: {topics}\n"
                f"   title: {paper.get('title', '')}\n"
                f"   published: {paper.get('published', '')}\n"
                f"   url: {paper.get('url', '')}\n"
                f"   abstract: {abstract}"
            )
        return "\n\n".join(blocks)

    def _decode_ai_output(self, text: str, date: str, language: str = "zh") -> Dict[str, Any]:
        """Parse and validate the JSON returned by AI"""
        clean_text = text.strip()
        for marker in ["```json", "```"]:
            if clean_text.startswith(marker):
                clean_text = clean_text[len(marker):]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        try:
            parsed = json.loads(clean_text)
            # Default value injection
            parsed.setdefault("status", "success")
            if parsed.get("date") and parsed.get("date") != date:
                print(f"⚠️ Model date {parsed.get('date')!r} ignored; using pipeline date {date!r}")
            parsed["date"] = date
            parsed["lang"] = language
            parsed["theme"] = FIXED_THEME or parsed.get("theme", DEFAULT_THEME)
            parsed.setdefault("summary", [])
            parsed.setdefault("keywords", [])
            parsed.setdefault("categories", [])
            parsed = self._keep_focus_topics(parsed, language)

            print(f"✅ Data verified: {len(parsed['summary'])} highlights, {len(parsed['categories'])} sections")
            return parsed
        except json.JSONDecodeError as err:
            print(f"❌ JSON decoding failed: {err}")
            return self._create_emergency_fallback({"title": "Parsing Error"}, date)

    def _keep_focus_topics(self, parsed: Dict[str, Any], language: str) -> Dict[str, Any]:
        """Drop buckets and items outside the configured focus topics."""
        by_key = {}
        for category in parsed.get("categories") or []:
            key = category.get("key")
            if key in by_key or not any(topic["key"] == key for topic in FOCUS_TOPICS):
                continue
            items = []
            for item in category.get("items") or []:
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
                items.append({
                    "title": title,
                    "summary": str(item.get("summary") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "tags": tags[:3],
                })
            if items:
                by_key[key] = items

        ordered = []
        for topic in FOCUS_TOPICS:
            items = by_key.get(topic["key"])
            if not items:
                continue
            label = topic["name"].get(language, topic["name"]["en"])
            ordered.append({
                "key": topic["key"],
                "name": label,
                "icon": topic["icon"],
                "items": items,
            })

        parsed["categories"] = ordered
        if not ordered:
            parsed["status"] = "empty"
            parsed["summary"] = []
            parsed["keywords"] = []
            parsed["reason"] = I18N.get(language, I18N["zh"]).get(
                "empty_focus",
                "No items matched the focus topics.",
            )
        else:
            parsed["status"] = "success"
        return parsed

    def _generate_empty_state(self, date: str, msg: str, lang: str) -> Dict[str, Any]:
        """Standardized response for missing data"""
        return {
            "status": "empty",
            "date": date,
            "lang": lang,
            "theme": FIXED_THEME or DEFAULT_THEME,
            "summary": [],
            "keywords": [],
            "categories": [],
            "reason": msg
        }

    def _create_emergency_fallback(self, data: Dict[str, Any], date: str) -> Dict[str, Any]:
        """Minimal result when AI fails completely"""
        return {
            "status": "empty",
            "date": date,
            "theme": DEFAULT_THEME,
            "summary": [],
            "keywords": [],
            "categories": [],
            "reason": "AI processing failed",
            "lang": "en",
        }

def analyze_content(content: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    """Legacy helper for backward compatibility"""
    proc = ContentProcessor()
    return proc.process_news(content, target_date)

# LLMAnalyzer alias for compatibility
class LLMAnalyzer(ContentProcessor):
    def analyze(self, content, date, lang="zh"):
        return self.process_news(content, date, lang)
