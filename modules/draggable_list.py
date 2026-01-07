import os
import sys
import shutil
from PyQt6.QtWidgets import QAbstractItemView, QLabel
from PyQt6.QtGui import QDrag, QPixmap, QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtCore import Qt, QMimeData, QUrl, QSize
from qfluentwidgets import ListWidget, MessageBox, InfoBar, InfoBarPosition

class DraggableListWidget(ListWidget):
    """支持拖放的列表组件"""
    def __init__(self, topic_manager, parent=None):
        super().__init__(parent)
        self.topic_manager = topic_manager
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        # 允许外部拖放，但我们要小心处理内部移动
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        
        # 高亮相关
        self._highlight_item = None
        self._drag_source_item = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            # 记录拖拽源
            self._drag_source_item = self.currentItem()
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragMoveEvent(event)
        
        # 更新高亮效果
        target_item = self.itemAt(event.position().toPoint())
        self._update_highlight(target_item)

    def dragLeaveEvent(self, event):
        """拖拽离开时清除高亮"""
        self._clear_highlight()
        super().dragLeaveEvent(event)
    
    def _update_highlight(self, target_item):
        """更新目标项高亮"""
        # 清除旧高亮
        if self._highlight_item and self._highlight_item != target_item:
            self._clear_item_highlight(self._highlight_item)
        
        # 设置新高亮
        if target_item and target_item != self._drag_source_item:
            data = target_item.data(Qt.ItemDataRole.UserRole)
            if data and data.get('type') in ['topic', 'group']:
                # 主题/组：高亮为蓝色背景
                target_item.setBackground(QColor("#e3f2fd"))
                self._highlight_item = target_item
            elif data and data.get('type') == 'pdf':
                # PDF：高亮为浅色，表示会放到同级目录
                target_item.setBackground(QColor("#f5f5f5"))
                self._highlight_item = target_item
    
    def _clear_item_highlight(self, item):
        """清除单个项的高亮"""
        if item:
            item.setBackground(QColor(0, 0, 0, 0))  # 透明背景
    
    def _clear_highlight(self):
        """清除所有高亮"""
        if self._highlight_item:
            self._clear_item_highlight(self._highlight_item)
            self._highlight_item = None

    def dropEvent(self, event):
        # 清除高亮
        self._clear_highlight()
        
        # 判断是否为内部拖拽：
        # - 如果我们有记录的内部拖拽源项，则为内部拖拽
        # - 或者 event.source() 明确是 self
        is_internal_drag = (self._drag_source_item is not None) or (event.source() == self)
        
        # 1. External Files Drop (Check source to ensure it is NOT internal)
        if event.mimeData().hasUrls() and not is_internal_drag:
            urls = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    urls.append(url.toLocalFile())
            
            if not urls:
                event.ignore()
                return

            # 获取目标 item
            target_item = self.itemAt(event.position().toPoint())
            target_data = target_item.data(Qt.ItemDataRole.UserRole) if target_item else None
            
            # 特殊处理：如果拖拽单个 PDF 到另一个 PDF 上，视为导入翻译
            if len(urls) == 1 and target_data and target_data.get('type') == 'pdf':
                src_path = urls[0]
                if src_path.lower().endswith('.pdf') and os.path.exists(src_path):
                     # 构造临时的 source_data
                     source_data = {'type': 'pdf', 'path': src_path}
                     self._handle_translation_drop(source_data, target_data)
                     event.accept()
                     return

            if self.topic_manager.handle_external_drop(urls, target_data):
                event.accept()
            else:
                event.ignore()
            return

        # 2. Internal Move Drop
        # 获取拖拽源 item
        source_item = self.currentItem()
        if not source_item:
            event.ignore()
            return

        # 获取目标 item
        target_item = self.itemAt(event.position().toPoint())
        
        # 如果没有目标，或者是同一个 item，忽略
        if not target_item or target_item == source_item:
            event.ignore()
            return
            
        # 获取数据
        source_data = source_item.data(Qt.ItemDataRole.UserRole)
        target_data = target_item.data(Qt.ItemDataRole.UserRole)
        
        if not source_data or not target_data:
            event.ignore()
            return

        # 检查是否是 PDF 到 PDF 的拖拽（作为翻译版）
        if source_data.get('type') == 'pdf' and target_data.get('type') == 'pdf':
            # PDF 拖到 PDF 上：作为翻译版导入
            self._handle_translation_drop(source_data, target_data)
            self._drag_source_item = None
            event.accept()
            return
        
        # 调用管理器的移动逻辑
        if self.topic_manager.handle_drag_drop(source_data, target_data):
            event.accept()
            # 刷新显示
            self.topic_manager.refresh_list_display()
        else:
            event.ignore()
        
        # 清理内部拖拽源记录
        self._drag_source_item = None
    
    def _handle_translation_drop(self, source_data, target_data):
        """处理拖拽论文到另一个论文上作为翻译版"""
        try:
            source_path = source_data.get('path', '')
            target_path = target_data.get('path', '')
            
            if not source_path or not target_path:
                return
            
            # 检查源文件是否存在
            if not os.path.exists(source_path):
                print(f"Source file not found: {source_path}")
                return
            
            # 获取目标论文的分析目录
            main_window = self.topic_manager.main_window
            if not main_window:
                print("Main window not found")
                return
                
            # 支持打包后的环境
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            analysis_root = os.path.join(project_root, 'analysis')
            
            target_filename = os.path.basename(target_path)
            target_name_no_ext = os.path.splitext(target_filename)[0]
            target_analysis_dir = os.path.join(analysis_root, target_name_no_ext)
            translation_path = os.path.join(target_analysis_dir, 'Translation.pdf')
            
            source_filename = os.path.basename(source_path)
            
            # 检查是否已存在翻译版
            is_replace = os.path.exists(translation_path)
            
            title = '替换翻译版' if is_replace else '加载翻译版'
            if is_replace:
                 msg = '确认替换现有的翻译文件？'
            else:
                 msg = '确认加载该文件为翻译版？'
            
            # 使用 QTimer 延迟显示对话框，避免在拖放事件中直接显示
            from PyQt6.QtCore import QTimer
            
            def show_dialog():
                try:
                    w = MessageBox(title, msg, main_window)
                    w.yesButton.setText('确定')
                    w.cancelButton.setText('取消')
                    
                    if not w.exec():
                        return
                    
                    # 创建分析目录
                    os.makedirs(target_analysis_dir, exist_ok=True)
                    
                    # 复制文件作为翻译版
                    shutil.copy2(source_path, translation_path)
                    
                    # 刷新列表显示（显示绿点）
                    self.topic_manager.refresh_list_display()
                    
                    InfoBar.success(
                        title='操作成功' if is_replace else '导入成功',
                        content=f'已将 "{source_filename}" 设为翻译版',
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=2000,
                        parent=main_window
                    )
                except Exception as e:
                    print(f"Error in translation dialog: {e}")
                    InfoBar.error(
                        title='操作失败',
                        content=str(e),
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=main_window
                    )
            
            # 延迟 100ms 执行，确保拖放事件完成
            QTimer.singleShot(100, show_dialog)
            
        except Exception as e:
            print(f"Error in _handle_translation_drop: {e}")

    def startDrag(self, supportedActions):
        # 仅允许拖动 PDF 文件
        item = self.currentItem()
        if not item:
            return
            
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or data.get('type') != 'pdf':
            return
        
        # 记录拖拽源
        self._drag_source_item = item
            
        # Create Drag Object
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Set URLs for external drag (e.g. to Browser, Desktop)
        file_path = data['path']
        url = QUrl.fromLocalFile(file_path)
        mime_data.setUrls([url])
        
        drag.setMimeData(mime_data)
        
        # 创建拖动预览图像
        pixmap = self._create_drag_pixmap(item)
        if pixmap:
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        
        # Exec drag - 允许 Move 和 Copy，以便支持拖拽到外部应用或 Webview
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        
        # 拖拽结束后清理
        self._clear_highlight()
        self._drag_source_item = None
    
    def _create_drag_pixmap(self, item):
        """创建拖动时的预览图像"""
        import os
        
        # 获取文件名
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return None
        
        file_path = data.get('path', '')
        filename = os.path.basename(file_path)
        
        # 截断过长的文件名
        max_len = 35
        if len(filename) > max_len:
            filename = filename[:max_len-3] + '...'
        
        # 创建预览图像
        width = min(280, len(filename) * 7 + 24)
        height = 32
        
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(0, 0, 0, 0))  # 透明背景
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制米黄色圆角矩形背景 + 边框
        painter.setBrush(QBrush(QColor("#fffdf7")))  # 米黄色背景
        painter.setPen(QPen(QColor("#d0c8b8"), 1.5))  # 浅棕色边框
        painter.drawRoundedRect(1, 1, width - 2, height - 2, 5, 5)
        
        # 绘制文件名（深色文字）
        painter.setPen(QPen(QColor("#333333")))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(12, 21, filename)
        
        painter.end()
        
        return pixmap
