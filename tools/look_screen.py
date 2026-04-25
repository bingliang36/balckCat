"""
look_screen 工具 - 截取用户屏幕内容
当需要了解用户屏幕上显示的内容时调用此工具
"""

from PIL import ImageGrab
import io


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


def look_screen() -> str:
    """
    截取全屏截图，发送给 GLM-4.6V-Flash 分析，返回描述

    Returns:
        str: 对屏幕内容的描述
    """
    from zai import ZhipuAiClient
    from config import LLM_CONFIG
    import base64

    API_KEY = "f8bd5e54ab554b58ae6876a9aeb06002.Y1X7zu2X4Q7D36PV"
    MODEL = "glm-4.6v-flash"
    MAX_WIDTH = 1024

    # 截取屏幕
    img = ImageGrab.grab()

    w, h = img.size
    if w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        new_size = (MAX_WIDTH, int(h * ratio))
        img = img.resize(new_size)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    image_bytes = buf.getvalue()

    # 发送给 GLM
    img_base64 = base64.b64encode(image_bytes).decode("utf-8")
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
