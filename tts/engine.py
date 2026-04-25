#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS 模块 —— 工厂模式
支持豆包云端 TTS 和本地 vits-simple-api (GPT-SoVITS)
支持流式合成，边合成边播放
"""

import os
import base64
import uuid
import tempfile
import threading
import queue as _queue
import requests
import time

from abc import ABC, abstractmethod

from config import TTS_CONFIG
from utils.emotion import EmotionTrigger


# ══════════════════════════════════════════════════════════════════════════════
#  TTSProvider 抽象基类
# ══════════════════════════════════════════════════════════════════════════════

class TTSProvider(ABC):
    """TTS 提供者抽象基类"""

    @abstractmethod
    def synthesize(self, text: str) -> bytes | None:
        """同步合成语音，返回音频 bytes，失败返回 None"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """返回提供者名称，用于日志"""
        pass

    def get_audio_format(self) -> str:
        """返回音频格式后缀，如 'mp3', 'wav'"""
        return 'mp3'

    def synthesize_streaming(self, text: str, chunk_callback):
        """
        流式合成语音。
        chunk_callback: 收到音频片段时回调，接收 (audio_bytes, is_last) 参数
        默认实现： fallback 到同步合成
        """
        audio = self.synthesize(text)
        if audio:
            chunk_callback(audio, True)


# ══════════════════════════════════════════════════════════════════════════════
#  豆包 TTS 提供者
# ══════════════════════════════════════════════════════════════════════════════

class DoubaoTTSProvider(TTSProvider):
    """豆包云端 TTS"""

    URL = 'https://openspeech.bytedance.com/api/v1/tts'

    def __init__(self, cfg: dict):
        self.api_key    = cfg.get('api_key', '').strip()
        self.voice_type = cfg.get('voice_type', '').strip()
        self.cluster    = cfg.get('cluster', 'volcano_icl').strip()
        self.speed      = float(cfg.get('speed_ratio', 1.0))
        self.enabled    = bool(self.api_key) and bool(self.voice_type)

        if self.enabled:
            print(f'[tts] 豆包 TTS 已启用  voice={self.voice_type}  cluster={self.cluster}')
        else:
            print('[tts] 豆包 TTS 未正确配置')

    def get_provider_name(self) -> str:
        return 'doubao'

    def synthesize(self, text: str) -> bytes | None:
        if not self.enabled:
            return None

        payload = {
            'app': {'cluster': self.cluster},
            'user': {'uid': 'desktop_pet'},
            'audio': {
                'voice_type':  self.voice_type,
                'encoding':    'mp3',
                'speed_ratio': self.speed,
            },
            'request': {
                'reqid':     str(uuid.uuid4()),
                'text':      text[:512],
                'operation': 'query',
            },
        }
        headers = {
            'x-api-key':    self.api_key,
            'Content-Type': 'application/json',
        }
        for attempt in range(2):
            try:
                import time
                t0 = time.time()
                resp = requests.post(
                    self.URL, headers=headers, json=payload, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                code = data.get('code')
                if code == 3000:
                    duration = data.get('addition', {}).get('duration', '?')
                    audio = base64.b64decode(data['data'])
                    print(f'[tts] 豆包合成成功  时长={duration}ms  耗时={time.time()-t0:.2f}s  大小={len(audio)/1024:.1f}KB  文本={text[:20]}')
                    return audio
                print(f'[tts] 豆包 API 错误 code={code}  message={data.get("message", "")}')
                return None
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                if attempt == 0:
                    print(f'[tts] 豆包连接异常，重试中... ({e})')
                else:
                    print(f'[tts] 豆包重试失败: {e}')
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  本地 TTS 提供者 (vits-simple-api / GPT-SoVITS)
# ══════════════════════════════════════════════════════════════════════════════

class LocalTTSProvider(TTSProvider):
    """本地 vits-simple-api (GPT-SoVITS) 支持流式"""

    def __init__(self, cfg: dict):
        self.url            = cfg.get('url', 'http://127.0.0.1:23456').strip()
        self.model_id       = int(cfg.get('model_id', 0))
        self.format         = cfg.get('format', 'wav').strip()
        self.lang           = cfg.get('lang', 'auto').strip()
        self.reference_audio = cfg.get('reference_audio', '').strip()
        self.prompt_text    = cfg.get('prompt_text', '').strip()
        self.prompt_lang    = cfg.get('prompt_lang', 'auto').strip()
        self.preset         = cfg.get('preset', 'default').strip()
        self.enabled        = bool(self.url)

        if self.enabled:
            print(f'[tts] 本地 TTS 已启用  url={self.url}  model_id={self.model_id}')
        else:
            print('[tts] 本地 TTS 未配置 url')

    def get_provider_name(self) -> str:
        return 'local'

    def get_audio_format(self) -> str:
        return self.format or 'wav'

    def synthesize(self, text: str) -> bytes | None:
        """同步合成"""
        if not self.enabled:
            return None

        import random
        import string

        fields = {
            'text':       text[:512],
            'id':         str(self.model_id),
            'format':     self.format,
            'lang':       self.lang,
            'segment_size': '30',
            'preset':     self.preset,
            'prompt_text':   self.prompt_text,
            'prompt_lang':   self.prompt_lang,
        }

        if self.reference_audio and os.path.exists(self.reference_audio):
            upload_name = os.path.basename(self.reference_audio)
            upload_type = f'audio/{upload_name.split(".")[-1]}'
            with open(self.reference_audio, 'rb') as f:
                fields['reference_audio'] = (upload_name, f.read(), upload_type)

        boundary = '----VoiceConversionFormBoundary' + ''.join(
            random.sample(string.ascii_letters + string.digits, 16)
        )

        from requests_toolbelt.multipart.encoder import MultipartEncoder
        m = MultipartEncoder(fields=fields, boundary=boundary)
        headers = {'Content-Type': m.content_type}

        api_url = f'{self.url}/voice/gpt-sovits'

        for attempt in range(2):
            try:
                import time
                t0 = time.time()
                resp = requests.post(api_url, data=m, headers=headers, timeout=30)
                resp.raise_for_status()
                audio = resp.content
                print(f'[tts] 本地合成成功  文本={text[:20]}  耗时={time.time()-t0:.2f}s  大小={len(audio)/1024:.1f}KB')
                return audio
            except Exception as e:
                if attempt == 0:
                    print(f'[tts] 本地 TTS 连接异常，重试中... ({e})')
                else:
                    print(f'[tts] 本地 TTS 重试失败: {e}')
        return None

    def synthesize_streaming(self, text: str, chunk_callback):
        """
        流式合成：边合成边回调音频片段
        vits-simple-api 的 streaming 模式通过 chunked transfer encoding 返回音频
        """
        if not self.enabled:
            return

        import random
        import string

        fields = {
            'text':       text[:512],
            'id':         str(self.model_id),
            'format':     'mp3',  # 流式必须用 mp3
            'lang':       self.lang,
            'segment_size': '30',
            'preset':     self.preset,
            'prompt_text':   self.prompt_text,
            'prompt_lang':   self.prompt_lang,
            'streaming':  'true',
        }

        if self.reference_audio and os.path.exists(self.reference_audio):
            upload_name = os.path.basename(self.reference_audio)
            upload_type = f'audio/{upload_name.split(".")[-1]}'
            with open(self.reference_audio, 'rb') as f:
                fields['reference_audio'] = (upload_name, f.read(), upload_type)

        boundary = '----VoiceConversionFormBoundary' + ''.join(
            random.sample(string.ascii_letters + string.digits, 16)
        )

        from requests_toolbelt.multipart.encoder import MultipartEncoder
        m = MultipartEncoder(fields=fields, boundary=boundary)
        headers = {'Content-Type': m.content_type}

        api_url = f'{self.url}/voice/gpt-sovits'

        try:
            resp = requests.post(api_url, data=m, headers=headers, timeout=60)
            resp.raise_for_status()
            # 先把全部数据收完（不用 stream=True 接收，避免惰性迭代问题）
            all_data = resp.content
            # 再逐块送回调（模拟流式效果）
            pos = 0
            total = len(all_data)
            while pos + 8192 < total:
                chunk_callback(all_data[pos:pos + 8192], False)
                pos += 8192
            if pos < total:
                chunk_callback(all_data[pos:], True)
            print(f'[tts] 流式合成完成  文本={text[:20]}')
        except Exception as e:
            print(f'[tts] 流式合成失败: {e}')
            raise  # 让外层 _play_streaming 的 except 捕获并做 fallback


# ══════════════════════════════════════════════════════════════════════════════
#  TTS 工厂
# ══════════════════════════════════════════════════════════════════════════════

class TTSFactory:
    """TTS 工厂，根据配置创建对应的 TTS 提供者"""

    @staticmethod
    def create(cfg: dict) -> TTSProvider:
        provider = cfg.get('provider', 'doubao').strip().lower()
        if provider == 'local':
            return LocalTTSProvider(cfg.get('local', {}))
        else:
            return DoubaoTTSProvider(cfg.get('doubao', cfg))


# ══════════════════════════════════════════════════════════════════════════════
#  TTS 门面类
# ══════════════════════════════════════════════════════════════════════════════

class TTS:
    """
    TTS 播放器，支持流式合成和播放流水线

    流水线逻辑:
    1. 新句子到达 → 立即开始后台流式合成
    2. 合成完毕 → 一次性加载音频并播放
    3. 播放期间 → 按时间点触发表情和口型
    4. 播放结束 → 继续处理下一句
    """

    def __init__(self, on_amplitude=None, on_expression=None, on_turn_complete=None):
        self._provider = TTSFactory.create(TTS_CONFIG)
        self.on_amplitude = on_amplitude
        self.on_expression = on_expression  # 表情触发回调 (expression_name: str) -> None
        self.on_turn_complete = on_turn_complete  # 本轮对话所有句子播完回调

        self._q = _queue.Queue()
        self._current_file = None
        self._streaming_active = False
        self._turn_ended = False
        self._first_synth_done = False  # 本轮第一次合成是否已完成
        self._first_synth_sent_time = None  # 本轮第一段文字送入TTS的时间（现已改为队列项自带，不再共用）

        self._pygame = None
        self._worker_thread = None

        if self._provider.enabled:
            try:
                import pygame
                pygame.mixer.init()
                self._pygame = pygame
                print(f'[tts] 初始化成功  provider={self._provider.get_provider_name()}')
                threading.Thread(target=self._worker, daemon=True).start()
            except ImportError:
                print('[tts] 缺少 pygame，TTS 已关闭')
                self._provider.enabled = False

    # ── 公开接口 ────────────────────────────────────────────────────────────────
    def speak_async(self, text: str, emotion_triggers: list = None):
        """
        异步发送句子到流水线，立即返回
        emotion_triggers: EmotionTrigger 列表，字符位置 + 对应表情名
        """
        if self._provider.enabled and text.strip():
            import time
            sent_time = time.time()
            if self._first_synth_done is False:
                self._first_synth_sent_time = sent_time
            self._q.put((text, emotion_triggers or [], sent_time))

    def clear(self):
        """清空队列并停止当前播放"""
        while not self._q.empty():
            try:
                self._q.get_nowait()
                self._q.task_done()
            except Exception:
                pass
        if self._pygame:
            try:
                self._pygame.mixer.music.stop()
            except Exception:
                pass
        self._streaming_active = False

    # ── 内部 worker ────────────────────────────────────────────────────────────
    def _worker(self):
        """后台工作线程：流式合成 + 播放 + 情绪触发"""
        while True:
            item = self._q.get()
            if len(item) == 3:
                text, emotion_triggers, sent_time = item
            else:
                text, emotion_triggers = item
                sent_time = None
            try:
                self._streaming_active = True
                self._play_streaming(text, emotion_triggers, sent_time)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f'[tts] 播放出错: {e}')
            finally:
                self._streaming_active = False
                self._q.task_done()
                # 检查本轮是否已标记结束 且 队列已空
                if self.on_turn_complete and self._turn_ended and self._q.empty():
                    self._turn_ended = False  # 重置
                    import time
                    time.sleep(1.0)
                    self.on_turn_complete()

    def end_turn(self):
        """
        标记本轮对话结束：当 LLM 回答完毕后调用。
        这样当前队列里剩余的句子播完后，会等待 1000ms 再触发 on_turn_complete。
        """
        self._turn_ended = True
        self._first_synth_done = False  # 重置，下一轮重新记录
        self._first_synth_sent_time = None

    def _split_text_by_punctuation(self, text: str):
        """
        按标点符号分句：碰到 。！？，； 就截断
        返回分句列表，每句保留结尾标点（除最后一句）
        """
        import re
        # 匹配中日文标点
        pattern = r'([。！？，；])'
        parts = re.split(pattern, text)
        chunks = []
        # parts 格式：['前半句', '标点', '后半句', '标点', ...]
        for i in range(0, len(parts) - 1, 2):
            chunk = parts[i] + (parts[i + 1] if i + 1 < len(parts) else '')
            if chunk.strip():
                chunks.append(chunk)
        # 最后一段（没有标点）
        if parts[-1].strip():
            chunks.append(parts[-1])
        return chunks

    def _adjust_triggers_for_chunk(self, triggers: list, char_offset: int):
        """把 triggers 的字符位置调整为相对于当前分句"""
        adjusted = []
        for t in triggers:
            rel_pos = t.char_pos - char_offset
            if 0 <= rel_pos < 500:  # 合理范围内
                adjusted.append(EmotionTrigger(rel_pos, t.expression_name))
        return adjusted

    def _play_streaming(self, text: str, emotion_triggers: list, sent_time: float = None):
        """分句流式：按标点分句，逐句合成+播放"""
        chunks = self._split_text_by_punctuation(text)
        total_chunks = len(chunks)

        for i, chunk in enumerate(chunks):
            # 计算本句在原文中的字符偏移
            char_offset = text.index(chunk) if i == 0 else text.index(chunk, text.index(chunks[i - 1]) + len(chunks[i - 1]))
            # 筛选出本句对应的情绪触发点
            triggers = self._adjust_triggers_for_chunk(emotion_triggers, char_offset)

            print(f'[tts] 分句 [{i+1}/{total_chunks}]: {chunk[:30]}')

            try:
                audio_bytes = self._provider.synthesize(chunk)
            except Exception as e:
                print(f'[tts] 分句合成出错: {e}')
                audio_bytes = None

            # 记录第一段合成的耗时
            if not self._first_synth_done and audio_bytes and sent_time is not None:
                self._first_synth_done = True
                synth_time = time.time() - sent_time
                print(f'[tts] 首段合成完成  TTS合成耗时={synth_time:.3f}s')

            if audio_bytes:
                try:
                    self._play_sync(audio_bytes, triggers, len(chunk))
                except Exception as e:
                    print(f'[tts] 分句播放出错: {e}')
            else:
                print(f'[tts] 分句合成失败，跳过: {chunk[:20]}')

    def _estimate_duration(self, text_length: int) -> float:
        """
        估算音频时长（秒）
        基准：中文约 400字/分钟 ≈ 6.67字/秒
        取保守值 5字/秒，服务器 speed=1.0
        """
        return text_length / 5.0

    def _emotion_trigger_loop(self, triggers: list, total_len: int, total_duration: float):
        """
        按时间点触发表情
        每个触发点的时间 = (char_pos / total_len) × total_duration
        """
        import time
        if total_len == 0 or total_duration == 0:
            return

        for trigger in triggers:
            # 计算触发时间点
            trigger_time = (trigger.char_pos / total_len) * total_duration
            # 等待到达触发时间
            start_time = time.time()
            while time.time() - start_time < trigger_time:
                if not self._pygame.mixer.music.get_busy():
                    return  # 音频提前结束，不再触发
                self._pygame.time.wait(20)
            # 触发表情
            if self.on_expression:
                self.on_expression(trigger.expression_name)

    def _amplitude_loop(self):
        """播放期间持续触发口型回调"""
        if not self.on_amplitude:
            return
        import random
        while self._pygame.mixer.music.get_busy():
            self.on_amplitude(0.4 + random.random() * 0.4)
            self._pygame.time.wait(50)
        self.on_amplitude(0.0)

    def _play_sync(self, audio_bytes: bytes, emotion_triggers: list = None, text_length: int = 0):
        """同步播放：先完整合成，再播放"""
        import time
        import random as _random
        t0 = time.time()
        tmp_path = None
        print(f'[tts] _play_sync 开始  t0={t0}  audio_len={len(audio_bytes) if audio_bytes else 0}  text_len={text_length}')
        try:
            suffix = f'.{self._provider.get_audio_format()}'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            load_t = time.time()
            self._pygame.mixer.music.load(tmp_path)
            self._pygame.mixer.music.play()
            play_start = time.time()

            # 启动情绪触发线程
            if emotion_triggers and text_length > 0:
                total_duration = self._estimate_duration(text_length)
                threading.Thread(
                    target=self._emotion_trigger_loop,
                    args=(emotion_triggers, text_length, total_duration),
                    daemon=True
                ).start()

            clock = self._pygame.time.Clock()
            while self._pygame.mixer.music.get_busy():
                clock.tick(30)
                if self.on_amplitude:
                    self.on_amplitude(0.4 + _random.random() * 0.4)
            # 播放结束，闭嘴
            if self.on_amplitude:
                self.on_amplitude(0.0)
            self._pygame.mixer.music.unload()
            done_t = time.time()
            print(f'[tts] 播放完成  音频大小={len(audio_bytes)/1024:.1f}KB  加载={load_t-t0:.2f}s  播放={done_t-play_start:.2f}s  总计={done_t-t0:.2f}s')
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


class _DummyTTS:
    """TTS 不可用时的空实现"""
    def speak_async(self, text: str): pass
    def clear(self): pass
