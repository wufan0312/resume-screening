"""求职投递智能体（Agent）核心逻辑。

该 Agent 服务于正在找工作的求职者：
- 可接收用户粘贴的简历文本，或通过解析工具读取简历文件(URL)内容；
- 基于简历与求职偏好，自动检索多平台岗位并匹配打分、排序；
- 生成自然得体的打招呼语与投递建议（当前为人工在环，由求职者确认后实际投递）。
"""
import os
import json
from typing import Annotated

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage

from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory.memory_saver import get_memory_saver

from tools.resume_parser import parse_resume_file
from tools.job_search import find_matching_jobs
from tools.delivery import list_my_applications, update_application_status

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 30 轮对话 (60 条消息)，便于多份简历批量筛选
MAX_MESSAGES = 60


def _windowed_messages(old, new):
    """滑动窗口：只保留最近 MAX_MESSAGES 条消息"""
    return add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


def register_agent_tools():
    """返回本 Agent 使用的全部工具列表。"""
    return [
        parse_resume_file,
        find_matching_jobs,
        list_my_applications,
        update_application_status,
    ]


def build_agent(ctx=None):
    """构建并返回简历筛选 Agent 实例。"""
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    llm = ChatOpenAI(
        model=cfg["config"].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg["config"].get("temperature", 0.7),
        streaming=True,
        timeout=cfg["config"].get("timeout", 600),
        extra_body={
            "thinking": {
                "type": cfg["config"].get("thinking", "disabled")
            }
        },
        default_headers=default_headers(ctx) if ctx else {},
    )

    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=register_agent_tools(),
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
    )