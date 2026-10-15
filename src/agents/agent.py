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

from storage.memory.memory_saver import get_memory_saver

from tools.resume_parser import parse_resume_file
from tools.job_search import find_matching_jobs
from tools.delivery import list_my_applications, update_application_status

# 配置目录：相对项目根（src/.. 的上一级/config）
_CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config"))
LLM_CONFIG = os.path.join(_CONFIG_DIR, "agent_llm_config.json")

# 智谱 OpenAI 兼容基址（默认）；也可通过 ZHIPU_BASE_URL / OPENAI_BASE_URL 覆盖
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

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


def build_agent():
    """构建并返回求职投递 Agent 实例（智谱 GLM / 任意 OpenAI 兼容）。"""
    with open(LLM_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("ZHIPU_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )
    thinking = cfg["config"].get("thinking", "disabled")

    kwargs: dict = dict(
        model=cfg["config"].get("model", "glm-4-flash"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg["config"].get("temperature", 0.7),
        streaming=True,
        timeout=cfg["config"].get("timeout", 600),
    )
    if thinking and thinking != "disabled":
        kwargs["extra_body"] = {"thinking": {"type": thinking}}

    llm = ChatOpenAI(**kwargs)

    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=register_agent_tools(),
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
    )