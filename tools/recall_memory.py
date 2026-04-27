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
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户当前说的话，模型会用这句话作为线索去检索相关的历史记忆。直接传入用户输入即可。"
                }
            },
            "required": ["query"]
        }
    }
}


def recall_memory(query: str = "") -> str:
    """
    从 MemNet 检索相关记忆
    Args:
        query: 用户当前说的话，作为 recall 的检索线索
    Returns:
        str: 相关记忆的描述，如果无记忆则返回空字符串
    """
    from config import MEMNET_CONFIG
    if not MEMNET_CONFIG.get("enabled", True):
        return ""

    from memory.client import MemoryClient
    mc = MemoryClient()

    if not query:
        query = "请回忆与当前对话相关的历史记忆"

    print(f"[recall]query: {query}")
    result = mc.client.recall(
        memory_agent_name=mc.memory_agent_name,
        query=query,
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


# 兼容别名
recall_memory_definition = TOOL_DEFINITION
