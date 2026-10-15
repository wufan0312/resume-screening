"""【模板】猎聘数据源示例 —— 演示「如何新增一个招聘网站」。

本文件是**未注册的模板**，仅用于示范。要真正接入猎聘：
  1. 把下面的猎聘专属逻辑（搜索 URL 拼法、卡片选择器、解析规则）填实；
  2. 在 job_sources/__init__.py 里 import 并 registry.register(LiepinJobSource())；
  3. 在 config/job_sources.json 的 enabled 中加入 "liepin"，并在 sources 里配置。
核心匹配 / 报告流程**零改动**。

—— 这就是「不把 BOSS 写死、可任意加网站」的落地方式：每加一个站 = 一个子类 + 两行注册。
"""
from __future__ import annotations

from typing import List, Optional

from job_sources.base import JobPosting, SearchCriteria
from job_sources.browser import BrowserJobSource


class LiepinJobSource(BrowserJobSource):
    name = "liepin"          # 与 config/job_sources.json 启用名一致
    label = "猎聘"

    base_url = "https://www.liepin.com"
    card_selector = ".job-card-box"   # TODO: 按猎聘真实卡片选择器调整
    max_pages = 3
    page_delay = 3.0
    max_jobs = 30

    def cookie_env_names(self) -> List[str]:
        # 猎聘登录态环境变量名（同样仅从环境变量读取）
        return ["LIEPIN_COOKIE", "LIEPIN_COOKIE_FILE"]

    def build_search_urls(self, criteria: SearchCriteria) -> List[str]:
        # TODO: 按猎聘搜索页 URL 规则拼装（关键词 / 城市参数名可能不同）
        kw = (criteria.keywords[0] if criteria.keywords else "前端开发")
        city = criteria.city or ""
        from urllib.parse import quote

        return [f"{self.base_url}/zhaopin/?key={quote(kw)}&city={quote(city)}"]

    def parse_job_card(self, card) -> Optional[JobPosting]:
        # TODO: 按猎聘卡片真实 DOM 解析；可参考 boss.parse_boss_card_text 的纯函数思路做可单测解析
        try:
            text = card.inner_text()
        except Exception:
            return None
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return None
        return JobPosting(
            title=lines[0],
            company=lines[1] if len(lines) > 1 else "",
            location="",
            salary="",
            description=text,
            source=self.name,
        )
