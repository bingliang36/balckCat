"""
本地关键词管理器
负责扫描用户输入中的关键词、触发 recall、维护本地关键词索引文件
"""

import json
import os
import threading
import re
from datetime import datetime
from typing import List, Optional, Tuple

from config import MEMNET_CONFIG


class KeywordRecord:
    """关键词记录"""

    def __init__(self, keyword: str, role: str, character: str, last_seen: str):
        self.keyword = keyword
        self.memory_agent = MEMNET_CONFIG["memory_agent_name"]
        self.namespace = MEMNET_CONFIG["namespace"]
        self.role = role  # "user" 或 "assistant"
        self.character = character
        self.last_seen = last_seen

    def to_dict(self):
        return {
            "keyword": self.keyword,
            "memory_agent": self.memory_agent,
            "namespace": self.namespace,
            "character": self.character,
            "role": self.role,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            keyword=d["keyword"],
            role=d.get("role", "user"),
            character=d.get("character", "default"),
            last_seen=d.get("last_seen", ""),
        )


class KeywordManager:
    """
    本地关键词索引管理器
    - match(): 扫描用户输入是否命中已知关键词
    - update_and_get(): 同步提取关键词 + 话题摘要，阻塞直到完成
    """

    FILE_PATH = "memory/keywords.json"

    def __init__(self):
        self._lock = threading.Lock()
        self._records: List[KeywordRecord] = []
        self._load()

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load(self):
        """从文件加载关键词列表"""
        if not os.path.exists(self.FILE_PATH):
            self._records = []
            return
        try:
            with open(self.FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._records = [KeywordRecord.from_dict(d) for d in data]
            print(f"[keywords] 加载了 {len(self._records)} 条关键词")
        except Exception as e:
            print(f"[keywords] 加载失败: {e}")
            self._records = []

    def _save(self):
        """保存关键词列表到文件"""
        try:
            with open(self.FILE_PATH, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self._records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[keywords] 保存失败: {e}")

    # ── 命中检测 ────────────────────────────────────────────────────────────

    def match(self, text: str) -> List[KeywordRecord]:
        """
        检测 text 中是否包含已知关键词
        Returns: 按出现顺序排列的匹配记录列表
        """
        matched = []
        for record in self._records:
            if record.keyword in text:
                matched.append(record)
        return matched

    # ── 更新（同步，阻塞直到完成） ──────────────────────────────────────────

    def update_and_get(self, user_text: str, assistant_text: str) -> Tuple[List[str], str]:
        """
        同步提取关键词 + 生成话题摘要（阻塞直到完成）
        用于在 store 之前获取 metadata
        """
        from memory.client import MemoryClient
        mc = MemoryClient()

        # 分别从用户和助手文本中提取关键词
        user_kws = mc.extract_keywords(user_text, role="user")
        assistant_kws = mc.extract_keywords(assistant_text, role="assistant")
        all_kws = user_kws + assistant_kws

        # 生成话题摘要
        summary = mc.generate_summary(user_text, assistant_text)

        with self._lock:
            existing = {r.keyword for r in self._records}
            today = datetime.now().strftime("%Y-%m-%d")

            # 用户关键词
            for word in user_kws:
                if word not in existing:
                    record = KeywordRecord(
                        keyword=word,
                        role="user",
                        character="用户",
                        last_seen=today,
                    )
                    self._records.append(record)
                    print(f"[keywords] 新增关键词: {word}")

            # 助手关键词
            for word in assistant_kws:
                if word not in existing:
                    record = KeywordRecord(
                        keyword=word,
                        role="assistant",
                        character=MEMNET_CONFIG["character"],
                        last_seen=today,
                    )
                    self._records.append(record)
                    print(f"[keywords] 新增助手关键词: {word}")

            # 更新 last_seen
            for record in self._records:
                if record.keyword in user_text or record.keyword in assistant_text:
                    record.last_seen = today

            self._save()

        return all_kws, summary
