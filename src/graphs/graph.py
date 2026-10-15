"""求职投递智能体（节点化工作流，求职者视角）。

流程：
    开始 → 简历画像 → 岗位发现(多平台,可插拔) → 岗位匹配(翻转评分) → 生成招呼语 → 输出报告

输入（工作流状态字段）：
- my_resume: 求职者简历（文本，或 http/https 文件 URL）
- job_preferences: 求职偏好（dict 或字符串；dict 支持 keywords/city/salary/raw）
- jobs_input: 可选，手动粘贴的岗位列表（供 manual 数据源使用）
- sources: 可选，指定启用的数据源名；缺省读 config/job_sources.json

输出：
- report / output: 推荐岗位排名 + 每岗匹配分析 + 定制打招呼语
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from graphs.llm_client import call_llm_json
from job_sources.base import JobPosting, SearchCriteria
from job_sources.registry import registry, search_with_config
from job_sources.cities import detect_city
from storage.database.models.delivery import status_label
from tools.greeting_drafter import draft_greeting
from tools.job_match import match_jobs


class DeliveryState(TypedDict, total=False):
    my_resume: str
    job_preferences: Any
    jobs_input: List[Dict[str, Any]]
    sources: List[str]
    profile: str
    profile_data: Dict
    job_postings: List[JobPosting]
    matches: List[Dict]
    applications: List[Dict[str, Any]]
    report: str
    output: str


PROFILE_SYSTEM = (
    "你是简历解析专家。请从求职者简历中提取其「求职画像」，用于后续自动匹配岗位。\n"
    "严格只输出 JSON：\n"
    '{"skills": ["技能1"], "experience_years": "总年限概述", '
    '"roles": ["擅长角色1"], "education": "学历概述", '
    '"strengths": ["优势1"], "job_targets": ["目标岗位方向1"], '
    '"salary_expectation": "薪资期望(若简历中提及)", "summary": "一句话自我定位"}'
)


# ---------------------------------------------------------------- 节点函数


def start_node(state: DeliveryState) -> Dict:
    """开始节点：规范化简历输入，若是文件 URL 则解析为文本。"""
    my_resume = (state.get("my_resume") or "").strip()
    if my_resume.lower().startswith(("http://", "https://")):
        from tools.resume_parser import parse_resume_file

        parsed = parse_resume_file.invoke({"file_url": my_resume})
        my_resume = parsed if isinstance(parsed, str) else str(parsed)
    return {"my_resume": my_resume}


def profile_node(state: DeliveryState) -> Dict:
    """简历画像：从简历生成求职者技能/经验/目标等结构化画像文本。"""
    data = call_llm_json(PROFILE_SYSTEM, f"【求职者简历】\n{state.get('my_resume', '')}")
    lines = [
        f"一句话定位：{data.get('summary', '')}",
        f"技能：{'、'.join(data.get('skills', []) or [])}",
        f"经验年限：{data.get('experience_years', '')}",
        f"擅长角色：{'、'.join(data.get('roles', []) or [])}",
        f"学历：{data.get('education', '')}",
        f"优势：{'；'.join(data.get('strengths', []) or [])}",
        f"目标岗位：{'、'.join(data.get('job_targets', []) or [])}",
        f"薪资期望：{data.get('salary_expectation', '未提及')}",
    ]
    return {"profile": "\n".join(lines), "profile_data": data}


def _build_criteria(state: DeliveryState) -> SearchCriteria:
    prefs = state.get("job_preferences")
    keywords: List[str] = []
    city = ""
    salary = ""
    raw = ""
    if isinstance(prefs, dict):
        keywords = prefs.get("keywords", []) or []
        city = prefs.get("city", "") or ""
        salary = prefs.get("salary", "") or ""
        raw = prefs.get("raw", "") or ""
    else:
        raw = str(prefs or "")

    # 从简历画像抽取关键词，让 BOSS 等平台自动搜索更精准
    profile_data = state.get("profile_data") or {}
    if not keywords and profile_data:
        targets = list(profile_data.get("job_targets", []) or [])
        skills = list(profile_data.get("skills", []) or [])[:2]
        keywords = targets + skills
    # 城市：优先偏好里显式给的，否则从原始偏好 / 画像摘要里识别
    if not city:
        city = detect_city(raw) or detect_city(str(profile_data.get("summary", "")))

    return SearchCriteria(
        keywords=keywords, city=city, salary_expectation=salary, raw_preferences=raw
    )


def discovery_node(state: DeliveryState) -> Dict:
    """岗位发现：调用所有已启用数据源，自动检索匹配岗位（多平台可插拔）。"""
    # 若提供了手动岗位，注入 manual 数据源
    jobs_input = state.get("jobs_input") or []
    manual = registry.get("manual")
    if manual is not None and jobs_input:
        manual.set_jobs(jobs_input)

    sources_arg = state.get("sources")
    postings = search_with_config(
        _build_criteria(state), only_sources=sources_arg
    )
    return {"job_postings": postings}


def match_node(state: DeliveryState) -> Dict:
    """岗位匹配：对所有发现岗位做匹配打分并按匹配度排序。"""
    profile = state.get("profile", "")
    matches = match_jobs(profile, state.get("job_postings", []))
    matches.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"matches": matches}


def greeting_node(state: DeliveryState) -> Dict:
    """生成招呼语：为推荐岗位（score>=60）生成定制 BOSS 风格打招呼语。"""
    profile = state.get("profile", "")
    for m in state.get("matches", []):
        if m.get("score", 0) >= 60:
            try:
                m["greeting"] = draft_greeting(
                    profile,
                    m.get("title", ""),
                    m.get("company", ""),
                    m.get("matched_points", []),
                )
            except Exception:
                m["greeting"] = ""
    return {"matches": state.get("matches", [])}


def report_node(state: DeliveryState) -> Dict:
    """输出报告：汇总推荐排名、匹配分析与打招呼语。"""
    matches = state.get("matches", [])
    sections: List[str] = []

    if matches:
        detail = "# 求职岗位匹配报告\n\n## 一、岗位详评（按匹配度排序）\n"
        for i, m in enumerate(matches, 1):
            score = m.get("score", 0)
            conclusion = "推荐" if score >= 80 else ("待定" if score >= 60 else "不推荐")
            detail += (
                f"\n### {i}. {m.get('title')} @ {m.get('company')}"
                f"（{score} 分 · {m.get('recommendation')} · {conclusion}）\n"
            )
            detail += (
                f"- 城市：{m.get('location') or '—'}　薪资：{m.get('salary') or '—'}"
                f"　来源：{m.get('source') or '—'}\n"
            )
            detail += f"- 匹配点：{'；'.join(m.get('matched_points') or []) or '—'}\n"
            detail += f"- 差距点：{'；'.join(m.get('gap_points') or []) or '—'}\n"
            detail += f"- 建议：{m.get('suggestion') or '—'}\n"
            if m.get("greeting"):
                detail += f"- 打招呼语：{m.get('greeting')}\n"
        sections.append(detail)

        table = (
            "## 二、推荐排名\n\n"
            "| 排名 | 岗位 | 公司 | 得分 | 结论 | 来源 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        for i, m in enumerate(matches, 1):
            score = m.get("score", 0)
            conclusion = "推荐" if score >= 80 else ("待定" if score >= 60 else "不推荐")
            table += (
                f"| {i} | {m.get('title')} | {m.get('company')} | {score} | "
                f"{conclusion} | {m.get('source') or '—'} |\n"
            )
        sections.append(table)

        advice = "## 三、投递建议\n\n"
        top = matches[0]
        advice += (
            f"优先投递与画像最契合的「{top.get('title')} @ {top.get('company')}」"
            f"（{top.get('score')} 分）。\n"
        )
        advice += "80 分及以上建议优先投，60-79 分可考虑，60 以下暂不推荐。\n"
        advice += "（当前为人工在环：请确认清单与招呼语后，再前往对应平台投递。）\n"
        sections.append(advice)

    # 四、投递清单（人工在环）：把待投递岗位与话术落到报告，供用户逐项执行
    apps = state.get("applications") or []
    if apps:
        plan = (
            "## 四、投递清单（人工在环）\n\n"
            "以下岗位已记录为「待投递」。请在对应平台（如 BOSS直聘）完成实际投递后，\n"
            "用 `update_application_status` 工具把状态更新为 delivered；后续已读/已回/面试也请及时回写。\n\n"
        )
        for i, a in enumerate(apps, 1):
            aid = a.get("id")
            tag = f"#{aid}" if aid is not None else "（未落库）"
            plan += (
                f"{i}. {tag} {a.get('title')} @ {a.get('company')}"
                f"（{a.get('score')} 分 · {status_label(a.get('status', 'pending'))}）\n"
            )
            if a.get("greeting"):
                plan += f"   打招呼语：{a.get('greeting')}\n"
        sections.append(plan)

    report = (
        "\n".join(sections)
        if sections
        else "## 匹配完成\n\n未发现可匹配岗位，请检查简历与求职偏好，或启用更多数据源。"
    )
    return {"report": report, "output": report}


def delivery_node(state: DeliveryState) -> Dict:
    """投递执行（人工在环）：把推荐岗位落库为「待投递」记录，并产出投递清单。

    ⚠️ 实际在 BOSS 上的「点击投递」由求职者本人完成（规避封号/合规风险）。
    本节点只负责：① 持久化待投递清单；② 在报告里给出话术与操作指引。
    若数据库不可用，则降级为仅生成内存清单，不阻断整条流程。
    """
    matches = state.get("matches", []) or []
    profile = state.get("profile", "")
    try:
        from storage.database.db import get_session
        from storage.database.repo import delivery_repo

        session = get_session()
        try:
            applications = delivery_repo.persist_match_plan(session, matches, profile)
        finally:
            session.close()
    except Exception:
        # 降级：仅生成内存清单
        applications = []
        for m in matches:
            if int(m.get("score", 0) or 0) >= 60:
                applications.append(
                    {
                        "id": None,
                        "title": m.get("title", ""),
                        "company": m.get("company", ""),
                        "location": m.get("location", ""),
                        "salary": m.get("salary", ""),
                        "score": m.get("score", 0),
                        "status": "pending",
                        "greeting": m.get("greeting", ""),
                    }
                )
    return {"applications": applications}


# ---------------------------------------------------------------- 图编排


def _build_graph():
    g = StateGraph(DeliveryState)
    g.add_node("开始节点", start_node)
    g.add_node("简历画像", profile_node)
    g.add_node("岗位发现", discovery_node)
    g.add_node("岗位匹配", match_node)
    g.add_node("生成招呼语", greeting_node)
    g.add_node("投递执行", delivery_node)
    g.add_node("输出报告", report_node)

    g.add_edge(START, "开始节点")
    g.add_edge("开始节点", "简历画像")
    g.add_edge("简历画像", "岗位发现")
    g.add_edge("岗位发现", "岗位匹配")
    g.add_edge("岗位匹配", "生成招呼语")
    g.add_edge("生成招呼语", "投递执行")
    g.add_edge("投递执行", "输出报告")
    g.add_edge("输出报告", END)
    return g


# 模块级编译后的图实例，供 graph_helper.get_graph_instance("graphs.graph") 加载
graph = _build_graph().compile()
