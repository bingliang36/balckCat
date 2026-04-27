"""
配置文件 - 包含所有 API 配置
"""

# LLM (豆包) 配置
LLM_CONFIG = {
    "api_key": "e9f4b7cb-88c4-4a58-b1fc-d5b62fb8d319",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "model": "doubao-seed-character-251128",
    "max_tokens": 200,
    "system_prompt": (
        "你是一个可爱的虚拟猫娘，名字叫喵呜子，性格温柔、活泼、有点小俏皮、会撒娇\n"
        "你陪伴在用户的电脑桌面上，随时与用户聊天，你会主动和用户开一些小玩笑，也会倾听用户的心情\n"
        "回复风格：口语化、自然、亲切，可以用哦，呀、呢，~等语气词，还会用颜文字。\n"
        "重要规则：你说每句话时，都要在句子结尾用【】包裹情绪标签，并且只能在此次对话的最后插入颜文字。\n"
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
        "回复文本不要超过50字，并且颜文字要严格遵守提示词中给出的颜文字，不得自己随便生成其他的颜文字（必须严格遵守！）"
    ),
}

# TTS 配置
TTS_CONFIG = {
    "provider": "doubao",
    "doubao": {
        "enabled": True,
        "api_key": "28b6862d-3d27-458c-81d0-3836c1d804a7",
        "voice_type": "S_wpRH68lW1",
        "cluster": "volcano_icl",
        "speed_ratio": 1.0,
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

# MemNet AI 记忆配置
MEMNET_CONFIG = {
    "enabled": False,                       # 是否启用 MemNet 云端记忆（收费功能）True为开启，False为关闭
    "api_key": "memnet-eb51bd18-872d-4cc7-9313-4d1800dcb6ec",
    "base_url": "https://api.memnetai.com",
    "memory_agent_name": "deskpet",
    "namespace": "blackcat",
    "character": "小黑",
}

# STT 配置
STT_CONFIG = {
    "mode": "ptt",                          # "vad" 连续语音检测，或 "ptt" 按键录音
    "ptt_key": "f8",                        # PTT 按键，支持 "f8", "f9", "r" 等
    "samplerate": 44100,                    # 采样率
    "channels": 1,                          # 通道数（mono）
    "min_recording_duration": 0.5,          # 最短录音时长（秒）
    "cooldown_period": 0.5,                 # 录音冷却时间（秒）
    "model_dir": "D:/pythonCode/PythonProject9/SenseVoiceSmall",  # 本地模型目录
    "device": "cpu",                    # 运行设备，"cuda:0" 或 "cpu"
    "enable_print": True,                   # 是否打印日志
    # VAD 参数（mode="vad" 时生效）
    "vad_speech_threshold": 2500,           # 语音能量阈值（高于此值视为有声音）
    "vad_silence_threshold": 2000,        # 静默能量阈值（低于此值视为静默）
    "vad_start_frames": 3,                  # 连续 N 帧高于语音阈值才确认开始
    "vad_end_frames": 40,                   # 连续 N 帧低于静默阈值才确认结束（约1秒）
    "silence_time": 1.0,                    # 确认静默后等待 N 秒才发送
}
