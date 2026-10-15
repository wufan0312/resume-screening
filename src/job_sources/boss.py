"""BOSS直聘数据源（Phase 2 实现）。

能力：
  1. 基于简历画像 + 求职偏好，自动在 BOSS 上检索匹配岗位
     （不是逐条 JD 手动匹配，而是「用我的简历去 BOSS 上找匹配的岗」）；
  2. 通过 Playwright 打开 BOSS 搜索页并抓取岗位卡片；
  3. 登录态（Cookie）仅从环境变量读取，不入库、不硬编码；
  4. 遵守限流（默认 3s/页、最多 3 页、最多 30 条），降低风控风险。

接入方式：
  - 在 config/job_sources.json 的 enabled 中加入 "boss" 即启用；
  - 设置环境变量 BOSS_COOKIE（或 ZHIPIN_COOKIE）为你的登录态：
      * 推荐：浏览器开发者工具「Application → Cookies」导出为 JSON 数组；
      * 也支持 "k=v; k2=v2" 形式的 Cookie 头字符串；
      * 或把上述内容写入文件，用 BOSS_COOKIE_FILE / ZHIPIN_COOKIE_FILE 指向路径。
  - 未配置 Cookie 时 is_configured() 返回 False，search_all 会自动跳过并提示，
    不影响 mock / manual 等其它源。

⚠️ 合规：本能力仅用于本人账号、本人求职的自动化辅助，请保持低频，遵守 BOSS 服务条款。
"""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote

from job_sources.base import JobPosting, SearchCriteria
from job_sources.browser import BrowserJobSource
from job_sources.cities import detect_city

# BOSS 城市名 -> cityCode（常用；缺失时回退「全国 100010000」）
_BOSS_CITY_CODES: dict[str, str] = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "西安": "101110100",
    "苏州": "101190400",
    "重庆": "101040100",
    "长沙": "101250100",
    "天津": "101030100",
    "厦门": "101230200",
    "东莞": "101281600",
    "宁波": "101210400",
    "佛山": "101280800",
    "合肥": "101220100",
    "青岛": "101200200",
    "郑州": "101180100",
    "无锡": "101190200",
    "大连": "101070100",
    "福州": "101230100",
    "济南": "101120100",
    "昆明": "101290100",
    "哈尔滨": "101050100",
    "沈阳": "101080100",
    "石家庄": "101090100",
    "南昌": "101240100",
    "南宁": "101300100",
    "常州": "101191100",
    "珠海": "101281000",
    "中山": "101281100",
    "惠州": "101281500",
    "嘉兴": "101210300",
    "南通": "101190500",
}

_SALARY_RE = re.compile(r"(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*[Kk万])")
_AREA_RE = re.compile(r"([\u4e00-\u9fa5]{2,8}?(?:·|/|-|\s)[\u4e00-\u9fa5]{1,8}?(?:区|县|市))")
_EXP_RE = re.compile(r"(\d+\s*-\s*\d+\s*年|\d+\s*年以下|\d+\s*年以上|经验不限|应届)")


def resolve_boss_city_code(city: str) -> str:
    """把城市名解析为 BOSS 的 cityCode；空或未知回退「全国」。"""
    if not city:
        return "100010000"
    for name, code in _BOSS_CITY_CODES.items():
        if name in city:
            return code
    return "100010000"


def parse_boss_card_text(text: str, url: str = "", source: str = "boss") -> Optional[JobPosting]:
    """从 BOSS 岗位卡片的纯文本（card.inner_text()）解析出 JobPosting。

    把解析逻辑做成「纯函数」是为了可单测：给它一段仿真卡片文本即可验证，
    不必真正启动浏览器。BOSS 页面结构可能变化，若字段错位，优先微调本函数。
    """
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None

    title = lines[0]
    salary = ""
    location = ""
    experience = ""
    for ln in lines:
        m = _SALARY_RE.search(ln)
        if m and not salary:
            salary = m.group(1).replace(" ", "")
        # 地点：必须形如「城市·区/市」（避免误命中薪资里的「·」）
        m_area = _AREA_RE.search(ln)
        if m_area and not location and ln != title:
            location = m_area.group(1)
        m2 = _EXP_RE.search(ln)
        if m2 and not experience:
            experience = m2.group(1)

    # 公司名：取一个「非标题/薪资/地点/经验」的较短行
    company = ""
    for ln in lines[1:]:
        if ln in (salary, location, experience):
            continue
        if _SALARY_RE.search(ln) or _AREA_RE.search(ln):
            continue
        if len(ln) <= 30 and "：" not in ln and ":" not in ln and not ln.startswith("职位") and not ln.startswith("职责"):
            company = ln
            break

    # 描述：从「职位描述 / 岗位职责」等标记之后收集；否则取公司名之后
    desc_start = None
    for i, ln in enumerate(lines):
        if ln.startswith(("职位描述", "岗位描述", "岗位职责")) or "职位描述：" in ln or "职责" in ln:
            desc_start = i
            break
    if desc_start is None:
        try:
            ci = lines.index(company) if company in lines else 1
            desc_start = ci + 1
        except Exception:
            desc_start = 2
    description = " ".join(lines[desc_start:]).strip()

    extra: dict = {}
    if experience:
        extra["experience"] = experience
    return JobPosting(
        title=title,
        company=company,
        location=location,
        salary=salary,
        description=description,
        source=source,
        url=url,
        extra=extra,
    )


class BossJobSource(BrowserJobSource):
    name = "boss"
    label = "BOSS直聘"

    base_url = "https://www.zhipin.com"
    card_selector = ".job-card-wrapper"
    max_pages = 3
    page_delay = 3.0
    max_jobs = 30
    headless = True

    def cookie_env_names(self) -> List[str]:
        return ["BOSS_COOKIE", "ZHIPIN_COOKIE", "BOSS_COOKIE_FILE", "ZHIPIN_COOKIE_FILE"]

    def build_search_urls(self, criteria: SearchCriteria) -> List[str]:
        city_code = resolve_boss_city_code(criteria.city or detect_city(criteria.raw_preferences))
        keywords = list(criteria.keywords or [])
        # 兜底：没有结构化关键词时，从原始偏好粗略切分（取前 3 个词）
        if not keywords and criteria.raw_preferences:
            keywords = [
                k.strip()
                for k in re.split(r"[,，/、+ ]+", criteria.raw_preferences)
                if k.strip() and len(k.strip()) <= 12
            ][:3]
        if not keywords:
            keywords = ["前端开发"]
        urls: List[str] = []
        for kw in keywords[:3]:
            q = quote(kw)
            urls.append(f"{self.base_url}/web/geek/job?query={q}&city={city_code}")
        return urls

    def parse_job_card(self, card) -> Optional[JobPosting]:
        url = ""
        try:
            a = card.query_selector('a[href*="job_detail"]')
            if a is not None:
                href = a.get_attribute("href") or ""
                if href:
                    url = href if href.startswith("http") else f"{self.base_url}{href}"
        except Exception:
            url = ""
        try:
            text = card.inner_text()
        except Exception:
            return None
        return parse_boss_card_text(text, url, self.name)
