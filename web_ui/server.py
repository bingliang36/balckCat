"""
Web UI 服务 - FastAPI 后端
提供 HTTP 轮询聊天接口
"""

import json
import threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# FastAPI 应用
app = FastAPI(title="桌面宠物管理界面")

# 挂载静态文件
web_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(web_dir), html=True), name="static")


# 聊天消息队列（线程安全）
class MessageQueue:
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()

    def put(self, msg: dict):
        with self._lock:
            self._queue.append(msg)

    def get_all(self):
        with self._lock:
            msgs = self._queue.copy()
            self._queue.clear()
            return msgs

    def clear(self):
        with self._lock:
            self._queue.clear()


user_queue = MessageQueue()  # 用户发送的消息
assistant_queue = MessageQueue()  # 助手回复的 chunks


class MessageModel(BaseModel):
    text: str


@app.get("/")
async def get_index():
    """返回聊天页面"""
    return FileResponse(str(web_dir / "index.html"))


@app.post("/api/send")
async def send_message(msg: MessageModel):
    """接收用户消息，转发给宠物"""
    user_queue.put({"type": "chat", "text": msg.text})
    return JSONResponse({"status": "ok"})


@app.get("/api/poll")
async def poll_messages():
    """轮询获取助手回复"""
    return JSONResponse(assistant_queue.get_all())


@app.post("/api/reset")
async def reset_conversation():
    """重置对话状态"""
    assistant_queue.clear()
    return JSONResponse({"status": "ok"})


@app.get("/api/done")
async def force_done():
    """强制发送完成信号"""
    assistant_queue.put({"type": "done", "text": ""})
    return JSONResponse({"status": "ok"})


# 聊天回调函数（由主程序设置）
chat_callback = None


def set_chat_callback(callback):
    """设置聊天回调，由主程序调用"""
    global chat_callback
    chat_callback = callback


def get_user_message() -> str:
    """获取一个用户消息（非阻塞）"""
    msgs = user_queue.get_all()
    if msgs:
        return msgs[0].get("text", "")
    return ""


def send_chunk_sync(chunk: str):
    """发送 chunk 到浏览器"""
    assistant_queue.put({"type": "chunk", "text": chunk})


def send_done_sync():
    """发送完成信号"""
    assistant_queue.put({"type": "done", "text": ""})


def run_server(port=5000):
    """运行服务器"""
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
