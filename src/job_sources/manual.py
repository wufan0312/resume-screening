"""手动 / 粘贴式岗位源（Phase 1 开发可用，也作为人工在环的兜底）。

用户把岗位 JD 以文本或结构化列表传入，本数据源原样转换为 JobPosting。
不依赖任何外部平台，用于本地联调与无平台场景。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from job_sources.base import BaseJobSource, JobPosting, SearchCriteria


class ManualJobSource(BaseJobSource):
    name = "manual"
    label = "手动导入"

    def __init__(self, jobs: Optional[List[Dict[str, Any]]] = None) -> None:
        # 运行时由流程节点注入（从 state["jobs_input"] 取出）
        self._jobs: List[Dict[str, Any]] = jobs or []

    def set_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        self._jobs = jobs or []

    def search(self, criteria: SearchCriteria) -> List[JobPosting]:
        result: List[JobPosting] = []
        for j in self._jobs:
            if not isinstance(j, dict):
                continue
            result.append(
                JobPosting(
                    title=str(j.get("title", "")),
                    company=str(j.get("company", "")),
                    location=str(j.get("location", "")),
                    salary=str(j.get("salary", "")),
                    description=str(j.get("description", j.get("jd", ""))),
                    source=self.name,
                    url=str(j.get("url", "")),
                    extra=j.get("extra", {}) or {},
                )
            )
        return result
