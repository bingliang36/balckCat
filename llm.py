"""
LLM 模块 - 豆包云端模型 (OpenAI 兼容接口)
支持流式输出，逐句触发回调
"""

import threading
from openai import OpenAI
from config import LLM_CONFIG


class LLMClient:
    """豆包 LLM 客户端 (流式)"""

    def __init__(self):
        self.client = OpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
            timeout=30.0,
        )
        self.model = LLM_CONFIG["model"]
        self.max_tokens = LLM_CONFIG.get("max_tokens", 200)
        self.system_prompt = LLM_CONFIG["system_prompt"]
        self._history = []
        # 句子结束符（更全）
        self._SENT_ENDS = ('。', '！', '？', '…', '\n', '.', '?', '!')

    def ask(self, text: str, callback=None, chunk_callback=None):
        """
        发送消息给 LLM，流式接收
        callback:        最终完成回调，接收 (error, full_response)
        chunk_callback:  逐句/逐词回调，接收完整句子的字符串
                         用于流式触发 TTS
        """
        thread = threading.Thread(
            target=self._request,
            args=(text, callback, chunk_callback),
            daemon=True
        )
        thread.start()

    def _request(self, text: str, callback, chunk_callback):
        import time
        t0 = time.time()
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self._history,
                    {"role": "user", "content": text},
                ],
                max_tokens=self.max_tokens,
                stream=True,
            )

            full_response = ""
            buffer = ""  # 凑 buffer 用
            MIN_CHUNK = 5  # 凑满 N 字就送 TTS，不管是否完整
            first_chunk_time = None  # 收到第一个字的时间
            tts_first_chunk_time = None  # 触发 TTS 第一段的时间
            # 颜文字还没接收完整（括号不成对）时不截断
            def has_open_emoticon(b):
                return '(' in b and b.count('(') > b.count(')')

            def send_chunk(text):
                nonlocal tts_first_chunk_time
                if tts_first_chunk_time is None:
                    tts_first_chunk_time = time.time()
                    delay = tts_first_chunk_time - first_chunk_time
                    print(f'[llm] 首段TTS触发  首字→TTS耗时={delay:.3f}s')
                chunk_callback(text)

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if not content:
                    continue

                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    req_delay = first_chunk_time - t0
                    print(f'[llm] 首字返回  请求延迟={req_delay:.3f}s')

                full_response += content
                buffer += content

                if not chunk_callback:
                    continue

                has_punct = any(p in buffer for p in self._SENT_ENDS)
                # 碰到标点 且 字数够 且 没有未完成的颜文字 → 送 TTS
                if has_punct and len(buffer) >= MIN_CHUNK and not has_open_emoticon(buffer):
                    send_chunk(buffer)
                    buffer = ""

            # 发送剩余内容
            if buffer.strip() and chunk_callback:
                chunk_callback(buffer.strip())

            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": full_response})

            if callback:
                callback(None, full_response.strip())

            print(f'[llm] 云端请求完成  总耗时={time.time()-t0:.2f}s')

        except Exception as e:
            print(f"[llm] 请求失败: {e}  总耗时={time.time()-t0:.2f}s")
            if callback:
                callback(str(e), None)

    def clear_history(self):
        """清空对话历史"""
        self._history = []
