<p align="center">
  <img src="Icons/LOGO.png" alt="InsightPaper Logo" width="400">
</p>

<h1 align="center">InsightPaper</h1>

<p align="center">
  <strong>🔬 智能论文阅读与管理工具</strong>
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#使用指南">使用指南</a> •
  <a href="#快捷键">快捷键</a> •
  <a href="#技术栈">技术栈</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/PyQt6-6.0+-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## 📖 简介

**InsightPaper** 是一款专为科研人员和学生设计的智能论文阅读与管理工具。它集成了 PDF 阅读、翻译对照、AI 辅助分析、笔记管理等功能，帮助您更高效地阅读和理解学术论文。

## ✨ 功能特性

### 📚 论文管理
- **层级分类** - 支持 主题(Topic) → 组(Group) → 论文(PDF) 的三级层级管理
- **拖拽操作** - 支持拖拽导入论文，拖拽重新分类
- **翻译版管理** - 拖拽 PDF 到论文上即可设为翻译版

### 📖 阅读体验
- **并排阅读** - 原文与翻译版并排显示，同步滚动
- **高清渲染** - 后台多线程渲染，流畅阅读体验
- **页面旋转** - 支持单页旋转，状态自动保存
- **缩略图导航** - 侧边栏缩略图快速跳转

### ✏️ 标注工具
- **高亮笔刷** - 多种颜色高亮标记重点内容
- **橡皮擦** - 按住 Shift 快速切换橡皮擦模式
- **双视图同步** - 并排模式下标注自动同步

### 🤖 AI 助手
- **多平台支持** - 集成 ChatGPT、Gemini、豆包、DeepSeek、Grok
- **文本翻译** - Alt + 选中文本，一键发送至 AI 翻译
- **无缝切换** - 一键切换不同 AI 服务

### 📝 笔记功能
- **自动保存** - 每篇论文独立笔记，自动保存
- **结构化存储** - 笔记、缓存、标注统一管理

## 🚀 快速开始

### 方式一：运行源代码

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/InsightPaper.git
cd InsightPaper

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python mainwindow.py
```

### 方式二：使用打包版本

```bash
# 打包为独立 EXE
python build_exe.py

# 运行生成的可执行文件
./dist/InsightPaper.exe
```

### 依赖要求

- Python 3.9+
- PyQt6
- PyQt6-Fluent-Widgets
- PyMuPDF (fitz)

## 📖 使用指南

### 论文导入

1. **自动加载** - 程序启动时自动加载 `data` 文件夹中的论文
2. **拖拽导入** - 将 PDF 文件拖入论文列表
3. **分类管理** - 右键创建主题/组，拖拽论文进行分类

### 翻译版设置

将翻译后的 PDF 拖拽到原版论文上，即可设为翻译版。设置后：
- 论文前显示 🟢 绿点标记
- 单击打开并排阅读模式
- 双击切换为仅原文模式

### AI 辅助阅读

1. 点击右上角 🌐 图标打开 AI 助手
2. Alt + 鼠标选中文本可快速发送至豆包翻译
3. 使用顶部标签切换不同 AI 服务

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + 滚轮` | 缩放页面 |
| `Shift + 滚轮` | 调整笔刷大小 |
| `Alt + 拖拽` | 选中文本 |
| `右键拖拽` | 平移页面 |
| `Shift (按住)` | 切换橡皮擦模式 |

## 🏗️ 项目结构

```
InsightPaper/
├── mainwindow.py           # 主窗口入口
├── build_exe.py            # 打包脚本
├── requirements.txt        # 依赖列表
├── Icons/                  # 图标资源
│   ├── LOGO.png
│   └── LOGO.ico
├── modules/                # 功能模块
│   ├── pdf_viewer.py       # PDF 阅读器
│   ├── ai_assistant.py     # AI 助手集成
│   ├── topic_manager.py    # 主题/组管理
│   ├── draggable_list.py   # 拖拽列表组件
│   ├── edit_tools.py       # 编辑工具（笔刷）
│   ├── pdf_text_extractor.py  # 文本选择器
│   ├── shortcut_manager.py # 快捷键管理
│   └── help_dialog.py      # 帮助对话框
├── data/                   # 论文存放目录
└── analysis/               # 分析数据目录
    └── [论文名]/
        ├── Translation.pdf # 翻译版
        ├── analysis.txt    # 笔记
        ├── marker.json     # 笔刷标记
        └── cache_*/        # 渲染缓存
```

## 🛠️ 技术栈

- **GUI 框架**: PyQt6 + PyQt6-Fluent-Widgets
- **PDF 渲染**: PyMuPDF (fitz)
- **Web 集成**: PyQt6-WebEngine
- **打包工具**: PyInstaller

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

<p align="center">
  Made with ❤️ for Researchers
</p>

