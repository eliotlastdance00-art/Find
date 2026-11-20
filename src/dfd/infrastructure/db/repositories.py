"""SQLAlchemy implementations of the repository ports."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from dfd.domain import errors
from dfd.domain.entities import MediaType, Role, Scan, ScanStatus, User, Verdict
from dfd.domain.ports import ScanFilter
from dfd.infrastructure.db.models import ScanRow, UserRow
from dfd.infrastructure.db.session import SessionFactory

_ACTIVE = [s.value for s in ScanStatus if s.is_active]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _user(row: UserRow) -> User:
    return User(row.id, row.username, row.password_hash, Role(row.role), _aware(row.created_at))


def _scan(row: ScanRow) -> Scan:
    return Scan(
        id=row.id,
        user_id=row.user_id,
        filename=row.filename,
        stored_name=row.stored_name,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        media_type=MediaType(row.media_type),
        status=ScanStatus(row.status),
        created_at=_aware(row.created_at),
        progress=row.progress,
        verdict=Verdict(row.verdict) if row.verdict else None,
        prob_fake=row.prob_fake,
        visual_prob=row.visual_prob,
        audio_prob=row.audio_prob,
        details=dict(row.details or {}),
        error=row.error,
        duration_ms=row.duration_ms,
        finished_at=_aware(row.finished_at) if row.finished_at else None,
    )


def _fill(row: ScanRow, scan: Scan) -> ScanRow:
    row.user_id = scan.user_id
    row.filename = scan.filename
    row.stored_name = scan.stored_name
    row.sha256 = scan.sha256
    row.size_bytes = scan.size_bytes
    row.media_type = scan.media_type.value
    row.status = scan.status.value
    row.progress = scan.progress
    row.verdict = scan.verdict.value if scan.verdict else None
    row.prob_fake = scan.prob_fake
    row.visual_prob = scan.visual_prob
    row.audio_prob = scan.audio_prob
    row.details = scan.details
    row.error = scan.error
    row.duration_ms = scan.duration_ms
    row.created_at = scan.created_at
    row.finished_at = scan.finished_at
    return row


class SqlUserRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def add(self, username: str, password_hash: str, role: Role) -> User:
        row = UserRow(
            username=username,
            username_key=username.lower(),
            password_hash=password_hash,
            role=role.value,
            created_at=datetime.now(UTC),
        )
        with self._sessions() as session:
            session.add(row)
            try:
                session.commit()
            except IntegrityError as error:
                raise errors.UsernameTaken() from error
            return _user(row)

    def get(self, user_id: int) -> User | None:
        with self._sessions() as session:
            row = session.get(UserRow, user_id)
            return _user(row) if row else None

    def get_by_username(self, username: str) -> User | None:
        with self._sessions() as session:
            row = session.scalar(select(UserRow).where(UserRow.username_key == username.lower()))
            return _user(row) if row else None

    def count(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count()).select_from(UserRow)) or 0)


class SqlScanRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def add(self, scan: Scan) -> None:
        with self._sessions() as session:
            session.add(_fill(ScanRow(id=scan.id), scan))
            session.commit()

    def get(self, scan_id: str) -> Scan | None:
        with self._sessions() as session:
            row = session.get(ScanRow, scan_id)
            return _scan(row) if row else None

    def update(self, scan: Scan) -> None:
        with self._sessions() as session:
            row = session.get(ScanRow, scan.id)
            if row is None:
                return
            _fill(row, scan)
            session.commit()

    def delete(self, scan_id: str) -> None:
        with self._sessions() as session:
            row = session.get(ScanRow, scan_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def search(self, user_id: int | None, criteria: ScanFilter) -> tuple[list[Scan], int]:
        conditions = []
        if user_id is not None:
            conditions.append(ScanRow.user_id == user_id)
        if criteria.verdict is not None:
            conditions.append(ScanRow.verdict == criteria.verdict.value)
        if criteria.media_type is not None:
            conditions.append(ScanRow.media_type == criteria.media_type.value)
        if criteria.query:
            escaped = criteria.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(ScanRow.filename.ilike(f"%{escaped}%", escape="\\"))
        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(ScanRow).where(*conditions))
            rows = session.scalars(
                select(ScanRow)
                .where(*conditions)
                .order_by(ScanRow.created_at.desc())
                .limit(criteria.limit)
                .offset(criteria.offset)
            ).all()
            return [_scan(r) for r in rows], int(total or 0)

    def stats(self, user_id: int | None) -> dict[str, int]:
        conditions = [ScanRow.user_id == user_id] if user_id is not None else []
        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(ScanRow).where(*conditions))
            by_verdict = session.execute(
                select(ScanRow.verdict, func.count()).where(*conditions).group_by(ScanRow.verdict)
            ).all()
        result = {"total": int(total or 0), **{v.value: 0 for v in Verdict}}
        for verdict, count in by_verdict:
            if verdict:
                result[verdict] = int(count)
        return result

    def list_active(self) -> list[Scan]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ScanRow).where(ScanRow.status.in_(_ACTIVE)).order_by(ScanRow.created_at)
            ).all()
            return [_scan(r) for r in rows]
