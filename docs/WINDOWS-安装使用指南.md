# Terminator Windows 安装与使用指南

本文档面向 **Windows 用户**,介绍如何在 Windows 上安装、运行 Terminator 终端。

> **状态说明**:Windows 版为本次新增的原生移植(基于 Windows ConPTY + pyte + GTK 自绘渲染),已通过 Linux 侧 125 项自动化测试,但 ConPTY/渲染/命名管道 IPC 的**运行时行为需在真实 Windows 10 1809+ 环境下按 `docs/WINDOWS-ACCEPTANCE.md` 验收矩阵确认**。当前为 alpha 阶段,建议优先用于体验与反馈。

---

## 0. 一键安装(推荐,最快上手)

仓库根目录提供了一键脚本。**双击 `install-windows.bat`** 即可自动完成全部安装:检测并安装 Python、MSYS2、GTK3 与 Python 绑定、Terminator 依赖与本体,并创建桌面快捷方式。

```
install-windows.bat      ← 双击安装(自动跑完所有步骤)
run-windows.bat          ← 安装后双击启动(或双击桌面"Terminator"图标)
build-windows-package.ps1 ← 安装成功后双击构建可分发的独立程序包
```

要点:
- 首次 `winget` 可能弹一次源协议确认;之后全部无人值守。
- 一键脚本走 MSYS2 提供 GTK;`pywin32` 在 MSYS2 下无 wheel,**单实例命名管道 IPC 会降级(程序照常运行)**。
- 装完后默认启动 PowerShell;切换 cmd/WSL 见第 8 节。
- 想要可拷贝分发的独立 `terminator.exe`(内嵌 GTK DLL):先跑 `install-windows.bat`,再跑 `build-windows-package.ps1`,产物在 `dist\terminator\`。

> 一键脚本内部细节(出问题时可对照):见 `install-windows.ps1` 注释。

---

## 1. 系统要求

| 项 | 要求 |
|----|------|
| 操作系统 | Windows 10 版本 1809 及以上(ConPTY 依赖) |
| 架构 | x64 |
| Python | 3.10(x64) |
| GTK 运行时 | GTK3 + PyGObject(见下文 MSYS2 方案) |
| 显示器 | 需要桌面会话(ConPTY 子进程在有桌面的环境下运行) |

---

## 2. 依赖准备(三种方式,任选其一)

### 方式 A:MSYS2(推荐,开发与运行统一)

1. 安装 [MSYS2](https://www.msys2.org/)。
2. 打开 **MSYS2 MinGW64** 终端,安装 GTK3 与 Python 绑定:
   ```bash
   pacman -S --noconfirm \
     mingw-w64-x86_64-gtk3 \
     mingw-w64-x86_64-python3 \
     mingw-w64-x86_64-python3-gobject \
     mingw-w64-x86_64-cairo \
     mingw-w64-x86_64-pango
   ```
3. 让该 MSYS2 终端的 `bin` 出现在系统 `PATH` 中(后续打包与运行都需要 GTK DLL 可被发现)。

### 方式 B:GTK3 独立运行时

从 [gtk.org](https://www.gtk.org/docs/installations/windows/) 下载 GTK3 运行时安装包,安装后将其 `bin` 目录加入 `PATH`。再单独安装 Python 与 `pip install pygobject`(Windows 上 pygobject 的 wheel 较少,MSYS2 更省心)。

### 方式 C:WSL 兼容回退

若原生 GTK 运行时难以配置,可在 WSLg 下运行 Linux 版(非本 PR 范围,仅作降级体验)。

---

## 3. 获取源码

```bash
git clone https://github.com/gnome-terminator/terminator.git
cd terminator
git checkout feature/windows-port   # Windows 移植分支(本 PR)
```

或使用你自己的 fork。

---

## 4. 安装 Python 依赖

```bash
python -m pip install --upgrade pip
pip install pycairo pygobject configobj psutil pyte pywin32 pytest
```

> `dbus-python` 在 Windows 上**不需要**(setup.py 已用环境标记条件化,Linux 才装)。Windows 的 IPC 走命名管道(`ipc_win32.py`)。

---

## 5. 安装 Terminator 本体

```bash
python setup.py --without-gettext install
```

`--without-gettext` 跳过 Linux 专用的 `msgfmt`/`intltool-merge` 构建步骤(`.desktop`、AppStream 在 Windows 上不需要)。

---

## 6. 直接运行(开发期)

不打包,直接从源码运行:

```bash
python terminator
```

首次启动会创建用户配置目录 `%APPDATA%\terminator\`。

---

## 7. 打包为单程序(可选)

用随附的 PyInstaller 规格文件生成一个独立目录:

```bat
set GTK_BIN=C:\msys64\mingw64\bin
pip install pyinstaller
pyinstaller packaging\terminator.spec
```

产物在 `dist\terminator\terminator.exe`。把整个 `dist\terminator\` 目录拷走即可用(已内嵌 GTK DLL)。

> 详细打包说明见 `PACKAGING-WINDOWS.md`。

---

## 8. 基本使用

### 启动

双击 `terminator.exe`(或在终端运行 `python terminator`)。默认启动 **PowerShell**(`pwsh`/`powershell`)。

### 切换默认 Shell

编辑 `%APPDATA%\terminator\config`,在对应 profile 下设置:

```ini
[profiles]
  [[default]]
    use_custom_command = True
    custom_command = cmd.exe            # 或 wsl.exe ~ (WSL bash)
```

| 目标 Shell | `custom_command` |
|-----------|------------------|
| PowerShell | `powershell.exe -NoLogo` |
| PowerShell 7 | `pwsh.exe -NoLogo` |
| cmd | `cmd.exe` |
| WSL bash | `wsl.exe ~` |

### 常用快捷键(与 Linux 版一致)

| 操作 | 快捷键 |
|------|--------|
| 水平分屏 | `Ctrl+Shift+O` |
| 垂直分屏 | `Ctrl+Shift+E` |
| 新标签页 | `Ctrl+Shift+T` |
| 复制 | `Ctrl+Shift+C` |
| 粘贴 | `Ctrl+Shift+V` |
| 搜索 | `Ctrl+Shift+F` |
| 关闭当前窗格 | `Ctrl+Shift+W` |
| 打开偏好设置 | `Ctrl+Shift+P` |

> macOS 风格键位不在 Windows 适用。

### 颜色与光标

- 支持 24 位真彩色、256 色调色板、反显、粗体/斜体/下划线/删除线。
- 光标形状可在配置中选 `block`(块)/`underline`(下划线)/`ibeam`(竖线)。
- 光标颜色:配置 `cursor_bg_color` / `cursor_fg_color`;闪烁: `cursor_blink = True`。
- 窗口标题栏深/浅:配置 `window_decoration_style = dark|light|auto`(auto 按终端背景亮度自动)。

### URL

`Ctrl` + 单击 URL 用默认浏览器打开;悬停时光标变手型。

### 单实例

再次运行 `terminator.exe` 不会开新进程,而是通过命名管道把请求转发给已在运行的主实例(开新窗口/新标签等),与 Linux 上 DBus 的行为对应。

---

## 9. 配置文件位置(Windows)

| 用途 | 路径 |
|------|------|
| 用户配置 | `%APPDATA%\terminator\config` |
| 用户配置目录 | `%APPDATA%\terminator\` |
| 布局 JSON(可选) | `--configjson` 指定 |

> Linux 的 `~/.config/terminator` 与 `/etc/xdg/terminator` 在 Windows 上分别映射到 `%APPDATA%\terminator` 与 `%ProgramData%\terminator`。

---

## 10. 已知限制(alpha)

| 项 | 说明 |
|----|------|
| SIXEL 图形 | pyte 不支持,无法显示图形 |
| OSC-8 超链接悬停元数据 | 未暴露(正则 URL 匹配仍可用) |
| CJK 输入法(IME) | 尚未接入,中文输入可能受限 |
| `WINDOWID` 环境变量 | Windows 不设置(X11 专属),依赖它的 shell 会降级 |
| 运行时验证 | ConPTY/渲染/IPC 已写好并通过静态与 Linux 侧测试,真实 Windows 运行需按验收矩阵确认 |

完整的真机验收清单见 `docs/WINDOWS-ACCEPTANCE.md`。

---

## 11. 故障排查

**启动报 "需要 X 环境 / Gtk"**
→ GTK3 运行时未就绪。确认 MSYS2 的 `mingw64\bin` 在 `PATH`,或改用方式 B 的 GTK 运行时。

**子进程未启动 / "Unable to start shell"**
→ 默认 shell 未找到。在配置里显式设置 `custom_command`(见第 8 节),或确认 `pwsh.exe`/`powershell.exe` 在 `PATH`。

**中文乱码**
→ 确保 shell 输出 UTF-8。PowerShell 可执行 `chcp 65001`;`TERM` 默认为 `xterm-256color`。注意 IME 输入尚未支持(见已知限制)。

**分屏/标签不显示**
→ 布局容器逻辑与 Linux 共享,若异常请附 `--debug=2` 启动的日志反馈。

**单实例不转发命令**
→ 命名管道可能被占用;用 `--nodbus`(Linux 参数,Windows 同样可强制独立实例)启动绕过,或将日志反馈。

---

## 12. 反馈

请在 GitHub 仓库提 issue,并附:
- Windows 版本号(`winver`)
- 使用的 shell 与 GTK 运行时方式
- `--debug=2` 启动时的输出片段
- 是否使用打包版(`terminator.exe`)还是源码运行
