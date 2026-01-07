from PyQt6.QtWidgets import (QStackedWidget, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QSplitter, QListWidget, QListWidgetItem, 
                             QPushButton, QAbstractItemView)
from PyQt6.QtGui import QPixmap, QColor, QImage, QWheelEvent, QPainter, QBrush, QIcon, QCursor, QPen
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QThread
import os
import sys
from modules.pdf_text_extractor import PDFTextSelector
from modules.edit_tools import PdfBrushHandler
from qfluentwidgets import FluentIcon as FIF, TransparentToolButton

# --- 配置与样式 ---
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("PyMuPDF (fitz) not found. PDF viewing will be disabled.")

SCROLLBAR_STYLE = """
    QScrollBar:vertical, QScrollBar:horizontal { border: none; background: #f9f4e8; margin: 0px; }
    QScrollBar:vertical { width: 14px; } QScrollBar:horizontal { height: 14px; }
    QScrollBar::handle { background: #dcd3c1; border-radius: 7px; margin: 2px; }
    QScrollBar::handle:hover { background: #c5bba6; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
"""

THUMBNAIL_STYLE = """
    QListWidget { background-color: #f7f3ea; border: none; border-right: 1px solid #e0dfdc; outline: none; padding-top: 5px; }
    QListWidget::item { background-color: white; border: 1px solid #e0e0e0; border-radius: 4px; color: #555; margin: 2px 5px; }
    QListWidget::item:selected { border: 2px solid #0078d4; background-color: #f0f0f0; }
    QListWidget::item:hover { border: 1px solid #999; }
"""

def norm_path(path):
    """标准化路径用于比较"""
    return os.path.normcase(os.path.normpath(os.path.abspath(path))) if path else None


class PageRenderWorker(QThread):
    """后台线程渲染 PDF 页面，避免阻塞主线程"""
    pageRendered = pyqtSignal(int, QImage, float)  # page_num, image, y_position
    
    def __init__(self, doc_path, page_num, scale, y_position, cache_file=None):
        super().__init__()
        self.doc_path = doc_path
        self.page_num = page_num
        self.scale = scale
        self.y_position = y_position
        self.cache_file = cache_file
        self._cancelled = False
    
    def cancel(self):
        """标记此任务已取消"""
        self._cancelled = True
    
    def run(self):
        """在后台线程中渲染页面"""
        if self._cancelled:
            return
            
        # 1. 尝试从磁盘缓存加载
        if self.cache_file and os.path.exists(self.cache_file):
            img = QImage(self.cache_file)
            if not img.isNull() and not self._cancelled:
                self.pageRendered.emit(self.page_num, img, self.y_position)
                return
        
        # 2. 使用 fitz 渲染 (每个线程独立打开文档,确保线程安全)
        if not HAS_FITZ or not self.doc_path or not os.path.exists(self.doc_path):
            return
            
        try:
            doc = fitz.open(self.doc_path)
            if self._cancelled:
                doc.close()
                return
                
            page = doc.load_page(self.page_num)
            mat = fitz.Matrix(self.scale, self.scale)
            pix = page.get_pixmap(matrix=mat)
            
            # 创建 QImage (在工作线程中创建 QImage 是安全的)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            
            # 保存到缓存
            if self.cache_file and not self._cancelled:
                cache_dir = os.path.dirname(self.cache_file)
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)
                img.save(self.cache_file, "JPG", 90)
            
            doc.close()
            
            if not self._cancelled:
                self.pageRendered.emit(self.page_num, img, self.y_position)
                
        except Exception as e:
            print(f"[PageRenderWorker] Page {self.page_num} render error: {e}")


class PDFGraphicsView(QGraphicsView):
    """核心 PDF 阅读视图，支持后台线程渲染"""
    scrollChanged = pyqtSignal(float, float)
    zoomChanged = pyqtSignal(float)
    translationRequested = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setBackgroundBrush(QBrush(QColor("#fffdf7")))
        
        # 视图配置
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setStyleSheet(SCROLLBAR_STYLE)
        
        
        # 核心状态
        self.doc = None
        self.current_zoom = 1.0
        self.base_scale = 2.5  # 降低渲染分辨率以提升性能（原为3.0）
        self.page_items = []
        self.current_path = None
        self.cache_dir = None
        self._syncing = False
        self._is_panning = False
        self._pan_start_pos = None
        
        # 旋转状态跟踪
        self._page_rotations = {}  # page_num -> rotation_degrees (0, 90, 180, 270)
        self._rotation_file = None  # 旋转状态保存文件路径
        
        # 后台渲染线程管理
        self._active_workers = {}  # page_num -> PageRenderWorker
        self._page_count = 0
        self._page_padding = 20
        self._page_y_positions = []  # 存储每页的 y 位置
        self._page_heights = []  # 存储每页的高度
        
        # 初始渲染调度器 (仅用于启动后台任务，不阻塞主线程)
        self._render_idx = 0
        self._render_timer = QTimer()
        self._render_timer.setInterval(5)  # 每 5ms 调度一个渲染任务
        self._render_timer.timeout.connect(self._schedule_next_render)
        
        # 信号连接
        for bar in [self.verticalScrollBar(), self.horizontalScrollBar()]:
            bar.valueChanged.connect(self._on_scroll_changed)
            
        self.text_selector = PDFTextSelector(self)
        
        # 笔刷处理器
        self.brush_handler = PdfBrushHandler(self, self.scene_obj)

    def load_pdf(self, file_path, scroll_to_page=None, cache_dir=None, brush_path=None, rotation_path=None):
        """Standard PDF loading (No internal caching)"""
        # 1. 先停止任何正在进行的渲染任务
        self._render_timer.stop()
        self._cancel_all_workers()
        
        # 2. 显式关闭并释放旧文档（无论是否有 current_path）
        if self.doc is not None:
            try:
                self.doc.close()
            except:
                pass
            self.doc = None

        self.current_path = file_path
        self.cache_dir = cache_dir
        self.brush_path = brush_path
        
        # 设置旋转状态文件路径
        self._rotation_file = rotation_path
        self._page_rotations = {}
        self._load_rotation_state()
        
        # 初始化场景
        self.brush_handler.clear_graphics() # 先清理笔刷引用
        self.scene_obj.clear()
        self.page_items = []
        
        # 加载笔刷
        self.brush_handler.set_brush_path(brush_path)
        self.brush_handler.load_strokes()
        
        self._reset_view_state(zoom=1.0)
        
        # 检查是否可以加载
        if not HAS_FITZ and not (cache_dir and os.path.exists(os.path.join(cache_dir, "page_0.jpg"))):
            self._show_msg("无法加载 (fitz 未安装且无缓存)" if os.path.exists(file_path) else "文件不存在")
            return

        try:
            # 3. 加载新文档 - 确保 doc 被正确设置
            if HAS_FITZ and os.path.exists(file_path):
                self.doc = fitz.open(file_path)
                print(f"[PDF加载] 成功打开文档: {file_path}, 页数: {len(self.doc)}")
            else:
                print(f"[PDF加载] 使用缓存模式: {cache_dir}")
            
            self._render_pages()
            
            # 重新渲染笔刷（因为场景被清空了，但 handler 里已经 load 了数据）
            self.brush_handler.render_all_strokes()
            
            # 应用保存的旋转状态
            self._apply_saved_rotations()
            
            if scroll_to_page is not None:
                QTimer.singleShot(100, lambda: self.scroll_to_page(scroll_to_page))
        except Exception as e:
            self._show_msg(f"加载错误: {str(e)}")
            # print(f"Load error: {e}")

    def _render_pages(self):
        """启动异步后台渲染 (立即创建占位符，后台线程渲染实际内容)"""
        # 停止已有的渲染任务
        self._render_timer.stop()
        self._cancel_all_workers()
        
        # 确定页数
        page_count = 0
        if self._is_doc_open():
            page_count = len(self.doc)
        elif self.cache_dir:
            while os.path.exists(os.path.join(self.cache_dir, f"page_{page_count}.jpg")): 
                page_count += 1
            
        if page_count == 0: 
            return self._show_msg("无页面可显示")

        self._page_count = page_count
        self._page_y_positions = []
        self._page_heights = []
        
        # 1. 立即创建占位符 (快速，不阻塞)
        y = 0
        for i in range(page_count):
            # 获取页面尺寸 (这个操作很快，不需要后台线程)
            if self._is_doc_open():
                page = self.doc.load_page(i)
                rect = page.rect
                width = int(rect.width * self.base_scale)
                height = int(rect.height * self.base_scale)
            else:
                # 从缓存文件读取尺寸
                cache_file = os.path.join(self.cache_dir, f"page_{i}.jpg")
                if os.path.exists(cache_file):
                    img = QImage(cache_file)
                    width, height = img.width(), img.height()
                else:
                    width, height = 595 * 2, 842 * 2  # A4 默认尺寸
            
            # 创建白色占位符
            placeholder = QPixmap(width, height)
            placeholder.fill(QColor("#f8f8f8"))
            
            item = QGraphicsPixmapItem(placeholder)
            item.setPos(0, y)
            self.scene_obj.addItem(item)
            self.page_items.append(item)
            
            self._page_y_positions.append(y)
            self._page_heights.append(height)
            y += height + self._page_padding
        
        # 立即更新场景边界，让用户可以滚动
        self.scene_obj.setSceneRect(self.scene_obj.itemsBoundingRect())
        
        # 2. 启动后台渲染调度器
        self._render_idx = 0
        self._render_timer.start()
    
    def _schedule_next_render(self):
        """调度下一个后台渲染任务 (不阻塞主线程)"""
        if self._render_idx >= self._page_count:
            self._render_timer.stop()
            return
        
        # 限制同时进行的渲染任务数量
        MAX_CONCURRENT_WORKERS = 3
        if len(self._active_workers) >= MAX_CONCURRENT_WORKERS:
            return  # 等待现有任务完成
        
        page_num = self._render_idx
        
        # 跳过已经渲染的页面
        if page_num in self._active_workers:
            self._render_idx += 1
            return
        
        # 创建后台工作线程
        cache_file = os.path.join(self.cache_dir, f"page_{page_num}.jpg") if self.cache_dir else None
        y_pos = self._page_y_positions[page_num] if page_num < len(self._page_y_positions) else 0
        
        worker = PageRenderWorker(
            self.current_path, 
            page_num, 
            self.base_scale, 
            y_pos, 
            cache_file
        )
        worker.pageRendered.connect(self._on_page_rendered)
        worker.finished.connect(lambda: self._cleanup_worker(page_num))
        
        self._active_workers[page_num] = worker
        worker.start()
        
        self._render_idx += 1
    
    def _on_page_rendered(self, page_num, image, y_position):
        """后台渲染完成回调 (在主线程中执行)"""
        if page_num < len(self.page_items):
            # 将 QImage 转换为 QPixmap (必须在主线程中进行)
            qpix = QPixmap.fromImage(image)
            self.page_items[page_num].setPixmap(qpix)
    
    def _cleanup_worker(self, page_num):
        """清理已完成的工作线程"""
        if page_num in self._active_workers:
            worker = self._active_workers.pop(page_num)
            worker.deleteLater()
    
    def _cancel_all_workers(self):
        """取消所有正在进行的渲染任务"""
        for page_num, worker in list(self._active_workers.items()):
            worker.cancel()
            worker.quit()
            worker.wait(100)  # 等待最多 100ms
        self._active_workers.clear()

    def close_file(self, file_path):
        """Close specific file to release lock"""
        target = norm_path(file_path)
        current = norm_path(self.current_path)
        
        if target == current:
            # 停止正在进行的渲染
            self._render_timer.stop()
            self._cancel_all_workers()
            
            # Explicitly close doc
            # Avoid using boolean check on doc directly
            if self.doc is not None:
                try:
                    self.doc.close()
                except:
                    pass
                self.doc = None
            
            self.scene_obj.clear()
            self.page_items = []
            self.current_path = None
            self.current_zoom = 1.0

    # --- 辅助方法 ---
    def _is_doc_open(self):
        if not HAS_FITZ or not self.doc: return False
        try: return not getattr(self.doc, 'is_closed', False) and len(self.doc) >= 0
        except: return False

    def _reset_view_state(self, zoom):
        self.resetTransform()
        self.current_zoom = zoom
        s = zoom / self.base_scale
        self.scale(s, s)

    def _show_msg(self, text):
        self.scene_obj.clear()
        self.scene_obj.addText(text).setScale(2)
        
    def _set_scroll(self, v, h):
        self.verticalScrollBar().setValue(v)
        self.horizontalScrollBar().setValue(h)

    # --- 事件与交互 ---
    def wheelEvent(self, event):
        """Handle wheel event for scroll or brush size adjustment"""
        modifiers = event.modifiers()
        
        # Check for Shift + Scroll to adjust brush size
        # Note: Holding Shift might temporarily set mode to 'erase', so we allow resizing in 'erase' mode too if Shift is held.
        if (modifiers & Qt.KeyboardModifier.ShiftModifier) and \
           self.brush_handler and \
           self.brush_handler.manager.enabled:
           
            angle = event.angleDelta().y()
            if angle > 0:
                self.brush_handler.increase_width()
            elif angle < 0:
                self.brush_handler.decrease_width()
            
            event.accept()
            return

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.current_zoom * (1.1 if event.angleDelta().y() > 0 else 1/1.1))
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, e):
        # 1. Custom Pan: Right Mouse Button (No modifier needed)
        if e.button() == Qt.MouseButton.RightButton:
            self._is_panning = True
            self._pan_start_pos = e.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return

        scene_pos = self.mapToScene(e.pos())
        page_num = self.get_current_page()
        
        # 尝试由笔刷处理器处理
        if self.brush_handler.handle_mouse_press(e, page_num, scene_pos):
            e.accept()
            return
        
        if e.modifiers() == Qt.KeyboardModifier.AltModifier:
            self.text_selector.start_selection(scene_pos)
            e.accept()
        else: super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # 1. Custom Pan Handling
        if self._is_panning:
            delta = e.pos() - self._pan_start_pos
            self._pan_start_pos = e.pos()
            
            # Update scrollbars manually to simulate drag
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            e.accept()
            return
            
        scene_pos = self.mapToScene(e.pos())
        
        # 尝试由笔刷处理器处理
        if self.brush_handler.handle_mouse_move(e, scene_pos):
            e.accept()
            return

        if self.text_selector.is_selecting:
            self.text_selector.update_selection(scene_pos)
            e.accept()
        else: super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        # 1. Stop Panning
        if self._is_panning and e.button() == Qt.MouseButton.RightButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            # Restore proper cursor based on state
            self.brush_handler._update_cursor()
            e.accept()
            return

        # 尝试由笔刷处理器处理
        if self.brush_handler.handle_mouse_release(e):
            e.accept()
            return
        
        if self.text_selector.is_selecting:
            self.text_selector.end_selection(self.mapToScene(e.pos()))
            e.accept()
        else: super().mouseReleaseEvent(e)
        
    def keyPressEvent(self, event):
        if self.brush_handler:
            self.brush_handler.handle_key_event(event, True)
        super().keyPressEvent(event)
        
    def keyReleaseEvent(self, event):
        if self.brush_handler:
            self.brush_handler.handle_key_event(event, False)
        super().keyReleaseEvent(event)

    def set_zoom(self, z):
        z = max(0.2, min(z, 10.0))
        if z != self.current_zoom:
            self.scale(z / self.current_zoom, z / self.current_zoom)
            self.current_zoom = z
            if not self._syncing: self.zoomChanged.emit(z)

    def zoom_in(self): self.set_zoom(self.current_zoom * 1.1)
    def zoom_out(self): self.set_zoom(self.current_zoom / 1.1)

    def _on_scroll_changed(self):
        if self._syncing: return
        vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        self.scrollChanged.emit(
            vb.value() / max(1, vb.maximum()), 
            hb.value() / max(1, hb.maximum())
        )

    def sync_scroll_to(self, vr, hr):
        self._syncing = True
        vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        vb.setValue(int(vr * vb.maximum()))
        hb.setValue(int(hr * hb.maximum()))
        self._syncing = False

    def sync_zoom_to(self, z):
        if self._syncing: return
        self._syncing = True
        prev = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.set_zoom(z)
        self.setTransformationAnchor(prev)
        self._syncing = False

    def scroll_to_page(self, num):
        if 0 <= num < len(self.page_items):
            # Center horizontally, align top vertically
            item = self.page_items[num]
            self.centerOn(item.pixmap().width()/2, item.y() + self.viewport().height()/2)

    def get_current_page(self):
        if not self.page_items: return 0
        y = self.mapToScene(self.viewport().rect().center()).y()
        for i, item in enumerate(self.page_items):
            r = item.sceneBoundingRect()
            if r.top() <= y <= r.bottom(): return i
        return 0

    # === 笔刷相关方法 ===

    def set_brush_enabled(self, enabled):
        """启用/禁用笔刷模式"""
        self.brush_handler.set_enabled(enabled)
        
    def set_brush_mode(self, mode):
        """设置模式：draw / erase"""
        self.brush_handler.set_mode(mode)
    
    def undo(self):
        """撤销上一步操作"""
        return self.brush_handler.undo()
    
    def clear_brush_strokes(self):
        """清除所有笔刷笔画"""
        self.brush_handler.clear_graphics()
        self.brush_handler.manager.clear_strokes()
        if self.brush_path:
            self.brush_handler.manager.save_to_file(self.brush_path)
    
    def render_brush_strokes(self):
        """渲染所有已有的笔刷笔画到场景"""
        self.brush_handler.render_all_strokes()
    
    def rotate_current_page(self, degrees=90):
        """旋转当前可见页面（顺时针）"""
        page_num = self.get_current_page()
        if page_num < 0 or page_num >= len(self.page_items):
            return
        
        # 获取当前页面的 pixmap item
        item = self.page_items[page_num]
        if not item:
            return
        
        # 获取当前 pixmap
        current_pixmap = item.pixmap()
        if current_pixmap.isNull():
            return
        
        # 创建旋转后的 pixmap
        from PyQt6.QtGui import QTransform
        transform = QTransform().rotate(degrees)
        rotated_pixmap = current_pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        
        # 更新显示
        item.setPixmap(rotated_pixmap)
        
        # 重新布局所有页面（解决间隙和居中问题）
        self._relayout_pages()
        
        # 更新并保存旋转状态
        current_rotation = self._page_rotations.get(page_num, 0)
        new_rotation = (current_rotation + degrees) % 360
        if new_rotation == 0:
            self._page_rotations.pop(page_num, None)  # 移除0度旋转
        else:
            self._page_rotations[page_num] = new_rotation
        self._save_rotation_state()
    
    def _load_rotation_state(self):
        """从文件加载旋转状态"""
        if not self._rotation_file or not os.path.exists(self._rotation_file):
            return
        try:
            import json
            with open(self._rotation_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # JSON 的 key 是字符串，需要转换为整数
                self._page_rotations = {int(k): v for k, v in data.items()}
        except Exception as e:
            print(f"Error loading rotation state: {e}")
            self._page_rotations = {}
    
    def _save_rotation_state(self):
        """保存旋转状态到文件"""
        if not self._rotation_file:
            return
        try:
            import json
            # 确保目录存在
            os.makedirs(os.path.dirname(self._rotation_file), exist_ok=True)
            with open(self._rotation_file, 'w', encoding='utf-8') as f:
                json.dump(self._page_rotations, f)
        except Exception as e:
            print(f"Error saving rotation state: {e}")
    
    def _apply_saved_rotations(self):
        """应用加载的旋转状态到页面"""
        if not self._page_rotations:
            return
        
        # 延迟应用，确保页面已经渲染完成
        def apply_rotations():
            from PyQt6.QtGui import QTransform
            for page_num, rotation in self._page_rotations.items():
                if page_num < len(self.page_items):
                    item = self.page_items[page_num]
                    if item and not item.pixmap().isNull():
                        transform = QTransform().rotate(rotation)
                        rotated = item.pixmap().transformed(transform, Qt.TransformationMode.SmoothTransformation)
                        item.setPixmap(rotated)
            
            # 重新布局
            self._relayout_pages()
        
        # 延迟 500ms 执行，等待页面渲染完成
        QTimer.singleShot(500, apply_rotations)

    def _relayout_pages(self):
        """重新计算页面布局（处理旋转后的尺寸变化，居中显示）"""
        if not self.page_items:
            return
            
        y = 0
        max_width = 0
        
        # 1. 找出最大宽度
        for item in self.page_items:
            rect = item.boundingRect()
            max_width = max(max_width, rect.width())
            
        # 2. 重新设置位置
        self._page_y_positions = []
        for item in self.page_items:
            rect = item.boundingRect()
            
            # 计算居中 X 坐标 (相对于最宽的页面)
            x = (max_width - rect.width()) / 2
            
            item.setPos(x, y)
            
            self._page_y_positions.append(y)
            y += rect.height() + self._page_padding
            
        # 3. 更新场景边界
        self.scene_obj.setSceneRect(self.scene_obj.itemsBoundingRect())

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
        side_layout = QVBoxLayout(self.side_container)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Removed inner header/toggle button
        
        self.thumbnails = PDFThumbnailWidget()
        self.thumbnails.pageSelected.connect(self.scroll_to_page)
        side_layout.addWidget(self.thumbnails, 1)  # stretch=1，占满剩余空间
        
        self.splitter.addWidget(self.side_container)
        
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
        
        # Initial Hide
        self.side_container.hide() # Directly hide container
        self.sidebar_btn.hide() # Hidden until doc loaded? Or always show? 
        # Actually user wants it visible to toggle. But logically only when PDF is active.
        # Let's keep it visible but maybe disabled if no PDF.
        # But for now, just hide it initially like before, and show in _update_sidebar

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

    def _init_logo_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #e8f7f7;")
        layout = QVBoxLayout(page)
        lbl = QLabel("InsightPaper")
        lbl.setStyleSheet("color: #999; font-size: 24px; font-weight: bold;")
        
        # 尝试加载图片 LOGO - 支持打包后的环境
        # 对于打包的资源文件，使用 _MEIPASS（onefile 模式下的临时解压目录）
        if getattr(sys, 'frozen', False):
            # PyInstaller onefile 模式下，资源文件在 _MEIPASS 目录
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
            if self.side_container.width() < 50: # Avoid starting too small
                 # Only if splitter allows setting size, usually better to let layout handle or set minimum
                 pass

    def load_pdf(self, path, scroll_to_page=None, cache_dir=None, brush_path=None, rotation_path=None):
        if os.path.exists(path) or (cache_dir and os.path.exists(cache_dir)):
            self.viewer.load_pdf(path, scroll_to_page=scroll_to_page, cache_dir=cache_dir, brush_path=brush_path, rotation_path=rotation_path)
            self.stack.setCurrentIndex(1)
            self._update_sidebar(self.viewer.doc)
        else:
            self.clear()

    def load_side_by_side(self, path1, path2, cache_dir1=None, cache_dir2=None, brush_path=None, brush_path2=None, rotation_path=None, rotation_path2=None, scroll_to_page=None):
        if (os.path.exists(path1) or cache_dir1) and (os.path.exists(path2) or cache_dir2):
            self.left_view.load_pdf(path1, cache_dir=cache_dir1, brush_path=brush_path, rotation_path=rotation_path)
            self.right_view.load_pdf(path2, cache_dir=cache_dir2, brush_path=brush_path2, rotation_path=rotation_path2)
            self.stack.setCurrentIndex(2)
            self._update_sidebar(self.left_view.doc)
            
            if scroll_to_page is not None:
                QTimer.singleShot(100, lambda: self.scroll_to_page(scroll_to_page))
        else:
            self.load_pdf(path1, cache_dir=cache_dir1, brush_path=brush_path, rotation_path=rotation_path, scroll_to_page=scroll_to_page)

    def _update_sidebar(self, doc):
        self.thumbnails.set_doc(doc if HAS_FITZ else None)
        has_doc = doc is not None
        self.sidebar_btn.setVisible(has_doc)
        
        # Reset to collapsed
        self.expanded = True 
        self._toggle_sidebar() # This effectively hides it if expanded was True, or shows if False. 
        # Actually logic in _toggle_sidebar is: isVisible -> hide.
        # We want default startup state often collapsed?
        # Let's force hide initially upon load ?
        if self.side_container.isVisible():
             self.side_container.hide()
             self.expanded = False

    def close_file(self, path):
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
    def scroll_to_page(self, p): 
        idx = self.stack.currentIndex()
        if idx == 1: self.viewer.scroll_to_page(p)
        elif idx == 2: 
            self.left_view.scroll_to_page(p)
            self.right_view.scroll_to_page(p)

    def _active_view(self):
        return self.left_view if self.stack.currentIndex() == 2 else self.viewer

    # === 笔刷模式代理方法 ===
    def set_brush_enabled(self, enabled):
        """启用/禁用笔刷模式（所有视图）"""
        idx = self.stack.currentIndex()
        if idx == 1:
            # 单视图模式
            self.viewer.set_brush_enabled(enabled)
        elif idx == 2:
            # 双视图模式 - 两边同时启用，并链接同步
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
            # 单视图模式
            self.viewer.rotate_current_page()
        elif idx == 2:
            # 双视图模式 - 两边同步旋转
            self.left_view.rotate_current_page()
            self.right_view.rotate_current_page()