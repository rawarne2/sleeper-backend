"""Retention policy for ``value_snapshots``.

``full`` metrics keep every snapshot from the last ``KEEP_ALL_DAYS`` days and one per
day (the latest that day) before that. ``latest_only`` metrics keep one row per key:
ingest updates that row in place, and pruning removes any older leftovers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Dict, Iterable, List, Literal, Tuple

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from models.entities import ValueSnapshot
from models.extensions import db

Policy = Literal["full", "latest_only"]

KEEP_ALL_DAYS = 30
DEFAULT_POLICY: Policy = "latest_only"
METRIC_POLICY: Dict[str, Policy] = {"value": "full"}

_KEY_COLS = (
    ValueSnapshot.player_id, ValueSnapshot.pick_key, ValueSnapshot.source_key,
    ValueSnapshot.league_format, ValueSnapshot.config_key, ValueSnapshot.metric_key,
)


def metric_policy(metric_key: str) -> Policy:
    return METRIC_POLICY.get(metric_key, DEFAULT_POLICY)


@dataclass
class PruneReport:
    dry_run: bool
    cutoff: datetime
    deleted: Dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.deleted.values())


def _slices(session: Session) -> List[Tuple[str, str, str]]:
    rows = session.execute(
        select(ValueSnapshot.source_key, ValueSnapshot.league_format, ValueSnapshot.metric_key)
        .distinct()
    ).all()
    return sorted(tuple(r) for r in rows)


def _doomed_ids(session: Session, source_key: str, league_format: str, metric_key: str,
                cutoff: datetime) -> List[int]:
    policy = metric_policy(metric_key)
    partition = list(_KEY_COLS)
    where = [ValueSnapshot.source_key == source_key,
             ValueSnapshot.league_format == league_format,
             ValueSnapshot.metric_key == metric_key]
    if policy == "full":
        partition.append(func.date(ValueSnapshot.as_of))
        where.append(ValueSnapshot.as_of < cutoff)
    rn = func.row_number().over(
        partition_by=partition,
        order_by=(ValueSnapshot.as_of.desc(), ValueSnapshot.id.desc()),
    ).label("rn")
    ranked = select(ValueSnapshot.id, rn).where(and_(*where)).subquery()
    return list(session.execute(select(ranked.c.id).where(ranked.c.rn > 1)).scalars())


def _chunks(ids: List[int], size: int) -> Iterable[List[int]]:
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def prune_value_snapshots(
    *,
    dry_run: bool = True,
    keep_all_days: int = KEEP_ALL_DAYS,
    batch_size: int = 5000,
    now: datetime | None = None,
    session: Session | None = None,
) -> PruneReport:
    """Delete snapshots the retention policy no longer needs. Idempotent.

    Works one (source, format, metric) slice at a time and deletes in ``batch_size``
    id batches, committing each, so a long run never holds a big transaction.
    """
    session = session or db.session
    cutoff = (now or datetime.now(UTC)).replace(tzinfo=None) - timedelta(days=keep_all_days)
    report = PruneReport(dry_run=dry_run, cutoff=cutoff)
    for source_key, league_format, metric_key in _slices(session):
        ids = _doomed_ids(session, source_key, league_format, metric_key, cutoff)
        if not ids:
            continue
        report.deleted[f"{source_key}/{league_format}/{metric_key}"] = len(ids)
        if dry_run:
            continue
        for chunk in _chunks(ids, batch_size):
            session.execute(delete(ValueSnapshot).where(ValueSnapshot.id.in_(chunk)))
            session.commit()
    return report
