from sqlalchemy import func, select, update

from app.extensions import db
from app.models.clipboard_item import ClipboardItem
from app.models.device import Device
from app.models.user import User
from app.utils.time import from_unix_ms, utcnow


class SyncService:

    @staticmethod
    def pull(
        user: User,
        since: int | None,
        limit: int,
    ) -> tuple[list[ClipboardItem], bool]:
        """Return items changed since a Unix ms timestamp.

        Includes soft-deleted items (deleted_at set) so clients can reconcile
        local state. Fetches limit+1 to detect whether more pages exist.

        Cursor stability: Python datetimes have microsecond precision but the
        cursor is transmitted as Unix-ms (millisecond precision). If a page
        boundary falls inside a group of items that all share the same
        synced_at, truncating to ms and back produces a datetime slightly
        before the original, causing the same items to satisfy the > filter
        again → infinite loop on the client. Fix: when has_more is True,
        extend the page to include ALL remaining items that share the last
        item's synced_at, so the cursor always lands on a fresh timestamp.
        """
        query = select(ClipboardItem).where(ClipboardItem.user_id == user.id)

        if since is not None:
            query = query.where(ClipboardItem.synced_at > from_unix_ms(since))

        query = query.order_by(ClipboardItem.synced_at.asc(), ClipboardItem.id.asc()).limit(limit + 1)
        items = list(db.session.execute(query).scalars().all())

        has_more = len(items) > limit
        page = items[:limit]

        # Extend the page to include all remaining items with the same
        # synced_at as the last item, so no timestamp group is split across
        # pages and the cursor always points past a complete group.
        if has_more and page:
            boundary_ts = page[-1].synced_at
            boundary_ids = {i.id for i in page}
            extra = db.session.execute(
                select(ClipboardItem)
                .where(
                    ClipboardItem.user_id == user.id,
                    ClipboardItem.synced_at == boundary_ts,
                    ClipboardItem.id.notin_(boundary_ids),
                )
                .order_by(ClipboardItem.id.asc())
            ).scalars().all()
            page = page + list(extra)

        return page, has_more

    @staticmethod
    def push(user: User, items_data: list[dict]) -> int:
        """Batch upsert clipboard items. Returns count accepted.

        Existing items (same id + user_id) are updated; new items are inserted.
        client_created_at is immutable once set — never overwritten on update.
        """
        now = utcnow()
        ids = [item['id'] for item in items_data]

        # Fetch ALL records with matching IDs (no user filter) so we can detect
        # UUID collisions across users and skip them instead of crashing on a
        # primary-key IntegrityError.
        all_existing = {
            record.id: record
            for record in db.session.execute(
                select(ClipboardItem).where(ClipboardItem.id.in_(ids))
            ).scalars().all()
        }

        for item_data in items_data:
            record = all_existing.get(item_data['id'])
            if record:
                if record.user_id != user.id:
                    continue  # ID owned by another user — skip silently
                record.ciphertext = item_data['ciphertext']
                record.iv = item_data['iv']
                record.content_type = item_data['content_type']
                record.tags = item_data.get('tags')
                record.pinned = item_data.get('pinned', False)
                record.synced_at = now
            else:
                db.session.add(ClipboardItem(
                    id=item_data['id'],
                    user_id=user.id,
                    device_id=item_data.get('device_id'),
                    ciphertext=item_data['ciphertext'],
                    iv=item_data['iv'],
                    content_type=item_data['content_type'],
                    tags=item_data.get('tags'),
                    pinned=item_data.get('pinned', False),
                    client_created_at=item_data['client_created_at'],
                    synced_at=now,
                ))

        db.session.commit()
        return len(items_data)

    @staticmethod
    def soft_delete(user: User, ids: list[str]) -> int:
        """Soft-delete items by ID list. Updates synced_at so other devices pick up the deletion.

        Returns count of items actually deleted (already-deleted items are excluded).
        """
        now = utcnow()
        result = db.session.execute(
            update(ClipboardItem)
            .where(
                ClipboardItem.id.in_(ids),
                ClipboardItem.user_id == user.id,
                ClipboardItem.deleted_at.is_(None),
            )
            .values(deleted_at=now, synced_at=now)
            .execution_options(synchronize_session=False)
        )
        db.session.commit()
        return result.rowcount

    @staticmethod
    def count_clips(user: User) -> int:
        """Return the number of non-deleted clips for the user."""
        result = db.session.execute(
            select(func.count()).select_from(ClipboardItem).where(
                ClipboardItem.user_id == user.id,
                ClipboardItem.deleted_at.is_(None),
            )
        ).scalar()
        return result or 0

    @staticmethod
    def update_device_last_seen(user: User, device_id: str | None) -> None:
        if not device_id:
            return

        device = db.session.execute(
            select(Device).where(
                Device.id == device_id,
                Device.user_id == user.id,
            )
        ).scalar_one_or_none()

        if device:
            device.last_seen_at = utcnow()
            db.session.commit()
