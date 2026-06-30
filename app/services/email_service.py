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
        EmailService._send(to_email, 'Welcome to Snapit', _render_welcome(to_email))

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
            'Verify your Snapit email address',
            _render_verification(to_email, verify_url),
        )

    @staticmethod
    def send_expiry_warning(to_email: str, expires_at) -> None:
        from datetime import timezone
        date_str = expires_at.strftime('%B %d, %Y')
        EmailService._send(
            to_email,
            'Your Snapit subscription expires in 3 days',
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

def _base(title: str, preview: str, body: str) -> str:
    """
    Table-based email-client-safe wrapper.
    `preview` is the hidden preheader text shown in inbox snippets.
    """
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{title}</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#F0F4F8;-webkit-font-smoothing:antialiased;">

  <!-- Preheader -->
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;color:#F0F4F8;line-height:1px;">
    {preview}&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;&zwnj;&nbsp;&#8199;
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background-color:#F0F4F8;padding:40px 16px 64px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:560px;">

          <!-- Logo row -->
          <tr>
            <td style="padding:0 0 20px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background-color:#1A56DB;border-radius:10px;padding:8px 14px;">
                    <span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                                 font-size:15px;font-weight:700;color:#ffffff;letter-spacing:0.5px;">
                      Snapit
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body card -->
          <tr>
            <td style="background-color:#ffffff;border-radius:14px;border:1px solid #DDE3EE;
                       padding:40px 40px 36px;mso-padding-alt:40px 40px 36px;">
              {body}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 8px 0;">
              <p style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                         font-size:12px;color:#8A9BB5;line-height:1.6;text-align:center;">
                You received this because you have a Snapit account.
                &nbsp;·&nbsp;
                <a href="https://snapit.ink" style="color:#8A9BB5;text-decoration:underline;">snapit.ink</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _btn(url: str, text: str, color: str = '#1A56DB') -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:28px;">
      <tr>
        <td style="border-radius:8px;background-color:{color};">
          <a href="{url}"
             style="display:inline-block;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                    Helvetica,Arial,sans-serif;font-size:14px;font-weight:600;color:#ffffff;
                    text-decoration:none;padding:13px 28px;border-radius:8px;
                    mso-padding-alt:13px 28px;">
            {text}
          </a>
        </td>
      </tr>
    </table>"""


def _h1(text: str) -> str:
    return f"""<h1 style="margin:0 0 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                           Helvetica,Arial,sans-serif;font-size:22px;font-weight:700;
                           color:#0D1B35;line-height:1.3;">{text}</h1>"""


def _p(text: str, extra: str = '') -> str:
    return f"""<p style="margin:0 0 14px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                          Helvetica,Arial,sans-serif;font-size:15px;color:#3A4E6B;
                          line-height:1.65;{extra}">{text}</p>"""


def _divider() -> str:
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0 0;"><tr><td style="border-top:1px solid #EBF0F8;font-size:0;line-height:0;">&nbsp;</td></tr></table>'


def _icon_row(emoji: str, bg: str = '#EEF4FF') -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="background:{bg};border-radius:12px;padding:14px;font-size:28px;
                   line-height:1;text-align:center;width:56px;">
          {emoji}
        </td>
      </tr>
    </table>"""


# ── Templates ──────────────────────────────────────────────────────────────────

def _render_welcome(email: str) -> str:
    body = (
        _icon_row('👋')
        + _h1('Welcome to Snapit')
        + _p(f'Your account <strong style="color:#0D1B35;">{email}</strong> is ready. '
             'Download the app for your platform and your clipboard will start syncing instantly '
             'across all your devices.')
        + _p('Copy once — paste anywhere.')
        + _btn('https://snapit.ink/download', 'Download Snapit')
        + _divider()
        + _p('Need help? Reply to this email or visit '
             '<a href="https://snapit.ink" style="color:#1A56DB;text-decoration:none;">snapit.ink</a>.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Welcome to Snapit',
        'Your clipboard vault is ready — download the app and start syncing.',
        body,
    )


def _render_subscription_confirmed(email: str, tier: str) -> str:
    label = _tier_label(tier)
    features = {
        'pro': ['Unlimited sync across all devices', '30-day clipboard history', 'Up to 5 devices'],
        'pro_ai': ['Everything in Pro', 'OCR text extraction from images', 'AI-powered clipboard actions', 'Smart categorisation'],
        'team': ['Everything in Pro', 'Shared snippet libraries', 'Team management dashboard', 'Per-seat billing'],
    }.get(tier, [])

    feature_rows = ''.join(
        f'<tr><td style="padding:4px 0;">'
        f'<span style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;'
        f'font-size:14px;color:#3A4E6B;">✓&nbsp; {f}</span></td></tr>'
        for f in features
    )

    feature_table = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:16px 0 0;border-left:3px solid #1A56DB;padding-left:16px;">'
        f'<tbody>{feature_rows}</tbody></table>'
    ) if features else ''

    body = (
        _icon_row('🎉', '#EEFBF4')
        + _h1(f'Your {label} plan is active')
        + _p(f'Thanks for upgrading! Your <strong style="color:#0D1B35;">{label}</strong> features '
             'are now unlocked on all your devices.')
        + feature_table
        + _btn('https://snapit.ink/dashboard', 'Go to dashboard')
        + _divider()
        + _p('Your subscription renews automatically. Manage it any time from '
             '<a href="https://snapit.ink/billing" style="color:#1A56DB;text-decoration:none;">billing</a>.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        f'Snapit {label} — active',
        f'Your {label} plan is now active. Here\'s what you unlocked.',
        body,
    )


def _render_payment_failed(email: str) -> str:
    body = (
        _icon_row('⚠️', '#FFF5F5')
        + _h1('Payment failed')
        + _p('We couldn\'t charge your payment method for your Snapit subscription renewal. '
             'Your account will be downgraded if payment isn\'t updated within <strong style="color:#0D1B35;">7 days</strong>.')
        + _btn('https://snapit.ink/billing', 'Update payment method', '#DC2626')
        + _divider()
        + _p('If you believe this is an error, contact your card issuer or reply to this email.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Snapit — payment failed',
        'Action required: we couldn\'t process your Snapit payment.',
        body,
    )


def _render_password_reset(email: str, reset_url: str) -> str:
    body = (
        _icon_row('🔑')
        + _h1('Reset your password')
        + _p(f'We received a request to reset the password for '
             f'<strong style="color:#0D1B35;">{email}</strong>. '
             'Click the button below to choose a new one.')
        + _btn(reset_url, 'Reset password')
        + _divider()
        + _p('<strong style="color:#0D1B35;">This link expires in 1 hour.</strong> '
             'If you didn\'t request a password reset, you can safely ignore this email — '
             'your password has not been changed.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Reset your Snapit password',
        'Reset your Snapit password — this link expires in 1 hour.',
        body,
    )


def _render_verification(email: str, verify_url: str) -> str:
    body = (
        _icon_row('✉️')
        + _h1('Verify your email address')
        + _p(f'Please confirm that <strong style="color:#0D1B35;">{email}</strong> is your '
             'Snapit email address by clicking the button below.')
        + _btn(verify_url, 'Verify email address')
        + _divider()
        + _p('<strong style="color:#0D1B35;">This link expires in 24 hours.</strong> '
             'If you didn\'t create a Snapit account, you can ignore this email.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Verify your Snapit email',
        'Confirm your email address to finish setting up Snapit.',
        body,
    )


def _render_expiry_warning(email: str, date_str: str) -> str:
    body = (
        _icon_row('⏰', '#FFFBEB')
        + _h1('Your subscription expires soon')
        + _p(f'Your Snapit subscription expires on '
             f'<strong style="color:#0D1B35;">{date_str}</strong> — that\'s in 3 days. '
             'After it expires your account will revert to the free plan and sync will pause.')
        + _btn('https://snapit.ink/billing', 'Manage subscription')
        + _divider()
        + _p('If you\'d like to cancel instead, visit '
             '<a href="https://snapit.ink/billing" style="color:#1A56DB;text-decoration:none;">billing</a> '
             'and cancel before the renewal date. No charges will be made after cancellation.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Snapit subscription expiring soon',
        f'Your Snapit subscription expires on {date_str} — renew to keep syncing.',
        body,
    )


def _render_subscription_cancelled(email: str) -> str:
    body = (
        _icon_row('📋', '#F8F9FB')
        + _h1('Your subscription has been cancelled')
        + _p('Your Snapit subscription has been cancelled and your account has been moved to '
             'the free plan. Your clipboard history is still accessible — you just won\'t sync '
             'new clips across devices until you resubscribe.')
        + _btn('https://snapit.ink/billing', 'Resubscribe')
        + _divider()
        + _p('Changed your mind? You can resubscribe any time from the billing page. '
             'If you cancelled by mistake, reply to this email and we\'ll help.',
             'margin:20px 0 0;font-size:13px;color:#8A9BB5;')
    )
    return _base(
        'Snapit subscription cancelled',
        'Your Snapit subscription has been cancelled — your data is safe.',
        body,
    )
