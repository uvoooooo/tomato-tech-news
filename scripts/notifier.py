"""
Email Notification Module
Responsible for sending success, empty, or error notifications via email.
Supports legacy NOTIFICATION_TO or split NOTIFICATION_TO_ZH / NOTIFICATION_TO_EN lists.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    GITHUB_PAGES_URL,
    I18N,
    NOTIFICATION_RECIPIENTS,
    NOTIFICATION_TO_ZH,
    NOTIFICATION_TO_EN,
    use_split_notification_recipients,
)

# Email body copy: mail_locale matches report link locale (zh / en)
MAIL = {
    "zh": {
        "success_subj": "Tomato AI Daily · {day}",
        "success_lead": "<strong>{day}</strong> 的日报已发布。",
        "weekly_subj": "Tomato AI Weekly · {start} – {end}",
        "weekly_lead": "截至 <strong>{day}</strong> 的一周周报已发布。",
        "weekly_btn": "打开周报",
        "success_items": "条目数",
        "success_btn": "打开日报",
        "open_web": "在网页打开 ↗",
        "items_unit": "条",
        "success_copy_hint": "若按钮无法点击，请复制以下链接：",
        "empty_subj": "📭 今日无内容 - {day}",
        "empty_title": "今日无更新 — {day}",
        "empty_reason": "原因",
        "view_logs": "查看运行日志",
        "fail_subj": "❌ 流水线失败 - {day}",
        "fail_heading": "执行出错",
        "fail_date": "日期",
        "fail_actions": "在 GitHub Actions 中查看",
        "fail_no_ci": "（当前环境无 CI 运行链接。）",
        "footer_utc": "生成时间（UTC）",
    },
    "en": {
        "success_subj": "Tomato AI Daily · {day}",
        "success_lead": "The report for <strong>{day}</strong> is live.",
        "weekly_subj": "Tomato AI Weekly · {start} – {end}",
        "weekly_lead": "The weekly report ending <strong>{day}</strong> is live.",
        "weekly_btn": "Open Weekly",
        "success_items": "Total items",
        "success_btn": "Open Report",
        "open_web": "Open on the web ↗",
        "items_unit": "items",
        "success_copy_hint": "If the button does not work, copy this link:",
        "empty_subj": "📭 No News - {day}",
        "empty_title": "No updates for {day}",
        "empty_reason": "Reason",
        "view_logs": "View Logs",
        "fail_subj": "❌ Pipeline Failed - {day}",
        "fail_heading": "Execution Error",
        "fail_date": "Date",
        "fail_actions": "Check GitHub Actions",
        "fail_no_ci": "(No CI run URL in this environment.)",
        "footer_utc": "Generated at",
    },
}

_FONT = (
    "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',"
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"
)
_READ_MORE = "Read More ↗"


def _pretty_mail_date(day: str, lang: str) -> str:
    """Short date badge for the mail header, matching the site."""
    ui = I18N.get(lang, I18N["zh"])
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
        weekday = ui["weekdays"][dt.weekday()]
        if lang == "zh":
            return dt.strftime(ui["date_format"]) + f" {weekday}"
        return f"{weekday}, " + dt.strftime(ui["date_format"])
    except ValueError:
        return day


def _mail_date_label(report: Dict[str, Any], lang: str) -> str:
    kind = report.get("kind") or "daily"
    day = report.get("date") or ""
    if kind == "weekly" and report.get("window_start"):
        return f"{report['window_start']} – {report.get('window_end', day)}"
    return _pretty_mail_date(day, lang)


def build_inline_report_email(
    report: Dict[str, Any],
    link: str,
    mail_locale: str = "zh",
) -> Tuple[str, str]:
    """Dark inline-styled report body for the inbox. Returns (html, plain)."""
    loc = mail_locale if mail_locale in MAIL else "en"
    t = MAIL[loc]
    ui = I18N.get(loc, I18N["zh"])
    kind = report.get("kind") or "daily"
    weekly = kind == "weekly"
    page_title = ui.get("weekly_title", ui["title"]) if weekly else ui["title"]
    highlights_label = (
        ui.get("weekly_highlights", ui["highlights"]) if weekly else ui["highlights"]
    )
    date_label = _mail_date_label(report, loc)
    count = sum(len(c.get("items", [])) for c in report.get("categories", []))
    meta = f"{date_label} · {count} {t['items_unit']}"
    safe_href = escape(link, quote=True)
    year = datetime.utcnow().year

    highlights = [str(s).strip() for s in (report.get("summary") or []) if str(s).strip()]
    preheader = highlights[0] if highlights else meta

    blocks: List[str] = []

    if highlights:
        blocks.append(_section_label(highlights_label))
        blocks.append('<tr><td height="28" style="font-size:0;line-height:0;">&nbsp;</td></tr>')
        for line in highlights:
            blocks.append(_highlight_row(line))
        blocks.append('<tr><td height="40" style="font-size:0;line-height:0;">&nbsp;</td></tr>')

    for cat in report.get("categories") or []:
        items = cat.get("items") or []
        if not items:
            continue
        heading = f"{cat.get('icon', '')} {cat.get('name', '')}".strip()
        blocks.append(_section_label(heading))
        blocks.append('<tr><td height="24" style="font-size:0;line-height:0;">&nbsp;</td></tr>')
        for item in items:
            blocks.append(_card_row(item, ui.get("read_more", "Read More")))
        blocks.append('<tr><td height="28" style="font-size:0;line-height:0;">&nbsp;</td></tr>')

    body_rows = "\n".join(blocks)
    html = f"""<!DOCTYPE html>
<html lang="{loc}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <meta name="supported-color-schemes" content="dark">
  <title>{escape(page_title)} · {escape(date_label)}</title>
</head>
<body bgcolor="#000000" style="margin:0;padding:0;background:#000000;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#000000;">{escape(preheader)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#000000" style="background:#000000;">
    <tr><td align="center" style="padding:56px 20px 64px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;">
        <tr><td style="padding:0 0 14px;font-size:28px;line-height:32px;">🍅</td></tr>
        <tr><td style="font-family:{_FONT};font-size:40px;line-height:44px;font-weight:800;letter-spacing:-0.04em;color:#ffffff;">{escape(page_title)}</td></tr>
        <tr><td style="padding:12px 0 0;font-family:{_FONT};font-size:13px;letter-spacing:0.1em;text-transform:uppercase;color:#888888;">{escape(meta)}</td></tr>
        <tr><td height="56" style="font-size:0;line-height:0;">&nbsp;</td></tr>
        {body_rows}
        <tr><td height="24" style="font-size:0;line-height:0;">&nbsp;</td></tr>
        <tr><td align="left" style="padding:0;">
          <a href="{safe_href}" style="display:inline-block;font-family:{_FONT};font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;padding:12px 18px;border:1px solid #333333;border-radius:6px;">{escape(t["open_web"])}</a>
        </td></tr>
        <tr><td height="36" style="font-size:0;line-height:0;">&nbsp;</td></tr>
        <tr><td style="font-family:{_FONT};font-size:12px;line-height:18px;color:#555555;">© {year} {escape(ui["title"])} · {escape(ui["footer_text"])}</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    plain_lines = [page_title, meta, ""]
    if highlights:
        plain_lines.append(highlights_label)
        for line in highlights:
            plain_lines.append(f"- {line}")
        plain_lines.append("")
    for cat in report.get("categories") or []:
        items = cat.get("items") or []
        if not items:
            continue
        heading = f"{cat.get('icon', '')} {cat.get('name', '')}".strip()
        plain_lines.append(heading)
        for item in items:
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            url = str(item.get("url") or "").strip()
            plain_lines.append(f"* {title}")
            if summary:
                plain_lines.append(f"  {summary}")
            if url:
                plain_lines.append(f"  {url}")
        plain_lines.append("")
    plain_lines.append(link)
    return html, "\n".join(plain_lines).rstrip() + "\n"


def _section_label(text: str) -> str:
    return (
        f'<tr><td style="padding:0 0 10px;font-family:{_FONT};font-size:12px;'
        f'font-weight:700;letter-spacing:0.12em;text-transform:uppercase;'
        f'color:#888888;border-bottom:1px solid #222222;">{escape(text)}</td></tr>'
    )


def _highlight_row(text: str) -> str:
    return f"""
            <tr><td style="padding:0 0 14px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
                <td valign="top" width="22" style="font-family:{_FONT};font-size:16px;line-height:24px;color:#888888;">→</td>
                <td style="font-family:{_FONT};font-size:16px;line-height:24px;font-weight:500;color:#ffffff;">{escape(text)}</td>
              </tr></table>
            </td></tr>"""


def _card_row(item: Dict[str, Any], read_more_label: str) -> str:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    url = str(item.get("url") or "").strip()
    tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()][:4]
    safe_title = escape(title)
    title_html = safe_title
    if url:
        href = escape(url, quote=True)
        title_html = (
            f'<a href="{href}" style="color:#ffffff;text-decoration:none;">{safe_title}</a>'
        )
    summary_html = (
        f'<tr><td style="padding:8px 0 0;font-family:{_FONT};font-size:15px;'
        f'line-height:22px;color:#cccccc;">{escape(summary)}</td></tr>'
        if summary
        else ""
    )
    more_html = ""
    if url:
        href = escape(url, quote=True)
        label = escape(f"{read_more_label} ↗" if "↗" not in read_more_label else read_more_label)
        # Prefer the fixed approved copy when the site string is plain "Read More".
        if read_more_label == "Read More":
            label = escape(_READ_MORE)
        more_html = (
            f'<tr><td style="padding:12px 0 0;font-family:{_FONT};font-size:14px;'
            f'font-weight:600;"><a href="{href}" style="color:#ffffff;text-decoration:none;">'
            f"{label}</a></td></tr>"
        )
    tags_html = ""
    if tags:
        pills = "".join(
            f'<span style="display:inline-block;margin:0 8px 8px 0;padding:4px 10px;'
            f'font-family:{_FONT};font-size:11px;line-height:16px;color:#888888;'
            f'background:#111111;border-radius:999px;">{escape(tag)}</span>'
            for tag in tags
        )
        tags_html = f'<tr><td style="padding:14px 0 0;">{pills}</td></tr>'
    return f"""
            <tr><td style="padding:0 0 28px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr><td style="font-family:{_FONT};font-size:18px;line-height:26px;font-weight:700;color:#ffffff;">{title_html}</td></tr>
                {summary_html}
                {more_html}
                {tags_html}
              </table>
            </td></tr>"""


class AlertManager:
    """Manages outgoing email alerts for the automated pipeline"""

    def __init__(self, **kwargs):
        self.host = kwargs.get("host") or SMTP_HOST
        self.port = kwargs.get("port") or SMTP_PORT
        self.sender = kwargs.get("user") or SMTP_USER
        self.secret = kwargs.get("password") or SMTP_PASSWORD

        self.repo = os.getenv("GITHUB_REPOSITORY")
        self.run_id = os.getenv("GITHUB_RUN_ID")
        self.gh_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")

    def recipients_for_locale(self, mail_locale: str) -> List[str]:
        """Recipients who should receive templates + links for this mail locale."""
        if use_split_notification_recipients():
            if mail_locale == "zh":
                return list(NOTIFICATION_TO_ZH)
            if mail_locale == "en":
                return list(NOTIFICATION_TO_EN)
            return []
        return list(NOTIFICATION_RECIPIENTS)

    def _has_any_recipient(self) -> bool:
        if use_split_notification_recipients():
            return bool(NOTIFICATION_TO_ZH or NOTIFICATION_TO_EN)
        return bool(NOTIFICATION_RECIPIENTS)

    def _is_ready(self) -> bool:
        return bool(self.host and self.sender and self.secret and self._has_any_recipient())

    def notify_success(
        self,
        day: str,
        count: int,
        mail_locale: str = "zh",
        kind: str = "daily",
        window_start: str = "",
        window_end: str = "",
        report: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send success email in mail_locale. Weekly links point at week-{day}-{lang}.html."""
        recipients = self.recipients_for_locale(mail_locale)
        if not recipients:
            return True

        loc = mail_locale if mail_locale in MAIL else "en"
        t = MAIL[loc]
        link = self._build_report_link(day, mail_locale, kind)
        weekly = kind == "weekly"
        if weekly:
            subj = t["weekly_subj"].format(
                start=window_start or day,
                end=window_end or day,
                day=day,
            )
        else:
            subj = t["success_subj"].format(day=day)

        payload = dict(report or {})
        payload.setdefault("date", day)
        payload.setdefault("kind", kind)
        if window_start:
            payload.setdefault("window_start", window_start)
        if window_end:
            payload.setdefault("window_end", window_end)
        if payload.get("categories"):
            html, plain = build_inline_report_email(payload, link, loc)
            return self._dispatch(subj, html, plain, recipients)

        # Fallback when callers have no report body (legacy helpers).
        safe_href = escape(link, quote=True)
        safe_visible = escape(link)
        lead = t["weekly_lead" if weekly else "success_lead"].format(day=day)
        button = t["weekly_btn"] if weekly else t["success_btn"]
        plain = (
            f"Tomato AI Daily — {day}\n{t['success_items']}: {count}\n\n{link}\n"
            if loc == "en"
            else f"Tomato AI Daily — {day}\n{t['success_items']}：{count}\n\n{link}\n"
        )
        html = f"""
        <html>
        <body style="font-family: sans-serif; background: #f9f9f9; padding: 20px;">
            <div style="max-width: 550px; margin: auto; background: #fff; border-radius: 10px; border: 1px solid #eee; overflow: hidden;">
                <div style="background: #2c3e50; color: #fff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">Tomato AI Daily</h2>
                </div>
                <div style="padding: 25px;">
                    <p style="font-size: 16px;">{lead}</p>
                    <div style="background: #f0f4f8; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0; color: #34495e;">{t['success_items']}: <strong>{count}</strong></p>
                    </div>
                    <a href="{safe_href}" style="display: inline-block; text-align: center; background: #3498db; color: #fff; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">{button}</a>
                    <p style="margin-top: 18px; font-size: 12px; color: #555; word-break: break-all;">{t['success_copy_hint']}<br><a href="{safe_href}" style="color: #3498db;">{safe_visible}</a></p>
                </div>
                <div style="padding: 15px; border-top: 1px solid #eee; font-size: 11px; color: #999; text-align: center;">
                    {t['footer_utc']} {datetime.utcnow().strftime('%H:%M:%S')} UTC
                </div>
            </div>
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain, recipients)

    def notify_empty(self, day: str, reason: str, mail_locale: str = "zh") -> bool:
        recipients = self.recipients_for_locale(mail_locale)
        if not recipients:
            return True

        loc = mail_locale if mail_locale in MAIL else "en"
        t = MAIL[loc]
        subj = t["empty_subj"].format(day=day)
        log_url = self._get_ci_log_url()
        if log_url:
            safe_log = escape(log_url, quote=True)
            log_btn = f'<p><a href="{safe_log}">{t["view_logs"]}</a></p>'
            log_plain = f"\n{t['view_logs']}: {log_url}\n"
        else:
            log_btn = ""
            log_plain = ""

        reason_html = escape(reason)
        title_line = t["empty_title"].format(day=day)
        plain = f"{title_line}\n{t['empty_reason']}: {reason}{log_plain}"

        html = f"""
        <html>
        <body style="font-family: sans-serif; padding: 20px;">
            <h3>{title_line}</h3>
            <p>{t['empty_reason']}: {reason_html}</p>
            {log_btn}
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain, recipients)

    def notify_failure(self, day: str, err_msg: str, mail_locale: str = "zh") -> bool:
        recipients = self.recipients_for_locale(mail_locale)
        if not recipients:
            return True

        loc = mail_locale if mail_locale in MAIL else "en"
        t = MAIL[loc]
        subj = t["fail_subj"].format(day=day)
        log_url = self._get_ci_log_url()
        if log_url:
            safe_log = escape(log_url, quote=True)
            actions_html = f'<p><a href="{safe_log}">{t["fail_actions"]}</a></p>'
            actions_plain = f"\n{t['fail_actions']}: {log_url}\n"
        else:
            actions_html = f"<p>{t['fail_no_ci']}</p>"
            actions_plain = ""

        plain = f"{t['fail_heading']} — {day}\n\n{err_msg}{actions_plain}"
        html = f"""
        <html>
        <body style="font-family: monospace; background: #fff5f5; padding: 20px;">
            <h2 style="color: #c0392b;">{t['fail_heading']}</h2>
            <p><strong>{t['fail_date']}:</strong> {day}</p>
            <div style="background: #333; color: #0f0; padding: 15px; border-radius: 5px; overflow-x: auto;">
                <pre>{self._sanitize(err_msg)}</pre>
            </div>
            {actions_html}
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain, recipients)

    def _normalize_pages_base(self, base: str) -> str:
        base = (base or "").strip()
        if not base:
            return ""
        if base.startswith("//"):
            return "https:" + base.rstrip("/")
        if not base.startswith("http://") and not base.startswith("https://"):
            return "https://" + base.lstrip("/").rstrip("/")
        return base.rstrip("/")

    def _infer_github_pages_base(self) -> str:
        repo = self.repo or os.getenv("GITHUB_REPOSITORY", "")
        if not repo or "/" not in repo:
            return ""
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}"

    def _build_report_link(self, day: str, lang: str = "zh", kind: str = "daily") -> str:
        raw_base = GITHUB_PAGES_URL or os.getenv("GITHUB_PAGES_URL", "")
        base = self._normalize_pages_base(raw_base)
        if not base:
            base = self._infer_github_pages_base()
        path = f"week-{day}-{lang}.html" if kind == "weekly" else f"{day}-{lang}.html"
        if not base:
            return path
        return f"{base.rstrip('/')}/{path}"

    def _get_ci_log_url(self) -> Optional[str]:
        if self.repo and self.run_id:
            return f"{self.gh_url}/{self.repo}/actions/runs/{self.run_id}"
        return None

    def _dispatch(
        self,
        subject: str,
        html_body: str,
        plain_body: Optional[str],
        recipients: List[str],
    ) -> bool:
        if not self._is_ready():
            print("⚠️ SMTP not configured, skipping email.")
            return False
        if not recipients:
            return True

        try:
            envelope = MIMEMultipart("alternative")
            envelope["Subject"] = subject
            envelope["From"] = self.sender
            envelope["To"] = ", ".join(recipients)
            plain = plain_body or "This message requires an HTML-capable mail client."
            envelope.attach(MIMEText(plain, "plain", "utf-8"))
            envelope.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(self.host, self.port) as conn:
                conn.starttls()
                conn.login(self.sender, self.secret)
                conn.send_message(envelope)
            print(f"✅ Alert dispatched: {subject} → {len(recipients)} recipient(s)")
            return True
        except Exception as e:
            print(f"❌ Alert dispatch failed: {e}")
            return False

    def _sanitize(self, text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class EmailNotifier(AlertManager):
    def _is_configured(self):
        return self._is_ready()

    def send_success(self, d, c, lang="zh"):
        return self.notify_success(d, c, lang)

    def send_empty(self, d, r, lang="zh"):
        return self.notify_empty(d, r, lang)

    def send_error(self, d, e, lang="zh"):
        return self.notify_failure(d, e, lang)


def send_success_email(d, c, lang="zh"):
    return AlertManager().notify_success(d, c, lang)


def send_empty_email(d, r="", lang="zh"):
    return AlertManager().notify_empty(d, r, lang)


def send_error_email(d, e, lang="zh"):
    return AlertManager().notify_failure(d, e, lang)
