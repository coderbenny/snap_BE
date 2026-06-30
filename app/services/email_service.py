import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    """Send transactional email via Resend (primary) with SMTP fallback."""

    @staticmethod
    def send_welcome(to_email: str) -> None:
        EmailService._send(to_email, 'You\'re in — welcome to Snapit', _render_welcome(to_email))

    @staticmethod
    def send_subscription_confirmed(to_email: str, tier: str) -> None:
        label = _tier_label(tier)
        EmailService._send(
            to_email,
            f'Your Snapit {label} plan is active',
            _render_subscription_confirmed(to_email, tier),
        )

    @staticmethod
    def send_payment_failed(to_email: str) -> None:
        EmailService._send(
            to_email,
            'Action required — Snapit payment failed',
            _render_payment_failed(to_email),
        )

    @staticmethod
    def send_password_reset(to_email: str, reset_url: str) -> None:
        EmailService._send(
            to_email,
            'Reset your Snapit password',
            _render_password_reset(to_email, reset_url),
        )

    @staticmethod
    def send_verification(to_email: str, verify_url: str) -> None:
        EmailService._send(
            to_email,
            'Confirm your email to start syncing',
            _render_verification(to_email, verify_url),
        )

    @staticmethod
    def send_expiry_warning(to_email: str, expires_at) -> None:
        date_str = expires_at.strftime('%B %d, %Y')
        EmailService._send(
            to_email,
            f'Your Snapit plan expires on {date_str}',
            _render_expiry_warning(to_email, date_str),
        )

    @staticmethod
    def send_subscription_cancelled(to_email: str) -> None:
        EmailService._send(
            to_email,
            'Your Snapit subscription has been cancelled',
            _render_subscription_cancelled(to_email),
        )

    # ── Dispatch ──────────────────────────────────────────────────────────────

    @staticmethod
    def _send(to: str, subject: str, html: str) -> None:
        if not EmailService._send_via_resend(to, subject, html):
            EmailService._send_via_smtp(to, subject, html)

    @staticmethod
    def _send_via_resend(to: str, subject: str, html: str) -> bool:
        api_key = current_app.config.get('RESEND_API_KEY', '')
        if not api_key:
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
            logger.info('email.sent provider=resend to=%s subject=%r', to, subject)
            return True
        except Exception:
            logger.exception('email.resend_failed to=%s — falling back to SMTP', to)
            return False

    @staticmethod
    def _send_via_smtp(to: str, subject: str, html: str) -> None:
        host = current_app.config.get('SMTP_HOST', '')
        port = current_app.config.get('SMTP_PORT', 587)
        username = current_app.config.get('SMTP_USERNAME', '')
        password = current_app.config.get('SMTP_PASSWORD', '')
        mail_from = current_app.config.get('MAIL_FROM', '')

        if not (host and username and password):
            logger.error('email.smtp_not_configured — dropped to=%s subject=%r', to, subject)
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
            logger.info('email.sent provider=smtp to=%s subject=%r', to, subject)
        except Exception:
            logger.exception('email.smtp_failed to=%s subject=%r', to, subject)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tier_label(tier: str) -> str:
    return {'pro': 'Pro', 'pro_ai': 'Pro + AI', 'team': 'Team'}.get(tier, tier.title())


# ── Base template ──────────────────────────────────────────────────────────────

def _base(title: str, preview: str, header_color: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#ECEEF2;-webkit-font-smoothing:antialiased;">

  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;
              color:#ECEEF2;line-height:1px;">
    {preview}&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background-color:#ECEEF2;padding:40px 16px 60px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:540px;">

          <!-- Header -->
          <tr>
            <td style="background-color:{header_color};border-radius:12px 12px 0 0;
                       padding:22px 32px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background-color:rgba(255,255,255,0.15);border-radius:7px;
                             padding:5px 12px;">
                    <span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                                 Helvetica,Arial,sans-serif;font-size:14px;font-weight:700;
                                 color:#ffffff;letter-spacing:0.8px;text-transform:uppercase;">
                      Snapit
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background-color:#ffffff;border-radius:0 0 12px 12px;
                       border:1px solid #DDE1EA;border-top:none;
                       padding:36px 36px 32px;mso-padding-alt:36px 36px 32px;">
              {body}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 8px 0;">
              <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                         Helvetica,Arial,sans-serif;font-size:12px;color:#9AA5B8;
                         line-height:1.6;text-align:center;">
                Snapit · Clipboard sync for every device
                &nbsp;·&nbsp;
                <a href="https://snapit.ink" style="color:#9AA5B8;text-decoration:underline;">
                  snapit.ink
                </a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _btn(url: str, text: str, bg: str = '#1C4ED8') -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:24px;">
      <tr>
        <td style="border-radius:8px;background-color:{bg};">
          <a href="{url}"
             style="display:inline-block;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                    Helvetica,Arial,sans-serif;font-size:14px;font-weight:600;color:#ffffff;
                    text-decoration:none;padding:12px 26px;border-radius:8px;
                    mso-padding-alt:12px 26px;">
            {text}
          </a>
        </td>
      </tr>
    </table>"""


def _h1(text: str) -> str:
    return (
        f'<h1 style="margin:0 0 10px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:21px;font-weight:700;'
        f'color:#0D1421;line-height:1.3;">{text}</h1>'
    )


def _p(text: str, small: bool = False, color: str = '#4A5568') -> str:
    size = '13px' if small else '15px'
    return (
        f'<p style="margin:0 0 14px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
        f'Helvetica,Arial,sans-serif;font-size:{size};color:{color};line-height:1.65;">'
        f'{text}</p>'
    )


def _divider() -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:24px 0 20px;">'
        '<tr><td style="border-top:1px solid #EDF0F5;font-size:0;line-height:0;">&nbsp;</td></tr>'
        '</table>'
    )


def _feature_list(items: list) -> str:
    rows = ''.join(
        f'<tr><td style="padding:5px 0;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="width:20px;vertical-align:top;padding-top:1px;">'
        f'<span style="font-size:13px;">&#10003;</span></td>'
        f'<td style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,'
        f'sans-serif;font-size:14px;color:#4A5568;line-height:1.5;">{item}</td>'
        f'</tr></table></td></tr>'
        for item in items
    )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:16px 0 0;padding:16px 18px;background:#F7F8FC;'
        f'border-radius:8px;width:100%;">'
        f'<tbody>{rows}</tbody></table>'
    )


# ── Templates ──────────────────────────────────────────────────────────────────

def _render_welcome(email: str) -> str:
    body = (
        _h1('Your clipboard vault is ready.')
        + _p(
            f'Hi <strong style="color:#0D1421;">{email}</strong> — your email is confirmed '
            'and your Snapit account is live. '
            'Download the app on your devices and anything you copy will be waiting on all of them.'
        )
        + _feature_list([
            'Copy on your Mac, paste on your Windows PC',
            'Full clipboard history — never lose something you copied',
            'End-to-end encrypted so only you can read your clips',
        ])
        + _btn('https://snapit.ink/download', 'Download Snapit')
        + _divider()
        + _p(
            'Questions? Just reply to this email — we read every one.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Welcome to Snapit',
        'Your email is confirmed. Download the app and start syncing your clipboard.',
        '#1C4ED8',
        body,
    )


def _render_verification(email: str, verify_url: str) -> str:
    body = (
        _h1('One step before you start syncing.')
        + _p(
            f'You signed up with <strong style="color:#0D1421;">{email}</strong>. '
            'Confirm that address and your account will be ready to go — '
            'this takes two seconds.'
        )
        + _btn(verify_url, 'Confirm my email')
        + _divider()
        + _p(
            '<strong style="color:#0D1421;">Link expires in 24 hours.</strong> '
            'If you didn\'t sign up for Snapit, ignore this — no account will be created.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Confirm your Snapit email',
        'Confirm your email to activate your account and start syncing.',
        '#1C4ED8',
        body,
    )


def _render_password_reset(email: str, reset_url: str) -> str:
    body = (
        _h1('Reset your password.')
        + _p(
            f'We received a password reset request for '
            f'<strong style="color:#0D1421;">{email}</strong>. '
            'Click below to choose a new password. '
            'If this wasn\'t you, your account is safe — just ignore this email.'
        )
        + _btn(reset_url, 'Choose a new password')
        + _divider()
        + _p(
            '<strong style="color:#0D1421;">This link expires in 1 hour</strong> '
            'and can only be used once. After resetting, you\'ll be signed out of all devices.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Reset your Snapit password',
        'Reset your password — this link expires in 1 hour.',
        '#374151',
        body,
    )


def _render_subscription_confirmed(email: str, tier: str) -> str:
    label = _tier_label(tier)
    features = {
        'pro': [
            'Unlimited sync across all your devices',
            '30-day clipboard history',
            'Up to 5 devices at once',
        ],
        'pro_ai': [
            'Everything in Pro',
            'OCR — pull text out of any image you copy',
            'AI-powered clipboard actions',
            'Smart auto-categorisation',
        ],
        'team': [
            'Everything in Pro',
            'Shared snippet libraries for your whole team',
            'Team management dashboard',
            'Per-seat billing, cancel anytime',
        ],
    }.get(tier, [])

    body = (
        _h1(f'{label} is active on your account.')
        + _p(
            f'Your <strong style="color:#0D1421;">{label}</strong> subscription is confirmed '
            'and your upgraded features are live across all your devices right now.'
        )
        + (_feature_list(features) if features else '')
        + _btn('https://snapit.ink/dashboard', 'Open dashboard')
        + _divider()
        + _p(
            'Your subscription renews automatically. Cancel or manage it any time from '
            '<a href="https://snapit.ink/billing" style="color:#1C4ED8;text-decoration:none;">'
            'your billing page</a>.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        f'Snapit {label} — active',
        f'Your {label} plan is live. Here\'s everything you just unlocked.',
        '#166534',
        body,
    )


def _render_payment_failed(email: str) -> str:
    body = (
        _h1('We couldn\'t process your payment.')
        + _p(
            'Your Snapit subscription renewal failed. '
            'This usually means your card was declined or expired. '
            'If it isn\'t updated within <strong style="color:#0D1421;">7 days</strong>, '
            'your account will move to the free plan and cross-device sync will stop.'
        )
        + _btn('https://snapit.ink/billing', 'Update payment method', '#B91C1C')
        + _divider()
        + _p(
            'Already updated your card? It may take a few minutes to retry. '
            'Reply to this email if you need help sorting it out.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Snapit — payment failed',
        'Action needed: we couldn\'t charge your card for your Snapit renewal.',
        '#B91C1C',
        body,
    )


def _render_expiry_warning(email: str, date_str: str) -> str:
    body = (
        _h1(f'Your plan expires on {date_str}.')
        + _p(
            'After that date your account moves to the free plan — '
            'sync between devices will stop and your history will be limited. '
            'Renew now to keep everything running without interruption.'
        )
        + _btn('https://snapit.ink/billing', 'Renew my plan')
        + _divider()
        + _p(
            'Not renewing? No action needed — your account stays active on the free plan '
            'and your existing clips are kept safe.',
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Snapit subscription expiring soon',
        f'Your Snapit plan expires {date_str}. Renew to keep syncing across devices.',
        '#92400E',
        body,
    )


def _render_subscription_cancelled(email: str) -> str:
    body = (
        _h1('Your subscription has been cancelled.')
        + _p(
            'Your Snapit subscription is cancelled and your account is now on the free plan. '
            'Your clipboard history is still there — '
            'you just won\'t sync new clips across devices.'
        )
        + _feature_list([
            'Your account and all existing clips are preserved',
            'You can resubscribe any time and pick up where you left off',
            'Local clipboard history on each device still works',
        ])
        + _btn('https://snapit.ink/billing', 'Resubscribe')
        + _divider()
        + _p(
            "Cancelled by mistake or changed your mind? Reply to this email and we'll sort it out.",
            small=True,
            color='#9AA5B8',
        )
    )
    return _base(
        'Snapit subscription cancelled',
        'Your subscription is cancelled. Your account and clips are still safe.',
        '#374151',
        body,
    )
