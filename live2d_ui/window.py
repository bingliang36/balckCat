from PyQt5.QtWidgets import QWidget, QMenu, QMessageBox
from PyQt5.QtCore import Qt, QPoint, QEvent
from PyQt5.QtGui import QCursor, QIcon
from .opengl_widget import Live2DOpenGLWidget


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

        from config import WINDOW_WIDTH, WINDOW_HEIGHT
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.opengl_widget = Live2DOpenGLWidget(self)
        self.opengl_widget.setGeometry(self.rect())
        # 别名，方便外部访问
        self.live2d_widget = self.opengl_widget

        self._drag_position: QPoint = None
        self._prev_drag_pos: QPoint = None
        self._prev_drag_time: float = None
        self._scale = 1.0  # 当前缩放比例
        # 惯性平滑参数
        self._inertia_x = 0.0
        self._inertia_y = 0.0
        self.INERTIA_SCALE = 0.3
        self.MAX_INERTIA = 30.0
        self.ALPHA = 0.15  # 低通滤波系数，越小越平滑但响应越慢
        # 眼珠追踪参数
        self._eye_track_x = 0.0  # 平滑后的眼珠X
        self._eye_track_y = 0.0  # 平滑后的眼珠Y
        self._mouse_near_model = False  # 鼠标是否在模型附近
        self.EYE_SCALE = 1.5  # 眼珠追踪灵敏度
        self.EYE_ALPHA = 0.12  # 眼珠平滑系数

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

                # 眼珠追踪：按下时检测是否在模型附近，决定是否开启追踪
                if self.live2d_widget.model:
                    w = self.opengl_widget.width()
                    h = self.opengl_widget.height()
                    lx = local_pos.x()
                    ly = local_pos.y()
                    # 模型区域：占窗口上半部分偏中
                    in_model_area = (h * 0.1 <= ly <= h * 0.85)
                    self._mouse_near_model = in_model_area

                    # 模型交互：使用区域检测代替 HitTest
                    # 模型大约占窗口上半部分（头部在中上部，身体在下半部）
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
            local_pos = event.pos()
            w = self.opengl_widget.width()
            h = self.opengl_widget.height()
            lx = local_pos.x()
            ly = local_pos.y()

            # 眼珠追踪：鼠标在模型附近时，眼球跟随鼠标
            if self.live2d_widget.model:
                in_model_area = (h * 0.1 <= ly <= h * 0.85)
                if in_model_area:
                    # 以模型中心为原点，范围映射到 [-1, 1]
                    model_cx = w * 0.5
                    model_cy = h * 0.4
                    nx = (lx - model_cx) / (w * 0.5)
                    ny = (ly - model_cy) / (h * 0.4)
                    # 限制范围
                    nx = max(-1.0, min(1.0, nx))
                    ny = max(-1.0, min(1.0, ny))
                    # 低通滤波平滑
                    target_x = nx * self.EYE_SCALE
                    target_y = ny * self.EYE_SCALE
                    self._eye_track_x = self._eye_track_x + self.EYE_ALPHA * (target_x - self._eye_track_x)
                    self._eye_track_y = self._eye_track_y + self.EYE_ALPHA * (target_y - self._eye_track_y)
                    self.live2d_widget.model.SetParameterValue("ParamEyeBallX", self._eye_track_x)
                    self.live2d_widget.model.SetParameterValue("ParamEyeBallY", self._eye_track_y)

            if event.buttons() == Qt.LeftButton and self._drag_position:
                self.move(event.globalPos() - self._drag_position)

                # 物理惯性：拖拽时计算窗口移动速度，施加给模型的 physics 参数
                # 使用低通滤波平滑，避免生硬抖动
                if self.live2d_widget.model and self._prev_drag_pos is not None:
                    from time import time as _t
                    curr_time = _t()
                    dt = curr_time - (self._prev_drag_time or curr_time)
                    if dt > 0:
                        curr_pos = event.globalPos()
                        dx = (curr_pos.x() - self._prev_drag_pos.x()) / dt  # 像素/秒
                        dy = (curr_pos.y() - self._prev_drag_pos.y()) / dt
                        # 限制范围后，用低通滤波平滑
                        target_vx = max(-self.MAX_INERTIA, min(self.MAX_INERTIA, dx * self.INERTIA_SCALE))
                        target_vy = max(-self.MAX_INERTIA, min(self.MAX_INERTIA, -dy * self.INERTIA_SCALE))
                        self._inertia_x = self._inertia_x + self.ALPHA * (target_vx - self._inertia_x)
                        self._inertia_y = self._inertia_y + self.ALPHA * (target_vy - self._inertia_y)
                        self.live2d_widget.model.SetParameterValue("ParamAngleX", self._inertia_x)
                        self.live2d_widget.model.SetParameterValue("ParamAngleY", self._inertia_y)
                    self._prev_drag_pos = event.globalPos()
                    self._prev_drag_time = curr_time

            return super().eventFilter(obj, event)

        # 左键释放
        if etype == QEvent.MouseButtonRelease:
            # 松手后将物理参数设为0，靠物理系统的内建恢复力自然回弹
            if self.live2d_widget.model:
                self.live2d_widget.model.SetParameterValue("ParamAngleX", 0.0)
                self.live2d_widget.model.SetParameterValue("ParamAngleY", 0.0)
                self.live2d_widget.model.SetParameterValue("ParamEyeBallX", 0.0)
                self.live2d_widget.model.SetParameterValue("ParamEyeBallY", 0.0)
            self._inertia_x = 0.0
            self._inertia_y = 0.0
            self._eye_track_x = 0.0
            self._eye_track_y = 0.0
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
                    from config import WINDOW_WIDTH, WINDOW_HEIGHT
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
