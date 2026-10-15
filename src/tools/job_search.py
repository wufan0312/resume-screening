"""岗位检索 + 匹配一体化工具（供 Agent 对话模式调用）。

把「发现岗位」与「匹配打分」封装成一个工具，让求职顾问 Agent 能一句话完成
“按我的简历找匹配岗位”。
"""
from __future__ import annotations

from langchain.tools import tool

from job_sources.base import SearchCriteria
from job_sources.registry import search_all
from tools.job_match import match_jobs


@tool
def find_matching_jobs(resume_text: str, preferences: str = "") -> str:
    """根据求职者简历文本与求职偏好，自动检索多平台岗位并匹配打分，返回 Top 推荐。

    当用户提供简历（文本或解析后的内容）与求职偏好（目标岗位/城市/薪资等）时调用，
    返回按匹配度排序的推荐岗位列表，含得分、推荐指数与匹配点。

    Args:
        resume_text: 求职者简历文本或解析后的内容。
        preferences: 求职偏好描述，如“前端+AI方向，深圳，期望20-30K”。
    """
    criteria = SearchCriteria(raw_preferences=preferences)
    postings = search_all(criteria)
    if not postings:
        return (
            "未检索到匹配岗位。请确认已在 config/job_sources.json 启用数据源"
            "（如 mock / manual），并提供简历与求职偏好。"
        )
    matches = match_jobs(resume_text, postings)
    matches.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = matches[:5]
    lines = [f"为您匹配到 {len(top)} 个岗位（共检索 {len(postings)} 个）："]
    for i, m in enumerate(top, 1):
        lines.append(
            f"{i}. {m['title']} @ {m['company']}（{m['score']}分 / {m['recommendation']}）"
            f" 城市:{m.get('location', '—')} 薪资:{m.get('salary', '—')} 来源:{m.get('source', '—')}"
        )
        if m.get("matched_points"):
            lines.append(f"   匹配点：{'、'.join(m['matched_points'][:2])}")
    return "\n".join(lines)
