"""
MemNet 记忆客户端
封装 memories（存储）和 recall（回忆）接口
"""

from typing import List

from memnetai.basics.request.memnetai_client import MemNetAIClient
from memnetai.basics.request.message.message import Message

from config import MEMNET_CONFIG


class MemoryClient:
    """MemNet AI 记忆客户端（异步存储）"""

    def __init__(self):
        self.client = MemNetAIClient(
            base_url=MEMNET_CONFIG["base_url"],
            api_key=MEMNET_CONFIG["api_key"],
        )
        self.memory_agent_name = MEMNET_CONFIG["memory_agent_name"]
        self.namespace = MEMNET_CONFIG["namespace"]
        self.character = MEMNET_CONFIG["character"]

    def recall(self, query: str) -> str:
        """
        回忆接口，根据关键词查询记忆
        Returns:
            str: 记忆内容（直接拼接到用户输入），空字符串表示无记忆
        """
        try:
            result = self.client.recall(
                memory_agent_name=self.memory_agent_name,
                query=query,
                character=self.character,
                recall_deep=1,
                is_include_linked_new_memories_from_invalid=0,
                is_using_associative_thinking=1,
                is_using_common_sense_database=1,
                is_using_global_common_sense_database=1,
                is_using_memory_agent_common_sense_database=0,
                is_returning_detailed_memory_info=0,
            )
            if not result:
                return ""

            resp = result.get("response_json", {})
            data = resp.get("data", {})
            content = data.get("memoryPrompt", "") or data.get("content", "") or data.get("text", "")
            if content:
                print(f"[memory] 回忆到: {str(content)[:100]}")
            return str(content) if content else ""

        except Exception as e:
            print(f"[memory] 回忆失败: {e}")
            return ""

    def store(self, messages: List[Message], async_mode: int = 1):
        """
        异步存储对话到 MemNet
        async_mode=1: 请求后立即返回，后台完成记忆
        """
        try:
            self.client.memories(
                memory_agent_name=self.memory_agent_name,
                messages=messages,
                language="zh-CN",
                is_third_person=0,
                metadata="",
                async_mode=async_mode,
            )
            if async_mode:
                print("[memory] 记忆任务已提交（异步）")
            else:
                print("[memory] 记忆已完成")
        except Exception as e:
            print(f"[memory] 存储失败: {e}")
