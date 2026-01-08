from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt

class ShortcutManager:
    """
    Centralized Shortcut Manager
    Handles all application-wide shortcuts.
    """
    def __init__(self, main_window):
        self.main_window = main_window
        self.shortcuts = [] # Keep references
        self.init_shortcuts()
        
    def init_shortcuts(self):
        # --- Zoom Controls ---
        # Zoom In (Ctrl + + / Ctrl + =)
        self.add_shortcut(QKeySequence.StandardKey.ZoomIn, self.zoom_in)
        self.add_shortcut("Ctrl+=", self.zoom_in) 
        
        # Zoom Out (Ctrl + -)
        self.add_shortcut(QKeySequence.StandardKey.ZoomOut, self.zoom_out)
        self.add_shortcut("Ctrl+-", self.zoom_out)

        # --- File Operations ---
        # Open Folder (Ctrl + O)
        # self.add_shortcut("Ctrl+O", self.open_folder)
        
        # --- Edit Tools ---
        # Toggle Brush/Highlight Mode (B)
        self.add_shortcut("B", self.toggle_brush_mode)
        
        # Switch to Eraser (Shift+B)
        self.add_shortcut("Shift+B", self.toggle_eraser_mode)


    def add_shortcut(self, key, slot):
        """Helper to safely add a shortcut"""
        if isinstance(key, str):
            seq = QKeySequence(key)
        else:
            seq = key
            
        shortcut = QShortcut(seq, self.main_window)
        # Context: ApplicationShortcut might be safer if focus issues arise, 
        # but WindowShortcut (default) is usually fine for MainWindow.
        # shortcut.setContext(Qt.ShortcutContext.WindowShortcut) 
        shortcut.activated.connect(slot)
        self.shortcuts.append(shortcut)

    # --- Actions ---

    def zoom_in(self):
        if hasattr(self.main_window, 'pdf_viewer'):
            self.main_window.pdf_viewer.zoom_in()

    def zoom_out(self):
        if hasattr(self.main_window, 'pdf_viewer'):
            self.main_window.pdf_viewer.zoom_out()
            
    # def open_folder(self):
    #     if hasattr(self.main_window, 'open_folder_dialog'):
    #         self.main_window.open_folder_dialog()
            
    def import_pdf(self):
        if hasattr(self.main_window, 'show_import_menu'):
            self.main_window.show_import_menu()
    
    def toggle_brush_mode(self):
        """切换高亮标记模式（快捷键 B）"""
        if hasattr(self.main_window, 'edit_tools_manager'):
            self.main_window.edit_tools_manager.toggle_brush_mode()
            
    def toggle_eraser_mode(self):
        """切换到橡皮擦模式 (快捷键 Shift+B)"""
        if hasattr(self.main_window, 'edit_tools_manager'):
            self.main_window.edit_tools_manager.toggle_eraser_mode()

    # def undo(self):
    #     """撤销操作 (Ctrl+Z)"""
    #     if hasattr(self.main_window, 'undo_edit'):
    #         self.main_window.undo_edit()
