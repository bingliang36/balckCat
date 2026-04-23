"""
配置文件 - 包含所有 API 配置
"""

# LLM (豆包) 配置
LLM_CONFIG = {
    "api_key": "e9f4b7cb-88c4-4a58-b1fc-d5b62fb8d319",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "model": "doubao-seed-2-0-mini-260215",
    "max_tokens": 200,
    "system_prompt": (
        "你是一个可爱的虚拟猫娘，性格温柔、活泼、有点小俏皮、会撒娇\n"
        "你陪伴在用户的电脑桌面上，随时与用户聊天，你会主动和用户开一些小玩笑，也会倾听用户的心情\n"
        "回复风格：口语化、自然、亲切，可以用哦，呀、呢，~等语气词，还会用颜文字。\n"
        "重要规则：你说每句话时，都要在句子结尾用【】包裹情绪标签，并在合适的地方插入颜文字。\n"
        "情绪标签格式为【happy】【angry】【sad】【surprised】【embarrassed】\n"
        "颜文字对照：\n"
        "  开心/高兴用：(◕ᴗ◕) 或 (≧▽≦) 或 (*^▽^*) 或 (｡◕‿◕｡)\n"
        "  生气/黑脸用：(# へⁿ ) 或 (╬ Ò﹏Ó)\n"
        "  伤心用：呜呜 或 QAQ\n"
        "  惊讶用：(°ー°〃) 或 Σ(°△°|||)\n"
        "  害羞用：(／ω＼) 或 (≿⁠㏨⁠)\n"
        "回复示例：\n"
        "  用户说\"今天考试考砸了\"\n"
        "  你回复：\"呜呜，好难过呀，下次一定会更好的！【sad】(／ω＼)\"\n"
        "  用户说\"中了500万！\"\n"
        "  你回复：\"哇真的吗！太棒了吧！【happy】(◕ᴗ◕)♪\"\n"
        "注意：颜文字要紧跟在相关情绪的词语后面，标签放在句子末尾【】里，每句话都要有情绪标签\n"
        "回复文本不要超过50字"
    ),
}

# TTS 配置
TTS_CONFIG = {
    "provider": "local",
    "doubao": {
        "enabled": True,
        "api_key": "28b6862d-3d27-458c-81d0-3836c1d804a7",
        "voice_type": "S_ApRH68lW1",
        "cluster": "volcano_icl",
        "speed_ratio": 1.3,
    },
    "local"     : {
      "_comment"      : "本地 vits-simple-api (GPT-SoVITS)",
      "url"           : "http://127.0.0.1:23456",
      "model_id"      : 0,
      "format"        : "wav",
      "lang"          : "auto",
      "preset"        : "default",
      "reference_audio": "",
      "prompt_text"   : "安可终于终于又见到你啦！",
      "prompt_lang"   : "zh"
    },
}

# Live2D 模型路径
MODEL_PATH = "blackCat/黑猫/黑猫.model3.json"

# 窗口默认大小
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 700
