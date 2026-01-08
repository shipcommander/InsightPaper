import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QStackedWidget, QHBoxLayout, 
                             QPushButton, QListWidget, QListWidgetItem, QLabel, QApplication, QFileDialog, QAbstractItemView)
from PyQt6.QtCore import QUrl, Qt, QMimeData, QTimer, pyqtSignal, QObject, QSize, QProcess
import sys
from PyQt6.QtGui import QDrag, QCursor, QDesktopServices
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineDownloadRequest
from qfluentwidgets import FluentIcon as FIF, Flyout, FlyoutAnimationType, TransparentToolButton, InfoBar, InfoBarPosition, RoundMenu, Action, MenuAnimationType

# --- Simplified WebEnginePage (No complex injection) ---
class WebEnginePage(QWebEnginePage):
    """Custom Page to filter noisy JS console messages"""
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Filter out common noisy warnings
        if "ResizeObserver" in message or "Content Security Policy" in message:
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

class PopupWindow(QWidget):
    """Simple Popup Window for Login"""
    popoutClosed = pyqtSignal()

    def __init__(self, profile, parent=None):
        super().__init__(None) # Top-level window
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1200, 800)
        self.webview = QWebEngineView()
        
        # Use simple page with same profile
        page = WebEnginePage(profile, self.webview)
        self.webview.setPage(page)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.webview)
        self.webview.titleChanged.connect(self.setWindowTitle)
        
        if parent:
            geom = parent.geometry()
            self.move(geom.center() - self.rect().center())

    def closeEvent(self, event):
        self.popoutClosed.emit()
        super().closeEvent(event)

class DownloadManager(QObject):
    """Simple Download Manager - 直接保存到 download 文件夹"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        if getattr(sys, 'frozen', False):
             root_dir = os.path.dirname(sys.executable)
        else:
             root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.dir = os.path.join(root_dir, "download")
        os.makedirs(self.dir, exist_ok=True)

    def handle_download(self, item: QWebEngineDownloadRequest):
        """直接保存到 download 文件夹，不弹窗"""
        filename = item.downloadFileName()
        save_path = os.path.join(self.dir, filename)
        
        # 如果文件已存在，添加序号
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            save_path = os.path.join(self.dir, f"{base}_{counter}{ext}")
            counter += 1
        
        item.setDownloadDirectory(self.dir)
        item.setDownloadFileName(os.path.basename(save_path))
        item.accept()
        item.stateChanged.connect(lambda: self._finish(item, save_path))

    def _finish(self, item, path):
        if item.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self.history.append(path)
            if self.parent(): self.parent().on_download_success(path)
    
    def open_download_folder(self):
        """打开下载文件夹"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.dir))

class AIWebViewer(QWidget):
    serviceChanged = pyqtSignal(str)
    closeRequested = pyqtSignal()  # 关闭信号，用于返回 PDF 视图

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dl_mgr = DownloadManager(self)
        
        # --- Service Configuration ---
        self.services = [
            {"key": "chatgpt", "name": "ChatGPT", "url": "https://chatgpt.com/"},
            {"key": "gemini",  "name": "Gemini",  "url": "https://gemini.google.com/"},
            {"key": "doubao",  "name": "豆包",      "url": "https://www.doubao.com/chat/"},
            {"key": "deepseek","name": "DeepSeek","url": "https://chat.deepseek.com/"},
            {"key": "grok",    "name": "Grok",    "url": "https://grok.com/"},
            {"key": "doc2x",   "name": "Doc2X",   "url": "https://doc2x.noedgeai.com/"},
            {"key": "scholar", "name": "Google学术","url": "https://scholar.google.com/"}
        ]
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(10, 5, 10, 5)
        
        # 菜单按钮（三横线）- 用于切换 AI 模型
        self.btn_menu = TransparentToolButton(FIF.MENU, self)
        self.btn_menu.setToolTip("切换 AI 模型")
        self.btn_menu.clicked.connect(self.show_menu)
        
        self.lbl_title = QLabel("ChatGPT")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #555; margin-left: 8px;")

        self.btn_dl = TransparentToolButton(FIF.DOWNLOAD, self)
        self.btn_dl.clicked.connect(self.show_downloads)
        
        self.btn_refresh = TransparentToolButton(FIF.SYNC, self)
        self.btn_refresh.clicked.connect(lambda: self.stack.currentWidget().reload())
        
        # 关闭按钮 - 点击返回 PDF 视图
        self.btn_close = TransparentToolButton(FIF.CLOSE, self)
        self.btn_close.setToolTip("关闭 AI 助手，返回文档预览")
        self.btn_close.clicked.connect(self.closeRequested.emit)

        # Header Layout: 菜单按钮在最左边，关闭按钮在最右边
        header.addWidget(self.btn_menu)
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(self.btn_dl)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.btn_close)
        
        header_frame = QWidget()
        header_frame.setStyleSheet("background-color: #f7f3ea; border-bottom: 1px solid #e0e0e0;")
        header_frame.setLayout(header)
        header_frame.setFixedHeight(45)
        layout.addWidget(header_frame)

        # Stacked Widget
        self.stack = QStackedWidget()
        if getattr(sys, 'frozen', False):
            base_cache = os.path.dirname(sys.executable)
        else:
            base_cache = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        for svc in self.services:
            view = self.create_web_view(
                svc["name"], 
                os.path.join(base_cache, "analysis", f"cache_{svc['key']}"), 
                svc["url"]
            )
            self.stack.addWidget(view)
            
        layout.addWidget(self.stack)
        
        # 默认加载第一个服务（ChatGPT），无需用户选择
        if self.services:
            first_svc = self.services[0]
            self.stack.setCurrentIndex(0)
            self.lbl_title.setText(first_svc["name"])

    def create_web_view(self, name, cache_path, url):
        os.makedirs(cache_path, exist_ok=True)
        view = QWebEngineView()
        
        profile = QWebEngineProfile(name, view)
        profile.setPersistentStoragePath(cache_path)
        profile.setCachePath(cache_path)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        # Note: No custom UserAgent, No injection script (as requested)
        
        profile.downloadRequested.connect(self.dl_mgr.handle_download)
        
        page = WebEnginePage(profile, view)
        view.setPage(page)
        view.setUrl(QUrl(url))
        return view

    def pop_out_current(self):
        """Pop out current view to new window"""
        current_view = self.stack.currentWidget()
        if not current_view: return
        
        popup = PopupWindow(current_view.page().profile(), self.window())
        popup.webview.setUrl(current_view.url())
        popup.setWindowTitle(f"登录 - {self.lbl_title.text()}")
        popup.resize(1200, 800)
        popup.show()
        
        popup.popoutClosed.connect(current_view.reload)

    def pop_out_service(self, service_key):
        """Pop out a specific service by key for login"""
        for i, svc in enumerate(self.services):
            if svc["key"] == service_key:
                view = self.stack.widget(i)
                if not view: return
                
                popup = PopupWindow(view.page().profile(), self.window())
                popup.webview.setUrl(view.url())
                popup.setWindowTitle(f"登录 - {svc['name']}")
                popup.resize(1200, 800)
                popup.show()
                popup.popoutClosed.connect(view.reload)
                return

    def show_menu(self):
        menu = RoundMenu(parent=self)
        for i, svc in enumerate(self.services):
            action = Action(FIF.CHAT, svc["name"])
            action.triggered.connect(lambda _, idx=i, n=svc["name"], k=svc["key"]: self.switch_service(idx, n, k))
            menu.addAction(action)
        menu.exec(QCursor.pos(), aniType=MenuAnimationType.DROP_DOWN)

    def switch_service(self, index, name, key):
        self.stack.setCurrentIndex(index)
        self.lbl_title.setText(name)
        self.serviceChanged.emit(key)

    def on_download_success(self, path):
        InfoBar.success("下载完成", os.path.basename(path), duration=2000, parent=self)

    def load_chatgpt(self):
        """Switch to ChatGPT WebView"""
        self.switch_service(0, "ChatGPT", "chatgpt")

    def load_gemini(self):
        """Switch to Gemini WebView"""
        self.switch_service(1, "Gemini", "gemini")

    def load_doubao(self):
        """Switch to Doubao WebView"""
        self.switch_service(2, "豆包", "doubao")

    def load_deepseek(self):
        """Switch to DeepSeek WebView"""
        self.switch_service(3, "DeepSeek", "deepseek")
        
    def load_grok(self):
        """Switch to Grok WebView"""
        self.switch_service(4, "Grok", "grok")

    def show_downloads(self):
        """显示下载列表 - 显示 download 文件夹中的所有文件，支持拖动"""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractItemView
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        
        # 获取 download 文件夹中的所有文件
        download_files = []
        if os.path.exists(self.dl_mgr.dir):
            for f in os.listdir(self.dl_mgr.dir):
                full_path = os.path.join(self.dl_mgr.dir, f)
                if os.path.isfile(full_path):
                    download_files.append(full_path)
            # 按修改时间排序（最新的在前）
            download_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        container = QWidget()
        container.setFixedWidth(300)
        container.setStyleSheet("background: white; border-radius: 8px;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # 标题栏
        header = QHBoxLayout()
        title = QLabel(f"下载 ({len(download_files)})")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")
        
        # 打开文件夹按钮
        open_folder_btn = TransparentToolButton(FIF.FOLDER, container)
        open_folder_btn.setToolTip("打开下载文件夹")
        open_folder_btn.clicked.connect(self.dl_mgr.open_download_folder)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(open_folder_btn)
        layout.addLayout(header)
        
        if not download_files:
            empty_label = QLabel("下载文件夹为空")
            empty_label.setStyleSheet("color: #999; font-size: 12px;")
            layout.addWidget(empty_label)
        else:
            # 创建可拖动的列表
            file_list = DraggableDownloadList(container)
            file_list.setStyleSheet("""
                QListWidget {
                    border: none;
                    background: transparent;
                }
                QListWidget::item {
                    padding: 4px 8px;
                    border-radius: 4px;
                    color: #333;
                }
                QListWidget::item:hover {
                    background: #f0f0f0;
                    color: #333;
                }
                QListWidget::item:selected {
                    background: #e3f2fd;
                    color: #333;
                }
            """)
            
            for path in download_files:
                filename = os.path.basename(path)
                # 截断过长的文件名
                display_name = filename if len(filename) <= 35 else filename[:32] + "..."
                
                item = QListWidgetItem(display_name)
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, path)
                file_list.addItem(item)
            
            # 设置固定高度，最多显示 8 个文件
            item_height = 28
            max_items = 8
            list_height = min(len(download_files), max_items) * item_height + 10
            file_list.setFixedHeight(list_height)
            
            layout.addWidget(file_list)
        
        Flyout.make(container, self.btn_dl, self, aniType=FlyoutAnimationType.DROP_DOWN)
    
    def _open_file_location(self, file_path):
        """打开文件所在位置"""
        if os.path.exists(file_path):
            # Windows: 使用 explorer 并选中文件
            import subprocess
            subprocess.run(['explorer', '/select,', file_path])


class DraggableDownloadList(QListWidget):
    """支持拖动文件的下载列表"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
    
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path or not os.path.exists(file_path):
            return
        
        # 创建拖动对象
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(file_path)])
        drag.setMimeData(mime_data)
        
        # 创建拖动预览
        pixmap = self._create_drag_pixmap(item)
        if pixmap:
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        
        drag.exec(Qt.DropAction.CopyAction)
    
    def _create_drag_pixmap(self, item):
        """创建拖动预览图像"""
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush
        
        filename = item.text()
        
        # 创建预览图像
        width = min(280, len(filename) * 7 + 24)
        height = 32
        
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(0, 0, 0, 0))
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制背景
        painter.setBrush(QBrush(QColor("#e3f2fd")))
        painter.setPen(QPen(QColor("#90caf9"), 1.5))
        painter.drawRoundedRect(1, 1, width - 2, height - 2, 5, 5)
        
        # 绘制文件名
        painter.setPen(QPen(QColor("#1976d2")))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(12, 21, filename)
        
        painter.end()
        
        return pixmap

    @property
    def webview(self):
        return self.stack.currentWidget()