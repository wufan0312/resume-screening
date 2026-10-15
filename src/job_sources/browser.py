"""基于 Playwright 的浏览器类招聘数据源通用基类。

设计目标：把「浏览器启动、登录态注入、翻页、限流、容错」等所有脏活统一收口，
让对接一个新招聘网站变得极简——子类只需实现：

    1. build_search_urls(criteria) -> List[str]   怎么拼搜索页 URL
    2. parse_job_card(card) -> Optional[JobPosting]  怎么从一张卡片解析出岗位

其余（启动浏览器、注入 Cookie、翻页、限流、登录墙检测、异常兜底）都由本类完成。

⚠️ 合规提醒（请务必阅读）：
- 自动检索会占用平台服务器资源，请务必保持低频（默认 page_delay=3s、max_pages=3、
  max_jobs=30），切勿并发、切勿高频刷接口，避免账号被风控 / 封禁。
- 登录态（Cookie）仅从环境变量读取，**绝不**写入代码或数据库。
- 本能力用于你「本人账号、本人求职」的自动化辅助，请遵守目标平台服务条款。
- BOSS 等平台页面结构会变动，若选择器失效，优先调整子类的 card_selector / 解析函数。
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Any, Dict, List, Optional

from job_sources.base import BaseJobSource, JobPosting, SearchCriteria

# 浏览器指纹：尽量贴近真实桌面 Chrome，降低被识别为自动化的概率
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_STEALTH_JS = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    "Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });"
    "Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });"
)


_PLAYWRIGHT_OK: "bool | None" = None


def _playwright_available() -> bool:
    """探测 Playwright 是否可用（缓存结果）。云端沙箱未安装时返回 False。"""
    global _PLAYWRIGHT_OK
    if _PLAYWRIGHT_OK is None:
        try:
            import playwright  # noqa: F401

            _PLAYWRIGHT_OK = True
        except Exception:
            _PLAYWRIGHT_OK = False
    return _PLAYWRIGHT_OK


class BrowserJobSource(BaseJobSource):
    """浏览器类数据源基类。需配合 Playwright 使用（pip install playwright && playwright install chromium）。"""

    # —— 子类可覆盖的平台参数 ——
    base_url: str = ""
    card_selector: str = ""          # 岗位卡片的 CSS 选择器
    max_pages: int = 3              # 单个关键词最多翻几页
    page_delay: float = 3.0         # 翻页之间的礼貌等待（秒）
    max_jobs: int = 30              # 单次检索最多采集岗位数（控制频率）
    headless: bool = True           # 是否无头模式（调试时可设为 False 看过程）

    def cookie_env_names(self) -> List[str]:
        """返回用于读取登录态的环境变量名（按顺序尝试）。子类覆盖。"""
        return ["JOB_SOURCE_COOKIE"]

    # —— 运行期配置（来自 config/job_sources.json 的 sources.<name>） ——
    def configure(self, cfg: Dict[str, Any]) -> None:
        if not isinstance(cfg, dict):
            return
        if "headless" in cfg:
            self.headless = bool(cfg["headless"])
        if "max_jobs" in cfg:
            self.max_jobs = int(cfg["max_jobs"])
        if "max_pages" in cfg:
            self.max_pages = int(cfg["max_pages"])
        if "page_delay" in cfg:
            self.page_delay = float(cfg["page_delay"])

    def is_configured(self) -> bool:
        """未安装 Playwright 或未配置登录态 Cookie 时返回 False，
        使 search_with_config 自动跳过并提示——云端无浏览器依赖时优雅降级，不报错。"""
        if not _playwright_available():
            return False
        return any(os.environ.get(n) for n in self.cookie_env_names())

    # —— 子类必须实现 ——
    def build_search_urls(self, criteria: SearchCriteria) -> List[str]:
        raise NotImplementedError

    def parse_job_card(self, card) -> Optional[JobPosting]:
        raise NotImplementedError

    # —— 通用抓取流程（子类一般无需覆盖） ——
    def search(self, criteria: SearchCriteria) -> List[JobPosting]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                f"[{self.label}] 未安装 Playwright。请执行："
                "pip install playwright && playwright install chromium"
            ) from e

        if not self.is_configured():
            names = " / ".join(self.cookie_env_names())
            raise RuntimeError(
                f"[{self.label}] 未配置登录态（缺少 Cookie 环境变量 {names}）。"
                "请配置后再在 config/job_sources.json 启用本源。"
            )

        urls = self.build_search_urls(criteria)
        if not urls:
            return []

        collected: List[JobPosting] = []
        seen = set()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            context.add_init_script(_STEALTH_JS)
            cookies = self._load_cookies()
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    # 个别字段缺失不应阻断整体；交由平台自行处理
                    pass
            page = context.new_page()
            page.set_default_timeout(20000)

            for url in urls:
                if len(collected) >= self.max_jobs:
                    break
                for page_idx in range(1, self.max_pages + 1):
                    page_url = self._with_page(url, page_idx)
                    try:
                        page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
                    except Exception:
                        break
                    self._wait_for_cards(page)
                    if self._is_login_wall(page):
                        raise RuntimeError(
                            f"[{self.label}] 打开页面后检测到登录墙，请检查 Cookie 是否"
                            "有效 / 是否已过期。"
                        )
                    cards = page.query_selector_all(self.card_selector)
                    if not cards:
                        break
                    for card in cards:
                        if len(collected) >= self.max_jobs:
                            break
                        try:
                            job = self.parse_job_card(card)
                        except Exception:
                            job = None
                        if not job:
                            continue
                        key = (job.title, job.company, job.location)
                        if key in seen:
                            continue
                        seen.add(key)
                        collected.append(job)
                    if not self._has_next(page):
                        break
                    self._polite_sleep()
            browser.close()
        return collected

    # —— 可覆盖的钩子 ——
    def _with_page(self, url: str, page_idx: int) -> str:
        """拼接翻页参数。默认用 &page=N。"""
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}page={page_idx}"

    def _wait_for_cards(self, page) -> None:
        try:
            page.wait_for_selector(self.card_selector, timeout=10000)
        except Exception:
            pass

    def _is_login_wall(self, page) -> bool:
        try:
            text = page.inner_text().replace(" ", "")
        except Exception:
            return False
        return ("扫码登录" in text) or ("请登录" in text) or ("登录BOSS" in text)

    def _has_next(self, page) -> bool:
        """默认始终尝试翻页（直到 max_pages 或空卡片）。子类可精确识别「下一页」按钮。"""
        return True

    def _polite_sleep(self) -> None:
        time.sleep(self.page_delay + random.uniform(0, 1.5))

    # —— Cookie 加载（仅从环境变量，支持字符串 / 文件 / JSON / header 串） ——
    def _load_cookies(self) -> List[Dict[str, Any]]:
        raw = ""
        for name in self.cookie_env_names():
            val = os.environ.get(name)
            if val:
                raw = val
                break
        if not raw:
            return []
        # 若环境变量指向一个文件，读取文件内容
        if raw.endswith((".json", ".txt")) and os.path.isfile(raw):
            try:
                with open(raw, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
            except Exception:
                return []
        # 1) JSON 数组：[{name, value, domain, path}, ...]
        if raw.lstrip().startswith("["):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [c for c in data if isinstance(c, dict)]
            except Exception:
                pass
        # 2) Cookie header 串：k1=v1; k2=v2
        host = ""
        try:
            from urllib.parse import urlparse

            host = urlparse(self.base_url).netloc
        except Exception:
            host = ""
        cookies = []
        for part in raw.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            cookies.append(
                {
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": host,
                    "path": "/",
                }
            )
        return cookies
