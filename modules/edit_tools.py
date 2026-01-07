"""
编辑工具模块 - 用于PDF高亮标注
支持在原文和翻译版之间同步高亮
"""

import json
import os
import uuid
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QPen, QColor, QPainterPath, QPixmap, QPainter, QBrush, QCursor, QPolygonF, QPainterPathStroker
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QRectF, QPointF
from qfluentwidgets import RoundMenu, Action, MenuAnimationType, InfoBar, InfoBarPosition, FluentIcon as FIF

class BrushStroke:
    """单个笔刷笔画数据"""
    def __init__(self, points=None, color=None, width=20, page_num=0, stroke_id=None, path_data=None):
        self.points = points or []  # [(x, y), ...]  (仅用于初始绘制)
        self.color = color or QColor(255, 255, 0, 100)  # 默认黄色半透明
        self.width = width
        self.page_num = page_num
        self.id = stroke_id or str(uuid.uuid4())
        # path_data: list of list of points [[(x,y),...], ...] specifically for complex shapes after erasing
        self.path_data = path_data 
    
    def to_dict(self):
        return {
            'id': self.id,
            'points': self.points,
            'path_data': self.path_data,
            'color': [self.color.red(), self.color.green(), self.color.blue(), self.color.alpha()],
            'width': self.width,
            'page_num': self.page_num
        }
    
    @classmethod
    def from_dict(cls, data):
        stroke = cls()
        stroke.id = data.get('id', str(uuid.uuid4()))
        stroke.points = data.get('points', [])
        stroke.path_data = data.get('path_data', None)
        c = data.get('color', [255, 255, 0, 100])
        stroke.color = QColor(c[0], c[1], c[2], c[3])
        stroke.width = data.get('width', 20)
        stroke.page_num = data.get('page_num', 0)
        return stroke
    
    def copy(self):
        """Create a deep copy"""
        new_s = BrushStroke(
             points=[p for p in self.points],
             color=QColor(self.color),
             width=self.width,
             page_num=self.page_num,
             stroke_id=self.id,
             path_data=[ [pt for pt in poly] for poly in self.path_data ] if self.path_data else None
        )
        return new_s


class BrushManager(QObject):
    """
    笔刷管理器 - 管理笔刷数据
    支持撤销(Undo)操作，支持部分擦除(modify)
    """
    strokeAdded = pyqtSignal(BrushStroke)
    strokeRemoved = pyqtSignal(str) # stroke_id
    strokeModified = pyqtSignal(BrushStroke) # Modified stroke

    def __init__(self):
        super().__init__()
        self.enabled = False
        self.mode = 'draw' # 'draw' or 'erase'
        self.brush_color = QColor(255, 255, 0, 100)  # 黄色高亮
        self.brush_width = 25
        self.strokes = []  # 所有笔画
        self.current_stroke = None
        self.is_drawing = False
        
        # 撤销栈 [ {'type': 'add'|'remove'|'modify', 'stroke': BrushStroke, 'old_stroke': BrushStroke}, ... ]
        self.undo_stack = []

    def set_enabled(self, enabled):
        self.enabled = enabled
        
    def set_mode(self, mode):
        self.mode = mode
    
    def start_stroke(self, pos, page_num=0):
        if not self.enabled or self.mode != 'draw':
            return
        self.is_drawing = True
        self.current_stroke = BrushStroke(
            points=[(pos.x(), pos.y())],
            color=QColor(self.brush_color),
            width=self.brush_width,
            page_num=page_num
        )
    
    def add_point(self, pos):
        if self.is_drawing and self.current_stroke:
            self.current_stroke.points.append((pos.x(), pos.y()))
    
    def end_stroke(self):
        if self.is_drawing and self.current_stroke and len(self.current_stroke.points) > 1:
            completed_stroke = self.current_stroke
            self.add_stroke(completed_stroke, is_new_action=True)
            
            self.is_drawing = False
            self.current_stroke = None
            return completed_stroke
            
        self.is_drawing = False
        self.current_stroke = None
        return None
    
    def add_stroke(self, stroke, is_new_action=False):
        """添加笔画"""
        self.strokes.append(stroke)
        if is_new_action:
             pass # self.undo_stack.append({'type': 'add', 'stroke': stroke})
        self.strokeAdded.emit(stroke)
        return stroke
        
    def remove_stroke(self, stroke_id, is_new_action=False):
        """移除笔画"""
        for s in self.strokes:
            if s.id == stroke_id:
                self.strokes.remove(s)
                # if is_new_action:
                #     pass # self.undo_stack.append({'type': 'remove', 'stroke': s})
                self.strokeRemoved.emit(s.id)
                return True
        return False

    def modify_stroke(self, stroke_id, new_path_polygons, old_stroke_copy=None):
        """修改笔画 (用于擦除后的形状更新)"""
        for s in self.strokes:
            if s.id == stroke_id:
                if old_stroke_copy is None:
                    old_stroke_copy = s.copy() # Backup if not provided
                
                # Update data
                s.path_data = new_path_polygons
                # Points are now invalid representation for this complex shape
                s.points = [] 
                
                # self.undo_stack.append({
                #    'type': 'modify',
                #    'stroke': s,           # The object itself (current state)
                #    'old_stroke': old_stroke_copy # The state before modification
                # })
                self.strokeModified.emit(s)
                return True
        return False

    def add_stroke_from_sync(self, stroke):
        new_stroke = BrushStroke(
            points=stroke.points.copy(),
            color=QColor(stroke.color),
            width=stroke.width,
            page_num=stroke.page_num,
            stroke_id=stroke.id,
            path_data=[ [pt for pt in poly] for poly in stroke.path_data ] if stroke.path_data else None
        )
        self.strokes.append(new_stroke)
        self.strokeAdded.emit(new_stroke)
        return new_stroke
    
    def clear_strokes(self):
        self.strokes.clear()
        # self.undo_stack.clear()

    def undo(self):
        """执行撤销操作"""
        return False
        # if not self.undo_stack:
        #     return False
            
        # action = self.undo_stack.pop()
        # action_type = action['type']
        
        # if action_type == 'add':
        #     # Reverse: Remove
        #     stroke = action['stroke']
        #     self.remove_stroke(stroke.id, is_new_action=False)
            
        # elif action_type == 'remove':
        #     # Reverse: Add
        #     stroke = action['stroke']
        #     self.add_stroke(stroke, is_new_action=False)
            
        # elif action_type == 'modify':
        #     # Reverse: Restore old state
        #     current_stroke = action['stroke']
        #     old_snapshot = action['old_stroke']
            
        #     # Find the object in list
        #     # Restore attributes
        #     current_stroke.points = old_snapshot.points
        #     current_stroke.path_data = old_snapshot.path_data
            
        #     # Signal update to re-render
        #     self.strokeModified.emit(current_stroke)
            
        # elif action_type == 'batch_modify':
        #     # Reverse batch modifications
        #     for sub_action in action['actions']:
        #         current_stroke = sub_action['stroke']
        #         old_snapshot = sub_action['old_stroke']
                
        #         current_stroke.points = old_snapshot.points
        #         current_stroke.path_data = old_snapshot.path_data
        #         self.strokeModified.emit(current_stroke)
            
        # return True

    def save_to_file(self, file_path):
        data = {'strokes': [s.to_dict() for s in self.strokes]}
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"保存笔刷失败: {e}")
            return False
    
    def load_from_file(self, file_path):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.strokes = [BrushStroke.from_dict(s) for s in data.get('strokes', [])]
                return True
        except Exception as e:
            print(f"加载笔刷失败: {e}")
        return False


class BrushGraphicsItem(QGraphicsPathItem):
    """笔刷图形项"""
    def __init__(self, stroke: BrushStroke, parent=None):
        super().__init__(parent)
        self.stroke = stroke
        self._build_path()
        self.setAcceptHoverEvents(False)
    
    def _build_path(self):
        path = QPainterPath()
        
        # Priority: path_data (complex shape) > points (simple stroke)
        if self.stroke.path_data:
            # Reconstruct path from polygons
            for poly_points in self.stroke.path_data:
                if not poly_points: continue
                polygon = QPolygonF([QPointF(pt[0], pt[1]) for pt in poly_points])
                path.addPolygon(polygon)
            
            self.setPath(path)
            # Shapes have no "stroke width" themselves, they are filled areas
            self.setPen(QPen(Qt.PenStyle.NoPen))
            self.setBrush(QBrush(self.stroke.color))
            
        elif len(self.stroke.points) > 1:
            # Standard stroke
            p0 = self.stroke.points[0]
            path.moveTo(p0[0], p0[1])
            for p in self.stroke.points[1:]:
                path.lineTo(p[0], p[1])
            
            self.setPath(path)
            pen = QPen(self.stroke.color)
            pen.setWidth(self.stroke.width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self.setPen(pen)
            self.setBrush(Qt.GlobalColor.transparent) # Or Qt.NoBrush which is just 0

            self.setPen(pen)
            self.setBrush(Qt.GlobalColor.transparent)
            
        self.setOpacity(0.5)


class PdfBrushHandler:
    """
    具体的笔刷交互处理器
    """
    def __init__(self, view: QGraphicsView, scene):
        self.view = view
        self.scene = scene
        self.manager = BrushManager()
        self.brush_path = None
        self._graphics_items = {} # Map ID to Item
        self._current_item = None
        
        # Tracking modifications during erasure
        self._erased_snapshots = {} # stroke_id -> old_stroke_copy
        self._modified_items = set() # Items currently being erased
        
        # Connect Manager Signals
        self.manager.strokeAdded.connect(self._on_stroke_added)
        self.manager.strokeRemoved.connect(self._on_stroke_removed)
        self.manager.strokeModified.connect(self._on_stroke_modified)
    
    def set_brush_path(self, path):
        self.brush_path = path
        
    def load_strokes(self):
        self.clear_graphics()
        self.manager.clear_strokes()
        if self.brush_path and os.path.exists(self.brush_path):
            if self.manager.load_from_file(self.brush_path):
                self.render_all_strokes()

    def set_enabled(self, enabled):
        self.manager.set_enabled(enabled)
        self._update_cursor()
    
    def set_mode(self, mode):
        """mode: 'draw' or 'erase'"""
        self.manager.set_mode(mode)
        self._update_cursor()
        
    def _update_cursor(self):
        if not self.manager.enabled:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
            return

        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        if self.manager.mode == 'draw':
            self._set_circle_cursor(color=self.manager.brush_color, width=self.manager.brush_width)
        elif self.manager.mode == 'erase':
            # Eraser cursor: Grey #888888, no X, simple circle
            self._set_circle_cursor(color=QColor(128, 128, 128), width=self.manager.brush_width, is_eraser=True)

    def _set_circle_cursor(self, color, width, is_eraser=False):
        dpr = self.view.viewport().devicePixelRatio() if self.view else 1.0
        brush_w = max(10, width)
        size = int(brush_w * dpr)
        
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        c = QColor(color)
        c.setAlpha(150)
        
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        
        # Center circle
        painter.drawEllipse(1, 1, brush_w-2, brush_w-2)
        
        # User requested NO X inside the circle for eraser
        
        painter.end()
        self.view.setCursor(QCursor(pixmap))

    def handle_wheel_event(self, e):
        """处理滚轮事件：按住 Ctrl 或 Alt 调整笔刷大小"""
        if not self.manager.enabled: return False
        
        if e.modifiers() == Qt.KeyboardModifier.AltModifier:
            delta = e.angleDelta().y()
            step = 5
            if delta > 0:
                self.manager.brush_width += step
            else:
                self.manager.brush_width = max(5, self.manager.brush_width - step)
            
            self._update_cursor_and_drag()
            return True
        return False

    def handle_mouse_press(self, e, page_num, scene_pos):
        if not self.manager.enabled: return False
        if e.button() != Qt.MouseButton.LeftButton: return False
        
        if self.manager.mode == 'draw':
            self.manager.start_stroke(scene_pos, page_num)
            # Temporary local item for immediate feedback
            if self.manager.current_stroke:
                self._current_item = BrushGraphicsItem(self.manager.current_stroke)
                self.scene.addItem(self._current_item)
        elif self.manager.mode == 'erase':
            # Start erasing session
            self._erased_snapshots.clear()
            self._modified_items.clear()
            self._last_erase_pos = scene_pos
            self._erase_at(scene_pos)
            
        return True

    def handle_mouse_move(self, e, scene_pos):
        if not self.manager.enabled: return False

        if self.manager.mode == 'draw':
            if not self.manager.is_drawing: return False
            self.manager.add_point(scene_pos)
            if self._current_item:
                self._current_item._build_path()
        elif self.manager.mode == 'erase':
            if e.buttons() & Qt.MouseButton.LeftButton:
                self._erase_at(scene_pos, self._last_erase_pos)
                self._last_erase_pos = scene_pos
        return True

    def handle_mouse_release(self, e):
        if not self.manager.enabled: return False
        
        if self.manager.mode == 'draw':
            if not self.manager.is_drawing: return False
            stroke = self.manager.end_stroke()
            if self._current_item:
                self.scene.removeItem(self._current_item)
                self._current_item = None
            if stroke and self.brush_path:
                self.manager.save_to_file(self.brush_path)
        
        elif self.manager.mode == 'erase':
             if e.button() == Qt.MouseButton.LeftButton:
                 # Commit modifications
                 for item in self._modified_items:
                     # Convert path to polygons for serializable storage
                     new_path = item.path()
                     # toFillPolygons returns list[QPolygonF]
                     polys = new_path.toFillPolygons()
                     poly_data = []
                     for poly in polys:
                         # Convert QPolygonF to list of points
                         pts = []
                         for i in range(poly.count()):
                             pt = poly.at(i)
                             pts.append((pt.x(), pt.y()))
                         if pts:
                             poly_data.append(pts)
                     
                     original = self._erased_snapshots.get(item.stroke.id)
                     self.manager.modify_stroke(item.stroke.id, poly_data, original)
                 
                 if self._modified_items and self.brush_path:
                     self.manager.save_to_file(self.brush_path)
                 
                 self._erased_snapshots.clear()
                 self._modified_items.clear()

        return True

    def _erase_at(self, scene_pos, last_pos=None):
        """Pixel-level erase using path subtraction with interpolation"""
        w = self.manager.brush_width
        eraser_path = QPainterPath()
        
        if last_pos and last_pos != scene_pos:
            # Create a capsule shape from last_pos to scene_pos
            path_line = QPainterPath()
            path_line.moveTo(last_pos)
            path_line.lineTo(scene_pos)
            
            stroker = QPainterPathStroker()
            stroker.setWidth(w)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            eraser_path = stroker.createStroke(path_line)
        else:
            # Just a circle at current pos
            eraser_path.addEllipse(scene_pos, w/2, w/2)
            
        # Optimize eraser path
        eraser_path = eraser_path.simplified()
        
        # Determine bounding rect for improved query performance
        selection_rect = eraser_path.boundingRect()
        items = self.scene.items(selection_rect)
        
        for item in items:
            try:
                # Check for validity
                if not isinstance(item, BrushGraphicsItem) or not item.stroke or not item.scene():
                    continue

                # Optimization: Check if item actually strictly intersects with our eraser shape
                if not item.path().intersects(eraser_path):
                    continue

                # If this item hasn't been touched in this drag session yet, snapshot it
                if item.stroke.id not in self._erased_snapshots:
                    self._erased_snapshots[item.stroke.id] = item.stroke.copy()
                    
                    # Convert simple stroke to path shape if it's the first time being erased
                    if not item.stroke.path_data:
                        if not item.path().isEmpty():
                             stroker = QPainterPathStroker()
                             stroker.setWidth(item.stroke.width)
                             stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                             stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                             # simplified() ensures the path is a clean planar graph 
                             # prevents winding issues where holes might appear filled
                             fill_path = stroker.createStroke(item.path()).simplified()
                             
                             item.setPath(fill_path)
                             item.setPen(QPen(Qt.PenStyle.NoPen))
                             item.setBrush(QBrush(item.stroke.color))
                
                # Perform subtraction
                current_path = item.path()
                new_path = current_path.subtracted(eraser_path)
                
                if new_path != current_path:
                    item.setPath(new_path)
                    self._modified_items.add(item)
            except RuntimeError:
                continue
    
    def increase_width(self):
        """Increase brush width by 1"""
        self.manager.brush_width = min(50, self.manager.brush_width + 1)
        self._update_cursor()
        
    def decrease_width(self):
        """Decrease brush width by 1"""
        self.manager.brush_width = max(1, self.manager.brush_width - 1)
        self._update_cursor()

    def handle_key_event(self, event, is_press):
        """Handle key events for tool switching (Shift for temporary eraser)"""
        if event.key() == Qt.Key.Key_Shift and self.manager.enabled:
            target_mode = 'erase' if is_press else 'draw'
            # Only switch if we are in the opposite mode (drawing -> eraser on press, eraser -> drawing on release)
            if (is_press and self.manager.mode == 'draw') or (not is_press and self.manager.mode == 'erase'):
                self.manager.set_mode(target_mode)
                self._update_cursor()

    def _on_stroke_added(self, stroke):
        item = BrushGraphicsItem(stroke)
        self.scene.addItem(item)
        self._graphics_items[stroke.id] = item

    def _on_stroke_removed(self, stroke_id):
        if stroke_id in self._graphics_items:
            item = self._graphics_items[stroke_id]
            if item.scene():
                self.scene.removeItem(item)
            del self._graphics_items[stroke_id]

    def _on_stroke_modified(self, stroke):
        """Redraw modified stroke completely"""
        if stroke.id in self._graphics_items:
            item = self._graphics_items[stroke.id]
            if item.scene():
                self.scene.removeItem(item)
        
        new_item = BrushGraphicsItem(stroke)
        self.scene.addItem(new_item)
        self._graphics_items[stroke.id] = new_item

    def render_all_strokes(self):
        for id, item in list(self._graphics_items.items()):
            if item.scene(): self.scene.removeItem(item)
        self._graphics_items.clear()
        
        for s in self.manager.strokes:
            self._on_stroke_added(s)

    def clear_graphics(self):
        for item in list(self._graphics_items.values()):
            try:
                # 检查 C++ 对象是否仍然存在
                if not item or not item.scene():
                    continue
                self.scene.removeItem(item)
            except RuntimeError:
                # Ignored wrapped C/C++ object deleted
                pass
        self._graphics_items.clear()
        
    def undo(self):
        success = self.manager.undo()
        if success and self.brush_path:
            self.manager.save_to_file(self.brush_path)
        return success


class EditToolsManager:
    """主要用于菜单和全局控制"""
    def __init__(self, main_window):
        self.main_window = main_window
    
    def show_edit_menu(self):
        menu = RoundMenu(parent=self.main_window)
        pdf_viewer = self.main_window.pdf_viewer
        
        is_enabled = pdf_viewer.is_brush_enabled()
        
        # Highlight
        highlight_action = Action(FIF.PENCIL_INK, "高亮画笔")
        highlight_action.setCheckable(True)
        highlight_action.setChecked(is_enabled and pdf_viewer.get_brush_mode() == 'draw')
        highlight_action.triggered.connect(lambda: self.set_tool('draw'))
        menu.addAction(highlight_action)
        
        # Eraser
        eraser_action = Action(FIF.DELETE, "橡皮擦")
        eraser_action.setCheckable(True)
        eraser_action.setChecked(is_enabled and pdf_viewer.get_brush_mode() == 'erase')
        eraser_action.triggered.connect(lambda: self.set_tool('erase'))
        menu.addAction(eraser_action)
        
        menu.exec(QCursor.pos(), aniType=MenuAnimationType.DROP_DOWN)
    
    def set_tool(self, mode):
        # self.main_window.right_content_stack.setCurrentIndex(0) # Deprecated
        pdf_viewer = self.main_window.pdf_viewer
        pdf_viewer.set_brush_enabled(True)
        pdf_viewer.set_brush_mode(mode)
        
        msg = '已切换到高亮画笔' if mode == 'draw' else '已切换到橡皮擦'
        InfoBar.success(
            title=msg,
            content='按住鼠标左键进行操作',
            parent=self.main_window,
            position=InfoBarPosition.TOP,
            duration=2000
        )
        
    def toggle_brush_mode(self):
        # Default toggle to Brush (B)
        pdf_viewer = self.main_window.pdf_viewer
        if pdf_viewer.is_brush_enabled() and pdf_viewer.get_brush_mode() == 'draw':
             self.close_edit_mode()
        else:
             self.set_tool('draw')
             
    def toggle_eraser_mode(self):
        # Ctrl+B specific handler: Switch to Eraser
        pdf_viewer = self.main_window.pdf_viewer
        
        # Always switch to Eraser if not already in Eraser mode
        current_mode = pdf_viewer.get_brush_mode()
        is_enabled = pdf_viewer.is_brush_enabled()
        
        if not is_enabled or current_mode != 'erase':
            self.set_tool('erase')
        # If already eraser, maybe toggle back to draw? 
        # User said "calls need ... will switch to eraser", imply one way usually, 
        # but standard toggles are nice. 
        # "不需要退出编辑的模式" -> Just switch tool.
        
    def close_edit_mode(self):
        pdf_viewer = self.main_window.pdf_viewer
        pdf_viewer.set_brush_enabled(False)
        InfoBar.info(
            title='编辑模式已关闭',
            content='恢复正常浏览模式',
            parent=self.main_window,
            position=InfoBarPosition.TOP,
            duration=2000
        )
