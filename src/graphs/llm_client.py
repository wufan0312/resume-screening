"""工作流 LLM 调用辅助模块。

基于项目 LLM 集成配置（config/agent_llm_config.json）与环境的模型基址，
为简历筛选工作流的各节点提供统一的模型调用与 JSON 解析能力。
与 Agent 使用同一可用通道（ChatOpenAI + COZE_INTEGRATION_MODEL_BASE_URL）。
"""
import json
import os
import re

from langchain_openai import ChatOpenAI
from coze_coding_utils.runtime_ctx.context import default_headers, new_context
from coze_coding_utils.log.write_log import request_context

WORKSPACE_PATH = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
_LLM_CONFIG_PATH = os.path.join(WORKSPACE_PATH, "config", "agent_llm_config.json")


def _get_text(content) -> str:
    """安全地从模型响应中提取纯文本（兼容 str / list[dict] / list[str]）。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        if content and isinstance(content[0], str):
            return " ".join(content).strip()
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return " ".join(parts).strip()
    return str(content)


def _get_llm() -> ChatOpenAI:
    """依据项目配置构建与 Agent 一致的 ChatOpenAI 实例。"""
    try:
        with open(_LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    model = cfg.get("config", {}).get("model", "doubao-seed-2-0-pro-260215")
    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")
    ctx = request_context.get() or new_context(method="resume_screening_workflow")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=cfg.get("config", {}).get("temperature", 0.3),
        timeout=cfg.get("config", {}).get("timeout", 600),
        extra_body={
            "thinking": {"type": cfg.get("config", {}).get("thinking", "disabled")}
        },
        default_headers=default_headers(ctx) if ctx else {},
    )


def call_llm(system_prompt: str, user_prompt: str, *, temperature: float = 0.3) -> str:
    """调用大模型，返回纯文本响应。"""
    llm = _get_llm()
    response = llm.invoke(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    return _get_text(getattr(response, "content", ""))


def call_llm_json(system_prompt: str, user_prompt: str, *, temperature: float = 0.2) -> dict:
    """调用大模型并要求返回 JSON，自动从中提取合法 JSON 对象。"""
    raw = call_llm(system_prompt, user_prompt, temperature=temperature)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"error": "failed to parse model output", "raw": raw[:500]}