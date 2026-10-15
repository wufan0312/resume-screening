"""招聘平台数据源抽象层。

所有招聘平台（BOSS直聘、猎聘、LinkedIn…）都实现同一个 BaseJobSource 接口，
核心匹配流程只依赖本文件的抽象类型，不依赖任何具体平台。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class JobPosting:
    """一条岗位（JD）的标准化结构，跨平台统一。"""

    title: str
    company: str
    location: str = ""
    salary: str = ""
    description: str = ""  # JD 正文 / 岗位要求
    source: str = ""  # 来源平台标识，如 "boss" / "liepin" / "manual"
    url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchCriteria:
    """根据简历画像 + 求职偏好生成的检索条件。"""

    keywords: List[str] = field(default_factory=list)  # 技能 / 职位关键词
    city: str = ""
    salary_expectation: str = ""
    experience: str = ""  # 经验年限倾向
    raw_preferences: str = ""  # 用户原始偏好文本


class BaseJobSource(ABC):
    """招聘平台数据源基类。子类实现 search() 即可接入。"""

    #: 平台唯一标识，需与 config/job_sources.json 中的启用名一致
    name: str = "base"

    #: 人类可读的平台名称
    label: str = "base"

    def configure(self, cfg: Dict[str, Any]) -> None:
        """可选：用 config/job_sources.json 中 sources.<name> 的配置初始化本源。

        默认无操作；浏览器类数据源可借此读入 headless / max_jobs 等参数。
        """
        return None

    def is_configured(self) -> bool:
        """可选：本源是否具备运行条件（如登录态 / 凭据已就绪）。

        默认 True。需要登录态的平台（如 BOSS）应重写为：缺少 Cookie 时返回 False，
        这样 search_all 会自动跳过并提示，而不是抛错中断整个流程。
        """
        return True

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> List[JobPosting]:
        """根据检索条件返回岗位列表。

        实现方需自行处理平台登录态、反爬、分页、限流等；
        单个平台异常由调用方（search_all）捕获并跳过，不影响其它平台。
        """
        raise NotImplementedError
