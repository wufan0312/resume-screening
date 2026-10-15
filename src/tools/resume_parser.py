"""简历文档解析工具：从用户上传的简历文件(URL)中提取文本内容。

支持 PDF、Word(DOC/DOCX)、TXT、CSV、图片等多种格式。
当用户提供简历文件的下载链接/对象存储 URL 时，使用此工具解析其内容，
返回可被大模型阅读的纯文本。
"""
from langchain.tools import tool

from coze_coding_dev_sdk.fetch import FetchClient
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context


@tool
def parse_resume_file(file_url: str) -> str:
    """解析简历文件并提取其中的文本内容。

    当用户以链接(URL)形式提供简历文件（支持 PDF、Word DOC/DOCX、TXT 等格式）时，
    调用本工具读取并解析该文件，返回可阅读的文本，供后续筛选分析使用。

    Args:
        file_url: 简历文件的访问链接（http/https 开头的下载地址或对象存储 URL）。
    """
    ctx = request_context.get() or new_context(method="parse_resume_file")
    client = FetchClient(ctx=ctx)
    response = client.fetch(url=file_url)

    if response.status_code != 0:
        return f"简历文件解析失败：{response.status_message}"

    parts = []
    for item in response.content:
        if getattr(item, "type", None) == "text":
            text = getattr(item, "text", "")
            if text:
                parts.append(text)

    content = "\n".join(parts).strip()
    if not content:
        return "未能从该文件中提取到有效文本内容，请确认该文件是否为简历文档。"
    return content