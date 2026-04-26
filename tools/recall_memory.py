"""
recall_memory 工具 - 根据当前对话上下文从 MemNet 回忆相关记忆
当用户提到之前聊过的内容，或者模型觉得需要参考历史记忆时调用
"""

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "recall_memory",
        "description": "从记忆系统中检索与当前对话相关的历史记忆。当你需要知道用户之前说过什么、或者需要参考历史信息来回答时，调用此工具。例如用户提到'你还记得上次我们聊了什么吗'或者'我之前告诉你我的名字是...'时使用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# 兼容别名
recall_memory_definition = TOOL_DEFINITION


def recall_memory() -> str:
    """
    从 MemNet 检索相关记忆
    Returns:
        str: 相关记忆的描述，如果无记忆则返回空字符串
    """
    from memory.client import MemoryClient
    mc = MemoryClient()

    # 直接用通用 query 让 MemNet 的关联思考发挥最大作用
    # MemNet 内部会根据对话上下文联想相关记忆
    result = mc.client.recall(
        memory_agent_name=mc.memory_agent_name,
        query="请回忆与当前对话相关的历史记忆，包括用户的信息、喜好、之前讨论过的话题等",
        character=mc.character,
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
    content = data.get("memoryPrompt", "") or ""
    return str(content) if content else ""
