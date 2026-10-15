"""投递状态数据模型（Phase 3）。

设计要点（人工在环）：
- 一次「投递」= 一条 Application 记录，内嵌岗位快照（岗位可能随时下架/变动，落库即定格）；
- status 用枚举字符串，便于统计与每日汇报；
- 实际在 BOSS 上的「点击投递」动作由求职者本人完成（规避封号/合规风险），
  系统在用户确认后把岗位记录为「待投递」，再由用户回写真实状态（已读/已回/面试…）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from storage.database.shared.model import Base


class DeliveryStatus(str, Enum):
    """投递状态机。pending → delivered → read → replied/interview/rejected/withdrawn。"""

    PENDING = "pending"        # 待投递：已生成清单，用户尚未在平台投递
    DELIVERED = "delivered"    # 已投递：用户已在平台发送
    READ = "read"              # 已读
    REPLIED = "replied"        # 已回复
    INTERVIEW = "interview"    # 面试邀约
    REJECTED = "rejected"      # 不合适 / 未通过
    WITHDRAWN = "withdrawn"    # 已撤回


STATUS_LABELS: dict[str, str] = {
    DeliveryStatus.PENDING.value: "待投递",
    DeliveryStatus.DELIVERED.value: "已投递",
    DeliveryStatus.READ.value: "已读",
    DeliveryStatus.REPLIED.value: "已回复",
    DeliveryStatus.INTERVIEW.value: "面试邀约",
    DeliveryStatus.REJECTED.value: "不合适",
    DeliveryStatus.WITHDRAWN.value: "已撤回",
}


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value)


class Application(Base):
    """一条投递记录（含岗位快照与状态追踪）。"""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # —— 岗位快照 ——
    source: Mapped[str] = mapped_column(String(64), default="", comment="来源平台，如 boss/manual")
    title: Mapped[str] = mapped_column(String(255), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    salary: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    job_extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # —— 匹配与话术 ——
    profile_summary: Mapped[str] = mapped_column(Text, default="", comment="投递时使用的简历画像摘要")
    matched_score: Mapped[int] = mapped_column(Integer, default=0, comment="匹配度(0-100)")
    matched_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment="匹配点")
    recommendation: Mapped[str] = mapped_column(String(64), default="")
    greeting: Mapped[str] = mapped_column(Text, default="", comment="定制打招呼语")

    # —— 状态追踪 ——
    status: Mapped[str] = mapped_column(
        String(32), default=DeliveryStatus.PENDING.value, index=True
    )
    note: Mapped[str] = mapped_column(Text, default="", comment="备注/HR回复摘要等")

    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
