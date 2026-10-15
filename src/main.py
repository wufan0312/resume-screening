"""求职投递智能体 —— 纯本地 FastAPI 服务入口（已去除 Coze 依赖）。

提供标准 HTTP 接口：
- POST /run                一次性执行（默认 workflow 投递流水线；APP_MODE=agent 或含 messages 时走对话 Agent）
- POST /stream_run         SSE 流式执行（workflow 节点更新 / agent 文本 token）
- POST /v1/chat/completions  OpenAI Chat 兼容（对接对话 Agent）
- GET  /health             健康检查
- GET  /graph_parameter     workflow 输入输出 schema

运行：
    python -m main -m http -p 5000        # 本地起服务（需先 cd src 或设置 PYTHONPATH=src）
    python -m main -m flow -i '{"my_resume":"...","job_preferences":"..."}'   # 命令行跑一次流水线
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

# 将 src/ 加入 sys.path，保证 `from graphs.xxx / storage.xxx` 等导入可用
_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import event

from storage.database.db import get_engine
from storage.database.shared.model import Base
from storage.memory.memory_saver import get_memory_saver
from graphs.graph import graph as workflow_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("delivery_agent")

APP_MODE = os.getenv("APP_MODE", "workflow").lower()
TIMEOUT_SECONDS = 900

# 对话 Agent 懒加载（避免缺少 API key 时启动即失败）
_agent_app = None


def _build_agent_app():
    from agents.agent import build_agent

    return build_agent()


def get_agent_app():
    global _agent_app
    if _agent_app is None:
        _agent_app = _build_agent_app()
    return _agent_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    if not str(engine.url).startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_utc(dbapi_conn, _):
            with dbapi_conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")

    # 幂等建投递表：表不存在才建；数据库不可用时仅告警，不阻断启动
    try:
        from storage.database.repo.delivery_repo import create_delivery_tables

        create_delivery_tables(engine=engine)
        logger.info("delivery tables ensured")
    except Exception as e:
        logger.warning(f"ensure delivery tables skipped: {e}")
    yield


app = FastAPI(title="Job Delivery Agent", lifespan=lifespan)


def _sse_event(data: Any, event_id: Any = None) -> str:
    id_line = f"id: {event_id}\n" if event_id else ""
    return f"{id_line}event: message\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _use_agent(payload: Dict[str, Any]) -> bool:
    return APP_MODE == "agent" or "messages" in payload


@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    run_id = uuid.uuid4().hex
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        if _use_agent(payload):
            agent = get_agent_app()
            result = await agent.ainvoke(
                {"messages": payload.get("messages", [])},
                config={"configurable": {"thread_id": run_id}},
            )
            return {"run_id": run_id, "result": result}
        result = await workflow_graph.ainvoke(payload)
        if isinstance(result, dict):
            result["run_id"] = run_id
        return result
    except Exception as e:
        logger.exception(f"/run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stream_run")
async def http_stream_run(request: Request):
    run_id = uuid.uuid4().hex
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    async def event_gen():
        try:
            if _use_agent(payload):
                agent = get_agent_app()
                async for chunk in agent.astream(
                    {"messages": payload.get("messages", [])},
                    config={"configurable": {"thread_id": run_id}},
                    stream_mode="messages",
                ):
                    msg = chunk[0] if isinstance(chunk, tuple) else chunk
                    text = getattr(msg, "content", None)
                    if text:
                        yield _sse_event({"type": "token", "content": text}, run_id)
            else:
                async for node_name, output in workflow_graph.astream(payload, stream_mode="updates"):
                    yield _sse_event({"type": "node", "node": node_name, "output": output}, run_id)
        except Exception as e:
            logger.exception(f"/stream_run error: {e}")
            yield _sse_event({"type": "error", "content": str(e)}, run_id)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """OpenAI Chat Completions 兼容接口（对接对话 Agent）。"""
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    messages = payload.get("messages", [])
    stream = payload.get("stream", False)
    agent = get_agent_app()

    if stream:
        async def gen():
            try:
                async for chunk in agent.astream(
                    {"messages": messages},
                    config={"configurable": {"thread_id": uuid.uuid4().hex}},
                    stream_mode="messages",
                ):
                    msg = chunk[0] if isinstance(chunk, tuple) else chunk
                    text = getattr(msg, "content", None)
                    if text:
                        yield (
                            f"data: {json.dumps({'choices':[{'delta':{'content':text}}]}, ensure_ascii=False)}\n\n"
                        )
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    result = await agent.ainvoke(
        {"messages": messages},
        config={"configurable": {"thread_id": uuid.uuid4().hex}},
    )
    out_msgs = result.get("messages", []) if isinstance(result, dict) else []
    content = out_msgs[-1].content if out_msgs else ""
    return {
        "object": "chat.completion",
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


@app.get("/graph_parameter")
async def graph_parameter():
    return {
        "input_schema": workflow_graph.get_input_schema().model_json_schema(),
        "output_schema": workflow_graph.get_output_schema().model_json_schema(),
        "code": 0,
        "msg": "",
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode: http/flow/agent")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string for flow mode")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    if not input_str:
        return {"text": "你好"}
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        return {"text": input_str}


def start_http_server(port):
    logger.info(f"Start HTTP Server, Port: {port}")
    # 直接传 app 对象（reload 关闭，避免重复 import 字符串路径）
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    args = parse_args()
    if args.m == "http":
        start_http_server(args.p)
    elif args.m == "flow":
        payload = parse_input(args.i)
        result = asyncio.run(workflow_graph.ainvoke(payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "agent":
        agent = _build_agent_app()
        res = asyncio.run(
            agent.ainvoke(
                {"messages": [("user", "你好")]},
                config={"configurable": {"thread_id": "1"}},
            )
        )
        print(res)
