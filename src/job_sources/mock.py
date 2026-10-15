"""Mock 岗位源，提供示例岗位用于本地端到端验证（无需任何平台账号）。"""
from __future__ import annotations

from typing import List

from job_sources.base import BaseJobSource, JobPosting, SearchCriteria

_SAMPLE: List[Dict[str, str]] = [
    {
        "title": "高级前端开发工程师",
        "company": "示例科技",
        "location": "深圳",
        "salary": "20-35K",
        "description": "要求 5 年以上前端经验，精通 React/Next.js/TypeScript，有 AI 应用落地经验优先。",
    },
    {
        "title": "AI 应用开发工程师",
        "company": "示例智能",
        "location": "杭州",
        "salary": "25-40K",
        "description": "负责 AI Agent 平台研发，熟悉 LangGraph/FastAPI，有 RAG 与流式输出经验。",
    },
    {
        "title": "全栈开发工程师",
        "company": "示例云",
        "location": "北京",
        "salary": "18-30K",
        "description": "React + Node/Python 全栈，能独立交付产品，有 LLM 接入经验者优先。",
    },
]


class MockJobSource(BaseJobSource):
    name = "mock"
    label = "示例数据"

    def search(self, criteria: SearchCriteria) -> List[JobPosting]:
        return [
            JobPosting(
                title=d["title"],
                company=d["company"],
                location=d["location"],
                salary=d["salary"],
                description=d["description"],
                source=self.name,
            )
            for d in _SAMPLE
        ]
