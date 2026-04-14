from PyQt5.QtWidgets import QWidget, QMenu, QMessageBox
from PyQt5.QtCore import Qt, QPoint, QEvent
from PyQt5.QtGui import QCursor
from live2D.live2d_opengl_widget import Live2DOpenGLWidget


class Live2DWindow(QWidget):
    # 缩放范围
    MIN_SCALE = 0.3
    MAX_SCALE = 2.0

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        from llm.config import WINDOW_WIDTH, WINDOW_HEIGHT
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.opengl_widget = Live2DOpenGLWidget(self)
        self.opengl_widget.setGeometry(self.rect())
        # 别名，方便外部访问
        self.live2d_widget = self.opengl_widget

        self._drag_position: QPoint = None
        self._prev_drag_pos: QPoint = None
        self._prev_drag_time: float = None
        self._scale = 1.0  # 当前缩放比例

        # 安装事件过滤器，统一处理鼠标事件
        self.opengl_widget.installEventFilter(self)

        self.setMouseTracking(True)

    def eventFilter(self, obj, event):
        """
        事件过滤器：拦截 opengl_widget 的鼠标事件，统一在 Window 层处理
        """
        if obj is not self.opengl_widget:
            return super().eventFilter(obj, event)

        etype = event.type()

        # 左键点击：拖动 或 模型交互
        if etype == QEvent.MouseButtonPress:
            global_pos = event.globalPos()
            local_pos = event.pos()  # 相对于 opengl_widget

            if event.button() == Qt.LeftButton:
                self._drag_position = global_pos - self.frameGeometry().topLeft()
                self._prev_drag_pos = global_pos
                from time import time as _t
                self._prev_drag_time = _t()

                # 模型交互：使用区域检测代替 HitTest
                # 模型大约占窗口上半部分（头部在中上部，身体在下半部）
                if self.live2d_widget.model:
                    w = self.opengl_widget.width()
                    h = self.opengl_widget.height()
                    lx = local_pos.x()
                    ly = local_pos.y()

                    # 粗略区域判断：头部大约在窗口上半部分偏中
                    # 身体在窗口下半部分
                    in_head = (h * 0.1 <= ly <= h * 0.7)
                    in_body = (ly > h * 0.5)

                    if in_head:
                        import random
                        expr = random.choice(["expression2", "expression6"])
                        self.live2d_widget.model.ResetExpression()
                        self.live2d_widget.model.SetExpression(expr)
                        print(f'[live2d] 点击头部触发表情: {expr}')
                        self.live2d_widget.model.StartRandomMotion("Idle", 1)
                    elif in_body:
                        self.live2d_widget.model.StartRandomMotion("Idle", 1)
                        print('[live2d] 点击身体触发动作')

            elif event.button() == Qt.RightButton:
                self.show_context_menu(QCursor.pos())

            return super().eventFilter(obj, event)  # 事件继续传递

        # 左键拖动
        if etype == QEvent.MouseMove:
            if event.buttons() == Qt.LeftButton and self._drag_position:
                self.move(event.globalPos() - self._drag_position)

                # 物理惯性：拖拽时计算窗口移动速度，施加给模型的 physics 参数
                if self.live2d_widget.model and self._prev_drag_pos is not None:
                    from time import time as _t
                    curr_time = _t()
                    dt = curr_time - (self._prev_drag_time or curr_time)
                    if dt > 0:
                        curr_pos = event.globalPos()
                        dx = (curr_pos.x() - self._prev_drag_pos.x()) / dt  # 像素/秒
                        dy = (curr_pos.y() - self._prev_drag_pos.y()) / dt
                        # 施加惯性力：让头发/尾巴/饰品随拖拽方向摆动
                        self.live2d_widget.model.AddParameterValue("ParamAngleX", dx * 0.001)
                        self.live2d_widget.model.AddParameterValue("ParamAngleY", -dy * 0.001)
                    self._prev_drag_pos = event.globalPos()
                    self._prev_drag_time = curr_time

            return super().eventFilter(obj, event)

        # 左键释放
        if etype == QEvent.MouseButtonRelease:
            self._drag_position = None
            self._prev_drag_pos = None
            self._prev_drag_time = None
            return super().eventFilter(obj, event)

        # 滚轮缩放
        if etype == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 0.1 if delta > 0 else -0.1
                new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, self._scale + step))
                if new_scale != self._scale:
                    self._scale = new_scale
                    old_center = self.geometry().center()
                    from llm.config import WINDOW_WIDTH, WINDOW_HEIGHT
                    new_w = max(200, min(1400, int(WINDOW_WIDTH * self._scale)))
                    new_h = max(280, min(1400, int(WINDOW_HEIGHT * self._scale)))
                    self.resize(new_w, new_h)
                    new_geo = self.frameGeometry()
                    new_geo.moveCenter(old_center)
                    self.move(new_geo.topLeft())
                    print(f'[live2d] 缩放: {self._scale:.1f}x')
            return super().eventFilter(obj, event)

        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        self.opengl_widget.setGeometry(self.rect())
        super().resizeEvent(event)

    def show_context_menu(self, pos: QPoint):
        """右键菜单：选择情绪"""
        menu = QMenu(self)

        # 情绪子菜单
        emotion_menu = QMenu("切换表情", self)
        emotion_actions = [
            ("开心 (aixinyan)",  "expression2"),
            ("黑脸 (heilian)",   "expression7"),
            ("泪眼 (yanlei)",    "expression5"),
            ("惊讶 (quanquanyan)", "expression3"),
            ("害羞 (lianhong)",  "expression6"),
        ]
        for label, expr_name in emotion_actions:
            action = emotion_menu.addAction(label)
            action.triggered.connect(
                lambda checked, e=expr_name: self.live2d_widget.trigger_emotion(e)
            )

        menu.addMenu(emotion_menu)
        menu.addSeparator()
        menu.addAction("重置表情", lambda: self.live2d_widget.trigger_emotion(None))
        menu.addSeparator()
        menu.addAction("Exit", self.close)
        menu.addAction("About", self.show_about)
        menu.exec_(pos)

    def show_about(self):
        QMessageBox.about(
            self,
            "About Live2D Widget",
            "Live2D Desktop Widget\nBlack Cat Model"
        )
