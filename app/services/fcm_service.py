import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def init_fcm() -> bool:
    """Initialize Firebase Admin SDK from FIREBASE_CREDENTIALS env var (path to JSON).
    Returns True if initialised, False if credentials not configured (non-fatal)."""
    global _initialized
    if _initialized:
        return True

    creds_path = os.environ.get('FIREBASE_CREDENTIALS', '')
    if not creds_path:
        logger.info('FCM disabled: FIREBASE_CREDENTIALS not set')
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info('FCM initialised')
        return True
    except Exception:
        logger.exception('FCM init failed')
        return False


def send_transfer_incoming(
    fcm_token: str,
    session_id: str,
    file_name: str,
    file_size: int,
    sender_device_name: str,
    mime_type: str = 'application/octet-stream',
    target_device_id: str = '',
) -> None:
    """Send a data-only FCM push for an incoming transfer.
    Silently no-ops if Firebase is not initialised or the send fails."""
    if not _initialized:
        return
    try:
        from firebase_admin import messaging
        message = messaging.Message(
            data={
                'type': 'transfer_incoming',
                'session_id': session_id,
                'file_name': file_name,
                'file_size': str(file_size),
                'sender_device_name': sender_device_name,
                'mime_type': mime_type,
                'target_device_id': target_device_id,
            },
            android=messaging.AndroidConfig(priority='high'),
            token=fcm_token,
        )
        messaging.send(message)
    except Exception:
        logger.exception('FCM send failed for session %s', session_id)
