# -*- coding: utf-8 -*-
"""
构建脚本：生成图标并打包为单文件 exe。

用法：
    python build.py

依赖：
    pip install PySide6-Essentials PyInstaller
"""
import os
import struct
import subprocess
import sys

from PySide6.QtCore import Qt, QRectF, QBuffer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap
from PySide6.QtWidgets import QApplication


def make_icon(path: str):
    """用 PySide6 绘制一个十字 + 中心点的图标并保存为 .ico（内嵌 PNG）。"""
    app = QApplication([])  # 生成像素图需要 QApplication 实例
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(0, 255, 80), 24, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(128, 24, 128, 88)
    p.drawLine(128, 168, 128, 232)
    p.drawLine(24, 128, 88, 128)
    p.drawLine(168, 128, 232, 128)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(255, 40, 40)))
    p.drawEllipse(QRectF(104, 104, 48, 48))
    p.end()

    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    pm.save(buf, "PNG")
    png = bytes(buf.data())

    # 构造 ICO 容器（含单个 32bpp PNG 图像）
    ico = struct.pack("<HHH", 0, 1, 1)
    ico += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    ico += png
    with open(path, "wb") as f:
        f.write(ico)
    print("图标已生成:", path)


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    ico = os.path.join(base, "icon.ico")
    make_icon(ico)
    subprocess.run(
        [sys.executable, "-m", "PyInstaller",
         "--onefile", "--windowed",
         "--name", "ScreenCrosshair",
         "--icon", ico,
         "--noconfirm", "main.py"],
        cwd=base,
        check=True,
    )
    print("打包完成：", os.path.join(base, "dist", "ScreenCrosshair.exe"))


if __name__ == "__main__":
    main()
