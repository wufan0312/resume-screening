"""Phase 2（BOSS 自动检索）不依赖网络的单元验证。

覆盖：城市码映射、搜索 URL 构造、卡片纯文本解析、未配置源自动跳过。
真实浏览器抓取需在配置 Cookie 后手动验证（见 requirements-boss.txt）。
"""
import os
import sys

# 让 src 包可被导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from job_sources.boss import (
    BossJobSource,
    parse_boss_card_text,
    resolve_boss_city_code,
)
from job_sources.cities import detect_city
from job_sources.base import SearchCriteria
from job_sources.registry import search_with_config


def test_resolve_city_code():
    assert resolve_boss_city_code("深圳") == "101280600"
    assert resolve_boss_city_code("北京") == "101010100"
    assert resolve_boss_city_code("") == "100010000"  # 全国
    assert resolve_boss_city_code("火星") == "100010000"


def test_detect_city():
    assert detect_city("前端+AI，深圳，20-30K") == "深圳"
    assert detect_city("上海 全栈") == "上海"
    assert detect_city("没有城市信息") == ""


def test_build_search_urls():
    src = BossJobSource()
    urls = src.build_search_urls(
        SearchCriteria(keywords=["前端开发", "AI应用"], city="深圳")
    )
    assert len(urls) == 2
    assert all("city=101280600" in u for u in urls)
    assert "query=" in urls[0]


def test_build_search_urls_from_raw_fallback():
    src = BossJobSource()
    # 无结构化关键词时，从原始偏好切分（仍受长度/数量限制）
    urls = src.build_search_urls(
        SearchCriteria(raw_preferences="前端+AI，深圳，20-30K")
    )
    assert len(urls) >= 1
    assert "city=101280600" in urls[0]


_SAMPLE_CARD = """高级前端开发工程师
示例科技
20-35K·14薪
深圳·南山区
5-10年 | 本科
职位描述：
1. 精通 React、Next.js、TypeScript，有大型 B 端项目经验；
2. 熟悉 LangGraph / FastAPI，有 AI Agent 落地经验者优先。
立即沟通"""


def test_parse_boss_card_text():
    job = parse_boss_card_text(_SAMPLE_CARD, url="https://www.zhipin.com/x", source="boss")
    assert job is not None
    assert job.title == "高级前端开发工程师"
    assert job.company == "示例科技"
    assert job.location == "深圳·南山区"
    assert job.salary == "20-35K"
    assert "React" in job.description
    assert job.source == "boss"
    assert job.url.startswith("https://www.zhipin.com")


def test_is_configured_without_cookie():
    src = BossJobSource()
    # 确保没有相关环境变量
    for k in ("BOSS_COOKIE", "ZHIPIN_COOKIE", "BOSS_COOKIE_FILE", "ZHIPIN_COOKIE_FILE"):
        os.environ.pop(k, None)
    assert src.is_configured() is False


def test_is_configured_with_cookie():
    os.environ["BOSS_COOKIE"] = "a=b; c=d"
    try:
        # 有 Cookie 是必要条件，但仍需 Playwright 可用才算「已配置」
        has_pw = False
        try:
            import importlib

            importlib.import_module("playwright")
            has_pw = True
        except Exception:
            has_pw = False
        assert BossJobSource().is_configured() is has_pw
    finally:
        os.environ.pop("BOSS_COOKIE", None)


def test_search_with_config_skips_unconfigured_boss():
    # 不设置 BOSS Cookie：boss 应被跳过，mock 仍返回数据
    for k in ("BOSS_COOKIE", "ZHIPIN_COOKIE", "BOSS_COOKIE_FILE", "ZHIPIN_COOKIE_FILE"):
        os.environ.pop(k, None)
    postings = search_with_config(SearchCriteria(raw_preferences="前端 深圳"))
    assert postings, "mock 源应返回示例岗位"
    sources = {p.source for p in postings}
    assert "boss" not in sources, "未配置 Cookie 时不应出现 BOSS 岗位"
    assert "mock" in sources


if __name__ == "__main__":
    test_resolve_city_code()
    test_detect_city()
    test_build_search_urls()
    test_build_search_urls_from_raw_fallback()
    test_parse_boss_card_text()
    test_is_configured_without_cookie()
    test_is_configured_with_cookie()
    test_search_with_config_skips_unconfigured_boss()
    print("ALL_BOSS_TESTS_PASSED")
