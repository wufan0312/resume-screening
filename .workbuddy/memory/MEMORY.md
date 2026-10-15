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

## 运行与部署（Coze Vibe Coding）

- 项目即 Coze Vibe Coding 工程：`.coze`(entrypoint=src/main.py, run=scripts/http_run.sh) 依赖 coze_coding_utils/cozeloop/coze_workload_identity，**本地无法跑完整服务**，须进扣子空间运行/部署。
- 智能体 vs 工作流由 `graph_helper.is_agent_proj()` 决定（取扣子项目类型设置），仓库两套入口都在（agents/agent.py、graphs/graph.py）。
- LLM 走 Coze 集成通道（COZE_WORKLOAD_IDENTITY_API_KEY / COZE_INTEGRATION_MODEL_BASE_URL 自动注入），模型见 config/agent_llm_config.json。
- DB：`get_db_url()` 读 PGDATABASE_URL（Coze 注入）。投递表已在 main.py lifespan 幂等自动建（无需 manual init）。
- BOSS 源云端优雅降级：未装 playwright 或未配 Cookie 时 is_configured=False，`search_with_config` 自动跳过，不报错（playwright 懒加载不拖崩启动）。云端建议 enabled 不含 boss 或依赖降级。
