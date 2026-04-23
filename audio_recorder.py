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

from get_filenames import GetFilename


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
