from sqlalchemy import select

from app.extensions import db
from app.models.device import Device
from app.models.user import User


class DeviceService:

    @staticmethod
    def register(user: User, name: str, platform: str) -> Device:
        device = Device(user_id=user.id, name=name, platform=platform)
        db.session.add(device)
        db.session.commit()
        return device

    @staticmethod
    def list_for_user(user: User) -> list[Device]:
        return db.session.execute(
            select(Device)
            .where(Device.user_id == user.id)
            .order_by(Device.created_at.desc())
        ).scalars().all()

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
