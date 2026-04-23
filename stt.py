"""
STT 控制器
连接音频录制 → SenseVoice转写 → 触发LLM流程
"""

import os
from queue import Queue
from threading import Event

from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from audio_recorder import PTTAudioRecorder
from sensevoice_stt import SenseVoiceSTT


class STTController(QObject):
    """
    STT 控制器
    管理 PTT 录音和 SenseVoice 转写，
    将转写文本通过信号发出或直接调用 live2d_widget.send_message()
    """

    # 信号：录音状态变化 (is_recording: bool)
    recording_state_changed = pyqtSignal(bool)

    # 信号：转写完成 (text: str)
    transcription_completed = pyqtSignal(str)

    def __init__(self, live2d_widget, config: dict = None):
        """
        Args:
            live2d_widget: Live2DOpenGLWidget 实例，用于调用 send_message()
            config: STT 配置字典
        """
        super().__init__()

        self.live2d_widget = live2d_widget
        self.config = config or {}

        # 队列
        self.recording_filename_queue = Queue()
        self.stt_text_queue = Queue()

        # 录音状态事件
        self.is_recording_event = Event()

        # PTT 录音器
        self.recorder = PTTAudioRecorder(
            recording_filename_queue=self.recording_filename_queue,
            samplerate=self.config.get("samplerate", 44100),
            channels=self.config.get("channels", 1),
            record_key=self.config.get("ptt_key"),
            min_recording_duration=self.config.get("min_recording_duration", 1.0),
            cooldown_period=self.config.get("cooldown_period", 0.5),
            enable_print=self.config.get("enable_print", True),
        )

        # SenseVoice STT - 直接使用本地克隆的模型目录
        model_dir = self.config.get("model_dir") or ""
        stt_model_path = model_dir if os.path.isdir(model_dir) else os.path.join(
            os.path.expanduser("~"), ".cache", "modelscope", "hub", "iic", "SenseVoiceSmall"
        )
        self.stt = SenseVoiceSTT(
            recording_filename_queue=self.recording_filename_queue,
            stt_text_queue=self.stt_text_queue,
            is_recording_event=self.is_recording_event,
            model_dir=stt_model_path,
            device=self.config.get("device", "cuda:0"),
            enable_print=self.config.get("enable_print", True),
        )

        # 轮询定时器（Qt 主线程）
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_stt_text)

        # 退出事件
        self._exit_event = Event()

    def start(self):
        """启动 STT 系统"""
        # 启动 SenseVoice 转录线程
        self.stt.start(exit_event=self._exit_event)

        # 启动录音监听（pynput 在独立线程中运行）
        import threading
        thread = threading.Thread(target=self._run_recorder, daemon=True)
        thread.start()

        # 启动轮询定时器（100ms 间隔）
        self._poll_timer.start(100)

        print("[STT] STT 系统已启动")

    def _run_recorder(self):
        """在独立线程中运行录音器"""
        # 捕获并转发录音状态
        original_start = self.recorder.start_recording
        original_stop = self.recorder.stop_recording

        def wrap_start():
            self.is_recording_event.set()
            self.recording_state_changed.emit(True)
            original_start()

        def wrap_stop():
            original_stop()
            self.is_recording_event.clear()
            self.recording_state_changed.emit(False)

        self.recorder.start_recording = wrap_start
        self.recorder.stop_recording = wrap_stop

        try:
            self.recorder.start()
        except Exception as e:
            print(f"[STT] pynput 错误: {e}")

    def _poll_stt_text(self):
        """从 stt_text_queue 中取出转写文本并发送给 LLM"""
        try:
            text = self.stt_text_queue.get_nowait()
            if text and text.strip():
                print(f"[STT] 转写完成: {text}")
                # 发送到 Live2D 组件（复用现有的 send_message 流程）
                self.live2d_widget.send_message(text)
                # 同时发出信号供外部使用
                self.transcription_completed.emit(text)
            self.stt_text_queue.task_done()
        except Exception:
            pass

    def stop(self):
        """停止 STT 系统"""
        self._exit_event.set()
        self._poll_timer.stop()
        print("[STT] STT 系统已停止")

    @property
    def is_recording(self) -> bool:
        """当前是否正在录音"""
        return self.is_recording_event.is_set()
