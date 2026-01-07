from PyQt6.QtWidgets import QGraphicsRectItem, QToolTip, QMenu, QGraphicsSimpleTextItem
from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPen, QBrush, QClipboard, QGuiApplication, QAction, QCursor
import fitz

class PDFTextSelector:
    """
    Handles text selection logic for the PDFGraphicsView.
    Uses 'Scheme 1': RubberBand selection -> Coordinate Mapping -> fitz text extraction.
    """
    def __init__(self, view):
        self.view = view
        self.start_pos = None
        self.selection_rect_item = None
        self.is_selecting = False
        self.extracted_text = ""
        
        # Visual styling for the selection box
        # Visual styling: Modern dashed line
        self.pen = QPen(QColor(0, 90, 158), 1.5, Qt.PenStyle.DashLine)
        self.brush = QBrush(QColor(0, 120, 215, 30))
        
        # Initialize the graphics item
        self._init_graphics_item()

    def _init_graphics_item(self):
        self.selection_rect_item = QGraphicsRectItem()
        self.selection_rect_item.setPen(self.pen)
        self.selection_rect_item.setBrush(self.brush)
        self.selection_rect_item.setZValue(999) # Ensure it's on top
        self.selection_rect_item.hide()
        
        # Info text item for character count
        self.info_text_item = QGraphicsSimpleTextItem()
        self.info_text_item.setBrush(QBrush(QColor("black"))) # Text color
        self.info_text_item.setZValue(1000) # Above rect
        self.info_text_item.hide()
        
        # Add to scene if scene exists, else wait
        if self.view.scene_obj:
            self.view.scene_obj.addItem(self.selection_rect_item)
            self.view.scene_obj.addItem(self.info_text_item)

    def start_selection(self, scene_pos):
        """Called on mouse press"""
        self.is_selecting = True
        self.start_pos = scene_pos
        self.extracted_text = ""
        
        # Ensure item is valid and in scene
        try:
            # Check if C++ object is still valid by accessing a property
            _ = self.selection_rect_item.scene()
        except RuntimeError:
            self._init_graphics_item()

        if self.selection_rect_item is None:
             self._init_graphics_item()
        
        # Check scene match and re-add if needed
        current_scene = self.view.scene_obj
        if self.selection_rect_item.scene() != current_scene:
            if self.selection_rect_item.scene():
                self.selection_rect_item.scene().removeItem(self.selection_rect_item)
            current_scene.addItem(self.selection_rect_item)
            
        if self.info_text_item.scene() != current_scene:
            if self.info_text_item.scene():
                self.info_text_item.scene().removeItem(self.info_text_item)
            current_scene.addItem(self.info_text_item)
            
        self.selection_rect_item.setRect(QRectF(scene_pos, scene_pos))
        self.selection_rect_item.show()
        
        # Show info item initially empty or 0
        self.info_text_item.setText("0 字")
        self.info_text_item.setPos(scene_pos.x() + 10, scene_pos.y() - 20)
        self.info_text_item.show()

    def update_selection(self, scene_pos):
        """Called on mouse move"""
        if not self.is_selecting or not self.start_pos:
            return
            
        rect = QRectF(self.start_pos, scene_pos).normalized()
        self.selection_rect_item.setRect(rect)
        
        # Update Info Text Position (follow top-right corner of selection)
        self.info_text_item.setPos(rect.topRight().x() + 5, rect.topRight().y() - 20)
        
        # Perform dynamic extraction to count characters
        self._extract_text_from_rect(rect)
        count = len(self.extracted_text)
        self.info_text_item.setText(f"{count} 字")

    def end_selection(self, scene_pos):
        """Called on mouse release"""
        if not self.is_selecting:
            return
            
        self.is_selecting = False
        final_rect = self.selection_rect_item.rect()
        self.selection_rect_item.hide()
        self.info_text_item.hide() # Hide info text
        
        # Perform final extraction
        self._extract_text_from_rect(final_rect)
        
        if self.extracted_text:
            self._copy_to_clipboard()

    def _extract_text_from_rect(self, scene_rect):
        """
        Maps the scene_rect to PDF page coordinates and extracts text using fitz.
        """
        # 安全检查文档是否可用（未关闭）
        if not self._is_doc_valid():
            print("[文本选择] 文档不可用或已关闭")
            return

        full_text = []
        
        # Iterate over all page items to see which ones intersect with the selection
        for i, item in enumerate(self.view.page_items):
            item_rect = item.sceneBoundingRect()
            
            # Check intersection
            if item_rect.intersects(scene_rect):
                # 1. Get the intersection rect in scene coords
                intersect_rect = item_rect.intersected(scene_rect)
                
                # 2. Map to item local coords (pixel coords on the rendered image)
                # item_rect.topLeft() is the scene pos of the page
                local_x = intersect_rect.x() - item_rect.x()
                local_y = intersect_rect.y() - item_rect.y()
                local_w = intersect_rect.width()
                local_h = intersect_rect.height()
                
                # 3. Map to PDF coords
                # The image was rendered with self.view.base_scale
                scale = self.view.base_scale
                pdf_rect = fitz.Rect(
                    local_x / scale,
                    local_y / scale,
                    (local_x + local_w) / scale,
                    (local_y + local_h) / scale
                )
                
                # 4. Extract text from the page
                try:
                    page = self.view.doc.load_page(i)
                    # "text" gives plain text, "blocks" gives structure. 
                    # "text" with clip is usually good enough for simple copy.
                    text = page.get_text("text", clip=pdf_rect, sort=True)
                    if text.strip():
                        full_text.append(text.strip())
                except Exception as e:
                    print(f"Extraction error on page {i}: {e}")

        self.extracted_text = "\n\n".join(full_text)
        
        # Don't trigger action automatically
        # if self.extracted_text:
        #    self._on_text_extracted()
    
    def _is_doc_valid(self):
        """安全检查文档是否有效且未关闭"""
        if not hasattr(self.view, 'doc') or self.view.doc is None:
            return False
        
        try:
            # 尝试访问文档的简单属性来检查是否已关闭
            _ = self.view.doc.is_closed
            return not self.view.doc.is_closed
        except (AttributeError, ValueError, RuntimeError):
            # 如果文档已关闭或无效，返回 False
            return False

    def _on_text_extracted(self):
        """Handle the extracted text (Menu or Clipboard)"""
        if not self.extracted_text:
            return
            
        from qfluentwidgets import RoundMenu, Action, MenuAnimationType, FluentIcon as FIF
        
        # Show a fluent menu at cursor position
        menu = RoundMenu(parent=self.view)
        
        # Info Action
        count = len(self.extracted_text)
        info_action = Action(FIF.ALBUM, f"选中 {count} 个字符")
        info_action.setEnabled(False)
        menu.addAction(info_action)
        
        # Translate Action
        translate_action = Action(FIF.CHAT, "翻译 (Doubao)")
        translate_action.triggered.connect(self._request_translation)
        menu.addAction(translate_action)
        
        menu.addSeparator()
        
        # Copy Action
        copy_action = Action(FIF.COPY, "复制文本")
        copy_action.triggered.connect(self._copy_to_clipboard)
        menu.addAction(copy_action)
        
        menu.exec(QCursor.pos(), aniType=MenuAnimationType.DROP_DOWN)

    def _copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.extracted_text)
        
        # Show Fluent Success InfoBar/StateToolTip
        from qfluentwidgets import InfoBar, InfoBarPosition
        
        # We need a widget to anchor the InfoBar to. The view or its window.
        # InfoBar needs a parent widget.
        parent_widget = self.view.window() 
        
        InfoBar.success(
            title='复制成功',
            content='文本已复制到剪贴板',
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
            parent=parent_widget
        )

    def _request_translation(self):
        """Emit signal to request translation"""
        if self.extracted_text and hasattr(self.view, 'translationRequested'):
            self.view.translationRequested.emit(self.extracted_text)
