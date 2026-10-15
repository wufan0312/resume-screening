# 投递简历智能体（Job Delivery Agent）

求职者视角的 AI 求职助手。上传一份简历 + 求职偏好，自动在招聘平台检索匹配岗位、基于「简历 vs 岗位 JD」翻转评分匹配度、生成定制打招呼语，并把「待投递」清单落库，最终由求职者人工在环完成实际投递与状态追踪。

> 本项目由 Coze Vibe Coding 模板改造而来：原模板是「HR 简历筛选」视角，本仓库将其翻转为「求职者投递」视角，并补齐岗位发现、匹配、投递执行、状态追踪等模块。

## 核心特性

- **视角翻转**：从「JD + N 份简历 → 排名谁该面试」改为「我的 1 份简历 → 推荐岗位 + 匹配分析 + 投递追踪」。
- **可插拔招聘数据源（不写死 BOSS）**：所有平台脏活在 `BrowserJobSource` 基类；新增一个招聘网站 = 1 个子类 + 注册 + 配置，核心流程零改动（内置 BOSS 直聘、猎聘模板、手动导入、Mock）。
- **自动岗位发现**：基于简历画像抽取的关键词（岗位方向 + 技能）与城市，跨多平台自动检索，无需逐条手动粘贴 JD。
- **翻转评分**：简历画像 vs 岗位 JD → 匹配度 0-100 + 推荐/不推荐 + 匹配点/差距点。
- **定制招呼语**：针对每个推荐岗位生成自然的打招呼语草稿（人工在环使用）。
- **投递状态追踪**：推荐岗位落库为「待投递」记录，支持回写 已读 / 已回 / 面试 / 拒信 / 已撤 等状态并统计。
- **Coze 原生**：标准 Coze Vibe Coding 项目，同时支持「智能体（对话）」与「工作流（一次性流程）」两种入口。

## 工作流

```
简历画像 → 岗位发现（多平台可插拔）→ 岗位匹配（翻转评分）
        → 生成招呼语 → 投递执行（人工在环，落库「待投递」）
        → 状态追踪 → 输出报告（推荐清单 + 匹配分析 + 招呼语 + 投递状态）
```

- **智能体模式**：对话式求职顾问，内部调用检索/匹配工具跑完整流程。
- **工作流模式**：一次性流水线，输入简历文本 + 求职偏好，输出报告。

## 目录结构

```
src/
  main.py                  # 服务入口（Coze 标准 /run /stream_run /v1/chat/completions 等契约）
  agents/agent.py          # 求职顾问 Agent（对话入口 + 工具注册）
  graphs/
    graph.py               # 求职者投递工作流（画像→发现→匹配→招呼语→投递→报告）
    llm_client.py          # LLM JSON 调用封装
  job_sources/             # 可插拔招聘数据源层（核心，不依赖具体平台）
    base.py                # JobPosting / SearchCriteria / BaseJobSource 抽象
    registry.py            # 注册表 + search_with_config（配置注入 + 未配置源自动跳过）
    browser.py             # 浏览器类基类（Playwright 懒加载 / 登录态 / 翻页限流 / 容错）
    cities.py              # 城市识别
    boss.py                # BOSS 直聘真实检索实现
    example_liepin.py      # 猎聘扩展模板（如何加新网站的示例）
    manual.py / mock.py    # 手动导入 / 示例数据源
  tools/
    resume_parser.py       # 简历文件解析
    job_match.py           # 翻转评分
    greeting_drafter.py    # 招呼语生成
    job_search.py          # 检索 + 匹配一体化工具（Agent 用）
    delivery.py            # 投递清单 / 状态更新工具
  storage/database/
    db.py                  # 同步 SQLAlchemy 连接
    models/delivery.py     # Application ORM + DeliveryStatus 枚举
    repo/delivery_repo.py  # 投递仓储层（落库 / 列表 / 改状态 / 统计 / 建表）
config/
  agent_llm_config.json    # 求职顾问提示词与模型配置
  job_sources.json         # 数据源启用配置（enabled + per-source 参数）
scripts/
  delivery_cli.py          # 投递记录管理 CLI（init/list/status/stats）
  http_run.sh / local_run.sh / setup.sh / pack.sh   # Coze 运行与部署脚本
tests/
  test_boss_source.py      # BOSS 源单测（URL 构造 / 卡片解析 / 未配置跳过）
  test_delivery_repo.py     # 投递仓储单测（内存 SQLite）
```

## 在 Coze 上运行

1. 将代码关联进 Coze Vibe Coding（关联 Git 仓库联网导入，或 Web IDE 编辑）。
2. 项目类型选择「智能体」或「工作流」——`is_agent_proj()` 据此选择入口，两套代码均已就绪。
3. 环境变量：LLM 密钥与 `PGDATABASE_URL` 由 Coze 运行时自动注入；敏感项（如本地自托管要用 `BOSS_COOKIE`）在「项目环境变量」中声明，**不要写入代码**。
4. 点击「运行 / 发布」→ Coze 自动执行 `setup.sh` + `http_run.sh` 起服务。
   - 投递状态表随服务启动**自动建表**（幂等），无需手动 `init`。
   - BOSS 源在无浏览器环境（默认未安装 Playwright）下**自动跳过、不报错**。

HTTP 调用示例（工作流）：

```
POST /run
{
  "my_resume": "（粘贴简历文本）",
  "job_preferences": {"keywords": ["前端", "AI"], "city": "深圳", "salary": "20-35K"},
  "jobs_input": [],
  "sources": ["mock"]
}
```

## 本地验证（不依赖 Coze 库）

完整服务依赖 Coze 运行时（`coze_coding_utils` 等仅在云端存在），本地只能运行不依赖 Coze 的部分：

```bash
# 单测（需 sqlalchemy，建议 Python 3.12）
python tests/test_boss_source.py
python tests/test_delivery_repo.py

# 投递记录管理（需配置 PG 或本地 SQLite）
python scripts/delivery_cli.py init    # 建表
python scripts/delivery_cli.py list    # 查看待投递清单
python scripts/delivery_cli.py status --id 3 --status delivered --note "已投"
python scripts/delivery_cli.py stats   # 按状态统计
```

## 配置：config/job_sources.json

```json
{
  "enabled": ["mock", "manual"],
  "sources": {
    "boss": {
      "headless": true,
      "max_jobs": 30,
      "max_pages": 3,
      "page_delay": 3.0
    }
  }
}
```

- `enabled`：启用的数据源名（云端建议 `["mock","manual"]`，本地装好 Playwright + Cookie 后加 `"boss"`）。
- `sources.<name>`：per-source 运行参数（翻页限流、无头模式等）。

## 如何新增一个招聘网站（BOSS 不写死）

只需三步，核心流程零改动：

1. 在 `src/job_sources/` 新建 `class XxxJobSource(BrowserJobSource)`，实现 `build_search_urls(profile, criteria)` 与 `parse_job_card(element)` 两个方法。
2. 在 `src/job_sources/__init__.py` 中 `registry.register(XxxJobSource())`。
3. 在 `config/job_sources.json` 的 `enabled` 加入 `"xxx"`。

参考 `example_liepin.py`（猎聘模板）。

## 合规提醒

- BOSS 自动检索默认 `page_delay=3s / max_pages=3 / max_jobs=30`，请保持低频，仅用于本人账号、本人求职。
- 投递采用**人工在环**：AI 产出清单与招呼语，由求职者本人在平台完成实际投递动作，系统仅做状态记录，规避封号与合规风险。

## 路线图

- Phase 1 匹配引擎（简历画像 + 翻转评分 + 排名报告）：已完成
- Phase 2 岗位发现（BOSS 自动检索 + 可插拔数据源层）：已完成
- Phase 3 投递执行 + 状态追踪（人工在环 + 落库 + CLI）：已完成
- Phase 4 每日汇报复盘（基于状态统计自动汇总当日投递进展）：待做

## 技术栈

FastAPI · LangGraph · SQLAlchemy 2.0 · Playwright（可选，浏览器类数据源）· Coze Vibe Coding 运行时
