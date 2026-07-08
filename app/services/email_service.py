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
        EmailService._send(to_email, "You're in — welcome to Snapit", _render_welcome(to_email))

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


# ── Constants ──────────────────────────────────────────────────────────────────

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _tier_label(tier: str) -> str:
    return {'pro': 'Pro', 'pro_ai': 'Pro + AI', 'team': 'Team'}.get(tier, tier.title())


# ── Base template ──────────────────────────────────────────────────────────────

def _base(title: str, preview: str, accent: str, body: str, to_email: str = '') -> str:
    """
    accent  — hex colour for the top stripe, icon badges, links, and CTA button
    body    — inner HTML between logo and footer
    """
    preview_pad = '&nbsp;&#8203;' * 20  # prevent preview text bleed
    sent_to = (
        f'<tr><td style="padding:8px 0 0;text-align:center;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:12px;color:#94A3B8;">'
        f'Sent to {to_email}</p></td></tr>'
    ) if to_email else ''

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml"
      xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="x-apple-disable-message-reformatting" />
  <meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no" />
  <title>{title}</title>
  <!--[if mso]>
  <noscript><xml><o:OfficeDocumentSettings>
    <o:PixelsPerInch>96</o:PixelsPerInch>
  </o:OfficeDocumentSettings></xml></noscript>
  <![endif]-->
  <style>
    @media only screen and (max-width:600px) {{
      .card {{ border-radius:0 !important; }}
      .card-pad {{ padding:28px 20px !important; }}
      .btn-cell a {{ display:block !important;text-align:center !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#EEF2F9;-webkit-font-smoothing:antialiased;
             -webkit-text-size-adjust:100%;mso-line-height-rule:exactly;">
  <!--[if mso | IE]><table role="presentation" border="0" cellpadding="0" cellspacing="0"
    width="100%" style="background-color:#EEF2F9;"><tr><td><![endif]-->

  <!-- Preview text -->
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
    {preview}{preview_pad}
  </div>

  <!-- Outer wrapper -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#EEF2F9;padding:48px 16px 64px;">
    <tr>
      <td align="center">
        <table role="presentation" class="card" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;max-width:560px;border-radius:14px;
                      background-color:#ffffff;
                      border:1px solid #DDE4F0;
                      box-shadow:0 2px 8px rgba(15,23,42,0.06);">

          <!-- Accent stripe -->
          <tr>
            <td style="height:4px;background-color:{accent};
                       border-radius:13px 13px 0 0;font-size:0;line-height:0;">&nbsp;</td>
          </tr>

          <!-- Logo bar -->
          <tr>
            <td style="padding:22px 32px 20px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0"
                     width="100%">
                <tr>
                  <td>
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <!-- Clipboard icon box -->
                        <td style="background-color:{accent};border-radius:7px;
                                   width:28px;height:28px;text-align:center;
                                   vertical-align:middle;padding:0;">
                          <span style="font-family:{_FONT};font-size:14px;
                                       color:#ffffff;line-height:28px;display:block;">
                            &#9635;
                          </span>
                        </td>
                        <td style="padding-left:9px;vertical-align:middle;">
                          <span style="font-family:{_FONT};font-size:15px;font-weight:700;
                                       color:#0F172A;letter-spacing:0.5px;">
                            Snapit
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Thin rule under logo -->
          <tr>
            <td style="padding:0 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="border-top:1px solid #EEF2F9;font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body content -->
          <tr>
            <td class="card-pad" style="padding:32px 32px 36px;">
              {body}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:0 32px 28px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="border-top:1px solid #EEF2F9;font-size:0;line-height:0;
                             padding-bottom:20px;">&nbsp;</td>
                </tr>
                <tr>
                  <td>
                    <p style="margin:0;font-family:{_FONT};font-size:12px;color:#94A3B8;
                               line-height:1.7;text-align:center;">
                      &copy; 2025 Snapit &nbsp;&middot;&nbsp;
                      <a href="https://snapit.ink" style="color:#94A3B8;text-decoration:underline;">
                        Website</a>&nbsp;&middot;&nbsp;
                      <a href="https://snapit.ink/dashboard" style="color:#94A3B8;text-decoration:underline;">
                        Dashboard</a>&nbsp;&middot;&nbsp;
                      <a href="mailto:support@snapit.ink" style="color:#94A3B8;text-decoration:underline;">
                        Support</a>
                    </p>
                  </td>
                </tr>
                {sent_to}
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
  <!--[if mso | IE]></td></tr></table><![endif]-->
</body>
</html>"""


# ── Component helpers ──────────────────────────────────────────────────────────

def _icon_badge(symbol: str, accent: str) -> str:
    """Large icon badge — a colored rounded box with a symbol, centred above the heading."""
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:20px;">
      <tr>
        <td style="background-color:{accent}1A;border-radius:14px;
                   width:52px;height:52px;text-align:center;vertical-align:middle;">
          <span style="font-family:{_FONT};font-size:24px;line-height:52px;
                       color:{accent};display:block;">{symbol}</span>
        </td>
      </tr>
    </table>"""


def _h1(text: str, accent: str = '#0F172A') -> str:
    return (
        f'<h1 style="margin:0 0 12px;font-family:{_FONT};font-size:22px;'
        f'font-weight:700;color:#0F172A;line-height:1.3;">{text}</h1>'
    )


def _p(text: str, small: bool = False, color: str = '#475569') -> str:
    size = '13px' if small else '15px'
    return (
        f'<p style="margin:0 0 16px;font-family:{_FONT};font-size:{size};'
        f'color:{color};line-height:1.7;">{text}</p>'
    )


def _email_pill(email: str, accent: str) -> str:
    """Inline styled badge showing the recipient email."""
    return (
        f'<span style="display:inline-block;background-color:{accent}15;'
        f'border:1px solid {accent}30;border-radius:5px;'
        f'padding:2px 8px;font-family:{_FONT};font-size:13px;'
        f'font-weight:600;color:{accent};">{email}</span>'
    )


def _btn(url: str, text: str, accent: str) -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"
           style="margin:24px 0 4px;">
      <tr>
        <td class="btn-cell" style="border-radius:9px;background-color:{accent};">
          <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
            xmlns:w="urn:schemas-microsoft-com:office:word"
            href="{url}" style="height:46px;v-text-anchor:middle;width:200px;"
            arcsize="20%" stroke="f" fillcolor="{accent}">
            <w:anchorlock/>
            <center style="color:#ffffff;font-family:sans-serif;font-size:14px;
                           font-weight:bold;">{text}</center>
          </v:roundrect><![endif]-->
          <!--[if !mso]><!-->
          <a href="{url}"
             style="display:inline-block;font-family:{_FONT};font-size:14px;
                    font-weight:600;color:#ffffff;text-decoration:none;
                    padding:13px 32px;border-radius:9px;
                    mso-hide:all;">
            {text}
          </a>
          <!--<![endif]-->
        </td>
      </tr>
    </table>"""


def _feature_list(items: list, accent: str = '#1D4ED8') -> str:
    rows = ''.join(
        f'<tr>'
        f'<td style="width:24px;vertical-align:top;padding:6px 8px 6px 0;">'
        f'<div style="width:18px;height:18px;background-color:{accent}18;'
        f'border-radius:50%;text-align:center;line-height:18px;">'
        f'<span style="font-family:{_FONT};font-size:10px;font-weight:700;'
        f'color:{accent};">&#10003;</span>'
        f'</div></td>'
        f'<td style="padding:6px 0;font-family:{_FONT};font-size:14px;'
        f'color:#334155;line-height:1.5;">{item}</td>'
        f'</tr>'
        for item in items
    )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
        f' style="margin:20px 0;padding:16px 18px;background:#F8FAFC;'
        f'border-radius:10px;border:1px solid #E2E8F0;width:100%;">'
        f'<tbody>{rows}</tbody></table>'
    )


def _security_box(text: str) -> str:
    """Gray callout box for security-relevant notes."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
        f' style="margin:20px 0 0;width:100%;">'
        f'<tr><td style="background-color:#F1F5F9;border-radius:9px;'
        f'border-left:3px solid #CBD5E1;padding:13px 16px;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:13px;'
        f'color:#475569;line-height:1.65;">'
        f'<span style="font-weight:600;color:#334155;">&#128274;&nbsp; Security note&nbsp;&nbsp;</span>'
        f'{text}</p>'
        f'</td></tr></table>'
    )


def _warning_box(text: str, accent: str) -> str:
    """Coloured callout box for warnings and important notices."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
        f' style="margin:20px 0 0;width:100%;">'
        f'<tr><td style="background-color:{accent}0F;border-radius:9px;'
        f'border-left:3px solid {accent};padding:13px 16px;">'
        f'<p style="margin:0;font-family:{_FONT};font-size:13px;'
        f'color:#475569;line-height:1.65;">{text}</p>'
        f'</td></tr></table>'
    )


def _divider() -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"'
        ' style="margin:24px 0;">'
        '<tr><td style="border-top:1px solid #EEF2F9;font-size:0;line-height:0;">&nbsp;</td></tr>'
        '</table>'
    )


# ── Email templates ────────────────────────────────────────────────────────────

def _render_verification(email: str, verify_url: str) -> str:
    ACCENT = '#4F46E5'
    body = (
        _icon_badge('&#9993;', ACCENT)
        + _h1('Confirm your email address')
        + _p(
            f'You signed up with {_email_pill(email, ACCENT)}. '
            'Tap the button below to verify that address and activate your account — '
            'it only takes a second.'
        )
        + _btn(verify_url, 'Verify my email', ACCENT)
        + _p(
            f'Or copy and paste this link into your browser:<br/>'
            f'<span style="font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;'
            f'color:#64748B;word-break:break-all;">{verify_url}</span>',
            small=True,
            color='#64748B',
        )
        + _security_box(
            'This link expires in <strong style="color:#334155;">24 hours</strong> and works once. '
            "If you didn't create a Snapit account, you can safely ignore this email — "
            'no account will be created.'
        )
    )
    return _base(
        'Confirm your Snapit email',
        'Verify your email address to activate your Snapit account and start syncing.',
        ACCENT,
        body,
        email,
    )


def _render_welcome(email: str) -> str:
    ACCENT = '#0EA5E9'
    body = (
        _icon_badge('&#9733;', ACCENT)
        + _h1("You're all set. Welcome to Snapit.")
        + _p(
            f'Hi {_email_pill(email, ACCENT)} — your email is confirmed and your account is live. '
            'Install the app on your Mac, phone, or both and everything you copy '
            'will be waiting on all of them instantly.'
        )
        + _feature_list(
            [
                '<strong>Copy anywhere, paste everywhere</strong> — real-time clipboard sync',
                '<strong>Never lose a clip</strong> — full history with instant search',
                '<strong>End-to-end encrypted</strong> — only you can read your clipboard',
                '<strong>File transfer</strong> — send files between devices over a secure relay',
            ],
            ACCENT,
        )
        + _btn('https://snapit.ink/download', 'Download the app', ACCENT)
        + _divider()
        + _p(
            'Got questions? Reply to this email — we read every one.',
            small=True,
            color='#94A3B8',
        )
    )
    return _base(
        'Welcome to Snapit',
        'Your account is confirmed. Download the app and start syncing your clipboard across every device.',
        ACCENT,
        body,
        email,
    )


def _render_password_reset(email: str, reset_url: str) -> str:
    ACCENT = '#7C3AED'
    body = (
        _icon_badge('&#128273;', ACCENT)
        + _h1('Reset your password')
        + _p(
            f'We received a password reset request for {_email_pill(email, ACCENT)}. '
            'Click the button below to choose a new password. '
            "If this wasn't you, your account is safe — just ignore this email."
        )
        + _btn(reset_url, 'Choose a new password', ACCENT)
        + _p(
            f'Or copy and paste this link into your browser:<br/>'
            f'<span style="font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;'
            f'color:#64748B;word-break:break-all;">{reset_url}</span>',
            small=True,
            color='#64748B',
        )
        + _security_box(
            'This link expires in <strong style="color:#334155;">1 hour</strong> and can only be '
            'used once. After resetting, you will be signed out of all devices. '
            "If you didn't request this, no action is needed."
        )
    )
    return _base(
        'Reset your Snapit password',
        'Reset your Snapit password — this link expires in 1 hour.',
        ACCENT,
        body,
        email,
    )


def _render_subscription_confirmed(email: str, tier: str) -> str:
    ACCENT = '#059669'
    label = _tier_label(tier)
    features = {
        'pro': [
            '<strong>Cross-device sync</strong> — all your devices, always in sync',
            '<strong>Unlimited clipboard history</strong> — never limited again',
            '<strong>Up to 5 devices</strong> — Mac, Windows, Android, and more',
            '<strong>File transfer</strong> — send files between any two devices instantly',
            '<strong>Priority support</strong> — get to the front of the queue',
        ],
        'pro_ai': [
            '<strong>Everything in Pro</strong> — all Pro features included',
            '<strong>OCR</strong> — pull text straight out of any image you copy',
            '<strong>AI clipboard actions</strong> — translate, summarise, reformat in one tap',
            '<strong>Smart auto-categorisation</strong> — clips organised automatically',
        ],
        'team': [
            '<strong>Everything in Pro</strong> — all Pro features included',
            '<strong>Shared snippet library</strong> — clips your whole team can access',
            '<strong>Team management</strong> — invite, remove, and manage members',
            '<strong>Per-seat billing</strong> — only pay for who\'s on the team',
        ],
    }.get(tier, [])

    body = (
        _icon_badge('&#10003;', ACCENT)
        + _h1(f'Your {label} plan is active.')
        + _p(
            f'Your <strong style="color:#0F172A;">{label}</strong> subscription is confirmed. '
            'Your upgraded features are live across all your devices right now — '
            'no restart needed.'
        )
        + (_feature_list(features, ACCENT) if features else '')
        + _btn('https://snapit.ink/dashboard', 'Open your dashboard', ACCENT)
        + _divider()
        + _p(
            'Your subscription renews automatically. Cancel or manage it any time from '
            f'<a href="https://snapit.ink/billing" style="color:{ACCENT};text-decoration:none;'
            f'font-weight:600;">your billing page</a>. '
            'Questions? Reply to this email.',
            small=True,
            color='#94A3B8',
        )
    )
    return _base(
        f'Snapit {label} — active',
        f"Your {label} plan is live. Here's everything you just unlocked.",
        ACCENT,
        body,
        email,
    )


def _render_payment_failed(email: str) -> str:
    ACCENT = '#DC2626'
    body = (
        _icon_badge('&#9888;', ACCENT)
        + _h1("We couldn't process your payment.")
        + _p(
            'Your Snapit subscription renewal failed — your card was declined or has expired. '
            'Update your payment method to keep your plan active.'
        )
        + _warning_box(
            f'<strong style="color:#7F1D1D;">If not resolved within 7 days</strong>, '
            'your account will move to the free plan and cross-device sync will stop.',
            ACCENT,
        )
        + _btn('https://snapit.ink/billing', 'Update payment method', ACCENT)
        + _divider()
        + _p(
            "Already updated your card? It may take a few minutes to retry. "
            "Reply to this email if you need help sorting it out.",
            small=True,
            color='#94A3B8',
        )
    )
    return _base(
        'Snapit — payment failed',
        "Action needed: we couldn't charge your card for your Snapit renewal.",
        ACCENT,
        body,
        email,
    )


def _render_expiry_warning(email: str, date_str: str) -> str:
    ACCENT = '#D97706'
    body = (
        _icon_badge('&#9201;', ACCENT)
        + _h1(f'Your plan expires on {date_str}.')
        + _p(
            "Your Snapit subscription is expiring soon. After that date your account "
            "moves to the free plan — sync between devices will stop and your history "
            "will be limited to 100 items."
        )
        + _warning_box(
            'Renew now to keep everything running without interruption. '
            'All your clips, history, and settings are preserved.',
            ACCENT,
        )
        + _btn('https://snapit.ink/billing', 'Renew my plan', ACCENT)
        + _divider()
        + _p(
            "Not renewing? No action needed — your account stays active on the free plan "
            "and your existing clips are kept safe.",
            small=True,
            color='#94A3B8',
        )
    )
    return _base(
        'Snapit subscription expiring soon',
        f'Your Snapit plan expires {date_str}. Renew to keep syncing across devices.',
        ACCENT,
        body,
        email,
    )


def _render_subscription_cancelled(email: str) -> str:
    ACCENT = '#64748B'
    body = (
        _icon_badge('&#8594;', ACCENT)
        + _h1('Your subscription has been cancelled.')
        + _p(
            'Your Snapit subscription is now cancelled and your account has moved to '
            'the free plan. Your clipboard history is still there — '
            "you just won't sync new clips across devices."
        )
        + _feature_list(
            [
                '<strong>Your account is preserved</strong> — all your existing clips are safe',
                '<strong>Local history still works</strong> — clipboard history on each device continues',
                '<strong>Resubscribe any time</strong> — pick up exactly where you left off',
            ],
            ACCENT,
        )
        + _btn('https://snapit.ink/billing', 'Resubscribe', ACCENT)
        + _divider()
        + _p(
            "Cancelled by mistake or changed your mind? Reply to this email and we'll sort it out right away.",
            small=True,
            color='#94A3B8',
        )
    )
    return _base(
        'Snapit subscription cancelled',
        'Your subscription is cancelled. Your account and all your clips are still safe.',
        ACCENT,
        body,
        email,
    )
