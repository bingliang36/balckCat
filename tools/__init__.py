"""工具模块 - 视觉工具 + 记忆recall"""
from .look_screen import look_screen, look_screen_definition
from .look_camera import look_camera, look_camera_definition
from .recall_memory import recall_memory, recall_memory_definition
from .open_bilibili import open_bilibili, open_bilibili_definition

# 注意：联网搜索功能已移至 LLM 客户端原生支持
# 不再使用独立的 web_search 工具（联网搜索与函数调用冲突）

# 导出所有工具定义，用于注册到 LLM
TOOL_DEFINITIONS = [
    look_screen_definition,
    look_camera_definition,
    recall_memory_definition,
    open_bilibili_definition,
]

# 导出所有工具函数
TOOL_FUNCTIONS = {
    "look_screen": look_screen,
    "look_camera": look_camera,
    "recall_memory": recall_memory,
    "open_bilibili": open_bilibili,
}


def set_vision_mode(mode: str):
    """
    设置视觉工具的工作模式
    mode: "native_vision"（默认）或 "external_vlm"
    """
    global _vision_mode
    _vision_mode = mode
    # 同步设置到 look_screen 和 look_camera
    import tools.look_screen as ls
    import tools.look_camera as lc
    ls.VISION_MODE = mode
    lc.VISION_MODE = mode

_vision_mode = "native_vision"