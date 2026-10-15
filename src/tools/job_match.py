"""岗位匹配工具：把「求职者简历画像」与「岗位 JD」做匹配打分（原筛选逻辑的翻转）。

原项目：JD + 候选人简历 → 给候选人打分（招聘方视角）。
本工具：我的简历 + 岗位 JD → 给岗位打匹配度（求职者视角）。
"""
from __future__ import annotations

from typing import Dict, List

from graphs.llm_client import call_llm_json
from job_sources.base import JobPosting

MATCH_SYSTEM = (
    "你是求职匹配顾问。请基于「求职者的简历画像」与「目标岗位 JD」，"
    "评估该岗位与求职者的匹配程度。\n"
    "评分维度：技能栈匹配度、项目/业务相关度、经验年限契合度、"
    "求职意向/稳定性契合度，满分 100 分。\n"
    "严格只输出 JSON：\n"
    '{"score": 0到100的整数, "recommendation": "强烈推荐/推荐/可考虑/不建议", '
    '"matched_points": ["匹配点1"], "gap_points": ["差距点1"], '
    '"suggestion": "针对该岗位的一句话求职建议"}'
)


def match_job(profile: str, job: JobPosting) -> Dict:
    """对单个岗位做匹配打分。"""
    jd_text = (
        f"【岗位】{job.title} @ {job.company}\n"
        f"【城市】{job.location}　【薪资】{job.salary}\n"
        f"【JD】{job.description}"
    )
    verdict = call_llm_json(
        MATCH_SYSTEM,
        f"【求职者简历画像】\n{profile}\n\n{jd_text}",
    )
    try:
        score = int(verdict.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "source": job.source,
        "url": job.url,
        "score": score,
        "recommendation": verdict.get("recommendation", "可考虑"),
        "matched_points": verdict.get("matched_points", []) or [],
        "gap_points": verdict.get("gap_points", []) or [],
        "suggestion": verdict.get("suggestion", ""),
    }


def match_jobs(profile: str, jobs: List[JobPosting]) -> List[Dict]:
    """对一批岗位批量匹配打分。"""
    return [match_job(profile, j) for j in jobs]
