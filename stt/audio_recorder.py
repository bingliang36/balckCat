"""
PTT 音频录制模块
按指定按键录音，松开发送
"""

import sounddevice
from scipy.io.wavfile import write
from pynput.keyboard import Listener, Key, KeyCode
import threading
import time
import numpy as np
import os
from queue import Queue
from threading import Event

from utils.filename import GetFilename


class PTTAudioRecorder:
    """按键触发录音器 (Push-to-Talk)"""

    def __init__(
        self,
        recording_filename_queue: Queue,
        samplerate: int = 44100,
        channels: int = 1,
        record_key=None,
        min_recording_duration: float = 1.0,
        cooldown_period: float = 0.5,
        enable_print: bool = True,
    ):
        """
        Args:
            recording_filename_queue: 录音文件路径队列（录音结束时写入）
            samplerate: 采样率
            channels: 通道数
            record_key: 录音按键，默认 F8
            min_recording_duration: 最短录音时长（秒）
            cooldown_period: 录音冷却时间（秒）
            enable_print: 是否打印提示信息
        """
        # 队列
        self.recording_filename_queue = recording_filename_queue

        # 音频参数
        self.samplerate = samplerate
        self.channels = channels

        # 按键配置
        if record_key is None:
            record_key = Key.f8
        self.record_key = record_key

        # 时间控制
        self.min_recording_duration = min_recording_duration
        self.cooldown_period = cooldown_period
        self.last_recording_end_time = 0.0
        self.recording_start_time = 0.0

        # 状态
        self.is_recording = False
        self.stream = None
        self.recording_data = []
        self.listener = None

        # 文件名生成器
        self.recording_filename = GetFilename("temps/recording_", ".wav")

        # 确保 temps 目录存在
        os.makedirs("temps", exist_ok=True)

        self.enable_print = enable_print

    def start_recording(self):
        """开始录音"""
        current_time = time.time()

        # 检查冷却时间
        if current_time - self.last_recording_end_time < self.cooldown_period:
            if self.enable_print:
                print("录音冷却中，请稍后再试")
            return

        if not self.is_recording:
            if self.enable_print:
                print(f"\n录音中... (松开{self._get_key_name().upper()}停止)")
            self.is_recording = True
            self.recording_start_time = current_time

            # 创建音频流
            self.stream = sounddevice.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                dtype='int16'
            )
            self.recording_data = []
            self.stream.start()

            # 在独立线程中读取音频数据
            thread = threading.Thread(target=self._read_audio_loop, daemon=True)
            thread.start()

    def _read_audio_loop(self):
        """持续读取音频数据的线程"""
        while self.is_recording:
            try:
                data, _ = self.stream.read(1024)
                self.recording_data.append(data)
            except Exception as e:
                print(f"音频读取错误: {e}")
                break
            time.sleep(0.01)

    def stop_recording(self):
        """停止录音并保存"""
        if not self.is_recording:
            return

        recording_duration = time.time() - self.recording_start_time

        # 如果录音太短，等待足够时长
        if recording_duration < self.min_recording_duration:
            remaining = self.min_recording_duration - recording_duration
            if self.enable_print:
                print(f"录音时长不足 {self.min_recording_duration} 秒，等待中...")
            time.sleep(remaining)

        self.is_recording = False
        time.sleep(0.02)

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        # 合并录音数据并保存
        output_file = self.recording_filename.get_filename()
        write(output_file, self.samplerate, np.concatenate(self.recording_data))

        # 将文件路径放入队列
        self.recording_filename_queue.put(output_file)

        # 更新最后录音结束时间
        self.last_recording_end_time = time.time()

        if self.enable_print:
            print(f"录音完成: {output_file}")

    def _get_key_name(self):
        """获取按键名称"""
        if isinstance(self.record_key, Key):
            return self.record_key.name
        elif isinstance(self.record_key, KeyCode):
            return self.record_key.char
        return str(self.record_key)

    def _key_matches(self, key):
        """比较按键是否匹配，处理字符串和 Key 枚举的差异"""
        if key == self.record_key:
            return True
        if isinstance(self.record_key, str):
            key_name = getattr(key, 'name', None) or getattr(key, 'char', None)
            return key_name == self.record_key or str(key) == self.record_key
        return False

    def on_press(self, key):
        """按键按下事件"""
        try:
            if self._key_matches(key):
                threading.Thread(target=self.start_recording, daemon=True).start()
        except Exception as e:
            print(f"按键处理错误: {e}")

    def on_release(self, key):
        """按键松开事件"""
        try:
            if self._key_matches(key):
                self.stop_recording()
        except Exception as e:
            print(f"释放处理错误: {e}")

    def start(self):
        """启动键盘监听"""
        if self.enable_print:
            key_name = self._get_key_name()
            print(f"按 {key_name.upper()} 开始录音，松开 {key_name.upper()} 停止录音")

        self.listener = Listener(on_press=self.on_press, on_release=self.on_release)
        with self.listener:
            self.listener.join()


# ─────────────────────────────────────────────────────────────────────────────
# VAD 连续语音检测录音器
# ─────────────────────────────────────────────────────────────────────────────

class VADRecorder:
    """
    连续 VAD 录音器：无需按键，开口说话自动录音，静默自动发送
    能量阈值检测语音起止，适合游戏等场景
    """

    def __init__(
        self,
        recording_filename_queue,
        samplerate: int = 44100,
        channels: int = 1,
        speech_threshold: float = 0.01,
        silence_threshold: float = 0.003,
        start_frames: int = 3,
        end_frames: int = 40,
        silence_time: float = 1.5,
        min_recording_duration: float = 0.5,
        enable_print: bool = True,
        # 回调，由 STTController 注入
        on_speech_start=None,
        on_speech_end=None,
    ):
        self.recording_filename_queue = recording_filename_queue
        self.samplerate = samplerate
        self.channels = channels
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold
        self.start_frames = start_frames
        self.end_frames = end_frames
        self.silence_time = silence_time
        self.min_recording_duration = min_recording_duration
        self.enable_print = enable_print

        # 外部回调
        self.on_speech_start = on_speech_start or (lambda: None)
        self.on_speech_end = on_speech_end or (lambda _: None)

        self.stream = None
        self.is_recording = False
        self.recording_data = []
        self._running = False

        # 状态计数
        self._consecutive_speech = 0   # 连续语音帧计数
        self._consecutive_silence = 0  # 连续静默帧计数
        self._speech_start_time = 0.0  # 语音开始时间（检测到的那一刻）

        os.makedirs("temps", exist_ok=True)
        self.recording_filename = GetFilename("temps/recording_", ".wav")

    def _rms(self, data):
        """计算音频帧的 RMS 能量"""
        import numpy as np
        return np.sqrt(np.mean(data.astype(np.float32) ** 2))

    def _start_recording(self):
        """开始录音（内部）"""
        if self.is_recording:
            return
        if self.enable_print:
            print("\n[VAD] 检测到语音，开始录音...")
        self.is_recording = True
        self.recording_data = []
        self._speech_start_time = time.time()
        self._consecutive_silence = 0
        self.on_speech_start()

    def _stop_recording(self):
        """停止录音并保存（内部）"""
        if not self.is_recording:
            return
        self.is_recording = False

        duration = time.time() - self._speech_start_time
        if duration < self.min_recording_duration:
            if self.enable_print:
                print(f"[VAD] 录音太短 ({duration:.1f}s)，丢弃")
            return

        if not self.recording_data:
            return

        import numpy as np
        from scipy.io.wavfile import write
        output_file = self.recording_filename.get_filename()
        write(output_file, self.samplerate, np.concatenate(self.recording_data))

        if self.enable_print:
            print(f"[VAD] 录音完成: {output_file} ({duration:.1f}s)")

        self.recording_filename_queue.put(output_file)
        self.on_speech_end(output_file)

    def _audio_loop(self):
        """音频读取主循环"""
        import numpy as np

        blocksize = 1024
        self.stream = sounddevice.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype='int16'
        )
        self.stream.start()

        print_count = 0
        while self._running:
            try:
                data, _ = self.stream.read(blocksize)
            except Exception as e:
                print(f"[VAD] 音频读取错误: {e}")
                break

            energy = self._rms(data)

            # 每秒打印一次能量值帮助调试
            print_count += 1
            if print_count % 43 == 0:
                print(f"[VAD] energy={energy:.6f}  speech_thresh={self.speech_threshold}  silence_thresh={self.silence_threshold}")

            if self.is_recording:
                # 录音中：记录数据，检查静默
                self.recording_data.append(data)
                if energy < self.silence_threshold:
                    self._consecutive_silence += 1
                else:
                    self._consecutive_silence = 0

                # 连续 N 帧静默 + 超过沉默等待时间
                if self._consecutive_silence >= self.end_frames:
                    silence_elapsed = (self._consecutive_silence * blocksize) / self.samplerate
                    if silence_elapsed >= self.silence_time:
                        self._stop_recording()
                        self._consecutive_silence = 0
                        silence_printed = True
            else:
                # 未录音：检查是否开始
                if energy >= self.speech_threshold:
                    self._consecutive_speech += 1
                    if self._consecutive_speech >= self.start_frames:
                        print(f"[VAD] 触发！能量={energy:.6f}")
                        self._start_recording()
                        self._consecutive_speech = 0
                        silence_printed = False
                else:
                    self._consecutive_speech = 0
                    silence_printed = False

            time.sleep(0.01)

        # 退出时若还在录音则停止
        if self.is_recording:
            self._stop_recording()

        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass

    def start(self):
        """启动 VAD 录音（会开线程阻塞运行）"""
        if self.enable_print:
            print("[VAD] 连续语音检测已启动，开口说话自动录音，静默自动发送")
        self._running = True
        thread = threading.Thread(target=self._audio_loop, daemon=True)
        thread.start()

    def stop(self):
        """停止 VAD"""
        self._running = False
        if self.enable_print:
            print("[VAD] 已停止")
