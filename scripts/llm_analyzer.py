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
    CATEGORIES,
    THEMES,
    DEFAULT_THEME,
    FIXED_THEME
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
        if not raw_data or not raw_data.get("content"):
            return self._generate_empty_state(date_tag, "No content provided", language)

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
        
        cat_list = "\n".join([
            f"- {c['icon']} {c['name']}: {c['description']}"
            for c in CATEGORIES.values()
        ])
        
        theme_list = "\n".join([
            f"- {k}: {t['name']} - {t['description']}"
            for k, t in THEMES.items()
        ])
        
        return f"""You are an expert AI technology scout. Analyze the provided daily news content.
Target Language: {lang_label}.

[Target Date]
{date}

[News Source]
Title: {data.get('title', 'Unknown')}
URL: {data.get('link', '#')}
Body:
{data.get('content', '')[:14000]}

---

[Tasks]
1. Verify if content is meaningful. Status: "success" or "empty".
2. Highlights: Extract 3-5 critical breakthroughs or events. Keep each under 50 words.
3. Categorization: Group news into these buckets:
{cat_list}

   Each bucket should have:
   - key: ID (model/product/research/tools/funding/events)
   - name: Localized name ({lang_label})
   - icon: Assigned emoji
   - items: List of entries (title, summary, url, tags)

4. Keywords: Identify 5-10 trending entities or concepts.
5. Visual Theme: Pick the most appropriate style:
{theme_list}

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
      "key": "model",
      "name": "Models",
      "icon": "🤖",
      "items": [
        {{
          "title": "Short Title",
          "summary": "Brief summary",
          "url": "link",
          "tags": ["tag1"]
        }}
      ]
    }}
  ]
}}
```
"""

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
            
            print(f"✅ Data verified: {len(parsed['summary'])} highlights, {len(parsed['categories'])} sections")
            return parsed
        except json.JSONDecodeError as err:
            print(f"❌ JSON decoding failed: {err}")
            return self._create_emergency_fallback({"title": "Parsing Error"}, date)

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
            "status": "success",
            "date": date,
            "theme": DEFAULT_THEME,
            "summary": ["System encountered a processing error. Displaying raw data."],
            "keywords": ["Error"],
            "categories": [{
                "key": "model",
                "name": "General",
                "icon": "🤖",
                "items": [{
                    "title": data.get("title", "Unknown"),
                    "summary": "Unable to analyze content.",
                    "url": data.get("link", ""),
                    "tags": ["System"]
                }]
            }],
            "lang": "en"
        }

def analyze_content(content: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    """Legacy helper for backward compatibility"""
    proc = ContentProcessor()
    return proc.process_news(content, target_date)

# LLMAnalyzer alias for compatibility
class LLMAnalyzer(ContentProcessor):
    def analyze(self, content, date, lang="zh"):
        return self.process_news(content, date, lang)
