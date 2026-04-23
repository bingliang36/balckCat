"""
SenseVoice 语音转文字模块
基于 FunAudioLLM/SenseVoice 模型
"""

import sys
import os
from queue import Queue
from threading import Thread, Event
import queue
import time
import logging
import warnings

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess


class SenseVoiceSTT:
    """SenseVoice STT 引擎"""

    def __init__(
        self,
        recording_filename_queue: Queue,
        stt_text_queue: Queue,
        is_recording_event: Event = None,
        model_dir: str = None,
        stt_model: str = "SenseVoiceSmall",
        vad_model: str = "speech_fsmn_vad_zh-cn-16k-common-pytorch",
        device: str = "cuda:0",
        enable_print: bool = True,
    ):
        """
        Args:
            recording_filename_queue: 录音文件路径队列（从中获取待转写文件）
            stt_text_queue: 转写文本输出队列（转写完成后写入）
            is_recording_event: 录音状态事件（用于中断处理）
            model_dir: 模型缓存目录，默认 ~/.cache/modelscope/hub/iic
            stt_model: STT 模型名称
            vad_model: VAD 模型名称
            device: 运行设备，"cuda:0" 或 "cpu"
            enable_print: 是否打印日志
        """
        self.recording_filename_queue = recording_filename_queue
        self.stt_text_queue = stt_text_queue
        self.is_recording_event = is_recording_event

        # 模型路径 - 如果 model_dir 是已存在的本地目录则直接使用
        if model_dir is None:
            model_dir = os.path.join(os.path.expanduser("~"), ".cache", "modelscope", "hub", "iic")
        self.model_dir = model_dir
        if os.path.isdir(model_dir):
            self.stt_model_path = model_dir
        else:
            self.stt_model_path = os.path.join(model_dir, stt_model)
        self.vad_model_path = vad_model  # VAD 使用模型标识符，让 funasr 自动下载
        self.device = device
        self.enable_print = enable_print

        # 中断状态
        self.was_interrupted = False

        # 初始化模型
        self._init_model()

    def _init_model(self):
        """初始化 SenseVoice 模型"""
        # 抑制日志输出
        logging.getLogger().setLevel(logging.CRITICAL + 1)
        warnings.filterwarnings("ignore")

        original_stdout = None
        if not self.enable_print:
            original_stdout = sys.stdout = open(os.devnull, 'w')

        try:
            self.model = AutoModel(
                model=self.stt_model_path,
                trust_remote_code=True,
                disable_update=True,
                remote_code="C:/Users/LENOVO/anaconda3/envs/live2d-pet/lib/site-packages/funasr/models/sense_voice",
                vad_model="fsmn-vad",  # 使用 funasr 内置 VAD 模型标识符
                vad_kwargs={"max_single_segment_time": 30000},
                device=self.device,
            )
        finally:
            if original_stdout:
                sys.stdout = original_stdout

        if self.enable_print:
            print("✅ SenseVoice 模型加载完成")

    def transcribe(self, audio_path: str) -> str:
        """
        转录单个音频文件

        Args:
            audio_path: 音频文件路径

        Returns:
            转录文本
        """
        res = self.model.generate(
            input=audio_path,
            cache={},
            language="auto",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        text = rich_transcription_postprocess(res[0]["text"])
        return text

    def _clear_queue(self, q: Queue):
        """清空队列"""
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break

    def transcribe_loop(self):
        """主循环：监听录音文件队列并进行转录"""
        while not getattr(self, '_exit_event', None) or not self._exit_event.is_set():
            # 检查是否正在录音（中断处理）
            if self.is_recording_event and self.is_recording_event.is_set():
                if not self.was_interrupted:
                    self._clear_queue(self.recording_filename_queue)
                    self.was_interrupted = True
                time.sleep(0.02)
                continue
            else:
                self.was_interrupted = False

            try:
                # 等待录音文件（阻塞最多0.5秒）
                audio_path = self.recording_filename_queue.get(timeout=0.5)

                # 再次检查录音状态
                if self.is_recording_event and self.is_recording_event.is_set():
                    self._clear_queue(self.recording_filename_queue)
                    self.was_interrupted = True
                    continue

                # 转录
                if self.enable_print:
                    print(f"[STT] 转录中: {audio_path}")
                text = self.transcribe(audio_path)
                if self.enable_print:
                    print(f"[STT] 结果: {text}")

                # 放入输出队列
                self.stt_text_queue.put(text)
                self.recording_filename_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                if self.enable_print:
                    print(f"[STT] 转录错误: {e}")
                continue

    def start(self, exit_event: Event = None):
        """
        启动转录线程

        Args:
            exit_event: 退出事件，用于优雅关闭
        """
        self._exit_event = exit_event
        thread = Thread(target=self.transcribe_loop, daemon=True)
        thread.start()
        return thread

