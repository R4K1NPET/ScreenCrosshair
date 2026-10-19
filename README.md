# ScreenCrosshair · 屏幕准星

一款无边框、可置顶、可鼠标穿透的屏幕准星叠加层工具，完全由AI制作。

## 功能特性

- **形状**：十字（四臂）、三角形（APEX 风格三线）、圆形、纯中心点，以及可自由组合的自定义臂（上 / 下 / 左 / 右）
  - T 字效果：选择「自定义臂组合」，开启上 / 左 / 右三臂、关闭下臂即可
- **可调参数**：每种形状均可调长度、粗细、间距、大小、旋转、水平 / 垂直偏移，并支持端点圆角
- **颜色**：主色与轮廓色各自独立的 RGBA 调色；轮廓厚度可调
- **中心点**：可开关、独立大小与颜色（或跟随主色）
- **窗口行为**：置顶、鼠标穿透、拖动模式、锁定屏幕中心、多显示器选择
- **防捕捉**：可开启「不被屏幕捕捉」，在截图 / 录屏 / 屏幕共享中隐藏准星（需 Windows 10 2004 及以上）
- **预设**：3 个可重命名、保存、载入的外观预设，托盘菜单可快速切换
- **其他**：设置窗口实时预览、可自由缩放、全局快捷键

## 全局快捷键

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+Alt+S | 显示 / 隐藏 设置面板 |
| Ctrl+Alt+H | 显示 / 隐藏 准星 |
| Ctrl+Alt+D | 切换 拖动模式 |
| Ctrl+Alt+C | 切换 锁定屏幕中心 |
| Ctrl+Alt+X | 退出程序 |

## 下载与使用

从 Releases 下载 `ScreenCrosshair.exe`，双击运行即可。右键托盘图标可打开设置、切换拖动 / 置顶等。

配置保存在 `%APPDATA%\ScreenCrosshair\config.json`，首次运行自动写入默认值。

## 从源码运行

```bash
pip install PySide6-Essentials PyInstaller
python main.py
```

## 打包为单文件 exe

```bash
python build.py
```

`build.py` 会先生成 `icon.ico`，再用 PyInstaller 打包为 `dist/ScreenCrosshair.exe`。

## 许可证

[MIT](LICENSE)
