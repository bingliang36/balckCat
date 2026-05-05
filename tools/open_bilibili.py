"""
open_bilibili 工具 - 打开B站
当用户说无聊、想看视频、想刷B站时调用
"""

import webbrowser
import subprocess
import platform


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "open_bilibili",
        "description": "打开B站（哔哩哔哩）视频网站。当用户说无聊、想看视频、想刷B站时调用此工具。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def open_bilibili() -> str:
    """打开B站首页"""
    system = platform.system()
    try:
        if system == "Windows":
            # 使用 cmd 打开默认浏览器
            subprocess.run(["cmd", "/c", "start", "https://www.bilibili.com"], check=True)
        elif system == "Darwin":
            subprocess.run(["open", "https://www.bilibili.com"], check=True)
        else:
            webbrowser.open("https://www.bilibili.com")
        return "已为你打开B站，快去看看有什么有趣的视频吧~"
    except Exception as e:
        return f"打开B站失败: {e}"


# 兼容旧命名
open_bilibili_definition = TOOL_DEFINITION