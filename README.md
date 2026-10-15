# 投递简历智能体（Job Delivery Agent）

求职者视角的 AI 求职助手。上传一份简历 + 求职偏好，自动在招聘平台检索匹配岗位、基于「简历 vs 岗位 JD」翻转评分匹配度、生成定制打招呼语，并把「待投递」清单落库，最终由求职者人工在环完成实际投递与状态追踪。

> 本项目由 Coze Vibe Coding 模板改造而来，已**完全去除 Coze 依赖**，可纯本地运行 / 自托管，不锁定任何云平台。

## 核心特性

- **视角翻转**：从「JD + N 份简历 → 排名谁该面试」改为「我的 1 份简历 → 推荐岗位 + 匹配分析 + 投递追踪」。
- **可插拔招聘数据源（不写死 BOSS）**：所有平台脏活在 `BrowserJobSource` 基类；新增一个招聘网站 = 1 个子类 + 注册 + 配置，核心流程零改动（内置 BOSS 直聘、猎聘模板、手动导入、Mock）。
- **自动岗位发现**：基于简历画像抽取的关键词（岗位方向 + 技能）与城市，跨多平台自动检索，无需逐条手动粘贴 JD。
- **翻转评分**：简历画像 vs 岗位 JD → 匹配度 0-100 + 推荐/不推荐 + 匹配点/差距点。
- **定制招呼语**：针对每个推荐岗位生成自然的打招呼语草稿（人工在环使用）。
- **投递状态追踪**：推荐岗位落库为「待投递」记录，支持回写 已读 / 已回 / 面试 / 拒信 / 已撤 等状态并统计。
- **纯本地可运行**：标准 FastAPI + LangGraph，无平台锁定，LLM 走智谱 GLM-4-Flash（或任意 OpenAI 兼容），数据库默认本地 SQLite。

## 工作流

```
简历画像 → 岗位发现（多平台可插拔）→ 岗位匹配（翻转评分）
        → 生成招呼语 → 投递执行（人工在环，落库「待投递」）
        → 状态追踪 → 输出报告（推荐清单 + 匹配分析 + 招呼语 + 投递状态）
```

- **Workflow 模式**（默认）：一次性流水线，输入简历文本 + 求职偏好，输出报告。
- **Agent 模式**：对话式求职顾问（设置 `APP_MODE=agent`），内部调用检索/匹配工具跑完整流程。

## 目录结构

```
src/
  main.py                  # 纯 FastAPI 服务入口（/run /stream_run /v1/chat/completions /health /graph_parameter）
  agents/agent.py          # 求职顾问 Agent（对话入口 + 工具注册）
  graphs/
    graph.py               # 求职者投递工作流（画像→发现→匹配→招呼语→投递→报告）
    llm_client.py          # LLM 调用封装（ChatOpenAI，智谱/OpenAI 兼容）
  job_sources/             # 可插拔招聘数据源层（核心，不依赖具体平台）
    base.py                # JobPosting / SearchCriteria / BaseJobSource 抽象
    registry.py            # 注册表 + search_with_config（配置注入 + 未配置源自动跳过）
    browser.py             # 浏览器类基类（Playwright 懒加载 / 登录态 / 翻页限流 / 容错）
    cities.py              # 城市识别
    boss.py                # BOSS 直聘真实检索实现
    example_liepin.py      # 猎聘扩展模板（如何加新网站的示例）
    manual.py / mock.py    # 手动导入 / 示例数据源
  tools/
    resume_parser.py       # 简历文件解析（httpx 下载 + PDF/Word/TXT 本地解析）
    job_match.py           # 翻转评分
    greeting_drafter.py    # 招呼语生成
    job_search.py          # 检索 + 匹配一体化工具（Agent 用）
    delivery.py            # 投递清单 / 状态更新工具
  storage/database/
    db.py                  # SQLAlchemy 连接（默认本地 SQLite，可选 PostgreSQL）
    models/delivery.py     # Application ORM + DeliveryStatus 枚举
    repo/delivery_repo.py  # 投递仓储层（落库 / 列表 / 改状态 / 统计 / 建表）
config/
  agent_llm_config.json    # LLM 模型与求职顾问提示词配置
  job_sources.json         # 数据源启用配置（enabled + per-source 参数）
scripts/
  run_local.sh             # 本地启动服务（设置 PYTHONPATH + 加载 .env）
  delivery_cli.py          # 投递记录管理 CLI（init/list/status/stats）
requirements.txt          # 依赖清单（已去除 coze-*）
.env.example              # 环境变量示例
```

## 本地运行

### 1. 安装依赖

```bash
# 方式 A（pip）
pip install -r requirements.txt

# 方式 B（uv，会按 pyproject.toml 重新生成 lock）
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写：
#   ZHIPU_API_KEY=你的智谱API Key        # 智谱 GLM-4-Flash，OpenAI 兼容
#   APP_MODE=workflow                    # 或 agent
#   PGDATABASE_URL=                       # 留空即用本地 SQLite（./delivery.db）
```

### 3. 启动服务

```bash
# 推荐：一键脚本（自动设置 PYTHONPATH 与 .env）
bash scripts/run_local.sh -p 5000
# 或：APP_MODE=agent bash scripts/run_local.sh

# 等价于：
# PYTHONPATH=src python -m main -m http -p 5000
```

启动后投递状态表会**自动建表**（默认落到本地 `./delivery.db`），无需手动 init。

### 4. 调用示例

```bash
# 一次性流水线（workflow）
curl -s -X POST http://localhost:5000/run \
  -H 'Content-Type: application/json' \
  -d '{"my_resume":"（粘贴简历文本）","job_preferences":{"keywords":["前端","AI"],"city":"深圳","salary":"20-35K"},"sources":["mock"]}'

# 健康检查
curl -s http://localhost:5000/health

# 查看输入输出 schema
curl -s http://localhost:5000/graph_parameter
```

命令行直接跑一次流水线（无需起服务）：

```bash
PYTHONPATH=src python -m main -m flow -i '{"my_resume":"...","job_preferences":"前端 AI 深圳"}'
```

### 5. 投递记录管理

```bash
PYTHONPATH=src python scripts/delivery_cli.py list
PYTHONPATH=src python scripts/delivery_cli.py status --id 3 --status delivered --note "已投"
PYTHONPATH=src python scripts/delivery_cli.py stats
```

## 配置：config/job_sources.json

```json
{
  "enabled": ["mock", "manual"],
  "sources": {
    "boss": { "headless": true, "max_jobs": 30, "max_pages": 3, "page_delay": 3.0 }
  }
}
```

- `enabled`：启用的数据源名（本地装好 Playwright + Cookie 后加 `"boss"`；云端/无浏览器环境会自动跳过）。
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
- 去 Coze 化（去除平台依赖，纯本地运行）：已完成
- Phase 4 每日汇报复盘（基于状态统计自动汇总当日投递进展）：待做

## 技术栈

FastAPI · LangGraph · SQLAlchemy 2.0 · httpx · Playwright（可选，浏览器类数据源）· 智谱 GLM-4-Flash（OpenAI 兼容）
