"""
MemNet 记忆客户端
封装 memories（存储）、recall（回忆）、关键词提取
"""

import threading
from typing import List, Optional

from memnetai.basics.request.memnetai_client import MemNetAIClient
from memnetai.basics.request.message.message import Message

from config import MEMNET_CONFIG, LLM_CONFIG


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

    def store(self, messages: List[Message], metadata: str = "", async_mode: int = 1):
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
                metadata=metadata,
                async_mode=async_mode,
            )
            if async_mode:
                print("[memory] 记忆任务已提交（异步）")
            else:
                print("[memory] 记忆已完成")
        except Exception as e:
            print(f"[memory] 存储失败: {e}")

    def extract_keywords(self, text: str, role: str = "user") -> List[str]:
        """
        用豆包模型从单段文本中提取关键词（实体名词、主题词等）
        role: "user" 或 "assistant"，决定提示词里的人称
        返回关键词列表
        """
        import re
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=LLM_CONFIG["base_url"],
                api_key=LLM_CONFIG["api_key"],
                timeout=15.0,
            )
            if role == "user":
                prompt = (
                    "你是一个关键词提取助手。请从用户说的话中提取关键实体名词（人名、物名、地名、事件等），"
                    "每个关键词长度2-10字，返回3-5个，用逗号分隔，只返回关键词列表，不要解释。\n\n"
                    f"用户：{text}\n\n"
                    "提取的关键词："
                )
            else:
                prompt = (
                    "你是一个关键词提取助手。请从AI助手的回复中提取关键实体名词（人名、物名、地名、事件等），"
                    "每个关键词长度2-10字，返回3-5个，用逗号分隔，只返回关键词列表，不要解释。\n\n"
                    f"助手：{text}\n\n"
                    "提取的关键词："
                )
            resp = client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"^\d+[.、）)]\\s*", "", raw)
            raw = raw.strip("，。、；：")
            keywords = [k.strip() for k in raw.split(",") if len(k.strip()) >= 2]
            print(f"[memory] 豆包提取[{role}]关键词: {keywords}")
            return keywords
        except Exception as e:
            print(f"[memory] 关键词提取失败: {e}")
            return []

    def generate_summary(self, user_text: str, assistant_text: str) -> str:
        """
        用豆包模型生成话题摘要，存入 MemNet metadata 字段
        """
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=LLM_CONFIG["base_url"],
                api_key=LLM_CONFIG["api_key"],
                timeout=15.0,
            )
            prompt = (
                "请用一句话简要概括以下对话的主题，不超过30字：\n\n"
                f"用户：{user_text}\n"
                f"助手：{assistant_text}\n\n"
                "摘要："
            )
            resp = client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0,
            )
            summary = (resp.choices[0].message.content or "").strip()
            print(f"[memory] 话题摘要: {summary}")
            return summary
        except Exception as e:
            print(f"[memory] 摘要生成失败: {e}")
            return ""
