"""
桌面宠物主程序
包含 Live2D 悬浮窗口和聊天输入面板
"""

import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from live2d_ui.window import Live2DWindow
from stt.controller import STTController
from config import WINDOW_WIDTH, WINDOW_HEIGHT, STT_CONFIG


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 创建 Live2D 宠物窗口
    pet_window = Live2DWindow()
    pet_window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    pet_window.move(100, 100)  # 放在屏幕左上角
    pet_window.show()

    # 创建聊天输入窗口
    chat_window = ChatWindow(pet_window.live2d_widget)
    chat_window.show()

    # 创建 STT 控制器（按键录音 + SenseVoice 转写）
    stt_controller = STTController(pet_window.live2d_widget, STT_CONFIG)
    stt_controller.recording_state_changed.connect(chat_window.on_recording_state_changed)
    stt_controller.start()

    sys.exit(app.exec_())


class ChatWindow(QWidget):
    """聊天输入窗口"""

    def __init__(self, live2d_widget):
        super().__init__()
        self.live2d_widget = live2d_widget

        self.setWindowTitle("和小猫聊天")
        self.setFixedWidth(400)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        # 样式
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: "Microsoft YaHei";
            }
            QLineEdit {
                background-color: #3d3d3d;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                color: #ffffff;
            }
            QLineEdit:focus {
                background-color: #4d4d4d;
            }
            QPushButton {
                background-color: #ff69b4;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #ff85c1;
            }
            QPushButton:pressed {
                background-color: #ff4da6;
            }
            QLabel {
                color: #aaaaaa;
                font-size: 12px;
            }
        """)

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 标题
        title = QLabel("和小猫聊天（回车发送）")
        layout.addWidget(title)

        # 输入框
        input_layout = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_box, 1)

        # 发送按钮
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        self.adjustSize()
        # 放在宠物窗口右侧
        from config import WINDOW_WIDTH
        self.move(120 + WINDOW_WIDTH, 100)

    def _on_send(self):
        text = self.input_box.text().strip()
        if text:
            self.live2d_widget.send_message(text)
            self.input_box.clear()

    def on_recording_state_changed(self, is_recording: bool):
        """录音状态变化时的回调"""
        if is_recording:
            self.send_btn.setText("录音中...")
            self.send_btn.setEnabled(False)
        else:
            self.send_btn.setText("发送")
            self.send_btn.setEnabled(True)


if __name__ == "__main__":
    main()
