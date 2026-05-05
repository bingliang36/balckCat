"""
LLM 模块 - 豆包云端模型 (OpenAI 兼容接口)
支持流式输出，逐句触发回调
支持 Function Calling 工具调用
支持原生视觉（look_screen/look_camera 返回 IMAGE:base64）
"""

import threading
from openai import OpenAI
from config import LLM_CONFIG, VISION_MODE


def _get_tool_function(name: str):
    """根据工具名查找工具函数"""
    # 动态导入工具模块
    from tools import TOOL_FUNCTIONS
    return TOOL_FUNCTIONS.get(name)


def _is_realtime_query(text: str) -> bool:
    """
    判断用户是否询问实时信息（需要联网搜索）
    """
    realtime_keywords = [
        "天气", "新闻", "今天", "现在", "最新", "实时",
        "股价", "股票", "比分", "比赛", "汇率", "行情",
        "热搜", "榜单", "排行", "热点",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in realtime_keywords)


def _apply_vision_mode():
    """启动时将 config 中的 VISION_MODE 应用到视觉工具"""
    from tools import set_vision_mode
    set_vision_mode(VISION_MODE)
    print(f"[llm] 视觉模式: {VISION_MODE}")


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
        # 应用视觉模式配置
        _apply_vision_mode()

    def set_tools(self, tools: list):
        """设置可用工具列表"""
        self._tools = tools


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

    def _stream_response(self, text: str, chunk_callback, done_callback=None):
        """
        将已有文本流式输出，模拟逐字返回的效果
        用于工具调用后的最终回复
        done_callback: 所有 chunk 发完后调用，用于通知 TTS 回合结束
        """
        import time
        t0 = time.time()
        MIN_CHUNK = 20
        buffer = ""
        first_chunk_time = None
        tts_first_chunk_time = None

        def has_open_emoticon(b):
            return '(' in b and b.count('(') > b.count(')')

        def send_chunk(text):
            nonlocal tts_first_chunk_time
            if tts_first_chunk_time is None:
                tts_first_chunk_time = time.time()
                delay = tts_first_chunk_time - first_chunk_time
                print(f'[llm] 首段TTS触发(stream)  首字→TTS耗时={delay:.3f}s')
            chunk_callback(text)

        for i, char in enumerate(text):
            buffer += char

            if first_chunk_time is None:
                first_chunk_time = time.time()
                req_delay = first_chunk_time - t0
                print(f'[llm] 首字返回(stream)  耗时={req_delay:.3f}s')

            # 凑满 MIN_CHUNK 字 且 碰到句末标点 且 没有未完成的颜文字 → 送 TTS
            has_sent_end = any(buffer.endswith(p) for p in self._SENT_ENDS)
            if len(buffer) >= MIN_CHUNK and has_sent_end and not has_open_emoticon(buffer):
                send_chunk(buffer)
                buffer = ""

        # 发送剩余内容（即使没有句末标点）
        if buffer.strip():
            send_chunk(buffer.strip())

        print(f'[llm] 流式输出完成  总耗时={time.time()-t0:.3f}s')
        if done_callback:
            done_callback()

    def _request_with_web_search(self, text: str, callback, chunk_callback):
        """
        联网搜索模式 - 使用豆包原生 web_search 工具
        不使用 function calling，直接用 responses API 的 web_search 工具
        """
        import time
        t0 = time.time()

        try:
            # 使用 responses API + web_search 工具（限制搜索范围，精简输出）
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "user", "content": text}
                ],
                tools=[{
                    "type": "web_search",
                    "max_keyword": 1,       # 最少搜索关键词
                    "limit": 2,             # 最多返回3条结果
                }],
                max_tool_calls=1,           # 只搜索一轮
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "weather_result",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "reply": {"type": "string", "description": "简短口语化回复，50字以内"}
                            },
                            "required": ["reply"]
                        },
                        "strict": True
                    }
                },
            )

            # 获取回复内容
            full_response = ""
            for item in response.output:
                if item.type == "message" and item.role == "assistant":
                    for content in item.content:
                        if content.type == "output_text":
                            full_response = content.text
                        elif content.type == "function":
                            import json
                            try:
                                args = json.loads(content.arguments or "{}")
                                summary = args.get("summary", "")
                                content_text = args.get("content", "")
                                parts = []
                                if summary:
                                    parts.append(summary)
                                if content_text:
                                    parts.append(content_text)
                                if parts:
                                    full_response = "。".join(parts)
                            except Exception as e:
                                print(f"[llm] 解析function输出失败: {e}")

            # 如果输出仍然是原始 JSON（包含 summary/content 字段），则清理
            if '"reply"' in full_response or '"summary"' in full_response or '"content"' in full_response:
                import json
                try:
                    data = json.loads(full_response)
                    # 优先取 reply，其次取 summary+content
                    reply = data.get("reply", "")
                    if reply:
                        full_response = reply
                    else:
                        summary = data.get("summary", "")
                        content_text = data.get("content", "")
                        parts = [p for p in [summary, content_text] if p]
                        full_response = "。".join(parts) if parts else str(data)
                except:
                    pass

            print(f"[llm] 最终回复: {full_response[:100]}...")

            req_done_time = time.time()
            req_delay = req_done_time - t0
            print(f"[llm] 联网搜索完成  请求延迟={req_delay:.3f}s  内容={full_response[:50]}...")

            # 保存历史
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": full_response})

            # 流式输出
            if chunk_callback and full_response:
                def done_callback():
                    if callback:
                        callback(None, full_response)
                self._stream_response(full_response, chunk_callback, done_callback)
            else:
                if callback:
                    callback(None, full_response)

        except Exception as e:
            print(f"[llm] 联网搜索失败: {e}")
            if callback:
                callback(str(e), None)

    def _request_with_tools(self, text: str, tools: list, callback, chunk_callback):
        """支持工具调用的请求处理"""
        import time
        t0 = time.time()

        # 判断是否需要联网搜索（实时信息查询）
        if _is_realtime_query(text):
            print("[llm] 检测到实时查询，使用联网搜索模式")
            self._request_with_web_search(text, callback, chunk_callback)
            return

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
                extra_kwargs = {}
                # 从 config 读取 reasoning_effort 控制思考深度
                reasoning_effort = LLM_CONFIG.get("reasoning_effort")
                if reasoning_effort:
                    extra_kwargs["reasoning_effort"] = reasoning_effort

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    stream=False,  # 工具调用模式不使用流式
                    **extra_kwargs,
                )

                assistant_msg = response.choices[0].message
                req_done_time = time.time()
                req_delay = req_done_time - t0
                print(f"[llm] 助手回复(工具调用)  请求延迟={req_delay:.3f}s  内容={assistant_msg.content[:30] if assistant_msg.content else 'None'}...")

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

                    # 解析工具参数
                    tool_args = {}
                    if tool_call.function.arguments:
                        import json
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            pass

                    # 查找并执行工具函数
                    tool_func = _get_tool_function(tool_name)
                    if not tool_func:
                        tool_result = f"错误：未找到工具 {tool_name}"
                    else:
                        try:
                            # recall_memory 需要用户的原始输入作为 query
                            if tool_name == "recall_memory":
                                tool_result = tool_func(query=text)
                            else:
                                tool_result = tool_func(**tool_args)
                            print(f"[llm] 工具结果: {tool_result[:50]}...")
                        except Exception as e:
                            tool_result = f"工具执行错误: {e}"
                            print(f"[llm] {tool_result}")

                    # 构建工具结果消息
                    # 如果工具返回的是 IMAGE:base64，需要以 image_url 格式传入
                    if tool_result.startswith("IMAGE:"):
                        base64_data = tool_result[6:]  # 去掉 "IMAGE:" 前缀
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}
                                }
                            ],
                            "name": tool_name,
                        }
                    else:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result,
                            "name": tool_name,
                        }
                    messages.append(tool_msg)

            # 超过最大轮次
            print(f"[llm] 警告：超过最大工具调用轮次 {max_rounds}")

        except Exception as e:
            print(f"[llm] 请求失败: {e}  总耗时={time.time()-t0:.2f}s")
            if callback:
                callback(str(e), None)


