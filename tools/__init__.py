"""视觉工具模块"""
from .look_screen import look_screen, look_screen_definition
from .look_camera import look_camera, look_camera_definition

# 导出所有工具定义，用于注册到 LLM
TOOL_DEFINITIONS = [look_screen_definition, look_camera_definition]

# 导出所有工具函数
TOOL_FUNCTIONS = {
    "look_screen": look_screen,
    "look_camera": look_camera,
}
