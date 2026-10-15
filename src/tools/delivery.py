"""投递状态相关工具（供 Agent 对话模式调用，人工在环）。

求职者可在对话里直接说：
- “看看我已投递的岗位” → list_my_applications
- “把 #3 标记为已读”   → update_application_status(3, "read")
- “#5 已面试邀约”       → update_application_status(5, "interview")
实际在 BOSS 上的「点击投递」仍由用户本人完成，系统只负责记录与追踪。
"""
from __future__ import annotations

from langchain.tools import tool

from storage.database.db import get_session
from storage.database.models.delivery import status_label
from storage.database.repo import delivery_repo


@tool
def list_my_applications(status: str = "") -> str:
    """查看我的投递记录与状态。可选 status 过滤（pending/delivered/read/replied/interview/rejected/withdrawn）。

    Args:
        status: 状态过滤，留空则返回全部。
    """
    session = get_session()
    try:
        apps = delivery_repo.list_applications(session, status=status or None)
        if not apps:
            return "暂无投递记录。" if not status else f"状态「{status}」下暂无投递记录。"
        lines = [f"共 {len(apps)} 条投递记录："]
        for a in apps:
            lines.append(
                f"- #{a.id} {a.title} @ {a.company}"
                f" ｜ {status_label(a.status)} ｜ 薪资 {a.salary or '—'}"
                f" ｜ 来源 {a.source or '—'} ｜ 匹配 {a.matched_score} 分"
            )
        return "\n".join(lines)
    finally:
        session.close()


@tool
def update_application_status(application_id: int, status: str, note: str = "") -> str:
    """更新某条投递记录的状态（人工在环回写真实进展）。

    Args:
        application_id: 投递记录 ID（来自 list_my_applications 的 #编号）。
        status: 新状态，取值 one of：pending/delivered/read/replied/interview/rejected/withdrawn。
        note: 可选备注，如 HR 回复摘要。
    """
    session = get_session()
    try:
        app = delivery_repo.update_status(session, application_id, status, note)
        if app is None:
            return f"未找到 ID={application_id} 的投递记录。"
        return f"已更新 #{app.id}《{app.title} @ {app.company}》状态为：{status_label(app.status)}。"
    finally:
        session.close()
