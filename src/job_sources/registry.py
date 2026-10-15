"""招聘平台数据源注册表。

核心流程只依赖本注册表，不依赖任何具体平台。
通过 register() 注册实现类，通过 config/job_sources.json 决定启用哪些、及其参数。

search_with_config：
  - 读取 config 的 enabled（启用的源）与 sources.<name>（每源参数）；
  - 对启用的源先 apply 参数（configure），再检查 is_configured；
  - 未配置（如 BOSS 缺 Cookie）的源**自动跳过并提示**，不抛错、不影响其它源；
  - 单个源检索异常也只跳过该源。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from job_sources.base import BaseJobSource, JobPosting, SearchCriteria

# 项目根目录下的 config/job_sources.json
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../src
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(_PROJECT_ROOT), "config", "job_sources.json"
)


class JobSourceRegistry:
    def __init__(self) -> None:
        self._sources: Dict[str, BaseJobSource] = {}

    def register(self, source: BaseJobSource) -> None:
        self._sources[source.name] = source

    def get(self, name: str) -> Optional[BaseJobSource]:
        return self._sources.get(name)

    def all(self) -> List[BaseJobSource]:
        return list(self._sources.values())

    def get_enabled(self, config_path: str = DEFAULT_CONFIG_PATH) -> List[BaseJobSource]:
        data = self._read_config(config_path)
        enabled_names = list(data.get("enabled", []))
        sources_cfg = data.get("sources", {})
        result = []
        for s in self.all():
            if s.name in enabled_names:
                cfg = sources_cfg.get(s.name)
                if cfg and hasattr(s, "configure"):
                    try:
                        s.configure(cfg)
                    except Exception:
                        pass
                result.append(s)
        return result


def _read_config(config_path: str) -> Dict:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


#: 全局注册表单例
registry = JobSourceRegistry()


def search_with_config(
    criteria: SearchCriteria,
    config_path: str = DEFAULT_CONFIG_PATH,
    only_sources: Optional[List[str]] = None,
) -> List[JobPosting]:
    """从已启用（或指定）数据源检索岗位并合并去重。

    - only_sources 不为空时，只检索这些源（仍走配置注入 + 配置检查）；
    - 未配置 / 检索失败的源自动跳过（打印提示），保证整体可用。
    """
    data = _read_config(config_path)
    enabled_names = set(data.get("enabled", []))
    sources_cfg = data.get("sources", {})

    postings: List[JobPosting] = []
    seen = set()
    for source in registry.all():
        if only_sources:
            if source.name not in only_sources:
                continue
        elif source.name not in enabled_names:
            continue

        cfg = sources_cfg.get(source.name)
        if cfg and hasattr(source, "configure"):
            try:
                source.configure(cfg)
            except Exception:
                pass

        if hasattr(source, "is_configured") and not source.is_configured():
            print(
                f"[job_sources] 跳过未配置的源：{source.label}（{source.name}）"
                "—— 请配置登录态/凭据后再启用。"
            )
            continue

        try:
            for job in source.search(criteria):
                key = (job.title, job.company, job.location)
                if key in seen:
                    continue
                seen.add(key)
                postings.append(job)
        except Exception as e:  # 单源失败不影响整体
            print(f"[job_sources] 源 {source.label} 检索失败，已跳过：{e}")
            continue
    return postings


#: 兼容别名（供 tools/job_search.py 等既有调用使用）
def search_all(
    criteria: SearchCriteria, config_path: str = DEFAULT_CONFIG_PATH
) -> List[JobPosting]:
    return search_with_config(criteria, config_path)
