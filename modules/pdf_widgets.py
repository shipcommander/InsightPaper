import os
import sys
from PyQt6.QtWidgets import (QStackedWidget, QLabel, QVBoxLayout, QHBoxLayout, QWidget, 
                             QSplitter, QListWidget, QListWidgetItem, QPushButton, 
                             QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog, QMessageBox)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from qfluentwidgets import FluentIcon as FIF, TransparentToolButton

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# Import PDFGraphicsView from the original file
from modules.pdf_viewer import PDFGraphicsView, HAS_FITZ

THUMBNAIL_STYLE = """
    QListWidget { background-color: #f7f3ea; border: none; border-right: 1px solid #e0dfdc; outline: none; padding-top: 5px; }
    QListWidget::item { background-color: white; border: 1px solid #e0e0e0; border-radius: 4px; color: #555; margin: 2px 5px; }
    QListWidget::item:selected { border: 2px solid #0078d4; background-color: #f0f0f0; }
    QListWidget::item:hover { border: 1px solid #999; }
"""

OUTLINE_STYLE = """
    QTreeWidget { background-color: #f7f3ea; border: none; outline: none; padding: 5px; color: #333; }
    QTreeWidget::item { padding: 4px; border-bottom: 1px solid #eee; color: #333; }
    QTreeWidget::item:hover { background-color: #f0f0f0; }
    QTreeWidget::item:selected { background-color: #dcdcdc; color: black; }
    QTreeWidget::item:selected:active { background-color: #dcdcdc; color: black; }
    QTreeWidget::item:selected:!active { background-color: #dcdcdc; color: black; }
    
    QMenu { 
        background-color: white; 
        border: 1px solid #d0d0d0; 
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 25px;
        color: black;
        background-color: transparent;
    }
    QMenu::item:selected {
        background-color: #f0f0f0;
        color: black;
    }
"""

class PDFThumbnailWidget(QListWidget):
    """侧边栏缩略图"""
    pageSelected = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(100, 142))
        self.setSpacing(2)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setStyleSheet(THUMBNAIL_STYLE)
        self.itemClicked.connect(lambda item: self.pageSelected.emit(item.data(Qt.ItemDataRole.UserRole)))
        
        self.doc = None
        self.loaded_idx = 0
        self.timer = QTimer()
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._load_batch)

    def set_doc(self, doc):
        self.timer.stop()
        self.clear()
        self.doc = doc
        self.loaded_idx = 0
        if doc: self.timer.start()

    def _load_batch(self):
        if not self.doc or getattr(self.doc, 'is_closed', False) or self.loaded_idx >= len(self.doc):
            return self.timer.stop()
            
        for _ in range(2): # Batch size
            if self.loaded_idx >= len(self.doc): break
            try:
                page = self.doc.load_page(self.loaded_idx)
                pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
                icon = QIcon(QPixmap.fromImage(QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)))
                
                item = QListWidgetItem(f"{self.loaded_idx+1}")
                item.setIcon(icon)
                item.setData(Qt.ItemDataRole.UserRole, self.loaded_idx)
                item.setTextAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
                self.addItem(item)
                self.loaded_idx += 1
            except Exception:
                self.timer.stop() 
                break

class PDFOutlineWidget(QTreeWidget):
    """侧边栏大纲/目录"""
    pageSelected = pyqtSignal(int, float) # (page_index, y_offset_in_pdf_points)
    tocChanged = pyqtSignal()
    addChapterRequested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(15)
        self.setStyleSheet(OUTLINE_STYLE)
        self.itemClicked.connect(self._on_item_clicked)
        
        # 启用拖拽设置层级
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        # 简化选择逻辑：支持 Shift 连选，移除冗余的 Ctrl 点选
        from PyQt6.QtWidgets import QAbstractItemView
        self.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)

        # 右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
    def set_doc(self, doc):
        self.clear()
        if not doc:
            return
            
        toc = doc.get_toc(simple=False)
        if not toc:
            return
            
        self.set_toc_data(toc)

    def add_custom_item(self, title, page_num, y_offset=0):
        """手动添加目录项"""
        item = QTreeWidgetItem([title])
        item.setData(0, Qt.ItemDataRole.UserRole, page_num - 1)
        # 存储 y 偏移量
        dest = {"y": y_offset}
        item.setData(0, Qt.ItemDataRole.UserRole + 1, dest)
        # 统一添加到根节点末尾
        self.addTopLevelItem(item)
        return item

    def _show_context_menu(self, pos):
        from qfluentwidgets import RoundMenu, Action, FluentIcon as FIF
        items = self.selectedItems()
        menu = RoundMenu(parent=self)
        
        if items:
            if len(items) == 1:
                # 单选时的管理
                rename_act = Action(FIF.EDIT, "重命名章节", self)
                rename_act.triggered.connect(lambda: self._rename_item(items[0]))
                menu.addAction(rename_act)
            
            del_act = Action(FIF.DELETE, f"删除已选章节 ({len(items)})", self)
            del_act.triggered.connect(self._delete_selected_items)
            menu.addAction(del_act)
        else:
            # 点击空白区域
            add_act = Action(FIF.ADD, "在当前页新建章节", self)
            add_act.triggered.connect(self.addChapterRequested.emit)
            menu.addAction(add_act)
            
        menu.exec(self.viewport().mapToGlobal(pos))

    def dropEvent(self, event):
        """拖放结束后更新目录结构"""
        super().dropEvent(event)
        # 拖放改变了层级结构，触发保存
        self.tocChanged.emit()

    def _rename_item(self, item):
        old_title = item.text(0)
        new_title, ok = QInputDialog.getText(self, "重命名章节", "请输入新的章节名称:", text=old_title)
        if ok and new_title and new_title != old_title:
            item.setText(0, new_title)
            self.tocChanged.emit()

    def _delete_selected_items(self):
        root = self.invisibleRootItem()
        for item in self.selectedItems():
            (item.parent() or root).removeChild(item)
        self.tocChanged.emit()

    def get_full_toc(self):
        """递归获取当前目录树的所有项 (level, title, page)"""
        toc = []
        def _walk(parent, level):
            for i in range(parent.childCount()):
                child = parent.child(i)
                title = child.text(0)
                page = child.data(0, Qt.ItemDataRole.UserRole)
                if page is not None:
                    toc.append([level, title, int(page) + 1])
                _walk(child, level + 1)
        
        _walk(self.invisibleRootItem(), 1)
        return toc

    def set_toc_data(self, toc):
        """直接使用给定的 TOC 数据填充树"""
        self.clear()
        if not toc:
            return
            
        stack = [(0, self.invisibleRootItem())]
        for entry in toc:
            level, title, page = entry[0], entry[1], entry[2]
            dest = entry[3] if len(entry) > 3 else {}
            
            # 确保层级不会跳级（例如从 1 直接跳到 3），防止 stack 为空
            level = max(1, level)
            while level <= stack[-1][0]:
                stack.pop()
            
            parent_item = stack[-1][1]
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, int(page) - 1)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, dest)
            parent_item.addChild(item)
            stack.append((level, item))
            if level == 1:
                item.setExpanded(True)

    def _on_item_clicked(self, item, column):
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        dest = item.data(0, Qt.ItemDataRole.UserRole + 1)
        
        if page_idx is not None and isinstance(page_idx, int):
            y_offset = 0.0
            if isinstance(dest, dict):
                # 1. 优先尝试解析原生 PDF 的 'to' 字段
                if "to" in dest:
                    to_val = dest["to"]
                    if hasattr(to_val, "y"): # 是 fitz.Point
                        y_offset = to_val.y
                    elif isinstance(to_val, (list, tuple)) and len(to_val) >= 2:
                        y_offset = to_val[1]
                # 2. 尝试解析手动添加的 'y' 字段
                elif "y" in dest:
                    y_offset = dest["y"]
            
            # 安全检查 y_offset
            try:
                y_offset = float(y_offset)
                if y_offset < 0: y_offset = 0.0
            except:
                y_offset = 0.0
                
            self.pageSelected.emit(page_idx, y_offset)

class PDFViewerWidget(QWidget):
    """主 PDF 阅读器组件 (含侧边栏与视图栈)"""
    translationRequested = pyqtSignal(str)
    aiAssistantRequested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. 主分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #e0dfdc; }")
        layout.addWidget(self.splitter)
        
        # 2. 侧边栏
        self.side_container = QWidget()
        self.side_container.setStyleSheet("background: #f7f3ea;")
        self.side_container.setMinimumWidth(150) # 设置最小宽度
        side_layout = QVBoxLayout(self.side_container)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        
        # 侧边栏顶部切换按钮
        self.side_tabs = QHBoxLayout()
        self.btn_thumb = QPushButton("缩略图")
        self.btn_outline = QPushButton("章节目录")
        
        for btn in [self.btn_thumb, self.btn_outline]:
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { padding: 10px; border: none; border-bottom: 2px solid transparent; color: #666; font-weight: bold; }
                QPushButton:hover { background-color: #eee; }
            """)
        
        self.btn_thumb.clicked.connect(lambda: self._switch_sidebar_tab(0))
        self.btn_outline.clicked.connect(lambda: self._switch_sidebar_tab(1))
        self.side_tabs.addWidget(self.btn_thumb)
        self.side_tabs.addWidget(self.btn_outline)
        side_layout.addLayout(self.side_tabs)

        self.side_stack = QStackedWidget()
        self.thumbnails = PDFThumbnailWidget()
        self.thumbnails.pageSelected.connect(self.scroll_to_page)
        
        self.outline = PDFOutlineWidget()
        self.outline.pageSelected.connect(self.scroll_to_page)
        self.outline.tocChanged.connect(self._save_modified_toc)
        self.outline.addChapterRequested.connect(self._prompt_add_chapter)
        
        self.side_stack.addWidget(self.thumbnails)
        self.side_stack.addWidget(self.outline)
        side_layout.addWidget(self.side_stack, 1)
        
        self.splitter.addWidget(self.side_container)
        self._switch_sidebar_tab(0) # 默认显示缩略图        
        # 3. 内容区 (Stack)
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        
        # Page 0: Logo
        self._init_logo_page()
        # Page 1: Single View
        self.viewer = PDFGraphicsView()
        self.viewer.translationRequested.connect(self.translationRequested.emit)
        self.stack.addWidget(self.viewer)
        # Page 2: Dual View
        self.dual_page = QWidget()
        self._init_dual_page()
        self.stack.addWidget(self.dual_page)
        
        # 初始化状态
        self.stack.setCurrentIndex(0)
        self.expanded = False
        
        # --- Sidebar Toggle Button (Overlay) ---
        self.sidebar_btn = TransparentToolButton(FIF.MENU, self)
        self.sidebar_btn.setFixedSize(36, 36)
        self.sidebar_btn.setIconSize(QSize(20, 20))
        self.sidebar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_btn.setToolTip("显示/隐藏 缩略图")
        self.sidebar_btn.clicked.connect(self._toggle_sidebar)
        self.sidebar_btn.setStyleSheet("""
            TransparentToolButton {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
            }
            TransparentToolButton:hover {
                background-color: rgba(255, 255, 255, 1.0);
                border: 1px solid rgba(0, 0, 0, 0.2);
            }
        """)

        # --- AI Toggle Button (Overlay) ---
        self.ai_btn = TransparentToolButton(FIF.GLOBE, self)
        self.ai_btn.setFixedSize(36, 36)
        self.ai_btn.setIconSize(QSize(20, 20))
        self.ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_btn.setToolTip("AI Assistant")
        self.ai_btn.clicked.connect(self.aiAssistantRequested.emit)
        
        # Style it as a rounded rectangle with slight background for visibility
        self.ai_btn.setStyleSheet("""
            TransparentToolButton {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
            }
            TransparentToolButton:hover {
                background-color: rgba(255, 255, 255, 1.0);
                border: 1px solid rgba(0, 0, 0, 0.2);
            }
        """)
        
        # --- Rotate Button (Overlay) - 位于 AI 按钮左侧 ---
        self.rotate_btn = TransparentToolButton(FIF.ROTATE, self)
        self.rotate_btn.setFixedSize(36, 36)
        self.rotate_btn.setIconSize(QSize(20, 20))
        self.rotate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rotate_btn.setToolTip("旋转当前页面 (顺时针90°)")
        self.rotate_btn.clicked.connect(self._rotate_current_page)
        self.rotate_btn.setStyleSheet("""
            TransparentToolButton {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
            }
            TransparentToolButton:hover {
                background-color: rgba(255, 255, 255, 1.0);
                border: 1px solid rgba(0, 0, 0, 0.2);
            }
        """)
        
        # --- Page Indicator (Bottom Right) ---
        self.page_indicator = QLabel(self)
        self.page_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_indicator.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
                padding: 4px 10px;
                color: #333;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                font-weight: 500;
            }
        """)
        self.page_indicator.hide()
        
        # Connect signals for page update
        self.viewer.scrollChanged.connect(lambda: self._update_page_indicator())
        self.left_view.scrollChanged.connect(lambda: self._update_page_indicator())
        self.right_view.scrollChanged.connect(lambda: self._update_page_indicator())
        self.stack.currentChanged.connect(lambda: self._update_page_indicator())

        # Initial Hide
        self.side_container.hide() # Directly hide container
        self.sidebar_btn.hide()
        
        # 初始分配比例（侧边栏 240px，剩余给内容区）
        self.splitter.setSizes([240, 1000])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position AI button at top right
        m_top = 10
        m_right = 20
        self.ai_btn.move(self.width() - self.ai_btn.width() - m_right, m_top)
        self.ai_btn.raise_()
        
        # Position Rotate button to the left of AI button
        rotate_x = self.width() - self.ai_btn.width() - m_right - self.rotate_btn.width() - 8
        self.rotate_btn.move(rotate_x, m_top)
        self.rotate_btn.raise_()
        
        # Position Sidebar button at top left
        m_left = 10
        self.sidebar_btn.move(m_left, m_top)
        self.sidebar_btn.raise_()
        
        # Position Page Indicator at bottom right
        self._update_page_indicator_pos()
        self.page_indicator.raise_()

    def _update_page_indicator_pos(self):
        if not self.page_indicator.isVisible(): return
        m_bottom = 20
        m_right = 20
        self.page_indicator.adjustSize()
        self.page_indicator.move(self.width() - self.page_indicator.width() - m_right, 
                                 self.height() - self.page_indicator.height() - m_bottom)

    def _update_page_indicator(self):
        view = self._active_view()
        if not view or not view.page_items:
            self.page_indicator.hide()
            return
            
        current = view.get_current_page() + 1
        total = len(view.page_items)
        if total == 0:
            self.page_indicator.hide()
            return
            
        self.page_indicator.setText(f"{current} / {total}")
        self.page_indicator.show()
        self._update_page_indicator_pos()

    def _init_logo_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #e8f7f7;")
        layout = QVBoxLayout(page)
        lbl = QLabel("InsightPaper")
        lbl.setStyleSheet("color: #999; font-size: 24px; font-weight: bold;")
        
        if getattr(sys, 'frozen', False):
            root = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(root, "Icons", "LOGO.png")
        if os.path.exists(logo_path):
            lbl.setPixmap(QPixmap(logo_path).scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl.setText("")
            
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        self.stack.addWidget(page)

    def _init_dual_page(self):
        layout = QVBoxLayout(self.dual_page)
        layout.setContentsMargins(0,0,0,0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet("QSplitter::handle { background-color: #666; width: 2px; }")
        
        self.left_view = PDFGraphicsView()
        self.right_view = PDFGraphicsView()
        
        # 滚动和缩放同步信号
        self.left_view.scrollChanged.connect(self.right_view.sync_scroll_to)
        self.left_view.zoomChanged.connect(self.right_view.sync_zoom_to)
        self.right_view.scrollChanged.connect(self.left_view.sync_scroll_to)
        self.right_view.scrollChanged.connect(self.left_view.sync_scroll_to)
        self.right_view.zoomChanged.connect(self.left_view.sync_zoom_to)

        self.left_view.translationRequested.connect(self.translationRequested.emit)
        self.right_view.translationRequested.connect(self.translationRequested.emit)
        
        split.addWidget(self.left_view)
        split.addWidget(self.right_view)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        layout.addWidget(split)

    def _toggle_sidebar(self):
        # Toggle visibility directly
        if self.side_container.isVisible():
            self.side_container.hide()
            self.expanded = False
        else:
            self.side_container.show()
            self.expanded = True

    def load_pdf(self, path, scroll_to_page=None, cache_dir=None, brush_path=None, rotation_path=None, toc_path=None):
        if os.path.exists(path) or (cache_dir and os.path.exists(cache_dir)):
            # 存储 toc_path 以便后续保存
            self.current_toc_path = toc_path
            
            self.viewer.load_pdf(path, scroll_to_page=scroll_to_page, cache_dir=cache_dir, brush_path=brush_path, rotation_path=rotation_path)
            self.stack.setCurrentIndex(1)
            self._update_sidebar(self.viewer.doc)
        else:
            self.clear()

    def load_side_by_side(self, path1, path2, cache_dir1=None, cache_dir2=None, brush_path=None, brush_path2=None, rotation_path=None, rotation_path2=None, scroll_to_page=None, toc_path=None, toc_path2=None):
        if (os.path.exists(path1) or cache_dir1) and (os.path.exists(path2) or cache_dir2):
            self.current_toc_path = toc_path
            
            self.left_view.load_pdf(path1, cache_dir=cache_dir1, brush_path=brush_path, rotation_path=rotation_path)
            self.right_view.load_pdf(path2, cache_dir=cache_dir2, brush_path=brush_path2, rotation_path=rotation_path2)
            self.stack.setCurrentIndex(2)
            self._update_sidebar(self.left_view.doc)
            
            if scroll_to_page is not None:
                QTimer.singleShot(100, lambda: self.scroll_to_page(scroll_to_page))
        else:
            self.load_pdf(path1, cache_dir=cache_dir1, brush_path=brush_path, rotation_path=rotation_path, scroll_to_page=scroll_to_page, toc_path=toc_path)

    def _update_sidebar(self, doc):
        """更新侧边栏内容 (缩略图 + 目录)"""
        self.thumbnails.set_doc(doc if HAS_FITZ else None)
        
        # 1. 尝试从 PDF 加载原始目录
        import copy
        base_toc = []
        if doc and HAS_FITZ:
            try:
                base_toc = doc.get_toc(simple=False)
            except:
                base_toc = []
        
        # 2. 如果有外部保存的目录 JSON，尝试加载并合并/覆盖
        if hasattr(self, 'current_toc_path') and self.current_toc_path and os.path.exists(self.current_toc_path):
            try:
                import json
                with open(self.current_toc_path, 'r', encoding='utf-8') as f:
                    saved_toc = json.load(f)
                    if isinstance(saved_toc, list):
                         # 这里直接使用保存的 TOC，因为它包含了用户所有的编辑 (包括原始章节和新增章节)
                         # 只要 save 时保存的是全量数据
                         base_toc = saved_toc 
            except Exception as e:
                print(f"Error loading external TOC: {e}")

        # 3. 设置到 UI
        self.outline.set_toc_data(base_toc)
        
        has_doc = doc is not None
        self.sidebar_btn.setVisible(has_doc)
        
        # 如果有目录，默认切到目录页
        has_toc = len(base_toc) > 0
        if has_doc and has_toc:
             self._switch_sidebar_tab(1)
        else:
             self._switch_sidebar_tab(0)
             
        # 默认初始侧边栏状态
        self.side_container.show()
        self.expanded = True
        self._toggle_sidebar() # Adjust based on expanded state
        if self.side_container.isVisible():
             self.side_container.hide()
             self.expanded = False

    def close_file(self, path):
        self.current_toc_path = None # 清理
        for v in [self.viewer, self.left_view, self.right_view]:
            v.close_file(path)
        if not self.viewer.current_path and not self.left_view.current_path:
            self.clear()

    def clear(self):
        # Explicitly close all documents in all views to release file locks
        if self.viewer.doc: self.viewer.close_file(self.viewer.current_path)
        if self.left_view.doc: self.left_view.close_file(self.left_view.current_path)
        if self.right_view.doc: self.right_view.close_file(self.right_view.current_path)
        
        self.stack.setCurrentIndex(0)
        self.side_container.hide()
        self.sidebar_btn.hide()

    # 代理方法
    def zoom_in(self): self._active_view().zoom_in()
    def zoom_out(self): self._active_view().zoom_out()
    def get_current_page(self): return self._active_view().get_current_page()
    def scroll_to_page(self, p, y_offset=0): 
        idx = self.stack.currentIndex()
        if idx == 1: self.viewer.scroll_to_page(p, y_offset)
        elif idx == 2: 
            self.left_view.scroll_to_page(p, y_offset)
            self.right_view.scroll_to_page(p, y_offset)

    def _active_view(self):
        return self.left_view if self.stack.currentIndex() == 2 else self.viewer

    # === 笔刷模式代理方法 ===
    def set_brush_enabled(self, enabled):
        """启用/禁用笔刷模式（所有视图）"""
        idx = self.stack.currentIndex()
        if idx == 1:
            self.viewer.set_brush_enabled(enabled)
        elif idx == 2:
            self.left_view.set_brush_enabled(enabled)
            self.right_view.set_brush_enabled(enabled)

    def set_brush_mode(self, mode):
        """设置笔刷模式: 'draw' or 'erase'"""
        idx = self.stack.currentIndex()
        if idx == 1:
            self.viewer.set_brush_mode(mode)
        elif idx == 2:
            self.left_view.set_brush_mode(mode)
            self.right_view.set_brush_mode(mode)

    def get_brush_mode(self):
        return self._active_view().brush_handler.manager.mode
    
    def clear_brush_strokes(self):
        """清除所有视图的笔刷笔画"""
        idx = self.stack.currentIndex()
        if idx == 1:
            self.viewer.clear_brush_strokes()
        elif idx == 2:
            self.left_view.clear_brush_strokes()
            self.right_view.clear_brush_strokes()
    
    def is_brush_enabled(self):
        """检查笔刷模式是否启用"""
        return self._active_view().brush_handler.manager.enabled

    def undo(self):
        """执行撤销操作"""
        return self._active_view().undo()
    
    def _rotate_current_page(self):
        """旋转当前页面（顺时针90度）"""
        idx = self.stack.currentIndex()
        if idx == 1:
            self.viewer.rotate_current_page()
        elif idx == 2:
            self.left_view.rotate_current_page()
            self.right_view.rotate_current_page()

    def _switch_sidebar_tab(self, index):
        """切换侧边栏标签页"""
        self.side_stack.setCurrentIndex(index)
        # 更新按钮样式
        active_style = "QPushButton { padding: 10px; border: none; border-bottom: 2px solid #0078d4; color: #0078d4; font-weight: bold; }"
        inactive_style = "QPushButton { padding: 10px; border: none; border-bottom: 2px solid transparent; color: #666; font-weight: bold; }"
        
        self.btn_thumb.setStyleSheet(active_style if index == 0 else inactive_style)
        self.btn_outline.setStyleSheet(active_style if index == 1 else inactive_style)

    def _save_modified_toc(self):
        """将修改后的目录保存到外部 JSON 文件 (不修改 PDF)"""
        view = self._active_view()
        if not view.current_path:
            return
            
        # 必须确保有保存路径
        if not hasattr(self, 'current_toc_path') or not self.current_toc_path:
            print("No TOC path configured, skipping save.")
            return

        toc_data = self.outline.get_full_toc()
        
        try:
            import json
            # 确保目录存在
            toc_dir = os.path.dirname(self.current_toc_path)
            if not os.path.exists(toc_dir):
                os.makedirs(toc_dir, exist_ok=True)
                
            with open(self.current_toc_path, 'w', encoding='utf-8') as f:
                json.dump(toc_data, f, ensure_ascii=False, indent=2)
                
            print(f"目录已保存至 JSON: {self.current_toc_path}")
                
        except Exception as e:
            print(f"保存目录 JSON 失败: {e}")

    def _update_sidebar(self, doc):
        """更新侧边栏内容 (缩略图 + 目录)"""
        self.thumbnails.set_doc(doc if HAS_FITZ else None)
        
        # 1. 尝试从 PDF 加载原始目录
        import copy
        base_toc = []
        if doc and HAS_FITZ:
            try:
                base_toc = doc.get_toc(simple=False)
            except:
                base_toc = []
        
        # 2. 如果有外部保存的目录 JSON，尝试加载并合并/覆盖
        if hasattr(self, 'current_toc_path') and self.current_toc_path and os.path.exists(self.current_toc_path):
            try:
                import json
                with open(self.current_toc_path, 'r', encoding='utf-8') as f:
                    saved_toc = json.load(f)
                    if isinstance(saved_toc, list):
                         # 这里直接使用保存的 TOC，因为它包含了用户所有的编辑 (包括原始章节和新增章节)
                         # 只要 save 时保存的是全量数据
                         base_toc = saved_toc 
            except Exception as e:
                print(f"Error loading external TOC: {e}")

        # 3. 设置到 UI
        self.outline.set_toc_data(base_toc)
        
        has_doc = doc is not None
        self.sidebar_btn.setVisible(has_doc)
        
        # 如果有目录，默认切到目录页
        has_toc = len(base_toc) > 0
        if has_doc and has_toc:
             self._switch_sidebar_tab(1)
        else:
             self._switch_sidebar_tab(0)
             
        # 默认初始侧边栏状态
        self.side_container.show()
        self.expanded = True
        self._toggle_sidebar() # Adjust based on expanded state
        if self.side_container.isVisible():
             self.side_container.hide()
             self.expanded = False

    def _prompt_add_chapter(self):
        """弹出对话框，利用剪贴板内容新建章节"""
        # 1. 获取剪贴板内容作为默认名称
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtWidgets import QInputDialog, QTreeWidgetItem
        from PyQt6.QtCore import Qt
        from qfluentwidgets import InfoBar, InfoBarPosition
        
        clipboard = QGuiApplication.clipboard()
        clipboard_text = clipboard.text().strip()
        
        # 限制长度以防剪贴板内容过多导致对话框畸形
        default_title = clipboard_text[:60] if clipboard_text else "新章节"
        
        current_page = self.get_current_page() + 1
        
        # 2. 交互询问
        title, ok = QInputDialog.getText(
            self, 
            "新建章节", 
            f"设置当前第 {current_page} 页为章节\n请输入名称:", 
            text=default_title
        )
        
        if ok and title:
            # 3. 计算当前精确的 Y 偏移
            view = self._active_view()
            y_offset = 0
            try:
                # 将当前的滚动位置映射回 PDF 点坐标
                scroll_y = view.verticalScrollBar().value() / view.current_zoom
                page_start_y = view._page_y_positions[current_page - 1]
                # 相对页面的高度偏移（场景坐标）
                y_scene_offset = max(0, scroll_y - page_start_y)
                # 转换回 PDF 点
                y_offset = y_scene_offset / view.base_scale
            except: pass

            # 4. 在 UI 中添加项
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, current_page - 1)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, {"y": y_offset})
            self.outline.addTopLevelItem(item)
            
            # 5. 同步保存到 PDF 内部
            self._save_modified_toc()
            
            # 反馈
            InfoBar.success(
                title='添加成功',
                content=f'已添加章节: {title}',
                orient=Qt.Orientation.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self.window()
            )
