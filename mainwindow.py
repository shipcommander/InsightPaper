import os
import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QFileDialog, QSplitter, QFrame, QStatusBar, 
                             QListWidgetItem, QAbstractItemView, QLineEdit, QSizePolicy)
from PyQt6.QtCore import Qt, QUrl, QSize, QFileInfo
from PyQt6.QtGui import QIcon, QDesktopServices, QColor, QCursor
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QSplitter, QFrame, QStatusBar, QListWidgetItem, QAbstractItemView, QLineEdit, QSizePolicy, QMenu



# --- Fluent Widgets ---
from qfluentwidgets import (FluentWindow, SubtitleLabel, BodyLabel, StrongBodyLabel,
                            PushButton, PrimaryPushButton, ListWidget, 
                            setTheme, Theme, FluentIcon as FIF, 
                            SimpleCardWidget, NavigationItemPosition, 
                            TextEdit, LineEdit, InfoBar, InfoBarPosition, MessageBox,
                            RoundMenu, Action, SegmentedWidget, TransparentToolButton, MenuAnimationType) # Added RoundMenu, Action, SegmentedWidget, TransparentToolButton

# --- 自定义模块 ---
from modules.topic_manager import TopicManager
from modules.shortcut_manager import ShortcutManager
from modules.ai_assistant import AIWebViewer # Corrected from AIWebViewerManager to AIWebViewer

from PyQt6.QtWidgets import QStackedWidget, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import Qt, QUrl
from modules.pdf_widgets import PDFViewerWidget
from modules.draggable_list import DraggableListWidget
from modules.help_dialog import HelpDialog
from modules.edit_tools import EditToolsManager

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.init_window_settings()
        self.init_data_variables()
        self.init_ui()
        
        # 自动加载 data 文件夹
        self._auto_load_default_folder()

    def _auto_load_default_folder(self):
        if getattr(sys, 'frozen', False):
            root_dir = os.path.dirname(sys.executable)
        else:
            root_dir = os.path.dirname(os.path.abspath(__file__))
            
        data_dir = os.path.join(root_dir, 'data')
        # 如果 data 文件夹不存在，自动创建
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
            except Exception as e:
                print(f"Failed to create data folder: {e}")
        
        # 加载 data 文件夹
        if os.path.isdir(data_dir):
            self.load_folder(data_dir)

    def init_window_settings(self):
        setTheme(Theme.LIGHT)
        self.setWindowTitle("InsightPaper")
        self.resize(1400, 850)
        self.windowEffect.setMicaEffect(self.winId())
        
        # Set Window Icon - 支持打包后的环境
        # 对于打包的资源文件，使用 _MEIPASS（onefile 模式下的临时解压目录）
        if getattr(sys, 'frozen', False):
            root_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            root_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(root_dir, 'Icons', 'LOGO.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 样式表优化
        self.setStyleSheet("""
            FluentWindow, QWidget#mainWorkspace { background-color: #f7f3ea; }
            SimpleCardWidget { background-color: #fffdf7; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; }
            QListWidget { background-color: rgba(255,255,255,0.95); border: 1px solid rgba(0,0,0,0.05); border-radius: 6px; }
        """)

    def init_data_variables(self):
        self.current_folder = ""
        self.pdf_files = [] # 存储 (filename, full_path)
        self.current_pdf_path = None
        
        # 使用TopicManager管理主题和组
        self.topic_manager = TopicManager(self)
        
        # 初始化快捷键管理器
        self.shortcut_manager = ShortcutManager(self)
        
        # 记录当前使用的 AI 服务，避免不必要的刷新
        self.current_ai_service = None  # "chatgpt" or "gemini" or None
        
        # 初始化编辑工具管理器
        self.edit_tools_manager = EditToolsManager(self)

    def init_ui(self):
        # 1. 导航栏设置
        self.navigationInterface.setExpandWidth(300)
        self._init_navigation()

        # 2. 主工作区
        main_widget = QWidget()
        main_widget.setObjectName("mainWorkspace")
        self.addSubInterface(main_widget, FIF.DOCUMENT, "Read")
        
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main Layout (Left: List, Right: Content)
        main_content_layout = QHBoxLayout()
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(0)

        # Left Panel (Container)
        self.left_panel = self._create_left_panel()
        left_container = SimpleCardWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.left_panel)
        main_content_layout.addWidget(left_container)

        # Right Content Stack (PDF Viewer vs AI)
        self.right_content_stack = QStackedWidget()

        # Page 1: PDF Viewer
        self.pdf_viewer = PDFViewerWidget()
        self.pdf_viewer.translationRequested.connect(self.handle_translation_request)
        # 连接 AI 助手按钮信号 - 点击后直接打开第一个 AI 服务
        self.pdf_viewer.aiAssistantRequested.connect(self.show_web_login_menu)

        right_pdf_container = SimpleCardWidget()
        right_pdf_layout = QVBoxLayout(right_pdf_container)
        right_pdf_layout.setContentsMargins(0, 0, 0, 0)
        right_pdf_layout.addWidget(self.pdf_viewer)
        self.right_content_stack.addWidget(right_pdf_container)

        # Page 2: AI Assistant
        self.ai_assistant_interface = AIWebViewer()
        # Connect service changed signal
        self.ai_assistant_interface.serviceChanged.connect(lambda k: setattr(self, 'current_ai_service', k))
        # 连接关闭信号 - 点击关闭按钮返回 PDF 视图
        self.ai_assistant_interface.closeRequested.connect(self.switch_to_pdf_viewer)
        self.right_content_stack.addWidget(self.ai_assistant_interface)

        main_content_layout.addWidget(self.right_content_stack, 1)
        
        layout.addLayout(main_content_layout)


        
        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setMaximumHeight(24)  # 限制高度
        self.status_bar.setStyleSheet("QStatusBar { background: #fff; color: #666; min-height: 20px; padding: 0px; margin: 0px; }")
        layout.addWidget(self.status_bar)
         
    def _create_left_panel(self):
        panel = QFrame()
        panel.setFixedWidth(300) # Slightly wider for analysis text
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 5, 10)
        layout.setSpacing(10)

        # Splitter to separate list and analysis
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(0)  # 隐藏分隔条句柄，使其不可拖动
        splitter.setStyleSheet("QSplitter::handle { background-color: transparent; }")  # 确保不可交互
        splitter.setChildrenCollapsible(False)

        # === 上部：论文列表 ===
        pdf_card = SimpleCardWidget()
        pc_layout = QVBoxLayout(pdf_card)
        pc_layout.setContentsMargins(10, 10, 10, 10)
        pc_layout.setSpacing(8)
        
        # 标题和计数
        pc_layout.addWidget(SubtitleLabel("Paper List"))
        self.pdf_count_label = BodyLabel("0 篇论文")
        self.pdf_count_label.setStyleSheet("color: #888; font-size: 11px;")
        pc_layout.addWidget(self.pdf_count_label)
        
        # 论文列表（支持层级显示：主题 > 组 > 论文）
        # 使用自定义的 DraggableListWidget
        self.pdf_list_widget = DraggableListWidget(self.topic_manager) 
        self.pdf_list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel) 

        self.pdf_list_widget.setAlternatingRowColors(True)
        self.pdf_list_widget.itemClicked.connect(self.on_list_item_clicked)
        self.pdf_list_widget.itemDoubleClicked.connect(self.on_list_item_double_clicked)
        # 添加右键菜单支持
        self.pdf_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pdf_list_widget.customContextMenuRequested.connect(self.show_pdf_context_menu)
        
        # 强制列表扩充以占据所有剩余空间
        self.pdf_list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        pc_layout.addWidget(self.pdf_list_widget, 1)  # 添加拉伸因子1，让列表占据剩余空间
        
        splitter.addWidget(pdf_card)

        # === 下部：论文分析 ===
        analysis_card = SimpleCardWidget()
        ac_layout = QVBoxLayout(analysis_card)
        ac_layout.setContentsMargins(10, 10, 10, 10)
        ac_layout.setSpacing(8)

        ac_layout.addWidget(SubtitleLabel("Paper Analysis"))
        
        self.analysis_edit = TextEdit()
        self.analysis_edit.setPlaceholderText("在此处输入论文概述或分析...")
        # Reduce font size slightly for sidebar
        self.analysis_edit.setStyleSheet("TextEdit { font-size: 12px; }")
        
        # Auto-save signal
        self.analysis_edit.textChanged.connect(self.save_current_analysis)
        
        ac_layout.addWidget(self.analysis_edit, 1)
        
        splitter.addWidget(analysis_card)
        
        # Set default proportions (List 70%, Analysis 30%)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)
        
        return panel

    def save_current_analysis(self):
        """Auto-save analysis text to file"""
        if not hasattr(self, 'current_analysis_path') or not self.current_analysis_path:
            return
            
        content = self.analysis_edit.toPlainText()
        try:
            with open(self.current_analysis_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f"Error saving analysis: {e}")

    def _init_navigation(self):
        # 添加导航项

        
        self.navigationInterface.addItem(
            routeKey='edit_tools',
            icon=FIF.EDIT,
            text='编辑',
            onClick=self.show_edit_menu,
            position=NavigationItemPosition.TOP
        )
        self.navigationInterface.addItem(
            routeKey='help',
            icon=FIF.HELP,
            text='帮助',
            onClick=self.show_help_dialog,
            position=NavigationItemPosition.BOTTOM
        )
        


    def toggle_ai_assistant(self):
        """Switch to AI Assistant or Back"""
         # Simple toggle logic for stack
        if self.right_content_stack.currentWidget() == self.ai_assistant_interface:
            self.switch_to_pdf_viewer()
        else:
        # If using stack, we just switch to the AI service logic
            if not self.current_ai_service:
                self._switch_to_ai_service("chatgpt")
            else:
                self._switch_to_ai_service(self.current_ai_service)
    


    def _switch_to_ai_service(self, service_key):
        """
        切换到指定 AI 服务: 切换 Stack 到 AI 页，并显示相应服务
        """
        # 1. Ensure we are showing the AI Assistant Page
        self.right_content_stack.setCurrentWidget(self.ai_assistant_interface)
        
        # 2. Switch the inner stack of AI Assistant to the correct service
        # Map key to method if needed, or directly use key if AIWebViewer supports it.
        # The simplified AIWebViewer in 1.py/ai_assistant.py uses simplified methods or index switching.
        if service_key == "chatgpt":
            self.ai_assistant_interface.load_chatgpt()
        elif service_key == "gemini":
            self.ai_assistant_interface.load_gemini()
        elif service_key == "doubao":
            self.ai_assistant_interface.load_doubao()
        elif service_key == "deepseek":
            self.ai_assistant_interface.load_deepseek()
        elif service_key == "grok":
            self.ai_assistant_interface.load_grok()
            
        self.current_ai_service = service_key

    # Helper to switch back to PDF
    def switch_to_pdf_viewer(self):
        self.right_content_stack.setCurrentIndex(0) # Index 0 is PDF Viewer
    



    def show_edit_menu(self):
        """显示编辑菜单：高亮标记工具"""
        self.edit_tools_manager.show_edit_menu()

    def show_web_login_menu(self):
        """打开 AI 助手，显示上次使用的服务（如果有），否则打开第一个"""
        # 如果之前使用过某个服务，继续使用该服务
        if self.current_ai_service:
            self._switch_to_ai_service(self.current_ai_service)
        elif self.ai_assistant_interface.services:
            # 否则使用第一个服务
            first_svc = self.ai_assistant_interface.services[0]
            self._switch_to_ai_service(first_svc["key"])

    def show_help_dialog(self):
        """显示帮助弹窗"""
        w = HelpDialog(self)
        w.exec()

    # --- 逻辑处理 ---

    def open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择存放论文的文件夹")
        if folder_path:
            self.load_folder(folder_path)

    def on_list_item_clicked(self, item):
        """处理列表项点击事件"""
        if not item:
            return
        
        data = item.data(Qt.ItemDataRole.UserRole)
        item_type = data.get('type')
        
        if item_type == 'topic':
            # 点击主题：展开/折叠
            topic_name = data['name']
            self.topic_manager.toggle_expand(topic_name)
            self.topic_manager.refresh_list_display()
        
        elif item_type == 'group':
            # 点击组：展开/折叠
            topic_name = data['topic']
            group_name = data['name']
            group_key = f"{topic_name}::{group_name}"
            self.topic_manager.toggle_expand(group_key)
            self.topic_manager.refresh_list_display()
        
        elif item_type == 'pdf':
            # 点击PDF：打开阅读
            # 点击PDF：打开阅读
            self.switch_to_pdf_viewer()
            pdf_path = data['path']
            self.current_pdf_path = pdf_path
            filename = os.path.basename(pdf_path)
            
            # --- Analysis Logic ---
            # 1. Determine Analysis Root
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                project_root = os.path.dirname(os.path.abspath(__file__))
            analysis_root = os.path.join(project_root, 'analysis')
            
            # 2. Determine Specific Analysis Folder
            pdf_name_no_ext = os.path.splitext(filename)[0]
            target_dir = os.path.join(analysis_root, pdf_name_no_ext)
            
            # 3. Create Directory
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                print(f"Failed to create analysis dir: {e}")
            
            # 4. 检查翻译版是否存在，存在则并排显示
            trans_path = os.path.join(target_dir, "Translation.pdf")
            
            # --- Define Cache Dirs ---
            cache_original = os.path.join(target_dir, "cache_original")
            cache_trans = os.path.join(target_dir, "cache_translation")
            
            # --- Brush/Marker File ---
            brush_path = os.path.join(target_dir, "marker.json")
            brush_path_trans = os.path.join(target_dir, "marker_trans.json")
            
            # --- TOC Files ---
            toc_path = os.path.join(target_dir, "toc_original.json")
            toc_path_trans = os.path.join(target_dir, "toc_translation.json") # Although currently unused for sidebar
            
            # --- Rotation State Files ---
            rotation_path = os.path.join(target_dir, "rotation.json")
            rotation_path_trans = os.path.join(target_dir, "rotation_trans.json")
            
            if os.path.exists(trans_path):
                # 并排显示原文和翻译版
                self.pdf_viewer.load_side_by_side(pdf_path, trans_path, cache_original, cache_trans, 
                                                   brush_path=brush_path, brush_path2=brush_path_trans,
                                                   rotation_path=rotation_path, rotation_path2=rotation_path_trans,
                                                   toc_path=toc_path, toc_path2=toc_path_trans) # <--- Pass toc_path here? Wait, load_side_by_side definition only takes one toc_path? 
                self.status_bar.showMessage(f"正在阅读 (并排模式): {filename}")
            else:
                # 仅显示原文
                self.pdf_viewer.load_pdf(pdf_path, cache_dir=cache_original, brush_path=brush_path, rotation_path=rotation_path, toc_path=toc_path)
                self.status_bar.showMessage(f"正在阅读: {filename}")
            
            # Switch to PDF view if not already
            self.switch_to_pdf_viewer()
            
            # 5. Determine Analysis File Path
            analysis_file_path = os.path.join(target_dir, "analysis.txt")
            self.current_analysis_path = analysis_file_path
            
            # 6. Load or Create File
            if os.path.exists(analysis_file_path):
                try:
                    with open(analysis_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.analysis_edit.setText(content)
                except Exception as e:
                    self.analysis_edit.setText(f"Error loading analysis: {e}")
            else:
                # Create empty file
                try:
                    with open(analysis_file_path, 'w', encoding='utf-8') as f:
                        f.write("")
                    self.analysis_edit.setText("")
                except Exception as e:
                    print(f"Failed to create analysis file: {e}")
                    self.analysis_edit.setText("")
    
    def load_folder(self, folder_path, clear_viewer=True):
        self.current_folder = folder_path
        # pdf_files 仅存储未分类（根目录下）的 PDF
        self.pdf_files = []
        # 清空现有的主题和组
        self.topic_manager.clear()
        # 根据参数决定是否清空预览
        if clear_viewer:
            self.pdf_viewer.clear()
        
        try:
            if not os.path.isdir(folder_path):
                return

            # 1. 扫描根目录 (Level 0)
            root_items = sorted(os.listdir(folder_path))
            
            for item in root_items:
                full_path = os.path.join(folder_path, item)
                
                # 情况 A：根目录下的 PDF -> 未分类论文
                if os.path.isfile(full_path) and item.lower().endswith('.pdf'):
                    self.pdf_files.append((item, full_path))
                
                # 情况 B：一级目录 -> 主题 (Topic)
                elif os.path.isdir(full_path):
                    topic_name = item
                    # 手动初始化主题结构，避免调用 add_topic 弹窗
                    self.topic_manager.topics[topic_name] = {'groups': {}, 'pdfs': []}
                    
                    # 2. 扫描主题目录 (Level 1)
                    # 默认展开所有主题，以便直接看到组
                    self.topic_manager.expanded_items.add(topic_name)
                    
                    topic_items = sorted(os.listdir(full_path))
                    for t_item in topic_items:
                        t_full_path = os.path.join(full_path, t_item)
                        
                        # 情况 B-1: 主题下的 PDF -> 该主题的直接论文
                        if os.path.isfile(t_full_path) and t_item.lower().endswith('.pdf'):
                            self.topic_manager.add_pdf_to_topic(t_full_path, topic_name)
                        
                        # 情况 B-2: 二级目录 -> 组 (Group)
                        elif os.path.isdir(t_full_path):
                            group_name = t_item
                            # 手动初始化组结构
                            self.topic_manager.topics[topic_name]['groups'][group_name] = []
                            
                            # 3. 扫描组目录 (Level 2)
                            group_items = sorted(os.listdir(t_full_path))
                            for g_item in group_items:
                                g_full_path = os.path.join(t_full_path, g_item)
                                
                                # 情况 B-2-1: 组下的 PDF -> 该组的论文
                                if os.path.isfile(g_full_path) and g_item.lower().endswith('.pdf'):
                                    self.topic_manager.add_pdf_to_group(g_full_path, topic_name, group_name)
            
            # 更新论文列表显示 (调用 TopicManager)
            self.topic_manager.refresh_list_display()
            
            # 计算总数
            total_count = len(self.pdf_files)
            for t_data in self.topic_manager.topics.values():
                total_count += len(t_data['pdfs'])
                for g_pdfs in t_data['groups'].values():
                    total_count += len(g_pdfs)
            
            self.status_bar.showMessage(f"已加载 {total_count} 篇论文")
            
        except Exception as e:
            self.status_bar.showMessage(f"加载失败: {str(e)}")
            print(f"Error loading folder: {e}")
    

    
    def show_pdf_context_menu(self, pos):
        """显示论文列表的右键菜单"""
        # 委托给 TopicManager 处理
        self.topic_manager.show_context_menu(pos)
        return

        from qfluentwidgets import RoundMenu, Action, MenuAnimationType
        
        item = self.pdf_list_widget.itemAt(pos)
        if not item:
            return
        
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        item_type = data.get('type')
        menu = RoundMenu(parent=self)
        


        # === 通用操作 (重命名, 删除) ===
        rename_action = Action(FIF.EDIT, "重命名")
        rename_action.triggered.connect(lambda: self.topic_manager.rename_item_with_ui(data))
        menu.addAction(rename_action)
        
        delete_action = Action(FIF.DELETE, "删除")
        delete_action.triggered.connect(lambda: self.topic_manager.delete_item_with_ui(data))
        menu.addAction(delete_action)
        
        # 显示菜单
        menu.exec(self.pdf_list_widget.mapToGlobal(pos), aniType=MenuAnimationType.DROP_DOWN)



    def on_list_item_double_clicked(self, item):
        """双击处理：切换到仅显示原文模式（如果当前是并排显示）"""
        if not item:
            return
            
        data = item.data(Qt.ItemDataRole.UserRole)
        if data.get('type') == 'pdf':
            # self.right_content_stack.setCurrentIndex(0) # Removed as stack is replaced by splitter
            pdf_path = data['path']
            filename = os.path.basename(pdf_path)
            
            # 双击时切换到仅显示原文
            # 双击时切换到仅显示原文
            
            # Logic to find Analysis Dir (Replicated from click event, ideally helper method)
            if getattr(sys, 'frozen', False):
                project_root = os.path.dirname(sys.executable)
            else:
                project_root = os.path.dirname(os.path.abspath(__file__))
            pdf_name_no_ext = os.path.splitext(filename)[0]
            cache_original = os.path.join(project_root, 'analysis', pdf_name_no_ext, "cache_original")
            brush_path = os.path.join(project_root, 'analysis', pdf_name_no_ext, "marker.json")
            
            self.pdf_viewer.load_pdf(pdf_path, cache_dir=cache_original, brush_path=brush_path)
            self.status_bar.showMessage(f"正在阅读 (仅原文): {filename}")

    def handle_translation_request(self, text):
        """Handle translation request from PDF Viewer"""
        from qfluentwidgets import InfoBar, InfoBarPosition
        from PyQt6.QtGui import QGuiApplication
        
        # 1. Switch to AI Assistant -> Doubao
        self._switch_to_ai_service("doubao")
        
        # 2. Copy text to clipboard
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        
        # 3. Show notification
        InfoBar.info(
            title='文本已复制',
            content='请在豆包对话框中粘贴 (Ctrl+V) 进行翻译',
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=self
        )
    
    def undo_edit(self):
        """Undo last edit operation"""
        if hasattr(self, 'pdf_viewer'):
            if self.pdf_viewer.undo():
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.success(
                    title='已撤销',
                    content='上一步操作已撤销',
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=1000
                )
            # Optional: Feedback if nothing to undo? No, silent is better usually.

if __name__ == "__main__":
    # Fix Taskbar Icon for Windows
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("insightpaper.app.1.0")
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
