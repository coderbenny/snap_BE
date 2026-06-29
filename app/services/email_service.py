import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    """Send transactional email via Resend (primary) with Google SMTP fallback."""

    # ── Public send methods ───────────────────────────────────────────────────

    @staticmethod
    def send_welcome(to_email: str) -> None:
        subject = 'Welcome to Snapit'
        html = _render_welcome(to_email)
        EmailService._send(to_email, subject, html)

    @staticmethod
    def send_subscription_confirmed(to_email: str, tier: str) -> None:
        subject = f'Your Snapit {tier.replace("_", " ").title()} plan is active'
        html = _render_subscription_confirmed(to_email, tier)
        EmailService._send(to_email, subject, html)

    @staticmethod
    def send_payment_failed(to_email: str) -> None:
        subject = 'Snapit — payment failed, action required'
        html = _render_payment_failed(to_email)
        EmailService._send(to_email, subject, html)

    # ── Dispatch: Resend → SMTP ───────────────────────────────────────────────

    @staticmethod
    def _send(to: str, subject: str, html: str) -> None:
        sent = EmailService._send_via_resend(to, subject, html)
        if not sent:
            EmailService._send_via_smtp(to, subject, html)

    @staticmethod
    def _send_via_resend(to: str, subject: str, html: str) -> bool:
        api_key = current_app.config.get('RESEND_API_KEY', '')
        if not api_key:
            logger.debug('Resend API key not configured — skipping')
            return False
        try:
            import resend
            resend.api_key = api_key
            resend.Emails.send({
                'from': current_app.config['MAIL_FROM'],
                'to': [to],
                'subject': subject,
                'html': html,
            })
            logger.info('Email sent via Resend to=%s subject=%r', to, subject)
            return True
        except Exception:
            logger.exception('Resend delivery failed for to=%s — falling back to SMTP', to)
            return False

    @staticmethod
    def _send_via_smtp(to: str, subject: str, html: str) -> None:
        host = current_app.config.get('SMTP_HOST', '')
        port = current_app.config.get('SMTP_PORT', 587)
        username = current_app.config.get('SMTP_USERNAME', '')
        password = current_app.config.get('SMTP_PASSWORD', '')
        mail_from = current_app.config.get('MAIL_FROM', '')

        if not (host and username and password):
            logger.error(
                'SMTP fallback not configured — email dropped for to=%s subject=%r', to, subject
            )
            return

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = mail_from
        msg['To'] = to
        msg.attach(MIMEText(html, 'html'))

        try:
            with smtplib.SMTP(host, port, timeout=10) as conn:
                conn.ehlo()
                conn.starttls()
                conn.login(username, password)
                conn.sendmail(mail_from, [to], msg.as_string())
            logger.info('Email sent via SMTP to=%s subject=%r', to, subject)
        except Exception:
            logger.exception('SMTP delivery also failed for to=%s subject=%r', to, subject)


# ── HTML templates ─────────────────────────────────────────────────────────────

def _base(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 16px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;border:1px solid #e5e7eb;padding:40px;">
        <tr><td>
          <p style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;">Snapit</p>
          {body}
          <p style="margin:32px 0 0;font-size:12px;color:#9ca3af;">
            You received this email because you have a Snapit account.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _render_welcome(email: str) -> str:
    body = f"""
      <h1 style="margin:0 0 12px;font-size:20px;color:#111827;">Welcome to Snapit</h1>
      <p style="margin:0 0 16px;font-size:15px;color:#374151;line-height:1.6;">
        Your account (<strong>{email}</strong>) is ready. Download the app for your platform
        and start syncing your clipboard instantly.
      </p>
      <a href="https://snapit.ink/download"
         style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
        Download Snapit
      </a>"""
    return _base('Welcome to Snapit', body)


def _render_subscription_confirmed(email: str, tier: str) -> str:
    tier_label = tier.replace('_', ' ').title()
    body = f"""
      <h1 style="margin:0 0 12px;font-size:20px;color:#111827;">
        Your {tier_label} plan is active
      </h1>
      <p style="margin:0 0 16px;font-size:15px;color:#374151;line-height:1.6;">
        Thanks for upgrading! Your <strong>{tier_label}</strong> features are now unlocked on
        all your devices. Your subscription renews automatically — manage it any time from
        the billing page.
      </p>
      <a href="https://snapit.ink/billing"
         style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
        View billing
      </a>"""
    return _base(f'Snapit {tier_label} plan active', body)


def _render_payment_failed(email: str) -> str:
    body = """
      <h1 style="margin:0 0 12px;font-size:20px;color:#b91c1c;">Payment failed</h1>
      <p style="margin:0 0 16px;font-size:15px;color:#374151;line-height:1.6;">
        We were unable to charge your payment method for your Snapit subscription renewal.
        Please update your card details to keep your plan active.
      </p>
      <a href="https://snapit.ink/billing"
         style="display:inline-block;background:#dc2626;color:#fff;text-decoration:none;
                padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
        Update payment method
      </a>"""
    return _base('Snapit — payment failed', body)
