"""
look_camera 工具 - 捕获用户摄像头画面
当需要了解用户本人、用户的状态或表情时调用此工具
"""

import io


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


def look_camera() -> str:
    """
    捕获摄像头一帧，发送给 GLM-4.6V-Flash 分析，返回描述

    Returns:
        str: 对摄像头画面的描述
    """
    import cv2
    from PIL import Image
    from zai import ZhipuAiClient
    import base64

    API_KEY = "f8bd5e54ab554b58ae6876a9aeb06002.Y1X7zu2X4Q7D36PV"
    MODEL = "glm-4.6v-flash"
    MAX_WIDTH = 1024

    # 捕获摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return "错误：无法打开摄像头"

    ret, frame = cap.read()
    cap.release()

    if not ret:
        return "错误：摄像头读取失败"

    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

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
