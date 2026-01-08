from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from qfluentwidgets import MessageBoxBase, SubtitleLabel

class HelpDialog(MessageBoxBase):
    """软件使用帮助弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("InsightPaper 使用指南", self)
        
        # 使用 QTextBrowser 显示富文本内容
        self.contentBrowser = QTextBrowser(self)
        self.contentBrowser.setOpenExternalLinks(True)
        # 基础样式：去除边框，背景透明
        self.contentBrowser.setStyleSheet("""
            QTextBrowser { 
                background-color: transparent; 
                border: none; 
                font-size: 14px; 
                color: #333; 
            }
        """)
        
        # --- 样式定义 ---
        
        # 1. 按键样式 (Key Style)
        # - background-color: 稍微带一点灰白，模拟键帽颜色
        # - border: 浅灰色边框
        # - border-bottom: 深灰色且加粗，模拟按键的高度/立体感 (3D效果核心)
        # - border-radius: 圆角
        # - padding: 内边距，让文字不拥挤
        key_css = (
            "display: inline-block;"
            "background-color: #f3f4f6;" 
            "border: 1px solid #d1d5db;"
            "border-bottom: 3px solid #9ca3af;" 
            "border-radius: 6px;"
            "padding: 2px 7px;"
            "font-family: 'Segoe UI', Consolas, monospace;"
            "font-size: 13px;"
            "font-weight: bold;"
            "color: #1f2937;"
            "vertical-align: middle;" 
        )
        
        # 2. 连接符样式 (+)
        plus_css = (
            "color: #9ca3af;"
            "font-weight: bold;"
            "font-size: 16px;"
            "margin: 0 4px;"
            "vertical-align: middle;"
        )

        # --- 辅助函数 ---
        
        def key(text):
            """生成按键 HTML"""
            return f"<span style='{key_css}'>{text}</span>"
            
        def combine(*args):
            """生成组合键 HTML，自动在中间插入 + 号"""
            # 将所有按键用 styled '+' 连接起来
            plus_html = f"<span style='{plus_css}'>+</span>"
            parts = [key(k) for k in args]
            return plus_html.join(parts)

        # --- HTML 内容构建 ---
        
        help_text = f"""
        <style>
            h3 {{ 
                color: #009faa; 
                margin-top: 15px; 
                margin-bottom: 10px; 
                font-family: 'Segoe UI', sans-serif; 
                font-weight: bold;
            }}
            table {{ width: 100%; border-collapse: separate; border-spacing: 0 10px; }}
            td {{ vertical-align: middle; }}
            .keys-col {{ width: 220px; }} /* 稍微加宽一点以容纳组合键 */
            .desc {{ 
                color: #4b5563; 
                font-size: 14px; 
                font-family: 'Segoe UI', sans-serif; 
                padding-left: 10px; 
            }}
        </style>

        <h3>🎨 绘图与编辑 (Editing)</h3>
        <table>
            <tr>
                <td class="keys-col">{key("B")}</td> 
                <td class='desc'>开启/关闭 高亮画笔</td>
            </tr>
            <tr>
                <td class="keys-col">{combine("Shift", "B")}</td> 
                <td class='desc'>切换 橡皮擦模式</td>
            </tr>
            <tr>
                <td class="keys-col">{combine("Shift", "滚轮")}</td> 
                <td class='desc'>调节笔刷/橡皮擦大小</td>
            </tr>
        </table>
        
        <h3>👀 视图控制 (View Control)</h3>
        <table>
            <tr>
                <td class="keys-col">{combine("Ctrl", "滚轮")}</td> 
                <td class='desc'>缩放画布 (Zoom)</td>
            </tr>
            <tr>
                <td class="keys-col">{combine("Ctrl", "右键拖拽")}</td> 
                <td class='desc'>平移画布 (Pan)</td>
            </tr>
            <tr>
                <td class="keys-col">{key("Space")}</td> 
                <td class='desc'>重置视图</td>
            </tr>
            <tr>
                <td class="keys-col">{combine("Alt", "左键拖拽")}</td> 
                <td class='desc'>选中文本 (Select Text)</td>
            </tr>
        </table>
        """
        
        self.contentBrowser.setHtml(help_text)
        self.contentBrowser.setMinimumHeight(450)
        self.contentBrowser.setMinimumWidth(600) # 稍微加宽以适应更好的布局
        
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(self.contentBrowser)
        
        # 按钮配置
        self.yesButton.setText("我知道了")
        self.cancelButton.hide()
        self.widget.setMinimumWidth(600)