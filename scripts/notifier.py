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
from typing import List, Optional

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    GITHUB_PAGES_URL,
    NOTIFICATION_RECIPIENTS,
    NOTIFICATION_TO_ZH,
    NOTIFICATION_TO_EN,
    use_split_notification_recipients,
)

# Email body copy: mail_locale matches report link locale (zh / en)
MAIL = {
    "zh": {
        "success_subj": "✅ 日报已就绪 - {day}",
        "success_lead": "<strong>{day}</strong> 的日报已发布。",
        "weekly_subj": "Tomato AI Weekly · {start} – {end}",
        "weekly_lead": "截至 <strong>{day}</strong> 的一周周报已发布。",
        "weekly_btn": "打开周报",
        "success_items": "条目数",
        "success_btn": "打开日报",
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
        "success_subj": "✅ Daily Ready - {day}",
        "success_lead": "The report for <strong>{day}</strong> is live.",
        "weekly_subj": "Tomato AI Weekly · {start} – {end}",
        "weekly_lead": "The weekly report ending <strong>{day}</strong> is live.",
        "weekly_btn": "Open Weekly",
        "success_items": "Total items",
        "success_btn": "Open Report",
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
    ) -> bool:
        """Send success email in mail_locale. Weekly links point at week-{day}-{lang}.html."""
        recipients = self.recipients_for_locale(mail_locale)
        if not recipients:
            return True

        loc = mail_locale if mail_locale in MAIL else "en"
        t = MAIL[loc]
        link = self._build_report_link(day, mail_locale, kind)
        safe_href = escape(link, quote=True)
        safe_visible = escape(link)
        weekly = kind == "weekly"
        if weekly:
            subj = t["weekly_subj"].format(
                start=window_start or day,
                end=window_end or day,
                day=day,
            )
        else:
            subj = t["success_subj"].format(day=day)
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
