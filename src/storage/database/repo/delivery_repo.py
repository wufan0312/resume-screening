"""投递状态仓储层（Phase 3）。

所有函数接受 SQLAlchemy `session`（同步）。生产环境由 storage.database.db.get_session() 提供
PostgreSQL 会话；单测可传入内存 SQLite 会话，互不干扰。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from storage.database.models.delivery import (
    Application,
    DeliveryStatus,
    status_label,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_delivery_tables(engine=None) -> None:
    """创建投递相关表。生产建议改用 Alembic 迁移；此处提供便捷初始化。"""
    from storage.database.shared.model import Base

    if engine is None:
        from storage.database.db import get_engine

        engine = get_engine()
    Base.metadata.create_all(engine)


def upsert_pending_application(
    session,
    *,
    source: str,
    title: str,
    company: str,
    location: str = "",
    salary: str = "",
    url: str = "",
    description: str = "",
    job_extra: Optional[dict] = None,
    profile_summary: str = "",
    matched_score: int = 0,
    matched_points: Optional[list] = None,
    recommendation: str = "",
    greeting: str = "",
    dedup: bool = True,
) -> Application:
    """把一条匹配岗位落库为「待投递」记录。

    dedup=True 时，若已存在相同 (source, title, company) 且仍为 pending 的记录，
    则更新其画像/分数/话术但保留原状态，避免重复建单。
    """
    if dedup:
        existing = (
            session.query(Application)
            .filter_by(
                source=source,
                title=title,
                company=company,
                status=DeliveryStatus.PENDING.value,
            )
            .first()
        )
        if existing is not None:
            existing.profile_summary = profile_summary
            existing.matched_score = matched_score
            existing.matched_points = matched_points
            existing.recommendation = recommendation
            existing.greeting = greeting
            existing.last_status_at = _now()
            session.commit()
            session.refresh(existing)
            return existing

    app = Application(
        source=source,
        title=title,
        company=company,
        location=location,
        salary=salary,
        url=url,
        description=description,
        job_extra=job_extra,
        profile_summary=profile_summary,
        matched_score=matched_score,
        matched_points=matched_points,
        recommendation=recommendation,
        greeting=greeting,
        status=DeliveryStatus.PENDING.value,
        last_status_at=_now(),
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def persist_match_plan(session, matches: List[Dict[str, Any]], profile: str = "") -> List[Dict[str, Any]]:
    """把匹配结果（graph 的 matches）批量落库为「待投递」记录，返回精简清单。

    仅落库 score>=60 的推荐岗位；返回供前端/报告展示的精简 dict 列表。
    """
    applications: List[Dict[str, Any]] = []
    for m in matches:
        score = int(m.get("score", 0) or 0)
        if score < 60:
            continue
        app = upsert_pending_application(
            session,
            source=m.get("source", ""),
            title=m.get("title", ""),
            company=m.get("company", ""),
            location=m.get("location", ""),
            salary=m.get("salary", ""),
            url=m.get("url", ""),
            description=m.get("description", ""),
            job_extra=m.get("extra"),
            profile_summary=profile,
            matched_score=score,
            matched_points=m.get("matched_points"),
            recommendation=m.get("recommendation", ""),
            greeting=m.get("greeting", ""),
        )
        applications.append(
            {
                "id": app.id,
                "title": app.title,
                "company": app.company,
                "location": app.location,
                "salary": app.salary,
                "score": app.matched_score,
                "status": app.status,
                "greeting": app.greeting,
            }
        )
    return applications


def list_applications(session, status: Optional[str] = None, limit: int = 50) -> List[Application]:
    q = session.query(Application)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(Application.created_at.desc()).limit(limit).all()


def get_application(session, app_id: int) -> Optional[Application]:
    return session.get(Application, app_id)


def update_status(session, app_id: int, status: str, note: str = "") -> Optional[Application]:
    """更新某条投递记录的状态。

    - status 不在枚举内时，原样保存（不强制约束，便于临时标记）；
    - 切到 delivered 且首次时，回填 applied_at。
    """
    app = session.get(Application, app_id)
    if app is None:
        return None
    app.status = status
    if note:
        app.note = note
    if status == DeliveryStatus.DELIVERED.value and app.applied_at is None:
        app.applied_at = _now()
    app.last_status_at = _now()
    session.commit()
    session.refresh(app)
    return app


def get_stats(session) -> Dict[str, int]:
    """按状态统计，用于每日汇报。返回各状态计数 + total。"""
    rows = (
        session.query(Application.status, func.count(Application.id))
        .group_by(Application.status)
        .all()
    )
    stats = {s.value: 0 for s in DeliveryStatus}
    for status_value, cnt in rows:
        stats[status_value] = cnt
    stats["total"] = sum(stats.values())
    return stats


def stats_with_labels(session) -> Dict[str, Any]:
    """带中文标签的统计，直接用于汇报展示。"""
    raw = get_stats(session)
    labeled = {
        "total": raw.pop("total", 0),
        "by_status": {status_label(k): v for k, v in raw.items() if v},
    }
    return labeled
