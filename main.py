# -*- coding: utf-8 -*-
"""
屏幕准星 (Screen Crosshair)
---------------------------
一个无边框、可置顶、可鼠标穿透的屏幕准星叠加层工具。

支持形状：十字 / 三角形(APEX 风格三线) / 圆形 / 纯中心点 / 自定义臂组合（T 字可由上/左/右臂组合实现）
支持参数：长度、粗细、间距、大小、旋转、偏移、端点样式
支持颜色：主色与轮廓色各自的 RGBA 独立调节
支持窗口：置顶、鼠标穿透、拖动模式、锁定屏幕中心、多显示器选择
"""

import json
import math
import os
import sys

from PySide6.QtCore import (
    Qt,
    QPoint,
    QRectF,
    QLineF,
    QTimer,
    QSize,
    Signal,
    QAbstractNativeEventFilter,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QAction,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "ScreenCrosshair"
ORG_NAME = "ScreenCrosshair"

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

WIN_SIZE = 520  # 准星窗口边长(逻辑像素)，需容纳最大准星


def default_config() -> dict:
    return {
        # ---- 形状 ----
        "shape": "cross",          # cross | tshape | triangle | circle | dot | custom
        "arm_up": True,
        "arm_down": True,
        "arm_left": True,
        "arm_right": True,
        # ---- 几何 ----
        "length": 12,              # 臂长 / 三角形每边截取后的基准
        "thickness": 2,            # 线宽
        "gap": 6,                  # 中心间距 / 三角形顶点缺口
        "size": 28,                # 圆形直径 / 三角形外接圆直径
        "rotate": 180,             # 三角形旋转角(度)，180 = 尖端朝下
        "edge_ratio": 100,         # 三角形每条边绘制长度比例(%)
        "round_cap": False,        # 圆角端点
        # ---- 颜色 ----
        "color": [0, 255, 80, 255],
        # ---- 轮廓 ----
        "outline_enabled": True,
        "outline_color": [0, 0, 0, 180],
        "outline_width": 1,        # 每侧向外扩展的像素
        # ---- 中心点 ----
        "dot_enabled": True,
        "dot_size": 2,
        "dot_use_main": False,
        "dot_color": [255, 40, 40, 255],
        # ---- 窗口 ----
        "always_on_top": True,
        "click_through": True,
        "exclude_from_capture": False,  # True = 不被截图/录屏/共享屏幕捕捉
        "lock_center": True,
        "monitor_index": 0,
        "offset_x": 0,
        "offset_y": 0,
        "visible": True,
        # ---- 预设槽位（3 个，元素为 None 或 {"name": str, "data": dict}）----
        "presets": [None, None, None],
        # ---- 设置窗口尺寸（可自由缩放后记忆）----
        "win_w": 1080,
        "win_h": 660,
    }


class Config:
    """配置容器：负责加载、合并默认值与持久化。"""

    def __init__(self):
        self.data = default_config()
        self.path = self._config_path()
        self.load()

    @staticmethod
    def _config_path() -> str:
        if getattr(sys, "frozen", False):
            base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        try:
            os.makedirs(base, exist_ok=True)
        except OSError:
            base = os.path.expanduser("~")
        return os.path.join(base, "config.json")

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in default_config().items():
                    if k in loaded:
                        self.data[k] = loaded[k]
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


# ---------------------------------------------------------------------------
# 绘制核心
# ---------------------------------------------------------------------------

def qcolor(rgba) -> QColor:
    r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
    a = int(rgba[3]) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)


def _triangle_vertices(cx: float, cy: float, radius: float, rotate_deg: float):
    """返回等边三角形的三个顶点。rotate=0 时尖端朝上。"""
    pts = []
    for i in range(3):
        ang = math.radians(rotate_deg + i * 120.0)
        pts.append((cx + radius * math.sin(ang), cy - radius * math.cos(ang)))
    return pts


def paint_crosshair(painter: QPainter, cfg: dict, cx: float, cy: float, outline: bool):
    """
    在 (cx, cy) 处绘制准星。
    outline=True 时绘制轮廓层(更粗的一层垫在下方)，颜色与宽度取自轮廓设置。
    """
    shape = cfg["shape"]
    length = float(cfg["length"])
    thickness = float(cfg["thickness"])
    gap = float(cfg["gap"])
    size = float(cfg["size"])

    if outline:
        if not cfg["outline_enabled"]:
            return
        color = qcolor(cfg["outline_color"])
        width = thickness + 2.0 * float(cfg["outline_width"])
    else:
        color = qcolor(cfg["color"])
        width = thickness

    if width <= 0:
        width = 0.5

    cap = Qt.RoundCap if cfg["round_cap"] else Qt.FlatCap
    pen = QPen(color, width, Qt.SolidLine, cap, Qt.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # ---- 直线臂系（十字 / T 字 / 自定义）----
    if shape in ("cross", "tshape", "custom"):
        dirs = []
        if cfg["arm_up"]:
            dirs.append((0.0, -1.0))
        if cfg["arm_down"]:
            dirs.append((0.0, 1.0))
        if cfg["arm_left"]:
            dirs.append((-1.0, 0.0))
        if cfg["arm_right"]:
            dirs.append((1.0, 0.0))
        for dx, dy in dirs:
            if length <= 0:
                continue
            x1 = cx + dx * gap
            y1 = cy + dy * gap
            x2 = cx + dx * (gap + length)
            y2 = cy + dy * (gap + length)
            painter.drawLine(QLineF(x1, y1, x2, y2))

    # ---- 圆形 ----
    elif shape == "circle":
        r = size / 2.0
        if r > 0:
            # 线宽向内/向外对称扩展，视觉上贴合 thickness
            painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

    # ---- 三线三角形（APEX 风格）----
    elif shape == "triangle":
        radius = size / 2.0
        pts = _triangle_vertices(cx, cy, radius, float(cfg["rotate"]))
        ratio = max(0.05, min(1.0, float(cfg["edge_ratio"]) / 100.0))
        for i in range(3):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % 3]
            ex, ey = bx - ax, by - ay
            elen = math.hypot(ex, ey)
            if elen <= 0:
                continue
            ux, uy = ex / elen, ey / elen
            half = elen / 2.0
            # 顶点缺口：每条边两端各缩进 gap
            avail = half - gap
            if avail <= 0:
                continue
            seg_half = avail * ratio
            mx, my = ax + ux * half, ay + uy * half
            x1 = mx - ux * seg_half
            y1 = my - uy * seg_half
            x2 = mx + ux * seg_half
            y2 = my + uy * seg_half
            painter.drawLine(QLineF(x1, y1, x2, y2))

    # ---- 中心点 ----
    if not outline and cfg["dot_enabled"]:
        _paint_dot(painter, cfg, cx, cy, False)
    elif outline and cfg["dot_enabled"] and cfg["outline_enabled"]:
        _paint_dot(painter, cfg, cx, cy, True)


def _paint_dot(painter: QPainter, cfg: dict, cx: float, cy: float, outline: bool):
    d = float(cfg["dot_size"])
    if d <= 0:
        return
    if outline:
        color = qcolor(cfg["outline_color"])
        d = d + 2.0 * float(cfg["outline_width"])
    else:
        color = qcolor(cfg["dot_color"] if not cfg["dot_use_main"] else cfg["color"])
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawEllipse(QRectF(cx - d / 2.0, cy - d / 2.0, d, d))


# ---------------------------------------------------------------------------
# 准星窗口
# ---------------------------------------------------------------------------

class CrosshairWindow(QWidget):
    """无边框透明叠加层窗口。"""

    moved = Signal(int, int)

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.drag_pos = None
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(WIN_SIZE, WIN_SIZE)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(False)
        self.apply_window_flags()

    # ---- 窗口标志 ----
    def apply_window_flags(self):
        was_visible = self.isVisible()
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if self.cfg.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        if self.cfg.get("click_through", True):
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
            self.raise_()

    def refresh(self):
        self.apply_window_flags()
        self.reposition()
        self.update()

    def reposition(self):
        screens = QApplication.screens()
        idx = int(self.cfg.get("monitor_index", 0))
        if idx >= len(screens):
            idx = 0
            self.cfg.set("monitor_index", 0)
        if not screens:
            return
        geo = screens[idx].geometry()
        if self.cfg.get("lock_center", True):
            ox = int(self.cfg.get("offset_x", 0))
            oy = int(self.cfg.get("offset_y", 0))
            x = geo.center().x() - WIN_SIZE // 2 + ox
            y = geo.center().y() - WIN_SIZE // 2 + oy
        else:
            px = self.cfg.get("win_pos_x")
            py = self.cfg.get("win_pos_y")
            if px is None or py is None:
                x = geo.center().x() - WIN_SIZE // 2
                y = geo.center().y() - WIN_SIZE // 2
            else:
                x, y = int(px), int(py)
        self.move(x, y)

    # ---- 屏幕捕捉保护 ----
    def apply_capture_affinity(self):
        """Windows 10 2004+：将窗口从截图/录屏/屏幕共享中排除。"""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            hwnd = int(self.winId())
            if not hwnd:
                return False
            WDA_NONE = 0x00000000
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            flag = WDA_EXCLUDEFROMCAPTURE if self.cfg.get("exclude_from_capture") else WDA_NONE
            return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, flag))
        except Exception:
            return False

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_capture_affinity()

    # ---- 绘制 ----
    def paintEvent(self, event):
        if not self.cfg.get("visible", True):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        c = WIN_SIZE / 2.0
        # 先画轮廓层，再画主体层
        paint_crosshair(painter, self.cfg.data, c, c, outline=True)
        paint_crosshair(painter, self.cfg.data, c, c, outline=False)
        painter.end()

    # ---- 拖动（仅在关闭鼠标穿透时可用）----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(new_pos)
            self.cfg.set("win_pos_x", new_pos.x())
            self.cfg.set("win_pos_y", new_pos.y())
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        event.accept()


# ---------------------------------------------------------------------------
# UI 组件
# ---------------------------------------------------------------------------

class SliderRow(QWidget):
    """标签 + 滑块 + 数值框的组合控件。"""

    valueChanged = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, value: int,
                 suffix: str = "", label_width: int = 64):
        super().__init__()
        self.suffix = suffix
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.label.setFixedWidth(label_width)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        self.spin.setFixedWidth(76)
        if suffix:
            self.spin.setSuffix(" " + suffix)
        layout.addWidget(self.label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(self._emit)

    def _emit(self, v):
        self.valueChanged.emit(int(v))

    def set_value(self, v):
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(int(v))
        self.spin.setValue(int(v))
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

    def value(self):
        return int(self.slider.value())

    def set_enabled(self, enabled: bool):
        self.label.setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.spin.setEnabled(enabled)


class ColorPicker(QWidget):
    """RGBA 四滑块 + 颜色预览 + 系统拾色器。"""

    changed = Signal(list)

    @staticmethod
    def _dropper_icon():
        """绘制一个吸管（dropper）图标，作为取色按钮。"""
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.translate(11, 13)
        p.rotate(-45)
        p.setPen(QPen(QColor(70, 70, 70), 1.6))
        p.setBrush(QBrush(QColor(210, 210, 210)))
        p.drawRect(QRectF(-2.5, -1.6, 13, 3.2))        # 管身
        p.setBrush(QBrush(QColor(140, 140, 140)))
        p.drawRect(QRectF(-7, -3.5, 4.5, 7))           # 尾端把手
        path = QPainterPath()
        path.moveTo(10.5, -1.6)
        path.lineTo(17, 0)
        path.lineTo(10.5, 1.6)
        path.closeSubpath()
        p.fillPath(path, QBrush(QColor(70, 70, 70)))    # 尖端
        p.end()
        return QIcon(pm)

    def __init__(self, title: str, rgba):
        super().__init__()
        self._rgba = list(rgba)
        box = QGroupBox(title)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setSpacing(3)

        head = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(58, 24)
        self.preview.setFrameShape(QFrame.Box)
        self.lbl_hex = QLabel()
        self.lbl_hex.setStyleSheet("font-family:Consolas,'Courier New',monospace;"
                                   "font-size:11px;color:#777;")
        self.btn_pick = QToolButton()
        self.btn_pick.setIcon(ColorPicker._dropper_icon())
        self.btn_pick.setIconSize(QSize(22, 22))
        self.btn_pick.setFixedSize(30, 30)
        self.btn_pick.setAutoRaise(True)
        self.btn_pick.setToolTip("取色（打开系统拾色器）")
        head.addWidget(self.preview)
        head.addWidget(self.lbl_hex)
        head.addStretch(1)
        head.addWidget(self.btn_pick)
        v.addLayout(head)

        self.rows = {}
        for key, name in (("r", "R"), ("g", "G"), ("b", "B"), ("a", "A")):
            row = SliderRow(name, 0, 255, int(self._rgba["rgba".index(key)]),
                            label_width=20)
            row.valueChanged.connect(lambda val, k=key: self._on_slider(k, val))
            self.rows[key] = row
            v.addWidget(row)

        self.btn_pick.clicked.connect(self._open_dialog)
        self._update_preview()

    def _on_slider(self, key, val):
        self._rgba["rgba".index(key)] = int(val)
        self._update_preview()
        self.changed.emit(list(self._rgba))

    def set_rgba(self, rgba):
        self._rgba = list(rgba)
        for key in self.rows:
            self.rows[key].set_value(int(self._rgba["rgba".index(key)]))
        self._update_preview()

    def rgba(self):
        return list(self._rgba)

    def _update_preview(self):
        r, g, b, a = self._rgba
        self.preview.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a / 255:.2f}); border: 1px solid #888;"
        )
        self.lbl_hex.setText(f"#{r:02X}{g:02X}{b:02X}  A{a}")

    def _open_dialog(self):
        r, g, b, a = self._rgba
        dlg = QColorDialog(QColor(r, g, b, a), self)
        dlg.setOption(QColorDialog.ShowAlphaChannel, True)
        if dlg.exec() == QDialog.Accepted:
            c = dlg.selectedColor()
            self.set_rgba([c.red(), c.green(), c.blue(), c.alpha()])
            self.changed.emit(list(self._rgba))


class PreviewWidget(QWidget):
    """设置面板内的实时预览。"""

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setMinimumHeight(200)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(30, 32, 38))
        # 棋盘格背景，便于观察半透明
        step = 10
        for y in range(0, self.height(), step):
            for x in range(0, self.width(), step):
                if ((x // step) + (y // step)) % 2 == 0:
                    p.fillRect(x, y, step, step, QColor(48, 50, 58))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        paint_crosshair(p, self.cfg.data, cx, cy, outline=True)
        paint_crosshair(p, self.cfg.data, cx, cy, outline=False)
        p.end()


# ---------------------------------------------------------------------------
# 设置面板
# ---------------------------------------------------------------------------

SHAPE_ITEMS = [
    ("十字 (四臂)", "cross"),
    ("三角形", "triangle"),
    ("圆形", "circle"),
    ("仅中心点", "dot"),
    ("自定义臂组合", "custom"),
]

# 预设槽位保存的字段（仅外观与位置，不含窗口行为）
PRESET_KEYS = (
    "shape", "arm_up", "arm_down", "arm_left", "arm_right",
    "length", "thickness", "gap", "size", "rotate", "edge_ratio",
    "round_cap", "color",
    "outline_enabled", "outline_color", "outline_width",
    "dot_enabled", "dot_size", "dot_use_main", "dot_color",
    "offset_x", "offset_y",
)


class SettingsDialog(QDialog):
    """准星设置主面板。"""

    def __init__(self, cfg: Config, overlay: "CrosshairWindow", app: "CrosshairApp"):
        super().__init__()
        self.cfg = cfg
        self.overlay = overlay
        self.app = app
        self.setWindowTitle("屏幕准星 · 设置")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint)
        self.setSizeGripEnabled(True)          # 右下角尺寸手柄，支持自由缩放
        self.setMinimumSize(700, 420)          # 下限，再小则由滚动区接管
        self.resize(int(self.cfg.get("win_w", 1080) or 1080),
                    int(self.cfg.get("win_h", 660) or 660))
        self._syncing = False  # True 期间抑制所有回调，防止中间状态写入配置
        self._build_ui()
        self._sync_from_cfg()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        # 外层：可滚动内容区 + 固定在底部按钮条
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        cols = QHBoxLayout(content)
        cols.setSpacing(10)
        root.addWidget(scroll, 1)

        col_shape = QVBoxLayout()
        col_look = QVBoxLayout()
        col_win = QVBoxLayout()
        cols.addLayout(col_shape, 3)
        cols.addLayout(col_look, 3)
        cols.addLayout(col_win, 4)

        # ===== 第 1 列：形状 + 几何 =====
        g_shape = QGroupBox("形状")
        gl = QGridLayout(g_shape)
        self.shape_combo = QComboBox()
        for label, key in SHAPE_ITEMS:
            self.shape_combo.addItem(label, key)
        self.shape_combo.currentIndexChanged.connect(self._on_shape)
        gl.addWidget(QLabel("类型"), 0, 0)
        gl.addWidget(self.shape_combo, 0, 1, 1, 3)
        self.arm_boxes = {}
        for i, (key, name) in enumerate((("arm_up", "上臂"), ("arm_down", "下臂"),
                                         ("arm_left", "左臂"), ("arm_right", "右臂"))):
            cb = QCheckBox(name)
            cb.stateChanged.connect(self._on_arm)
            self.arm_boxes[key] = cb
            gl.addWidget(cb, 1, i)
        col_shape.addWidget(g_shape)

        g_geo = QGroupBox("几何参数")
        vg = QVBoxLayout(g_geo)
        vg.setSpacing(3)
        self.row_length = SliderRow("长度", 0, 100, 12, "px")
        self.row_thickness = SliderRow("粗细", 1, 20, 2, "px")
        self.row_gap = SliderRow("间距", 0, 100, 6, "px")
        self.row_size = SliderRow("大小", 2, 240, 28, "px")
        self.row_rotate = SliderRow("旋转", 0, 359, 180, "°")
        self.row_edge = SliderRow("边线长度", 10, 100, 100, "%")
        self.row_offx = SliderRow("水平偏移", -300, 300, 0, "px")
        self.row_offy = SliderRow("垂直偏移", -300, 300, 0, "px")
        for r in (self.row_length, self.row_thickness, self.row_gap, self.row_size,
                  self.row_rotate, self.row_edge, self.row_offx, self.row_offy):
            r.valueChanged.connect(self._on_geometry)
            vg.addWidget(r)
        self.cb_round = QCheckBox("圆角端点")
        self.cb_round.stateChanged.connect(self._on_geometry)
        vg.addWidget(self.cb_round)
        col_shape.addWidget(g_geo)

        # ===== 预设槽位 =====
        g_preset = QGroupBox("预设槽位 (3 个 · 可重命名)")
        vp2 = QVBoxLayout(g_preset)
        vp2.setSpacing(4)
        self.preset_rows = []
        for i in range(3):
            row = QHBoxLayout()
            name = QLineEdit()
            name.setPlaceholderText(f"槽位 {i + 1}（空）")
            name.setToolTip("直接编辑名称即可重命名")
            btn_save = QPushButton("保存")
            btn_save.setFixedWidth(52)
            btn_save.setToolTip("把当前准星外观存入该槽位")
            btn_load = QPushButton("载入")
            btn_load.setFixedWidth(52)
            btn_load.setEnabled(False)
            btn_load.setToolTip("载入该槽位")
            row.addWidget(name, 1)
            row.addWidget(btn_save)
            row.addWidget(btn_load)
            vp2.addLayout(row)
            btn_save.clicked.connect(lambda _c=False, i=i: self._preset_save(i))
            btn_load.clicked.connect(lambda _c=False, i=i: self._preset_load(i))
            name.editingFinished.connect(lambda i=i: self._preset_rename(i))
            self.preset_rows.append((name, btn_save, btn_load))
        lbl = QLabel("提示：槽位保存形状/几何/颜色/轮廓/中心点/偏移，"
                     "不含窗口行为；托盘菜单可快速切换。")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#666;font-size:11px;")
        vp2.addWidget(lbl)
        col_shape.addWidget(g_preset)
        col_shape.addStretch(1)

        # ===== 第 2 列：颜色 / 轮廓 / 中心点 =====
        self.color_main = ColorPicker("主色 (RGBA)", [0, 255, 80, 255])
        self.color_main.changed.connect(self._on_color)
        col_look.addWidget(self.color_main)

        g_out = QGroupBox("轮廓 (描边)")
        vo = QVBoxLayout(g_out)
        vo.setSpacing(3)
        self.cb_outline = QCheckBox("启用轮廓")
        self.cb_outline.stateChanged.connect(self._on_outline)
        vo.addWidget(self.cb_outline)
        self.row_outline_w = SliderRow("轮廓宽度", 1, 10, 1, "px")
        self.row_outline_w.valueChanged.connect(self._on_outline)
        vo.addWidget(self.row_outline_w)
        self.color_outline = ColorPicker("轮廓色 (RGBA)", [0, 0, 0, 180])
        self.color_outline.changed.connect(self._on_outline_color)
        vo.addWidget(self.color_outline)
        col_look.addWidget(g_out)

        g_dot = QGroupBox("中心点")
        vd = QVBoxLayout(g_dot)
        vd.setSpacing(3)
        self.cb_dot = QCheckBox("启用中心点")
        self.cb_dot.stateChanged.connect(self._on_dot)
        vd.addWidget(self.cb_dot)
        self.row_dot = SliderRow("中心点大小", 0, 30, 2, "px")
        self.row_dot.valueChanged.connect(self._on_dot)
        vd.addWidget(self.row_dot)
        self.cb_dot_main = QCheckBox("中心点使用主色")
        self.cb_dot_main.stateChanged.connect(self._on_dot)
        vd.addWidget(self.cb_dot_main)
        self.color_dot = ColorPicker("中心点色 (RGBA)", [255, 40, 40, 255])
        self.color_dot.changed.connect(self._on_dot_color)
        vd.addWidget(self.color_dot)
        col_look.addWidget(g_dot)
        col_look.addStretch(1)

        # ===== 第 3 列：预览 + 窗口行为 + 快捷键 =====
        g_prev = QGroupBox("预览")
        vp = QVBoxLayout(g_prev)
        self.preview = PreviewWidget(self.cfg)
        vp.addWidget(self.preview)
        col_win.addWidget(g_prev, 1)

        g_win = QGroupBox("窗口行为")
        vw = QVBoxLayout(g_win)
        self.cb_top = QCheckBox("窗口置顶")
        self.cb_top.stateChanged.connect(self._on_window)
        vw.addWidget(self.cb_top)
        self.cb_through = QCheckBox("鼠标穿透 (穿透时无法拖动)")
        self.cb_through.stateChanged.connect(self._on_through)
        vw.addWidget(self.cb_through)
        self.cb_drag = QCheckBox("拖动模式 (关闭穿透以便拖动窗口)")
        self.cb_drag.stateChanged.connect(self._on_drag)
        vw.addWidget(self.cb_drag)
        self.cb_capture = QCheckBox("不被屏幕捕捉 (防截图/录屏/共享)")
        self.cb_capture.setToolTip(
            "调用 Windows SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)：\n"
            "开启后截图、录屏与屏幕共享中不会出现准星。\n"
            "需 Windows 10 2004 及以上；少数游戏/反作弊环境可能失效。")
        self.cb_capture.stateChanged.connect(self._on_capture)
        vw.addWidget(self.cb_capture)
        self.cb_lock = QCheckBox("锁定到屏幕中心")
        self.cb_lock.stateChanged.connect(self._on_window)
        vw.addWidget(self.cb_lock)
        row_mon = QHBoxLayout()
        row_mon.addWidget(QLabel("显示器"))
        self.mon_combo = QComboBox()
        self.mon_combo.currentIndexChanged.connect(self._on_window)
        row_mon.addWidget(self.mon_combo, 1)
        vw.addLayout(row_mon)
        self.lbl_hint = QLabel("提示：拖动模式关闭后可用鼠标拖动准星窗口；\n"
                               "锁定中心时可配合偏移量微调位置。")
        self.lbl_hint.setStyleSheet("color:#666;font-size:11px;")
        self.lbl_hint.setWordWrap(True)
        vw.addWidget(self.lbl_hint)
        col_win.addWidget(g_win)

        g_hot = QGroupBox("全局快捷键")
        vh = QVBoxLayout(g_hot)
        for text in ("Ctrl+Alt+S  显示/隐藏 设置面板",
                     "Ctrl+Alt+H  显示/隐藏 准星",
                     "Ctrl+Alt+D  切换 拖动模式",
                     "Ctrl+Alt+C  切换 锁定屏幕中心",
                     "Ctrl+Alt+X  退出程序"):
            lb = QLabel(text)
            lb.setStyleSheet("font-size:11px;")
            vh.addWidget(lb)
        col_win.addWidget(g_hot)

        # ===== 底部按钮（固定在窗口底部，不随滚动区滚动）=====
        btn_bar = QHBoxLayout()
        self.btn_toggle = QPushButton("隐藏准星")
        self.btn_toggle.clicked.connect(self.app.toggle_crosshair)
        self.btn_reset = QPushButton("恢复默认")
        self.btn_reset.clicked.connect(self._reset)
        self.btn_tray = QPushButton("最小化到托盘")
        self.btn_tray.clicked.connect(self.hide)
        self.btn_quit = QPushButton("退出")
        self.btn_quit.clicked.connect(self.app.quit_app)
        for b in (self.btn_toggle, self.btn_reset, self.btn_tray, self.btn_quit):
            btn_bar.addWidget(b)
        root.addLayout(btn_bar)

    # ---------------- 同步 ----------------
    def _sync_from_cfg(self):
        self._syncing = True
        try:
            self._do_sync_from_cfg()
        finally:
            self._syncing = False

    def _do_sync_from_cfg(self):
        d = self.cfg.data
        # 兼容旧版配置：tshape 已移出下拉，归一化为自定义臂组合（上/左/右）
        valid = {key for _, key in SHAPE_ITEMS}
        if d["shape"] not in valid:
            if d["shape"] == "tshape":
                d["shape"] = "custom"
                d["arm_up"], d["arm_down"] = True, False
                d["arm_left"], d["arm_right"] = True, True
            else:
                d["shape"] = "custom"
            self.app.save()
        idx = self.shape_combo.findData(d["shape"])
        self.shape_combo.setCurrentIndex(max(0, idx))
        for key, cb in self.arm_boxes.items():
            cb.setChecked(bool(d[key]))
        self.row_length.set_value(d["length"])
        self.row_thickness.set_value(d["thickness"])
        self.row_gap.set_value(d["gap"])
        self.row_size.set_value(d["size"])
        self.row_rotate.set_value(d["rotate"])
        self.row_edge.set_value(d["edge_ratio"])
        self.row_offx.set_value(d["offset_x"])
        self.row_offy.set_value(d["offset_y"])
        self.cb_round.setChecked(bool(d["round_cap"]))
        self.color_main.set_rgba(d["color"])
        self.cb_outline.setChecked(bool(d["outline_enabled"]))
        self.row_outline_w.set_value(d["outline_width"])
        self.color_outline.set_rgba(d["outline_color"])
        self.cb_dot.setChecked(bool(d["dot_enabled"]))
        self.row_dot.set_value(d["dot_size"])
        self.cb_dot_main.setChecked(bool(d["dot_use_main"]))
        self.color_dot.set_rgba(d["dot_color"])
        self.cb_top.setChecked(bool(d["always_on_top"]))
        self.cb_through.setChecked(bool(d["click_through"]))
        self.cb_drag.setChecked(not bool(d["click_through"]))
        self.cb_capture.setChecked(bool(d["exclude_from_capture"]))
        self.cb_lock.setChecked(bool(d["lock_center"]))
        self._sync_preset_ui()
        self._refresh_monitors()
        self._apply_shape_sensitivity()

    def _refresh_monitors(self):
        self.mon_combo.blockSignals(True)
        self.mon_combo.clear()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            g = s.geometry()
            self.mon_combo.addItem(f"{i + 1}. {s.name()} ({g.width()}x{g.height()})", i)
        idx = min(int(self.cfg.get("monitor_index", 0)), max(0, len(screens) - 1))
        self.mon_combo.setCurrentIndex(idx)
        self.mon_combo.blockSignals(False)

    def _apply_shape_sensitivity(self):
        shape = self.cfg.data["shape"]
        is_line = shape in ("cross", "tshape", "custom")
        is_tri = shape == "triangle"
        is_circle = shape == "circle"
        self.row_length.set_enabled(is_line)
        self.row_gap.set_enabled(is_line or is_tri)
        self.row_size.set_enabled(is_tri or is_circle)
        self.row_rotate.set_enabled(is_tri)
        self.row_edge.set_enabled(is_tri)
        for cb in self.arm_boxes.values():
            cb.setEnabled(True)
        self.btn_toggle.setText("显示准星" if not self.cfg.get("visible", True) else "隐藏准星")

    # ---------------- 事件处理 ----------------
    def _on_shape(self):
        if self._syncing:
            return
        key = self.shape_combo.currentData()
        self.cfg.set("shape", key)
        if key == "cross":
            self.cfg.set("arm_up", True); self.cfg.set("arm_down", True)
            self.cfg.set("arm_left", True); self.cfg.set("arm_right", True)
        elif key == "tshape":
            self.cfg.set("arm_up", True); self.cfg.set("arm_down", False)
            self.cfg.set("arm_left", True); self.cfg.set("arm_right", True)
        elif key == "dot":
            self.cfg.set("arm_up", False); self.cfg.set("arm_down", False)
            self.cfg.set("arm_left", False); self.cfg.set("arm_right", False)
        for k, cb in self.arm_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(bool(self.cfg.get(k, False)))
            cb.blockSignals(False)
        self._apply_shape_sensitivity()
        self.app.apply_and_save()

    def _on_arm(self):
        if self._syncing:
            return
        for k, cb in self.arm_boxes.items():
            self.cfg.set(k, cb.isChecked())
        # 手动修改臂组合时切到自定义
        cur = self.cfg.get("shape")
        if cur in ("cross", "tshape", "dot"):
            self.cfg.set("shape", "custom")
            self.shape_combo.blockSignals(True)
            self.shape_combo.setCurrentIndex(self.shape_combo.findData("custom"))
            self.shape_combo.blockSignals(False)
        self._apply_shape_sensitivity()
        self.app.apply_and_save()

    def _on_geometry(self):
        if self._syncing:
            return
        self.cfg.set("length", self.row_length.value())
        self.cfg.set("thickness", self.row_thickness.value())
        self.cfg.set("gap", self.row_gap.value())
        self.cfg.set("size", self.row_size.value())
        self.cfg.set("rotate", self.row_rotate.value())
        self.cfg.set("edge_ratio", self.row_edge.value())
        self.cfg.set("offset_x", self.row_offx.value())
        self.cfg.set("offset_y", self.row_offy.value())
        self.cfg.set("round_cap", self.cb_round.isChecked())
        self.app.apply_and_save()

    def _on_color(self, rgba):
        if self._syncing:
            return
        self.cfg.set("color", rgba)
        self.app.apply_and_save()

    def _on_outline(self):
        if self._syncing:
            return
        self.cfg.set("outline_enabled", self.cb_outline.isChecked())
        self.cfg.set("outline_width", self.row_outline_w.value())
        self.app.apply_and_save()

    def _on_outline_color(self, rgba):
        if self._syncing:
            return
        self.cfg.set("outline_color", rgba)
        self.app.apply_and_save()

    def _on_dot(self):
        if self._syncing:
            return
        self.cfg.set("dot_enabled", self.cb_dot.isChecked())
        self.cfg.set("dot_size", self.row_dot.value())
        self.cfg.set("dot_use_main", self.cb_dot_main.isChecked())
        self.app.apply_and_save()

    def _on_dot_color(self, rgba):
        if self._syncing:
            return
        self.cfg.set("dot_color", rgba)
        self.app.apply_and_save()

    def _on_window(self):
        if self._syncing:
            return
        self.cfg.set("always_on_top", self.cb_top.isChecked())
        self.cfg.set("lock_center", self.cb_lock.isChecked())
        if self.mon_combo.currentData() is not None:
            self.cfg.set("monitor_index", int(self.mon_combo.currentData()))
        self.overlay.apply_window_flags()
        self.overlay.reposition()
        self.app.save()

    def _on_through(self):
        if self._syncing:
            return
        self.cfg.set("click_through", self.cb_through.isChecked())
        self.cb_drag.blockSignals(True)
        self.cb_drag.setChecked(not self.cb_through.isChecked())
        self.cb_drag.blockSignals(False)
        self.overlay.apply_window_flags()
        self.app.save()

    def _on_drag(self):
        if self._syncing:
            return
        drag = self.cb_drag.isChecked()
        self.cfg.set("click_through", not drag)
        self.cb_through.blockSignals(True)
        self.cb_through.setChecked(not drag)
        self.cb_through.blockSignals(False)
        self.overlay.apply_window_flags()
        self.app.save()

    def _on_capture(self):
        if self._syncing:
            return
        self.cfg.set("exclude_from_capture", self.cb_capture.isChecked())
        self.overlay.apply_capture_affinity()
        self.app.save()

    # ---------------- 预设槽位 ----------------
    def _preset_slots(self) -> list:
        slots = list(self.cfg.get("presets") or [])
        while len(slots) < 3:
            slots.append(None)
        return slots[:3]

    def _sync_preset_ui(self):
        slots = self._preset_slots()
        for i, (name_edit, _btn_save, btn_load) in enumerate(self.preset_rows):
            slot = slots[i]
            name_edit.blockSignals(True)
            name_edit.setText(slot.get("name", f"预设 {i + 1}") if slot else "")
            name_edit.blockSignals(False)
            btn_load.setEnabled(bool(slot))

    def _preset_save(self, index):
        slots = self._preset_slots()
        prev = slots[index]
        name = self.preset_rows[index][0].text().strip()
        if not name:
            name = (prev or {}).get("name") or f"预设 {index + 1}"
        slots[index] = {"name": name,
                        "data": {k: self.cfg.data.get(k) for k in PRESET_KEYS}}
        self.cfg.set("presets", slots)
        self._sync_preset_ui()
        self.app.save()

    def _preset_load(self, index):
        slot = self._preset_slots()[index]
        if not slot:
            return
        for k, v in (slot.get("data") or {}).items():
            self.cfg.set(k, v)
        self._sync_from_cfg()
        self.app.apply_and_save()

    def _preset_rename(self, index):
        slots = self._preset_slots()
        name_edit = self.preset_rows[index][0]
        text = name_edit.text().strip()
        if not slots[index]:
            # 空槽位不创建预设，仅清理误输入的文字
            if text:
                name_edit.blockSignals(True)
                name_edit.setText("")
                name_edit.blockSignals(False)
            return
        if not text:
            text = slots[index].get("name") or f"预设 {index + 1}"
        slots[index]["name"] = text
        self.cfg.set("presets", slots)
        name_edit.blockSignals(True)
        name_edit.setText(text)
        name_edit.blockSignals(False)
        self.app.save()

    def _reset(self):
        keep = {k: self.cfg.data.get(k) for k in
                ("always_on_top", "click_through", "lock_center", "monitor_index",
                 "visible", "offset_x", "offset_y", "win_w", "win_h",
                 "exclude_from_capture", "presets")}
        self.cfg.data = default_config()
        for k, v in keep.items():
            if v is not None:
                self.cfg.data[k] = v
        self._sync_from_cfg()
        self.app.apply_and_save()

    def save_size(self):
        self.cfg.set("win_w", int(self.width()))
        self.cfg.set("win_h", int(self.height()))
        self.cfg.save()

    def closeEvent(self, event):
        self.save_size()
        event.ignore()
        self.hide()

    def refresh_state(self):
        self.btn_toggle.setText("显示准星" if not self.cfg.get("visible", True) else "隐藏准星")
        self.preview.update()


# ---------------------------------------------------------------------------
# 全局热键 (Windows)
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    WM_HOTKEY = 0x0312

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    class HotkeyFilter(QAbstractNativeEventFilter):
        def __init__(self, handlers: dict):
            super().__init__()
            self.handlers = handlers

        def nativeEventFilter(self, event_type, message):
            if event_type in ("windows_generic_MSG", "windows_dispatcher_MSG"):
                try:
                    addr = int(message)
                except Exception:
                    try:
                        addr = message.__int__()
                    except Exception:
                        return False, 0
                msg = ctypes.cast(addr, ctypes.POINTER(MSG)).contents
                if msg.message == WM_HOTKEY:
                    cb = self.handlers.get(int(msg.wParam))
                    if cb:
                        cb()
                        return True, 0
            return False, 0
else:
    HotkeyFilter = None


# ---------------------------------------------------------------------------
# 应用主体
# ---------------------------------------------------------------------------

def make_tray_icon(color: QColor = None) -> QIcon:
    """动态生成托盘图标，避免依赖外部资源文件。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(0, 255, 80), 6, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(32, 6, 32, 22)
    p.drawLine(32, 42, 32, 58)
    p.drawLine(6, 32, 22, 32)
    p.drawLine(42, 32, 58, 32)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(255, 40, 40)))
    p.drawEllipse(QRectF(28, 28, 8, 8))
    p.end()
    return QIcon(pm)


class CrosshairApp:
    def __init__(self):
        self.cfg = Config()
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName(APP_NAME)
        self.app.setOrganizationName(ORG_NAME)

        self.overlay = CrosshairWindow(self.cfg)
        self.settings = SettingsDialog(self.cfg, self.overlay, self)
        self._build_tray()
        self._register_hotkeys()

        self.overlay.refresh()
        if self.cfg.get("visible", True):
            self.overlay.show()
        self.settings.show()
        self.settings.raise_()
        self.save()  # 首次运行即落盘默认配置

    # ---------------- 托盘 ----------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon(), self.app)
        self.tray.setToolTip("屏幕准星")
        menu = QMenu()
        act_settings = QAction("设置面板", menu)
        act_settings.triggered.connect(self.toggle_settings)
        act_toggle = QAction("显示/隐藏 准星", menu)
        act_toggle.triggered.connect(self.toggle_crosshair)
        act_drag = QAction("拖动模式", menu)
        act_drag.setCheckable(True)
        act_drag.setChecked(not self.cfg.get("click_through", True))
        act_drag.triggered.connect(lambda checked: self.set_drag_mode(checked))
        act_top = QAction("窗口置顶", menu)
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.cfg.get("always_on_top", True)))
        act_top.triggered.connect(lambda c: self._set_flag("always_on_top", c))
        self.act_drag = act_drag
        self.act_top = act_top
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_settings)
        menu.addAction(act_toggle)
        menu.addSeparator()
        self.preset_menu = menu.addMenu("预设")
        self.preset_menu.aboutToShow.connect(self._rebuild_preset_menu)
        menu.addSeparator()
        menu.addAction(act_drag)
        menu.addAction(act_top)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _rebuild_preset_menu(self):
        """托盘预设菜单在每次展开时按当前槽位重建。"""
        self.preset_menu.clear()
        slots = self.cfg.get("presets") or [None, None, None]
        for i in range(3):
            slot = slots[i] if i < len(slots) else None
            title = f"{i + 1}. {slot.get('name', f'预设 {i + 1}')}" if slot else f"{i + 1}. （空）"
            act = QAction(title, self.preset_menu)
            act.setEnabled(bool(slot))
            act.triggered.connect(lambda _c=False, i=i: self.apply_preset(i))
            self.preset_menu.addAction(act)

    def apply_preset(self, index):
        """应用指定预设（供托盘菜单调用）。"""
        st = getattr(self, "settings", None)
        if st is not None:
            st._preset_load(index)
            return
        slots = self.cfg.get("presets") or []
        slot = slots[index] if index < len(slots) else None
        if not slot:
            return
        for k, v in (slot.get("data") or {}).items():
            self.cfg.set(k, v)
        self.overlay.update()
        self.save()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_settings()

    # ---------------- 热键 ----------------
    def _register_hotkeys(self):
        if sys.platform != "win32" or HotkeyFilter is None:
            return
        handlers = {
            1: self.toggle_settings,
            2: self.toggle_crosshair,
            3: self.toggle_drag_mode,
            4: self.toggle_lock_center,
            5: self.quit_app,
        }
        self.filter = HotkeyFilter(handlers)
        self.app.installNativeEventFilter(self.filter)
        u = ctypes.windll.user32
        keys = {1: 0x53, 2: 0x48, 3: 0x44, 4: 0x43, 5: 0x58}  # S H D C X
        for hid, vk in keys.items():
            u.RegisterHotKey(None, hid, MOD_CONTROL | MOD_ALT, vk)

    # ---------------- 行为 ----------------
    def apply_and_save(self):
        self.overlay.update()
        st = getattr(self, "settings", None)
        if st is not None:
            st.preview.update()
        self.save()

    def save(self):
        self.cfg.save()

    def toggle_settings(self):
        if self.settings.isVisible():
            self.settings.hide()
        else:
            self.settings.show()
            self.settings.raise_()
            self.settings.activateWindow()

    def toggle_crosshair(self):
        vis = not self.cfg.get("visible", True)
        self.cfg.set("visible", vis)
        if vis:
            self.overlay.apply_window_flags()
            self.overlay.reposition()
            self.overlay.show()
        else:
            self.overlay.hide()
        self.settings.refresh_state()
        self.save()

    def set_drag_mode(self, enabled: bool):
        self.cfg.set("click_through", not enabled)
        self.settings.cb_drag.blockSignals(True)
        self.settings.cb_through.blockSignals(True)
        self.settings.cb_drag.setChecked(enabled)
        self.settings.cb_through.setChecked(not enabled)
        self.settings.cb_drag.blockSignals(False)
        self.settings.cb_through.blockSignals(False)
        act = getattr(self, "act_drag", None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(bool(enabled))
            act.blockSignals(False)
        self.overlay.apply_window_flags()
        self.save()

    def toggle_drag_mode(self):
        self.set_drag_mode(bool(self.cfg.get("click_through", True)))

    def toggle_lock_center(self):
        val = not self.cfg.get("lock_center", True)
        self.cfg.set("lock_center", val)
        self.settings.cb_lock.blockSignals(True)
        self.settings.cb_lock.setChecked(val)
        self.settings.cb_lock.blockSignals(False)
        self.overlay.reposition()
        self.save()

    def _set_flag(self, key, value):
        self.cfg.set(key, bool(value))
        if key == "always_on_top":
            self.settings.cb_top.blockSignals(True)
            self.settings.cb_top.setChecked(bool(value))
            self.settings.cb_top.blockSignals(False)
        self.overlay.apply_window_flags()
        self.save()

    def quit_app(self):
        st = getattr(self, "settings", None)
        if st is not None:
            st.save_size()
        self.cfg.save()
        self.tray.hide()
        self.app.quit()

    def run(self):
        return self.app.exec()


def main():
    # 高 DPI 适配（Qt6 默认启用，此处确保取整策略稳定）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    ex = CrosshairApp()
    sys.exit(ex.run())


if __name__ == "__main__":
    main()
