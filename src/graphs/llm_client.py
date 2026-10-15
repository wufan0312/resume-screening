"""工作流 LLM 调用辅助模块。

基于项目 LLM 配置（config/agent_llm_config.json）与本地环境变量，
为投递工作流的各节点提供统一的模型调用与 JSON 解析能力。
与 Agent 使用同一通道（ChatOpenAI，智谱 GLM / 任意 OpenAI 兼容，
见 ZHIPU_API_KEY / ZHIPU_BASE_URL）。
"""
import json
import os
import re

from langchain_openai import ChatOpenAI

# 配置目录：相对项目根（src/.. 的上一级/config）
_CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config"))
_LLM_CONFIG_PATH = os.path.join(_CONFIG_DIR, "agent_llm_config.json")

# 智谱 OpenAI 兼容基址（默认）；也可通过 ZHIPU_BASE_URL / OPENAI_BASE_URL 覆盖
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


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
    """依据项目配置构建 ChatOpenAI 实例（智谱 GLM / 任意 OpenAI 兼容）。"""
    try:
        with open(_LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    model = cfg.get("config", {}).get("model", "glm-4-flash")
    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("ZHIPU_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )
    thinking = cfg.get("config", {}).get("thinking", "disabled")

    kwargs: dict = dict(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=cfg.get("config", {}).get("temperature", 0.3),
        timeout=cfg.get("config", {}).get("timeout", 600),
    )
    # 仅当显式开启 thinking 时附加（智谱 GLM 等默认不支持，避免报错）
    if thinking and thinking != "disabled":
        kwargs["extra_body"] = {"thinking": {"type": thinking}}

    return ChatOpenAI(**kwargs)


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