"""
Email Notification Module
Responsible for sending success, empty, or error notifications via email.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from html import escape
from typing import Optional
from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    NOTIFICATION_TO,
    GITHUB_PAGES_URL
)

class AlertManager:
    """Manages outgoing email alerts for the automated pipeline"""
    
    def __init__(self, **kwargs):
        """
        Initialize the alert manager
        Args:
            kwargs: Optional overrides for SMTP settings
        """
        self.host = kwargs.get('host') or SMTP_HOST
        self.port = kwargs.get('port') or SMTP_PORT
        self.sender = kwargs.get('user') or SMTP_USER
        self.secret = kwargs.get('password') or SMTP_PASSWORD
        self.recipient = kwargs.get('to_email') or NOTIFICATION_TO
        
        # CI context
        self.repo = os.getenv("GITHUB_REPOSITORY")
        self.run_id = os.getenv("GITHUB_RUN_ID")
        self.gh_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")

    def notify_success(self, day: str, count: int, lang: str = "zh") -> bool:
        """Send a success report email"""
        link = self._build_report_link(day, lang)
        safe_href = escape(link, quote=True)
        safe_visible = escape(link)
        subj = f"✅ Daily Ready - {day}"
        plain = (
            f"Tomato AI Daily — report for {day} is ready.\n"
            f"Total items: {count}\n\n"
            f"Open report: {link}\n"
        )

        html = f"""
        <html>
        <body style="font-family: sans-serif; background: #f9f9f9; padding: 20px;">
            <div style="max-width: 550px; margin: auto; background: #fff; border-radius: 10px; border: 1px solid #eee; overflow: hidden;">
                <div style="background: #2c3e50; color: #fff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">Tomato AI Daily</h2>
                </div>
                <div style="padding: 25px;">
                    <p style="font-size: 16px;">The report for <strong>{day}</strong> is live.</p>
                    <div style="background: #f0f4f8; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0; color: #34495e;">Total items: <strong>{count}</strong></p>
                    </div>
                    <a href="{safe_href}" style="display: inline-block; text-align: center; background: #3498db; color: #fff; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">Open Report</a>
                    <p style="margin-top: 18px; font-size: 12px; color: #555; word-break: break-all;">If the button does not work, copy this link:<br><a href="{safe_href}" style="color: #3498db;">{safe_visible}</a></p>
                </div>
                <div style="padding: 15px; border-top: 1px solid #eee; font-size: 11px; color: #999; text-align: center;">
                    Generated at {datetime.utcnow().strftime('%H:%M:%S')} UTC
                </div>
            </div>
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain)

    def notify_empty(self, day: str, reason: str) -> bool:
        """Send an alert when no news is found"""
        subj = f"📭 No News - {day}"
        log_url = self._get_ci_log_url()
        if log_url:
            safe_log = escape(log_url, quote=True)
            log_btn = f'<p><a href="{safe_log}">View Logs</a></p>'
            log_plain = f"\nLogs: {log_url}\n"
        else:
            log_btn = ""
            log_plain = ""
        plain = f"No updates for {day}\nReason: {reason}{log_plain}"
        reason_html = escape(reason)

        html = f"""
        <html>
        <body style="font-family: sans-serif; padding: 20px;">
            <h3>No updates for {day}</h3>
            <p>Reason: {reason_html}</p>
            {log_btn}
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain)

    def notify_failure(self, day: str, err_msg: str) -> bool:
        """Send a critical failure alert"""
        subj = f"❌ Pipeline Failed - {day}"
        log_url = self._get_ci_log_url()
        if log_url:
            safe_log = escape(log_url, quote=True)
            actions_html = f'<p><a href="{safe_log}">Check GitHub Actions</a></p>'
            actions_plain = f"\nGitHub Actions: {log_url}\n"
        else:
            actions_html = "<p>(No CI run URL in this environment.)</p>"
            actions_plain = ""

        plain = f"Pipeline failed for {day}\n\n{err_msg}{actions_plain}"
        html = f"""
        <html>
        <body style="font-family: monospace; background: #fff5f5; padding: 20px;">
            <h2 style="color: #c0392b;">Execution Error</h2>
            <p><strong>Date:</strong> {day}</p>
            <div style="background: #333; color: #0f0; padding: 15px; border-radius: 5px; overflow-x: auto;">
                <pre>{self._sanitize(err_msg)}</pre>
            </div>
            {actions_html}
        </body>
        </html>
        """
        return self._dispatch(subj, html, plain)

    def _normalize_pages_base(self, base: str) -> str:
        """Ensure GitHub Pages base is an absolute https URL."""
        base = (base or "").strip()
        if not base:
            return ""
        if base.startswith("//"):
            return "https:" + base.rstrip("/")
        if not base.startswith("http://") and not base.startswith("https://"):
            return "https://" + base.lstrip("/").rstrip("/")
        return base.rstrip("/")

    def _infer_github_pages_base(self) -> str:
        """Default project Pages URL: https://<owner>.github.io/<repo>/"""
        repo = self.repo or os.getenv("GITHUB_REPOSITORY", "")
        if not repo or "/" not in repo:
            return ""
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}"

    def _build_report_link(self, day: str, lang: str = "zh") -> str:
        """Construct absolute URL for the published HTML report (matches {day}-{lang}.html)."""
        raw_base = GITHUB_PAGES_URL or os.getenv("GITHUB_PAGES_URL", "")
        base = self._normalize_pages_base(raw_base)
        if not base:
            base = self._infer_github_pages_base()
        path = f"{day}-{lang}.html"
        if not base:
            return path
        return f"{base.rstrip('/')}/{path}"

    def _get_ci_log_url(self) -> Optional[str]:
        """Get the link to the current CI run"""
        if self.repo and self.run_id:
            return f"{self.gh_url}/{self.repo}/actions/runs/{self.run_id}"
        return None

    def _is_ready(self) -> bool:
        """Verify SMTP configuration"""
        return all([self.host, self.sender, self.secret, self.recipient])

    def _dispatch(self, subject: str, html_body: str, plain_body: Optional[str] = None) -> bool:
        """Execute the SMTP transfer (multipart/alternative: plain then HTML)."""
        if not self._is_ready():
            print("⚠️ SMTP not configured, skipping email.")
            return False
            
        try:
            envelope = MIMEMultipart('alternative')
            envelope['Subject'] = subject
            envelope['From'] = self.sender
            envelope['To'] = self.recipient
            plain = plain_body or "This message requires an HTML-capable mail client."
            envelope.attach(MIMEText(plain, 'plain', 'utf-8'))
            envelope.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            with smtplib.SMTP(self.host, self.port) as conn:
                conn.starttls()
                conn.login(self.sender, self.secret)
                conn.send_message(envelope)
            print(f"✅ Alert dispatched: {subject}")
            return True
        except Exception as e:
            print(f"❌ Alert dispatch failed: {e}")
            return False

    def _sanitize(self, text: str) -> str:
        """Escape HTML characters"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# Compatibility aliases
class EmailNotifier(AlertManager):
    def _is_configured(self): return self._is_ready()
    def send_success(self, d, c, lang="zh"): return self.notify_success(d, c, lang)
    def send_empty(self, d, r): return self.notify_empty(d, r)
    def send_error(self, d, e): return self.notify_failure(d, e)

def send_success_email(d, c, lang="zh"): return AlertManager().notify_success(d, c, lang)
def send_empty_email(d, r=""): return AlertManager().notify_empty(d, r)
def send_error_email(d, e): return AlertManager().notify_failure(d, e)
