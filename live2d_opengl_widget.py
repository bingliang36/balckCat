"""
Live2D OpenGL 渲染组件
集成了 LLM、TTS、情绪检测、口型同步
"""

from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QSurfaceFormat
import OpenGL.GL as GL

from time import time
import live2d.v3 as live2d
from live2d.v3 import StandardParams

from llm import LLMClient
from tts import TTS
from emotion import EmotionDetector, parse_emotion_from_text


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
        self.emotion_detector = EmotionDetector()
        self.tts = TTS(
            on_amplitude=self._on_amplitude,
            on_expression=self._on_expression,
            on_turn_complete=self._on_turn_complete
        )

        # 口型同步
        self.mouth_open = 0.0  # 0.0 ~ 1.0
        self.target_mouth_open = 0.0

        # 渲染定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # ~60 FPS

        # 微动作时间基准
        self._anim_t = 0.0

        # 开场动画标志
        self._intro_frames = 0  # 播放 N 帧后停止，0=未开始

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

        # 启动开场动画（360帧约6秒）
        self._intro_frames = 415

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
            self._anim_t += dt

            # 更新模型（表情、动作的主动画在此计算）
            self.model.Update()

            # 叠加微动作（在 Update 之后叠加，持续性的细微摆动）
            # v3 physics 规范化到 [-10,10]，输出 scale 约 25
            # 用 weight 让每次 Set 都以小幅度叠加，不会覆盖主表情/动作
            mt = self._anim_t

            # 开场动画：播放 （360帧约6秒）后自动停止
            if self._intro_frames > 0:
                self._intro_frames -= 1

                # 头部微微晃动
                self.model.SetParameterValue("ParamAngleX", math.sin(mt * 0.001) * 0.001, 0.001)
                self.model.SetParameterValue("ParamAngleY", math.sin(mt * 0.001) * 0.001, 0.001)
                self.model.SetParameterValue("ParamAngleZ", math.sin(mt * 0.001) * 0.001, 0.001)

                # 身体整体左右摇晃
                self.model.SetParameterValue("ParamBodyAngleX", math.sin(mt * 5) * 0.5, 0.04)

                # 眼睛微动
                self.model.SetParameterValue("ParamEyeBallX", math.sin(mt * 0.001) * 0.001, 0.001)
                self.model.SetParameterValue("ParamEyeBallY", math.sin(mt * 0.001) * 0.001, 0.001)
            elif self._intro_frames == 0:
                # 播放完毕后重置所有开场动画参数到0，恢复初始状态
                self.model.SetParameterValue("ParamAngleX", 0.0, 1.0)
                self.model.SetParameterValue("ParamAngleY", 0.0, 1.0)
                self.model.SetParameterValue("ParamAngleZ", 0.0, 1.0)
                self.model.SetParameterValue("ParamBodyAngleX", 0.0, 1.0)
                self.model.SetParameterValue("ParamEyeBallX", 0.0, 1.0)
                self.model.SetParameterValue("ParamEyeBallY", 0.0, 1.0)
                self._intro_frames = -1

            # 设置口型参数 (嘴唇张合)
            self.model.SetParameterValue(StandardParams.ParamMouthOpenY, self.mouth_open)

            # 绘制模型
            self.model.Draw()

    def send_message(self, text: str):
        """
        用户发送消息 → LLM (流式) → TTS (逐句触发) + 情绪检测
        """
        print(f"[chat] 用户: {text}")

        # 流式 LLM：逐句触发 TTS，最终回调用于情绪检测
        self.llm.ask(
            text,
            callback=self._on_llm_response,
            chunk_callback=self._on_llm_chunk
        )

    def _on_llm_chunk(self, sentence: str):
        """
        LLM 流式句子回调 — 解析情绪触发点，送 TTS 播放
        """
        print(f"[chat] 助手 (句): {sentence}")

        # 解析文本中的情绪标记和颜文字，提取纯净文本 + 触发点
        result = parse_emotion_from_text(sentence)
        print(f"[emotion] 纯净文本: {result.clean_text}  触发点: {[(t.char_pos, t.expression_name) for t in result.triggers]}")

        # 立即送 TTS 播放（异步不阻塞），带上情绪触发点
        self.tts.speak_async(result.clean_text, result.triggers)

    def _on_llm_response(self, error, reply: str):
        """LLM 完成回调 — 通知 TTS 本轮结束，播完后会还原表情"""
        if error:
            print(f"[llm] 错误: {error}")
            return
        print(f"[chat] 助手 (完毕): {reply}")
        self.tts.end_turn()

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
