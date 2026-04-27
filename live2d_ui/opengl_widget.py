"""
Live2D OpenGL 渲染组件
集成了 LLM、TTS、情绪检测、口型同步
支持视觉工具（look_screen, look_camera）
"""

from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QSurfaceFormat
import OpenGL.GL as GL

from time import time
import live2d.v3 as live2d
from live2d.v3 import StandardParams

from llm.client import LLMClient
from tts.engine import TTS
from utils.emotion import EmotionDetector, parse_emotion_from_text
from tools import TOOL_DEFINITIONS  # 视觉工具定义
from memory import MemoryClient  # 记忆模块（recall 作为工具调用）


class Live2DOpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        format = QSurfaceFormat()
        format.setAlphaBufferSize(8)
        format.setRenderableType(QSurfaceFormat.OpenGL)
        QOpenGLWidget.__init__(self, parent)
        self.setFormat(format)

        # Live2D 模型
        self.model = None
        self.last_time = None

        # LLM / TTS / 情绪检测
        self.llm = LLMClient()
        self.llm.set_tools(TOOL_DEFINITIONS)  # 注册视觉工具
        self.emotion_detector = EmotionDetector()
        self.tts = TTS(
            on_amplitude=self._on_amplitude,
            on_expression=self._on_expression,
            on_turn_complete=self._on_turn_complete
        )

        # 口型同步
        self.mouth_open = 0.0  # 0.0 ~ 1.0
        self.target_mouth_open = 0.0

        # 记忆模块
        self.memory_client = MemoryClient()
        self._last_user_text = ""     # 最近一次用户输入
        self._last_assistant_text = ""  # 最近一次AI回复

        # 聊天窗口引用（用于流式显示）
        self._chat_window = None
        self._current_bubble = None  # 当前正在流式输出的气泡

        # 渲染定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # ~60 FPS

        # 开场动画
        self._intro_t = 0.0       # 开场动画流逝时间（秒）
        self._intro_done = False   # 开场动画是否已结束
        self._intro_ear_phase = 0.0
        self._intro_blink_done = False

    def set_chat_window(self, chat_window):
        """设置聊天窗口引用，用于流式显示"""
        self._chat_window = chat_window

    def initializeGL(self):
        """初始化 OpenGL 和 Live2D 模型"""
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        # 初始化 Live2D
        live2d.init()
        live2d.glInit()

        # 加载模型
        from config import MODEL_PATH
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(MODEL_PATH)
        self.model.Resize(self.width(), self.height())
        self.model.SetAutoBreathEnable(True)
        self.model.SetAutoBlinkEnable(True)

        # 启动开场动画（5秒）
        self._intro_t = 0.0
        self._intro_done = False
        self._intro_ear_phase = 0.0
        self._intro_blink_done = False

        print("[live2d] 模型加载完成")

    def resizeGL(self, w, h):
        GL.glViewport(0, 0, w, h)
        if self.model:
            self.model.Resize(w, h)

    def paintGL(self):
        """渲染一帧"""
        import math
        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)

        if self.model:
            # 平滑口型过渡
            self.mouth_open += (self.target_mouth_open - self.mouth_open) * 0.3

            # 更新时间基准（秒）
            t = time()
            dt = t - (self.last_time or t)
            self.last_time = t

            # 更新模型（表情、动作的主动画在此计算）
            self.model.Update()

            # 开场动画（张嘴微笑 + 动耳朵 + 眨眼睛）
            # 用开场专属时间，不会随程序运行时不断累积
            INTRO_DURATION = 5.0
            FADE_START = 4.5  # 从第4.5秒开始 fade，fade 持续 0.5s

            if not self._intro_done:
                self._intro_t += dt
                elapsed = self._intro_t

                if elapsed >= INTRO_DURATION:
                    self._intro_done = True
                else:
                    # fade：开场=1.0，尾声=0.0
                    fade = 1.0 if elapsed < FADE_START else max(0.0, 1.0 - (elapsed - FADE_START) / (INTRO_DURATION - FADE_START))

                    # ── 1. 眨眼睛：开场后约 0.5s 执行一次 ──
                    if not self._intro_blink_done and elapsed >= 0.5:
                        self._intro_blink_done = True
                        self.model.SetParameterValue("ParamEyeLOpen", 0.0, 0.7)
                        self.model.SetParameterValue("ParamEyeROpen", 0.0, 0.7)

                    # ── 2. 张嘴微笑 + 眼笑 ──
                    mouth_open = (0.15 + math.sin(elapsed * math.pi * 1.5) * 0.08) * fade
                    self.model.SetParameterValue("ParamMouthOpenY", mouth_open, 0.5 * fade + 0.01)
                    self.model.SetParameterValue("ParamEyeLSmile", 0.4 * fade, 0.4 * fade + 0.01)
                    self.model.SetParameterValue("ParamEyeRSmile", 0.4 * fade, 0.4 * fade + 0.01)
                    self.model.SetParameterValue("ParamMouthForm", 0.5 * fade, 0.5 * fade + 0.01)

            # 设置口型参数 (嘴唇张合)
            self.model.SetParameterValue(StandardParams.ParamMouthOpenY, self.mouth_open)

            # 绘制模型
            self.model.Draw()

    def send_message(self, text: str):
        """
        用户发送消息 → LLM (工具调用) → TTS + 情绪
        记忆 recall 作为工具由 LLM 自行判断是否调用
        """
        print(f"[chat] 用户: {text}")

        # 保存用户输入，对话结束后用于异步存储到 MemNet
        self._last_user_text = text

        # 在聊天窗口显示用户消息
        if self._chat_window:
            self._chat_window.add_user_message(text)
            self._chat_window.show_window()

        # 使用带工具的 LLM 调用（recall 作为工具之一）
        self.llm.ask_with_tools(
            text,
            tools=TOOL_DEFINITIONS,
            callback=self._on_llm_response,
            chunk_callback=self._on_llm_chunk
        )

    def _on_llm_chunk(self, sentence: str):
        """
        LLM 流式句子回调 — 解析情绪触发点，送 TTS 播放，同时发送 chunk 到 WebSocket
        """
        print(f"[chat] 助手 (句): {sentence}")

        # 解析文本中的情绪标记和颜文字，提取纯净文本 + 触发点
        result = parse_emotion_from_text(sentence)
        print(f"[emotion] 解析结果  句: {repr(sentence[:30])}")
        print(f"[emotion] 纯净文本: {repr(result.clean_text[:30])}  触发点: {[(t.char_pos, t.expression_name) for t in result.triggers]}")
        print(f"[emotion] 送TTS  clean: {repr(result.clean_text)}  triggers: {[(t.char_pos, t.expression_name) for t in result.triggers]}")

        # 发送 chunk 到 HTTP 轮询队列（用于网页打字机效果）
        from web_ui import send_chunk_sync
        send_chunk_sync(sentence)

        # 立即送 TTS 播放（异步不阻塞），带上情绪触发点
        print(f"[tts] speak_async  raw={repr(sentence[:40])}  clean={repr(result.clean_text[:40])}  triggers={[(t.char_pos, t.expression_name) for t in result.triggers]}")
        if result.clean_text.strip():
            self.tts.speak_async(result.clean_text, result.triggers)
        elif result.triggers:
            # 纯净文本为空但有情绪触发点（整段都是颜文字/标签），立即触发表情
            print(f"[tts] 空文本触发情绪: {result.triggers[0].expression_name}")
            if self.model:
                self.model.ResetExpression()
                self.model.SetExpression(result.triggers[0].expression_name)
        else:
            print(f"[tts] 跳过（无文本无情绪）")

    def _on_llm_response(self, error, reply: str):
        """LLM 完成回调 — 通知 TTS 本轮结束，异步存储记忆"""
        if error:
            print(f"[llm] 错误: {error}")
            return
        print(f"[chat] 助手 (完毕): {reply}")
        self._last_assistant_text = reply

        # 发送完成信号到 WebSocket
        print("[llm] 发送 done 信号")
        from web_ui import send_done_sync
        send_done_sync()
        print("[llm] done 信号已发送")

        # 对话结束后，异步存储记忆
        self._async_store_memory()

        self.tts.end_turn()

    def _async_store_memory(self):
        """异步线程：存储对话到 MemNet（不提取关键词，LLM 自己判断何时 recall）"""
        import threading
        from memnetai.basics.request.message.message import Message
        from config import MEMNET_CONFIG

        def _do():
            if not MEMNET_CONFIG.get("enabled", True):
                return
            try:
                messages = [
                    Message(role="user", content=self._last_user_text, character="用户"),
                    Message(role="assistant", content=self._last_assistant_text, character=MEMNET_CONFIG["character"]),
                ]
                self.memory_client.store(messages, async_mode=1)
            except Exception as e:
                print(f"[memory] 异步存储失败: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def _on_turn_complete(self):
        """TTS 本轮所有句子播完后回调 — 还原到默认表情"""
        if self.model:
            self.model.ResetExpression()
            print('[live2d] 回合结束，表情还原')

    def _on_amplitude(self, amplitude: float):
        """
        TTS 音频幅度回调 → 驱动口型
        amplitude: 0.0 ~ 1.0
        """
        self.target_mouth_open = amplitude * 0.8  # 缩放到合适的张嘴幅度

    def _on_expression(self, expression_name: str):
        """
        TTS 情绪触发点回调 → 切换 Live2D 表情
        expression_name: Live2D 表情名（如 "expression2", "expression7"）
        """
        if expression_name and self.model:
            self.model.ResetExpression()
            self.model.SetExpression(expression_name)
            print(f'[live2d] 触发表情: {expression_name}')

    def trigger_emotion(self, expression_name: str | None):
        """
        主动触发表情或重置
        expression_name: "expression2" 等，或 None 表示 ResetExpression
        """
        if not self.model:
            return
        self.model.ResetExpression()
        if expression_name:
            self.model.SetExpression(expression_name)
            print(f'[live2d] 用户触发表情: {expression_name}')
        else:
            print('[live2d] 表情已重置')
