"""招聘数据源包。

设计目标：不让任何单一招聘平台（BOSS直聘、猎聘、LinkedIn…）被写死在核心逻辑里。
所有平台都实现同一个 BaseJobSource 接口，通过 registry 注册与启用。

新增一个招聘网站：
  1. 在 src/job_sources/ 下新建一个实现 BaseJobSource 的类（实现 search()）；
  2. 在本文件里 import 并 registry.register(YourSource())；
  3. 在 config/job_sources.json 的 enabled 中加入它的 name。
核心流程（匹配 / 报告）无需任何改动。
"""
from job_sources.base import BaseJobSource, JobPosting, SearchCriteria
from job_sources.registry import JobSourceRegistry, registry, search_all, search_with_config
from job_sources.manual import ManualJobSource
from job_sources.mock import MockJobSource
from job_sources.boss import BossJobSource
from job_sources.browser import BrowserJobSource
from job_sources.cities import detect_city

# 注册内置数据源。BOSS 为 Phase 2 实现，是否真正检索看 config/job_sources.json（需配 Cookie）。
registry.register(ManualJobSource())
registry.register(MockJobSource())
registry.register(BossJobSource())

__all__ = [
    "BaseJobSource",
    "JobPosting",
    "SearchCriteria",
    "JobSourceRegistry",
    "registry",
    "search_all",
    "search_with_config",
    "BrowserJobSource",
    "ManualJobSource",
    "MockJobSource",
    "BossJobSource",
    "detect_city",
]
