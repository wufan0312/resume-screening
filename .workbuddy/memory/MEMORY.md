# 项目长期记忆

## 目标与现状

- 用户目标：构建「投递简历」智能体（求职者视角），帮助求职者匹配岗位并完成投递/跟踪。
- 项目现状：已由原「简历筛选」（HR 视角）Coze 模板改造为「投递简历」智能体（求职者视角）；P1 匹配引擎 / P2 岗位发现(BOSS自动检索+可插拔数据源) / P3 投递执行+状态追踪 均已完成，P4 每日汇报复盘待做。
- 关键能力（已闭合原 gap）：翻转评分匹配、多平台自动岗位发现、人工在环投递、投递状态落库与统计。

## 可复用技术资产

- FastAPI + LangGraph 服务骨架（src/main.py）
- LLM JSON 调用封装（src/graphs/llm_client.py）
- 简历文件解析工具（src/tools/resume_parser.py）
- PostgreSQL/S3 存储接入（src/storage/）

## 注意事项

- README 已重写为求职者「投递简历智能体」项目描述（原「简历筛选」占位已作废）；核心提示词(config/agent_llm_config.json 的 sp)已是「求职顾问」。

## 改造方案（用户确认）

- 视角：求职者「投递简历智能体」。
- 关键决策：① 自动化程度=人工在环（不代投，规避封号/合规风险）；② 目标平台=BOSS直聘优先，但数据源层做成可插拔、不写死。
- 新工作流：简历画像 → 岗位发现(多平台) → 岗位匹配(翻转评分) → 生成招呼语 → [人工确认] 投递执行 → 状态追踪 → 报告。
- 四阶段：P1 匹配引擎 / P2 BOSS自动检索 / P3 投递执行+状态表 / P4 每日汇报复盘。

## 改造状态

- Phase 1 已实现：可插拔数据源层 src/job_sources/(base/registry/manual/mock/boss占位) + 配置驱动启用(config/job_sources.json)；翻转评分/招呼语/检索工具；求职者投递工作流 graph.py；求职顾问 Agent。
- Phase 2 已实现：BOSS 自动检索真实接入（src/job_sources/boss.py 继承 browser.py 基类），简历画像关键词/城市自动驱动多关键词搜索；未配 Cookie 自动跳过并提示；新增浏览器基类 browser.py、城市识别 cities.py、新站点模板 example_liepin.py；registry 增加 search_with_config（配置注入+未配置跳过）；graph 画像抽取关键词/城市增强。单测 tests/test_boss_source.py 全绿。
- Phase 3 已实现（人工在环）：投递状态数据模型 src/storage/database/models/delivery.py（Application ORM + DeliveryStatus 枚举 + 中文标签）；仓储层 repo/delivery_repo.py（persist_match_plan/list_applications/update_status/get_stats/create_delivery_tables，支持传入 session 便于 SQLite 单测）；graph 新增 delivery_node（匹配岗位→落库「待投递」记录，DB 不可用时降级内存清单）并接入边、报告增「四、投递清单（人工在环）」；tools/delivery.py（list_my_applications/update_application_status 工具）注册进 Agent；scripts/delivery_cli.py（init/list/status/stats）；单测 tests/test_delivery_repo.py 全绿（内存 SQLite）。
- 待办（P4）：每日汇报复盘（基于 get_stats 统计 + BOSS 每日投递进展自动汇总）。

## 运行与部署（纯本地，已去 Coze）

- 已完全去除 Coze 依赖：删除 `.coze` 文件、scripts 下 Coze 部署脚本、pyproject 的 4 个 coze-* 依赖、src 内所有 `coze_coding_utils`/`cozeloop`/`coze_workload_identity` 引用（src 下已 grep 确认无残留 import）；删除未使用的 src/storage/s3（coze 存储封装）；uv.lock 已删（用 uv 需重 `uv lock`）。
- 入口：`src/main.py` 纯 FastAPI+uvicorn，保留 `/run` `/stream_run` `/v1/chat/completions` `/health` `/graph_parameter`；去掉 `/async_run` `/cancel` `/task/{id}` 等 coze async_tasks 专属接口。本地启动：`bash scripts/run_local.sh`（设 PYTHONPATH=src + 加载 .env）；或 `PYTHONPATH=src python -m main -m http -p 5000`。
- LLM：智谱 GLM-4-Flash（OpenAI 兼容），密钥读 `ZHIPU_API_KEY` / `ZHIPU_BASE_URL`（兼容 `OPENAI_*`），模型见 config/agent_llm_config.json 的 `model=glm-4-flash`。
- DB：`get_db_url()` 优先读 `PGDATABASE_URL`，留空回退本地 SQLite（`./delivery.db`），零配置本地跑；投递表在 lifespan 幂等自动建。memory_saver 的 psycopg/postgres 依赖已懒加载，本地 SQLite 模式不引入 psycopg。
- 模式：`APP_MODE=workflow`（默认，一次性流水线）/ `agent`（对话式求职顾问）。
- BOSS 源优雅降级：未装 playwright 或未配 Cookie 时 `is_configured=False`，`search_with_config` 自动跳过，不报错（playwright 懒加载）。
- 依赖：`requirements.txt`（已去 coze，含 httpx/pypdf/docx2python 等）；本地跑建议 `pip install -r requirements.txt`。
