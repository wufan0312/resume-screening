"""简历文档解析工具：从文件（本地路径或 URL）中提取文本。

支持 PDF、Word(DOC/DOCX)、TXT、CSV 等格式。
当提供 http/https 链接时，先下载到临时文件再解析，返回可被大模型阅读的纯文本。
"""
import os
import tempfile
from typing import Optional

import httpx
from langchain.tools import tool

from pypdf import PdfReader
from docx2python import docx2python


def _read_pdf(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:  # 解析失败不应中断流程
        return f"[PDF 解析失败: {e}]"


def _read_docx(path: str) -> str:
    try:
        with docx2python(path) as doc:
            return doc.text or ""
    except Exception as e:
        return f"[DOCX 解析失败: {e}]"


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"[文本读取失败: {e}]"


def _parse_local(path: str) -> str:
    low = path.lower()
    if low.endswith(".pdf"):
        return _read_pdf(path)
    if low.endswith((".docx", ".doc")):
        return _read_docx(path)
    return _read_text(path)


@tool
def parse_resume_file(file_url: str) -> str:
    """解析简历文件并提取其中的文本内容。

    支持本地文件路径或 http/https 链接（PDF、Word DOC/DOCX、TXT、CSV 等）。
    当用户以链接或路径形式提供简历文件时，调用本工具读取并解析，返回可阅读文本。

    Args:
        file_url: 简历文件的本地路径或访问链接（http/https 开头）。
    """
    tmp_path: Optional[str] = None
    try:
        if file_url.lower().startswith(("http://", "https://")):
            resp = httpx.get(file_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            suffix = os.path.splitext(file_url.split("?")[0])[1] or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                tf.write(resp.content)
                tmp_path = tf.name
            content = _parse_local(tmp_path)
        else:
            content = _parse_local(file_url)
    except Exception as e:
        content = f"简历文件解析失败：{e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    if not content or not content.strip():
        return "未能从该文件中提取到有效文本内容，请确认该文件是否为简历文档。"
    return content.strip()
