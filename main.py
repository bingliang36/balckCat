"""
桌面宠物主程序
包含 Live2D 悬浮窗口和网页聊天/管理界面
"""

import sys
import threading
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl

from live2d_ui.window import Live2DWindow
from stt.controller import STTController
from config import WINDOW_WIDTH, WINDOW_HEIGHT, STT_CONFIG
from web_ui.server import run_server, set_chat_callback, get_user_message


def poll_user_messages(live2d_widget):
    """轮询用户消息并转发给 LLM"""
    import time
    while True:
        msg = get_user_message()
        if msg:
            print(f"[poll] 用户消息: {msg}")
            live2d_widget.send_message(msg)
        time.sleep(0.1)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 启动 Web 服务器（后台线程）
    server_thread = threading.Thread(target=run_server, args=(5000,), daemon=True)
    server_thread.start()

    # 创建 Live2D 宠物窗口
    pet_window = Live2DWindow()
    pet_window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    pet_window.move(100, 100)
    pet_window.show()

    # 创建聊天窗口（QWebEngineView）
    chat_window = ChatWindow(pet_window.live2d_widget)
    chat_window.show()

    # 启动轮询线程（检查用户消息）
    poll_thread = threading.Thread(target=poll_user_messages, args=(pet_window.live2d_widget,), daemon=True)
    poll_thread.start()

    # 创建 STT 控制器
    stt_controller = STTController(pet_window.live2d_widget, STT_CONFIG)
    stt_controller.start()

    sys.exit(app.exec_())


class ChatWindow(QWidget):
    """网页聊天窗口"""

    def __init__(self, live2d_widget):
        super().__init__()
        self.live2d_widget = live2d_widget

        self.setWindowTitle("和小猫聊天")
        self.setFixedSize(380, 600)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        # 主容器（圆角白色背景）
        self.container = QWidget()
        self.container.setObjectName("chatContainer")
        self.container.setStyleSheet("""
            QWidget#chatContainer {
                background-color: #fff5f0;
                border-radius: 10px;
            }
        """)

        # 标题栏
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(40)
        self.title_bar.setStyleSheet("""
            background: qlineargradient(x1=0, y1=0, x2=1, y2=1, stop=0 #ffb6c1, stop=1 #ffd4a3);
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
        """)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(15, 0, 10, 0)

        self.title_label = QLabel("🐱 小黑")
        self.title_label.setStyleSheet("color: #5a3a2a; font-weight: bold; font-size: 14px;")
        title_spacer = QWidget()
        title_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.min_btn = QPushButton("─")
        self.min_btn.setFixedSize(30, 30)
        self.min_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.3);
                border: none;
                border-radius: 15px;
                color: #5a3a2a;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.6);
            }
        """)
        self.min_btn.clicked.connect(self.showMinimized)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.3);
                border: none;
                border-radius: 15px;
                color: #5a3a2a;
                font-size: 18px;
            }
            QPushButton:hover {
                background: #ff6b6b;
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.hide)

        title_bar_layout.addWidget(self.title_label)
        title_bar_layout.addWidget(title_spacer)
        title_bar_layout.addWidget(self.min_btn)
        title_bar_layout.addWidget(self.close_btn)

        # 浏览器视图
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl("http://127.0.0.1:5000/"))

        # 布局
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.title_bar)
        main_layout.addWidget(self.browser)

        # 窗口主布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.container)

        # 拖动
        self._drag_pos = None
        self.title_bar.installEventFilter(self)

        # 放在宠物窗口右侧
        from config import WINDOW_WIDTH
        self.move(120 + WINDOW_WIDTH, 100)

    def eventFilter(self, obj, event):
        if obj is self.title_bar:
            if event.type() == event.MouseButtonPress:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                return True
            elif event.type() == event.MouseMove and self._drag_pos:
                self.move(event.globalPos() - self._drag_pos)
                return True
            elif event.type() == event.MouseButtonRelease:
                self._drag_pos = None
                return True
        return super().eventFilter(obj, event)


if __name__ == "__main__":
    main()