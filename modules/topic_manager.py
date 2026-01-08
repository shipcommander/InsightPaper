"""
主题和组管理模块
负责管理论文的主题和组织结构
"""

import os
import sys
import shutil
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter
from PyQt6.QtCore import Qt, QSize
from qfluentwidgets import (InfoBar, InfoBarPosition, MessageBoxBase, SubtitleLabel, 
                            LineEdit, ComboBox, BodyLabel, MessageBox, RoundMenu, Action, MenuAnimationType, FluentIcon as FIF)

# --- 辅助对话框类 ---

class CustomInputDialog(MessageBoxBase):
    """通用的单行输入对话框"""
    def __init__(self, title, label_text, placeholder="", parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setClearButtonEnabled(True)
        
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(10)
        self.viewLayout.addWidget(BodyLabel(label_text, self))
        self.viewLayout.addWidget(self.lineEdit)
        
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.lineEdit.returnPressed.connect(self.accept)
        self.widget.setMinimumWidth(350)

    def get_text(self):
        return self.lineEdit.text().strip()

class GroupInputDialog(MessageBoxBase):
    """添加组的对话框"""
    def __init__(self, topic_list, default_topic=None, parent=None):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel("添加组", self))
        self.viewLayout.addSpacing(10)

        # 主题选择
        self.topic_combo = ComboBox(self)
        self.topic_combo.addItems(topic_list)
        
        if default_topic and default_topic in topic_list:
            self.viewLayout.addWidget(BodyLabel(f"归属主题: {default_topic}", self))
            self.topic_combo.setCurrentText(default_topic)
            self.topic_combo.setVisible(False)
        else:
            self.viewLayout.addWidget(BodyLabel("选择主题:", self))
            self.viewLayout.addWidget(self.topic_combo)
        
        self.viewLayout.addSpacing(10)
        
        # 组名输入
        self.viewLayout.addWidget(BodyLabel("组名称:", self))
        self.group_edit = LineEdit(self)
        self.group_edit.setPlaceholderText("请输入组名称")
        self.group_edit.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.group_edit)
        
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.group_edit.returnPressed.connect(self.accept)
        self.widget.setMinimumWidth(350)

    def get_data(self):
        return self.topic_combo.currentText(), self.group_edit.text().strip()

# --- 主逻辑类 ---

class TopicManager:
    """主题和组管理器"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.topics = {}  # {topic: {'groups': {group: [pdfs]}, 'pdfs': [pdfs]}}
        self.expanded_items = set()

        # 缓存图标
        self._green_dot_icon = self._create_green_dot_icon()
        self._transparent_icon = self._create_transparent_icon()

    def clear(self):
        self.topics = {}
        self.expanded_items = set()

    # --- 内部工具方法 ---

    def _create_green_dot_icon(self):
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#00CC6A"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 8, 8)
        painter.end()
        return QIcon(pixmap)

    def _create_transparent_icon(self):
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.GlobalColor.transparent)
        return QIcon(pixmap)

    def _show_message(self, title, content, is_error=False, is_warning=False):
        """统一的消息提示封装"""
        func = InfoBar.error if is_error else (InfoBar.warning if is_warning else InfoBar.success)
        func(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self.main_window
        )

    def _get_current_root(self):
        """获取当前工作根目录"""
        return getattr(self.main_window, 'current_folder', "")

    def _resolve_path(self, item_data):
        """根据 item data 解析出文件系统绝对路径"""
        root = self._get_current_root()
        itype = item_data.get('type')
        
        if itype == 'topic':
            return os.path.join(root, item_data['name'])
        elif itype == 'group':
            return os.path.join(root, item_data['topic'], item_data['name'])
        elif itype == 'pdf':
            return item_data['path']
        return root

    def _get_unique_path(self, folder, filename):
        """处理文件名冲突，自动添加序号"""
        base, ext = os.path.splitext(filename)
        dst = os.path.join(folder, filename)
        counter = 1
        while os.path.exists(dst):
            dst = os.path.join(folder, f"{base}_{counter}{ext}")
            counter += 1
        return dst

    def _reload_ui(self):
        """重新加载文件系统并刷新UI"""
        # 保存展开状态 -> 重新加载数据 -> 恢复展开状态 -> 刷新列表
        saved_expanded = self.expanded_items.copy()
        # 仅刷新数据，保留当前阅读视图
        self.main_window.load_folder(self._get_current_root(), clear_viewer=False)
        self.expanded_items = saved_expanded
        self.refresh_list_display()

    # --- 核心功能：添加 ---

    def add_topic(self):
        root = self._get_current_root()
        if not root:
            self._show_message('请先选择文件夹', '请先打开一个文件夹用于存放论文数据', is_warning=True)
            return False

        dialog = CustomInputDialog("添加主题", "主题名称:", "请输入新主题名称", self.main_window)
        if not dialog.exec(): return False
        
        name = dialog.get_text()
        if not name: return False

        if name in self.topics:
            self._show_message('主题已存在', f'主题 "{name}" 已经存在', is_warning=True)
            return False

        try:
            os.makedirs(os.path.join(root, name), exist_ok=False)
            self.topics[name] = {'groups': {}, 'pdfs': []}
            self.refresh_list_display()
            self._show_message('添加成功', f'主题 "{name}" 已创建')
            return True
        except OSError:
            self._show_message('创建失败', '文件夹无法创建', is_error=True)
            return False

    def add_group(self, default_topic=None):
        root = self._get_current_root()
        if not root: return False
        if not self.topics:
            self._show_message('请先创建主题', '组必须属于某个主题', is_warning=True)
            return False

        # 获取上下文或默认主题
        if not default_topic:
            current_item = self.main_window.pdf_list_widget.currentItem()
            if current_item:
                data = current_item.data(Qt.ItemDataRole.UserRole)
                if data:
                    if data['type'] == 'topic': default_topic = data['name']
                    elif data['type'] == 'group': default_topic = data['topic']
                    elif data['type'] == 'pdf':
                        p = data.get('parent', '')
                        default_topic = p.split('::')[0] if '::' in str(p) else p

        dialog = GroupInputDialog(sorted(self.topics.keys()), default_topic, self.main_window)
        if not dialog.exec(): return False
        
        topic, group = dialog.get_data()
        if not topic or not group: return False

        if group in self.topics[topic]['groups']:
            self._show_message('组已存在', f'组 "{group}" 已在主题中', is_warning=True)
            return False

        try:
            os.makedirs(os.path.join(root, topic, group), exist_ok=False)
            self.topics[topic]['groups'][group] = []
            self.expanded_items.add(topic) # 自动展开主题
            self.refresh_list_display()
            self._show_message('添加成功', f'组 "{group}" 已创建')
            return True
        except OSError:
            self._show_message('创建失败', '文件夹无法创建', is_error=True)
            return False

    # --- 核心功能：列表显示 ---

    def refresh_list_display(self):
        """渲染 UI 列表"""
        list_widget = self.main_window.pdf_list_widget
        
        # 保存当前选中状态
        current_item = list_widget.currentItem()
        selected_data = current_item.data(Qt.ItemDataRole.UserRole) if current_item else None
        
        list_widget.clear()
        
        pdf_files = self.main_window.pdf_files
        
        # 检查翻译文件是否存在 - 支持打包后的环境
        if getattr(sys, 'frozen', False):
            analysis_root = os.path.join(os.path.dirname(sys.executable), 'analysis')
        else:
            analysis_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analysis')
        def has_trans(path):
            name = os.path.splitext(os.path.basename(path))[0]
            return os.path.exists(os.path.join(analysis_root, name, 'Translation.pdf'))

        # 辅助：创建列表项
        def create_item(text, data, indent_level=0, bold=False, color=None, icon=None):
            indent_str = "    " * indent_level
            item = QListWidgetItem(f"{indent_str} {text}")
            item.setData(Qt.ItemDataRole.UserRole, data)
            if bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            if color: item.setForeground(QColor(color))
            
            # Use provided icon or transparent placeholder to maintain alignment
            item.setIcon(icon if icon else self._transparent_icon)
            
            list_widget.addItem(item)

        # 1. 未分类论文
        categorized = set()
        for t_data in self.topics.values():
            categorized.update(t_data['pdfs'])
            for g_pdfs in t_data['groups'].values():
                categorized.update(g_pdfs)
        
        for name, path in pdf_files:
            if path not in categorized:
                create_item(name, {'type': 'pdf', 'path': path}, 
                            icon=self._green_dot_icon if has_trans(path) else None)

        # 2. 主题树
        for topic in sorted(self.topics.keys()):
            t_data = self.topics[topic]
            count = len(t_data['pdfs']) + sum(len(p) for p in t_data['groups'].values())
            
            # 主题 Header
            create_item(f"{topic} ({count})", {'type': 'topic', 'name': topic}, 
                        bold=True, color="#0078d4")


            is_expanded = topic in self.expanded_items
            if is_expanded:
                # 主题下的文件
                for path in t_data['pdfs']:
                    create_item(os.path.basename(path), 
                                {'type': 'pdf', 'path': path, 'parent': topic}, 
                                indent_level=1, 
                                icon=self._green_dot_icon if has_trans(path) else None)
                
                # 主题下的组
                for group in sorted(t_data['groups'].keys()):
                    g_pdfs = t_data['groups'][group]
                    g_key = f"{topic}::{group}"
                    
                    create_item(f"{group} ({len(g_pdfs)})", 
                                {'type': 'group', 'topic': topic, 'name': group}, 
                                indent_level=1, color="#8764b8")
                    
                    if g_key in self.expanded_items:
                        # 组下的文件
                        for path in g_pdfs:
                            create_item(os.path.basename(path), 
                                        {'type': 'pdf', 'path': path, 'parent': g_key}, 
                                        indent_level=2, 
                                        icon=self._green_dot_icon if has_trans(path) else None)

        # 3. 底部空白占位符 (方便在列表满时也能右键点击空白处)
        spacer_item = QListWidgetItem("")
        spacer_item.setFlags(Qt.ItemFlag.NoItemFlags)  # 完全不可交互,不会高亮或选中
        spacer_item.setSizeHint(QSize(0, 150)) # 150px 高度
        spacer_item.setData(Qt.ItemDataRole.UserRole, {'type': 'spacer'})
        list_widget.addItem(spacer_item)

        # Update total count label
        total_pdfs = len(pdf_files)
        for t_data in self.topics.values():
            total_pdfs += len(t_data['pdfs'])
            for g_pdfs in t_data['groups'].values():
                total_pdfs += len(g_pdfs)
                
        self.main_window.pdf_count_label.setText(f"{total_pdfs} 篇论文")
        
        # 恢复选中状态
        if selected_data:
            for i in range(list_widget.count()):
                it = list_widget.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == selected_data:
                    list_widget.setCurrentItem(it)
                    break

    # --- 核心功能：操作 (拖拽/重命名/删除) ---

    def handle_drag_drop(self, source_data, target_data):
        if source_data['type'] != 'pdf' or not os.path.exists(source_data['path']):
            return False

        # 确定目标文件夹
        target_dir = self._resolve_path(target_data)
        if target_data['type'] == 'pdf':
            target_dir = os.path.dirname(target_dir)
        
        if not target_dir or not os.path.exists(target_dir): return False
        if os.path.dirname(source_data['path']) == target_dir: return False # 原地不动

        try:
            # 关键：移动前必须释放文件锁（如果当前正在阅读该文件）
            self.main_window.pdf_viewer.close_file(source_data['path'])
            
            dst_path = self._get_unique_path(target_dir, os.path.basename(source_data['path']))
            shutil.move(source_data['path'], dst_path)
            self._reload_ui()
            return True
        except Exception as e:
            self._show_message('移动失败', str(e), is_error=True)
            return False

    def handle_external_drop(self, file_paths, target_data=None):
        target_dir = self._resolve_path(target_data) if target_data else self._get_current_root()
        
        if not target_dir or not os.path.exists(target_dir): return False
        
        # Calculate download dir path for check - 支持打包后的环境
        if getattr(sys, 'frozen', False):
            project_root = os.path.dirname(sys.executable)
        else:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        download_dir = os.path.normpath(os.path.join(project_root, 'download'))
        
        success_count = 0
        for src in file_paths:
            if not os.path.isfile(src) or not src.lower().endswith('.pdf'): continue
            
            try:
                # 避免自我复制/移动
                if os.path.normpath(os.path.dirname(src)) == os.path.normpath(target_dir): continue
                
                dst = self._get_unique_path(target_dir, os.path.basename(src))
                
                # Check if src is in download dir
                src_dir = os.path.normpath(os.path.dirname(src))
                if src_dir == download_dir:
                    shutil.move(src, dst)
                else:
                    shutil.copy2(src, dst)
                    
                success_count += 1
            except Exception as e:
                print(f"Import failed: {e}")

        if success_count > 0:
            self._reload_ui()
            self._show_message('导入成功', f'成功导入 {success_count} 个文件')
            return True
        return False

    def rename_item_with_ui(self, item_data):
        old_path = self._resolve_path(item_data)
        old_name = os.path.basename(old_path)
        
        # 对于 PDF 文件，显示时去掉后缀
        display_name = old_name
        if item_data['type'] == 'pdf' and old_name.lower().endswith('.pdf'):
            display_name = old_name[:-4]  # 去掉 .pdf 后缀
        
        dialog = CustomInputDialog("重命名", "新名称:", display_name, self.main_window)
        dialog.lineEdit.setText(display_name)
        dialog.lineEdit.selectAll()
        dialog.lineEdit.setFocus()
        if not dialog.exec(): return

        new_name = dialog.get_text()
        if not new_name: return
        
        # 1. 移除不合法字符 (Windows: < > : " / \ | ? *)
        import re
        # 首先替换换行符等为空格
        new_name = re.sub(r'[\r\n\t]', ' ', new_name)
        new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
        new_name = new_name.strip()

        # 2. 确保后缀正确
        if item_data['type'] == 'pdf':
             # 如果用户没写后缀，自动补全
             if not new_name.lower().endswith('.pdf'):
                 new_name += '.pdf'
        
        if new_name == old_name:
            return
        
        new_path = os.path.join(os.path.dirname(old_path), new_name)

        try:
            # --- 1. Check if the file (or a file inside it) is currently open ---
            was_open = False
            page_num = 0
            is_dual = False
            
            # Helper: Check if paths are effectively the same
            def is_path_open(check_path, file_path):
                if not check_path or not file_path: return False
                try:
                    return os.path.normpath(os.path.abspath(check_path)) == os.path.normpath(os.path.abspath(file_path))
                except:
                    return False

            if item_data['type'] == 'pdf':
                # Check active paths in all viewers
                # MainWindow usually tracks current_pdf_path, but trust the viewer state
                viewer_widget = self.main_window.pdf_viewer
                
                curr_viewer = getattr(viewer_widget.viewer, 'current_path', None)
                curr_left = getattr(viewer_widget.left_view, 'current_path', None)
                curr_right = getattr(viewer_widget.right_view, 'current_path', None)
                
                # Check if we are viewing this PDF (Single or Dual Left)
                if is_path_open(curr_viewer, old_path):
                    was_open = True
                    page_num = viewer_widget.get_current_page()
                    is_dual = False
                elif is_path_open(curr_left, old_path):
                    was_open = True
                    page_num = viewer_widget.get_current_page()
                    is_dual = True
                
                # If we detected it's open, or if we suspect it might be locked (e.g. Right view has translation derived from it)
                # Ideally, if we rename the Original, the Translation path also changes, so we should close that too.
                # So if 'was_open' is true, we clear everything.
                if was_open:
                     viewer_widget.clear()
                     # Give a tiny pause for threads to die if needed?
                     # In PyQt single thread, clear() calling cancel/wait should be enough.

            elif os.path.isdir(old_path):
                 # Logic for directories... (kept simple for now)
                 current_pdf = getattr(self.main_window, 'current_pdf_path', None)
                 if current_pdf and os.path.commonpath([old_path, current_pdf]) == os.path.normpath(old_path):
                     self.main_window.pdf_viewer.close_file(current_pdf)
            
            # --- 2. Rename with Retry (Windows Lock Handling) ---
            import time
            renamed = False
            last_error = None
            for i in range(3): # Try 3 times
                try:
                    os.rename(old_path, new_path)
                    renamed = True
                    break
                except OSError as e:
                    last_error = e
                    time.sleep(0.1 + i*0.1) # 100ms, 200ms...
            
            if not renamed:
                raise last_error

            # --- 3. Handle Analysis/Translation Folder Rename - 支持打包后的环境 ---
            if item_data['type'] == 'pdf':
                if getattr(sys, 'frozen', False):
                    analysis_root = os.path.join(os.path.dirname(sys.executable), 'analysis')
                else:
                    analysis_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analysis')
                old_base = os.path.splitext(old_name)[0]
                new_base = os.path.splitext(new_name)[0]
                old_analysis_dir = os.path.join(analysis_root, old_base)
                new_analysis_dir = os.path.join(analysis_root, new_base)
                
                if os.path.exists(old_analysis_dir):
                    if os.path.abspath(old_analysis_dir) != os.path.abspath(new_analysis_dir):
                         if not os.path.exists(new_analysis_dir):
                             try:
                                 os.rename(old_analysis_dir, new_analysis_dir)
                             except Exception as e:
                                 self._show_message('分析目录重命名失败', str(e), is_warning=True)
                
                # Update current_analysis_path if needed
                cur_analysis = getattr(self.main_window, 'current_analysis_path', '')
                if cur_analysis and cur_analysis.startswith(old_analysis_dir):
                    self.main_window.current_analysis_path = cur_analysis.replace(old_analysis_dir, new_analysis_dir, 1)

            # --- 4. Restore View ---
            if was_open:
                 self.main_window.current_pdf_path = new_path
                 
                 # Prepare paths
                 # Analysis dir is now new_analysis_dir
                 new_analysis_dir = os.path.join(analysis_root, new_base) # Ensure valid
                 
                 # Check for translation
                 new_trans_path = os.path.join(new_analysis_dir, 'Translation.pdf')
                 cache_original = os.path.join(new_analysis_dir, "cache_original")
                 brush_path = os.path.join(new_analysis_dir, "marker.json")
                 
                 if is_dual and os.path.exists(new_trans_path):
                     cache_trans = os.path.join(new_analysis_dir, "cache_translation")
                     brush_path2 = os.path.join(new_analysis_dir, "marker_trans.json")
                     self.main_window.pdf_viewer.load_side_by_side(
                         new_path, 
                         new_trans_path, 
                         cache_dir1=cache_original, 
                         cache_dir2=cache_trans,
                         brush_path=brush_path,
                         brush_path2=brush_path2,
                         scroll_to_page=page_num
                     )
                 else:
                     # Single view
                     self.main_window.pdf_viewer.load_pdf(
                         new_path, 
                         cache_dir=cache_original, 
                         brush_path=brush_path,
                         scroll_to_page=page_num
                     )
            
            # Update internal reference in case just the property was holding it
            elif item_data['type'] == 'pdf' and getattr(self.main_window, 'current_pdf_path', '') == old_path:
                 self.main_window.current_pdf_path = new_path
            
            self._reload_ui()
            self._show_message('重命名成功', f'已重命名为 "{new_name}"')
        except Exception as e:
            self._show_message('重命名失败', str(e), is_error=True)

    def delete_item_with_ui(self, item_data):
        path = self._resolve_path(item_data)
        path = os.path.normpath(path)  # 规范化路径，消除双斜杠等问题
        name = os.path.basename(path)
        
        # 先检查文件/目录是否存在
        if not os.path.exists(path):
            self._show_message('删除失败', f'文件或目录不存在:\n{path}', is_error=True)
            self._reload_ui()  # 刷新列表，移除无效项
            return
        
        msg = f"确定要删除 \"{name}\" 吗？此操作不可恢复！"
        if item_data['type'] in ['topic', 'group']:
            msg = f"确定要删除 \"{name}\" 及其所有内容吗？"
        elif item_data['type'] == 'pdf':
            msg = f"确定要删除 \"{name}\" 及其分析文件（翻译版、缓存等）吗？"

        w = MessageBox("确认删除", msg, self.main_window)
        w.yesButton.setText("删除")
        w.cancelButton.setText("取消")
        if not w.exec(): return

        try:
            # 关键：删除前必须释放文件锁
            # 如果是单个文件，直接尝试关闭它
            if item_data['type'] == 'pdf':
                self.main_window.pdf_viewer.close_file(path)
            
            # 如果是目录（主题/组），检查当前打开的文件是否在其内部
            elif os.path.isdir(path):
                current_pdf = getattr(self.main_window, 'current_pdf_path', None)
                if current_pdf and os.path.commonpath([path, current_pdf]) == os.path.normpath(path):
                    self.main_window.pdf_viewer.close_file(current_pdf)

            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
                # Note: clearing viewer is handled by close_file above, or we check again
                if getattr(self.main_window, 'current_pdf_path', '') == path:
                    self.main_window.pdf_viewer.clear()
            
            # === 同步删除 analysis 目录 ===
            if item_data['type'] == 'pdf':
                # 获取 analysis 根目录
                if getattr(sys, 'frozen', False):
                    analysis_root = os.path.join(os.path.dirname(sys.executable), 'analysis')
                else:
                    analysis_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analysis')
                
                # 计算对应的 analysis 子目录
                pdf_name_no_ext = os.path.splitext(name)[0]
                analysis_dir = os.path.join(analysis_root, pdf_name_no_ext)
                
                # 删除对应的分析目录（如果存在）
                if os.path.exists(analysis_dir) and os.path.isdir(analysis_dir):
                    try:
                        shutil.rmtree(analysis_dir)
                    except Exception as e:
                        print(f"删除分析目录失败: {e}")
            
            self._reload_ui()
            self._show_message('删除成功', '项目已删除')
        except Exception as e:
            self._show_message('删除失败', str(e), is_error=True)

    def toggle_expand(self, item_key):
        """切换展开状态"""
        if item_key in self.expanded_items:
            self.expanded_items.remove(item_key)
        else:
            self.expanded_items.add(item_key)
            
    def show_context_menu(self, pos):
        """显示上下文菜单"""
        list_widget = self.main_window.pdf_list_widget
        item = list_widget.itemAt(pos)
        
        menu = RoundMenu(parent=self.main_window)
        
        if not item or (item.data(Qt.ItemDataRole.UserRole) and item.data(Qt.ItemDataRole.UserRole).get('type') == 'spacer'):
            # 空白区域 (或占位符) -> 新增主题
            add_topic_action = Action(FIF.TAG, "新增主题")
            add_topic_action.triggered.connect(self.add_topic)
            menu.addAction(add_topic_action)
        else:
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data: return
            
            item_type = data.get('type')
            
            if item_type == 'topic':
                # 主题: 添加组, 重命名, 删除
                add_group_action = Action(FIF.ADD, "添加组")
                # 预设该主题为默认选项
                add_group_action.triggered.connect(lambda: self.add_group(default_topic=data['name']))
                menu.addAction(add_group_action)
                
                menu.addSeparator()
                
                rename_action = Action(FIF.EDIT, "重命名")
                rename_action.triggered.connect(lambda: self.rename_item_with_ui(data))
                menu.addAction(rename_action)
                
                delete_action = Action(FIF.DELETE, "删除")
                delete_action.triggered.connect(lambda: self.delete_item_with_ui(data))
                menu.addAction(delete_action)
                
            elif item_type == 'group':
                # 组: 重命名, 删除
                rename_action = Action(FIF.EDIT, "重命名")
                rename_action.triggered.connect(lambda: self.rename_item_with_ui(data))
                menu.addAction(rename_action)
                
                delete_action = Action(FIF.DELETE, "删除")
                delete_action.triggered.connect(lambda: self.delete_item_with_ui(data))
                menu.addAction(delete_action)
                
            elif item_type == 'pdf':
                # PDF: 重命名, 删除 (Add import menu logic if needed later)
                # Note: Currently Import logic is not requested here, keeping essential actions
                rename_action = Action(FIF.EDIT, "重命名")
                rename_action.triggered.connect(lambda: self.rename_item_with_ui(data))
                menu.addAction(rename_action)
                
                delete_action = Action(FIF.DELETE, "删除")
                delete_action.triggered.connect(lambda: self.delete_item_with_ui(data))
                menu.addAction(delete_action)

        menu.exec(list_widget.mapToGlobal(pos), aniType=MenuAnimationType.DROP_DOWN)

    def add_pdf_to_topic(self, pdf_path, topic_name):
        """将论文添加到指定主题"""
        if topic_name in self.topics and pdf_path not in self.topics[topic_name]['pdfs']:
            self.topics[topic_name]['pdfs'].append(pdf_path)
            return True
        return False
    
    def add_pdf_to_group(self, pdf_path, topic_name, group_name):
        """将论文添加到指定组"""
        if topic_name in self.topics and group_name in self.topics[topic_name]['groups']:
            if pdf_path not in self.topics[topic_name]['groups'][group_name]:
                self.topics[topic_name]['groups'][group_name].append(pdf_path)
                return True
        return False
