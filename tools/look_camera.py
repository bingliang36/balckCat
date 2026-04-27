"""
look_camera 工具 - 捕获用户摄像头画面
当需要了解用户本人、用户的状态或表情时调用此工具

支持两种模式：
- external_vlm: 捕获摄像头后发送给外部VLM模型分析（glm-4v等）
- native_vision: 捕获摄像头后返回base64，豆包等自带视觉的模型直接分析
"""

import io
import cv2
from PIL import Image
import base64


# 配置：视觉模式
# - "external_vlm": 使用外部VLM分析（Zhipu等）
# - "native_vision": 让LLM自带视觉处理
VISION_MODE = "native_vision"  # 默认使用原生视觉


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "look_camera",
        "description": "打开用户摄像头，捕获当前画面并返回描述。当你需要知道用户本人长什么样、用户的表情、用户是否在场时，调用此工具。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def _capture_camera() -> tuple:
    """
    捕获摄像头一帧

    Returns:
        (PIL.Image, base64_str) or None: 失败返回None
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

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


def look_camera() -> str:
    """
    捕获摄像头一帧，根据配置要么发送给外部VLM分析，要么返回base64供LLM原生视觉处理

    Returns:
        str: 视觉模式返回 "IMAGE:{base64}"，外部VLM模式返回描述文本
    """
    result = _capture_camera()
    if result is None:
        return "错误：无法打开摄像头"

    img, img_base64 = result

    if VISION_MODE == "native_vision":
        # 原生视觉模式：返回base64让LLM自己看
        return f"IMAGE:{img_base64}"
    else:
        # 外部VLM模式：发送给glm-4.6v分析
        from zai import ZhipuAiClient
        API_KEY = "f8bd5e54ab554b58ae6876a9aeb06002.Y1X7zu2X4Q7D36PV"
        MODEL = "glm-4.6v"

        client = ZhipuAiClient(api_key=API_KEY)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": img_base64}},
                        {"type": "text", "text": "请简要描述这张图片的内容，包括人物的表情、动作和状态，用中文回答，控制在50字以内。"}
                    ]
                }
            ],
            thinking={"type": "disabled"}
        )
        description = response.choices[0].message.content
        return f"摄像头画面：{description}"


# 兼容旧命名
look_camera_definition = TOOL_DEFINITION