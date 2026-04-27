"""
look_screen 工具 - 截取用户屏幕内容
当需要了解用户屏幕上显示的内容时调用此工具

支持两种模式：
- external_vlm: 捕获屏幕后发送给外部VLM模型分析（glm-4v等）
- native_vision: 捕获屏幕后返回base64，豆包等自带视觉的模型直接分析
"""

import io
from PIL import ImageGrab
import base64


# 配置：视觉模式
# - "external_vlm": 使用外部VLM分析（Zhipu等）
# - "native_vision": 让LLM自带视觉处理
VISION_MODE = "native_vision"  # 默认使用原生视觉


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "look_screen",
        "description": "截取用户当前屏幕的内容，并返回对屏幕内容的文字描述。当你需要知道用户在看什么、用户的屏幕上有什么内容时，调用此工具。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def _capture_screen() -> tuple[ImageGrab, str]:
    """
    捕获屏幕并压缩

    Returns:
        (PIL.Image, base64_str): 图像对象和base64编码
    """
    img = ImageGrab.grab()
    MAX_WIDTH = 1024
    w, h = img.size
    if w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        new_size = (MAX_WIDTH, int(h * ratio))
        img = img.resize(new_size)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    image_bytes = buf.getvalue()
    img_base64 = base64.b64encode(image_bytes).decode("utf-8")
    return img, img_base64


def look_screen() -> str:
    """
    截取全屏截图，根据配置要么发送给外部VLM分析，要么返回base64供LLM原生视觉处理

    Returns:
        str: 视觉模式返回 "IMAGE:{base64}"，外部VLM模式返回描述文本
    """
    img, img_base64 = _capture_screen()

    if VISION_MODE == "native_vision":
        # 原生视觉模式：返回base64让LLM自己看
        return f"IMAGE:{img_base64}"
    else:
        # 外部VLM模式：发送给glm-4v-flash分析
        from zai import ZhipuAiClient
        API_KEY = "f8bd5e54ab554b58ae6876a9aeb06002.Y1X7zu2X4Q7D36PV"
        MODEL = "glm-4v-flash"

        client = ZhipuAiClient(api_key=API_KEY)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": img_base64}},
                        {"type": "text", "text": "请简要描述这张截图的内容，用中文回答，控制在50字以内。"}
                    ]
                }
            ],
            thinking={"type": "disabled"}
        )
        description = response.choices[0].message.content
        return f"屏幕内容：{description}"


# 兼容旧命名
look_screen_definition = TOOL_DEFINITION