"""
屏幕守护模块 - 检测用户闲置并提醒
当用户长时间无操作时，宠物会主动发消息关心
"""

import threading
import time
from datetime import datetime, timedelta


class IdleMonitor:
    """屏幕守护：检测用户闲置状态"""

    def __init__(self, live2d_widget, config: dict):
        self.live2d_widget = live2d_widget
        self.config = config
        self.enabled = config.get("enabled", True)
        self.check_interval = config.get("check_interval", 10)
        self.idle_threshold = config.get("idle_threshold", 120)
        self.max_reminders = config.get("max_reminders", 3)
        self.reminder_cooldown = config.get("reminder_cooldown", 300)

        self._last_activity_time = time.time()
        self._reminder_count = 0
        self._last_reminder_time = None
        self._running = False

    def start(self):
        """启动闲置检测线程"""
        if not self.enabled:
            print("[idle] 屏幕守护已禁用")
            return
        self._running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
        print(f"[idle] 屏幕守护已启动（闲置阈值={self.idle_threshold}秒）")

    def stop(self):
        """停止闲置检测"""
        self._running = False

    def on_user_activity(self):
        """用户有活动时调用（可以在输入时调用）"""
        self._last_activity_time = time.time()
        self._reminder_count = 0

    def _monitor_loop(self):
        """检测循环"""
        while self._running:
            time.sleep(self.check_interval)

            idle_time = time.time() - self._last_activity_time

            if idle_time >= self.idle_threshold:
                # 检查是否可以提醒
                if self._can_remind():
                    self._send_reminder()
                    self._last_reminder_time = time.time()
                    self._reminder_count += 1

    def _can_remind(self) -> bool:
        """检查是否可以发送提醒"""
        # 超过最大提醒次数，不再提醒
        if self._reminder_count >= self.max_reminders:
            return False

        # 冷却时间内不提醒
        if self._last_reminder_time and (time.time() - self._last_reminder_time) < self.reminder_cooldown:
            return False

        return True

    def _send_reminder(self):
        """发送闲置提醒消息"""
        idle_minutes = int((time.time() - self._last_activity_time) / 60)
        messages = [
            "主人，你已经离开很久了喵...在想什么呢？",
            "喵呜，你是不是太忙了？记得休息一下哦~",
            "主人怎么不动了呀？是睡着了吗？",
        ]

        # 根据闲置时间选择消息
        if idle_minutes >= 60:
            msg = messages[2]  # 睡着了吗
        elif idle_minutes >= 30:
            msg = messages[1]  # 太忙了
        else:
            msg = messages[0]  # 离开很久了

        print(f"[idle] 闲置 {idle_minutes} 分钟，发送提醒: {msg}")

        # 通过 live2d_widget 发送消息（不经过用户输入）
        self._send_auto_message(msg)

    def _send_auto_message(self, text: str):
        """
        自动发送消息（宠物主动说话）
        直接走 LLM → TTS，不显示在用户聊天框
        """
        self.live2d_widget.trigger_auto_reply(text)

    def update_activity(self):
        """更新最后活动时间"""
        self.on_user_activity()