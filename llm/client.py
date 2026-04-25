"""
LLM 模块 - 豆包云端模型 (OpenAI 兼容接口)
支持流式输出，逐句触发回调
支持 Function Calling 工具调用
"""

import threading
import json
from openai import OpenAI
from config import LLM_CONFIG


class LLMClient:
    """豆包 LLM 客户端 (流式 + 工具调用)"""

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
        self._tools = []  # 工具定义列表
        # 句子结束符（更全）
        self._SENT_ENDS = ('。', '！', '？', '…', '\n', '.', '?', '!')

    def set_tools(self, tools: list):
        """设置可用工具列表"""
        self._tools = tools

    def ask(self, text: str, callback=None, chunk_callback=None):
        """
        发送消息给 LLM，流式接收（纯聊天，无工具）
        callback:        最终完成回调，接收 (error, full_response)
        chunk_callback: 逐句/逐词回调，接收完整句子的字符串
                         用于流式触发 TTS
        """
        thread = threading.Thread(
            target=self._request,
            args=(text, callback, chunk_callback),
            daemon=True
        )
        thread.start()

    def ask_with_tools(self, text: str, tools: list, callback=None, chunk_callback=None):
        """
        发送消息给 LLM，支持工具调用
        工具调用时会阻塞等待结果，然后继续对话直到最终回复

        callback:        最终完成回调，接收 (error, full_response)
        chunk_callback: 逐句/逐词回调，用于流式触发 TTS（仅在最终回复阶段生效）
        """
        thread = threading.Thread(
            target=self._request_with_tools,
            args=(text, tools, callback, chunk_callback),
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
            MIN_CHUNK = 7  # 凑满 N 字就送 TTS，不管是否完整
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

    def _stream_response(self, text: str, chunk_callback, done_callback=None):
        """
        将已有文本流式输出，模拟逐字返回的效果
        用于工具调用后的最终回复
        done_callback: 所有 chunk 发完后调用，用于通知 TTS 回合结束
        """
        MIN_CHUNK = 7
        buffer = ""

        def has_open_emoticon(b):
            return '(' in b and b.count('(') > b.count(')')

        for i, char in enumerate(text):
            buffer += char

            # 碰到标点 且 字数够 且 没有未完成的颜文字 → 送 TTS
            has_punct = any(buffer.endswith(p) for p in self._SENT_ENDS)
            if has_punct and len(buffer) >= MIN_CHUNK and not has_open_emoticon(buffer):
                chunk_callback(buffer)
                buffer = ""

        # 发送剩余内容
        if buffer.strip():
            chunk_callback(buffer.strip())

        # 所有 chunk 发完后通知 TTS 回合结束
        if done_callback:
            done_callback()

    def _request_with_tools(self, text: str, tools: list, callback, chunk_callback):
        """支持工具调用的请求处理"""
        import time
        t0 = time.time()

        # 构建消息历史
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self._history,
            {"role": "user", "content": text},
        ]

        max_rounds = 10  # 防止无限循环
        round_count = 0

        try:
            while round_count < max_rounds:
                round_count += 1
                print(f"[llm] 工具调用第 {round_count} 轮")

                # 发起请求
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    stream=False,  # 工具调用模式不使用流式
                )

                assistant_msg = response.choices[0].message
                print(f"[llm] 助手回复: {assistant_msg.content}")

                # 将助手回复加入历史
                messages.append(assistant_msg.model_dump())

                # 检查是否需要调用工具
                if not assistant_msg.tool_calls:
                    # 没有工具调用，这是最终回复，用流式输出
                    full_response = assistant_msg.content or ""
                    self._history.append({"role": "user", "content": text})
                    self._history.append({"role": "assistant", "content": full_response})

                    if chunk_callback and full_response:
                        # 流式输出最终回复，触发 TTS 和情绪
                        # done_callback 在所有 chunk 入队后通知 TTS 回合结束
                        def done_callback():
                            if callback:
                                callback(None, full_response)

                        self._stream_response(full_response, chunk_callback, done_callback)
                    else:
                        if callback:
                            callback(None, full_response)
                    print(f'[llm] 工具调用对话完成  总耗时={time.time()-t0:.2f}s')
                    return

                # 处理工具调用
                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call.function.name
                    print(f"[llm] 调用工具: {tool_name}")

                    # 查找并执行工具函数
                    tool_func = self._get_tool_function(tool_name, tools)
                    if not tool_func:
                        tool_result = f"错误：未找到工具 {tool_name}"
                    else:
                        try:
                            tool_result = tool_func()
                            print(f"[llm] 工具结果: {tool_result}")
                        except Exception as e:
                            tool_result = f"工具执行错误: {e}"
                            print(f"[llm] {tool_result}")

                    # 将工具结果回填
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                        "name": tool_name,
                    })

            # 超过最大轮次
            print(f"[llm] 警告：超过最大工具调用轮次 {max_rounds}")

        except Exception as e:
            print(f"[llm] 请求失败: {e}  总耗时={time.time()-t0:.2f}s")
            if callback:
                callback(str(e), None)

    def _get_tool_function(self, name: str, tools: list):
        """根据工具名查找工具函数"""
        # 动态导入工具模块
        from tools import TOOL_FUNCTIONS
        return TOOL_FUNCTIONS.get(name)

    def clear_history(self):
        """清空对话历史"""
        self._history = []
