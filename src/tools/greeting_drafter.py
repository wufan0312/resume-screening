"""打招呼语生成工具：针对推荐岗位，生成自然、克制的 BOSS 风格招呼语。"""
from __future__ import annotations

from graphs.llm_client import call_llm


GREETING_SYSTEM = (
    "你是求职助手。根据求职者的简历亮点与目标岗位，写一段自然、真诚、"
    "不超过 80 字的打招呼语（类似 BOSS直聘 开场白），突出最相关的 1-2 个匹配点，"
    "不夸大、不套模板，像真人发的第一句话。"
)


def draft_greeting(
    profile: str, job_title: str, company: str, matched_points: list
) -> str:
    """生成针对单个岗位的打招呼语。"""
    matched = "、".join(list(matched_points)[:2]) if matched_points else "相关经验"
    user = (
        f"【求职者简历亮点】\n{profile}\n\n"
        f"【目标岗位】{job_title} @ {company}\n"
        f"【最相关的匹配点】{matched}\n\n"
        "请直接输出这段打招呼语本身，不要任何解释或引号包裹。"
    )
    return call_llm(GREETING_SYSTEM, user).strip()
