from sqlalchemy import select

from app.extensions import db
from app.models.device import Device
from app.models.user import User
from app.utils.time import utcnow


class DeviceService:

    @staticmethod
    def register(
        user: User,
        device_id: str,
        name: str,
        platform: str,
        app_version: str | None = None,
    ) -> Device:
        device = db.session.execute(
            select(Device).where(Device.id == device_id, Device.user_id == user.id)
        ).scalar_one_or_none()

        if device:
            device.name = name
            device.platform = platform
            device.app_version = app_version
            device.last_seen_at = utcnow()
        else:
            device = Device(
                id=device_id,
                user_id=user.id,
                name=name,
                platform=platform,
                app_version=app_version,
            )
            db.session.add(device)

        db.session.commit()
        return device

    @staticmethod
    def list_for_user(user: User) -> list[Device]:
        return db.session.execute(
            select(Device)
            .where(Device.user_id == user.id)
            .order_by(Device.last_seen_at.desc())
        ).scalars().all()

    @staticmethod
    def update_fcm_token(user: User, device_id: str, token: str) -> bool:
        device = db.session.execute(
            select(Device).where(Device.id == device_id, Device.user_id == user.id)
        ).scalar_one_or_none()
        if not device:
            return False
        device.fcm_token = token
        db.session.commit()
        return True

    @staticmethod
    def delete(user: User, device_id: str) -> bool:
        device = db.session.execute(
            select(Device).where(Device.id == device_id, Device.user_id == user.id)
        ).scalar_one_or_none()

        if not device:
            return False

        db.session.delete(device)
        db.session.commit()
        return True
