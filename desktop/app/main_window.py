"""
主窗口：顶栏（Logo + 菜单栏）、侧栏（工程树）、主内容区。与 Web 端布局与交互一致。
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QMenu,
    QMenuBar,
    QListWidget,
    QListWidgetItem,
    QStatusBar,
    QMessageBox,
    QFileDialog,
    QTabWidget,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QStyledItemDelegate,
)
from PySide6.QtCore import Qt, Slot, Signal, QSize
from PySide6.QtGui import QAction, QFont, QIcon

from .icons import (
    icon_open_folder,
    icon_new_folder,
    icon_edit,
    icon_workspace,
    icon_refresh,
    icon_stack_flow,
    icon_mintpy_flow,
    icon_mintpy_config,
)
from .widgets.define_project_dialog import DefineProjectDialog
from .widgets.edit_project_dialog import EditProjectDialog
from .widgets.define_workspace_dialog import DefineWorkspaceDialog
from .widgets.tile_map_widget import MapWithToolbar, TileMapWidget, get_bbox_from_project
from .widgets.stack_flow_config_dialog import StackFlowConfigDialog
from .widgets.stack_flow_widget import StackFlowWidget
from .widgets.mintpy_config_dialog import MintPyConfigDialog
from .widgets.mintpy_quick_setup_dialog import MintPyQuickSetupDialog
from .widgets.mintpy_flow_widget import MintPyFlowWidget
from .widgets.new_data_to_download_dialog import NewDataToDownloadDialog
from .widgets.slc_hardlink_by_workspace_dialog import SlcHardlinkByWorkspaceDialog
from .widgets.check_zip_files_dialog import CheckZipFilesDialog
from .widgets.mintpy_to_shapefile_dialog import MintPyToShapefileDialog
from . import project_store


class ProjectItemWidget(QWidget):
    """树形结构工程节点的自定义 widget，包含工程名称和关闭按钮。"""
    
    close_clicked = Signal(dict)  # 发送要关闭的工程节点
    
    def __init__(self, node: dict, parent=None):
        super().__init__(parent)
        self._node = node
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        # 工程名称标签
        self.name_label = QLabel(self._node.get("name", "工程"))
        self.name_label.setStyleSheet("""
            QLabel {
                color: #f8fafc;
                font-size: 13px;
                padding: 2px;
            }
        """)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.name_label, 1)
        
        # 关闭按钮（小红叉）
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ef4444;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 9px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        self.close_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.close_btn.setToolTip("关闭工程")
        self.close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.close_btn)
        
    def _on_close_clicked(self):
        """关闭按钮被点击。"""
        self.close_clicked.emit(self._node)
    
    def get_node(self) -> dict:
        """返回关联的工程节点。"""
        return self._node


class MainWindow(QMainWindow):
    """InSAR 桌面主窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insight InSAR Processing System")
        _logo_path = Path(__file__).resolve().parent.parent.parent / "public" / "img" / "InSAR_Insight_Logo_Focused.png"
        if _logo_path.is_file():
            self.setWindowIcon(QIcon(str(_logo_path)))
        self.setMinimumSize(1024, 720)
        self.resize(1280, 800)

        # 工程列表：从本地 project_store 加载，每项 { id, name, radarType, projectPath }
        self._projects = project_store.load_projects()
        self._selected_project_id: str | None = None
        # 地图 Tab：project_id -> MapWithToolbar（含工具栏+地图），用于复用或刷新
        self._map_tabs: dict[str, MapWithToolbar] = {}
        # 工具对话框引用：避免 show() 后被 GC 回收
        self._tool_dialogs: list = []

        self._build_menubar()

        central = QWidget()
        central.setLayout(QVBoxLayout())
        central.layout().setContentsMargins(0, 0, 0, 0)
        central.layout().setSpacing(0)
        self.setCentralWidget(central)

        # 顶栏：简洁分隔条 + 工程区标题（中性样式）
        header = self._build_header()
        central.layout().addWidget(header)

        # 主体：侧栏 + 内容
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        body_layout.addWidget(self._sidebar)

        self._content = self._build_content()
        body_layout.addWidget(self._content, 1)

        central.layout().addWidget(body, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")
        self._refresh_project_list_ui()
        self._restore_current_project()
        self._connect_project_signals()

    def _build_menubar(self) -> None:
        """标准菜单栏：文件、工具、视图、帮助，风格与专业数据处理软件一致。"""
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        # 文件
        file_menu = menubar.addMenu("文件(&F)")
        act_open = QAction(icon_open_folder(), "打开工程(&O)...", self)
        act_open.triggered.connect(self._on_open_project)
        file_menu.addAction(act_open)
        act_new = QAction(icon_new_folder(), "新建工程(&N)...", self)
        act_new.triggered.connect(self._on_new_project)
        file_menu.addAction(act_new)
        file_menu.addSeparator()
        act_quit = QAction("退出(&Q)", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 工具
        tools_menu = menubar.addMenu("工具(&T)")
        act_new_data = QAction("新数据待下载列表(&N)...", self)
        act_new_data.triggered.connect(self._on_tool_new_data_to_download)
        tools_menu.addAction(act_new_data)
        act_slc_hardlink = QAction("SLC 按工作区硬链接(&L)...", self)
        act_slc_hardlink.triggered.connect(self._on_tool_slc_hardlink_by_workspace)
        tools_menu.addAction(act_slc_hardlink)
        act_check_zip = QAction("检查 ZIP 文件(&Z)...", self)
        act_check_zip.triggered.connect(self._on_tool_check_zip_files)
        tools_menu.addAction(act_check_zip)
        act_mintpy_shp = QAction("MintPy 转 Shapefile(&S)...", self)
        act_mintpy_shp.triggered.connect(self._on_tool_mintpy_to_shapefile)
        tools_menu.addAction(act_mintpy_shp)

        # 视图（占位，便于后续扩展）
        view_menu = menubar.addMenu("视图(&V)")
        # 可后续添加：主内容、地图、全屏等

        # 帮助
        help_menu = menubar.addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "Insight InSAR Processing System\n\nInSAR 数据处理桌面端。",
        )

    def _on_tool_new_data_to_download(self) -> None:
        self._tool_dialogs = [d for d in self._tool_dialogs if d.isVisible()]
        dlg = NewDataToDownloadDialog(self)
        dlg.show()
        self._tool_dialogs.append(dlg)

    def _on_tool_slc_hardlink_by_workspace(self) -> None:
        self._tool_dialogs = [d for d in self._tool_dialogs if d.isVisible()]
        dlg = SlcHardlinkByWorkspaceDialog(self)
        dlg.show()
        self._tool_dialogs.append(dlg)

    def _on_tool_check_zip_files(self) -> None:
        self._tool_dialogs = [d for d in self._tool_dialogs if d.isVisible()]
        dlg = CheckZipFilesDialog(self)
        dlg.show()
        self._tool_dialogs.append(dlg)

    def _on_tool_mintpy_to_shapefile(self) -> None:
        self._tool_dialogs = [d for d in self._tool_dialogs if d.isVisible()]
        dlg = MintPyToShapefileDialog(self)
        dlg.show()
        self._tool_dialogs.append(dlg)

    def _build_header(self) -> QFrame:
        """顶栏：中性分隔条 + 工程区标题，无醒目按钮。"""
        header = QFrame()
        header.setObjectName("headerFrame")
        header.setFixedHeight(36)
        header.setStyleSheet("""
            QFrame#headerFrame {
                background-color: rgba(0, 0, 0, 0.15);
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            }
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(0)
        title = QLabel("工程")
        title.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500;")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        layout.addWidget(title)
        layout.addStretch()
        return header

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(280)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 16, 16, 16)

        # 使用树形控件替代列表
        self._project_tree = QTreeWidget()
        self._project_tree.setObjectName("projectTree")
        self._project_tree.setHeaderHidden(True)
        self._project_tree.setRootIsDecorated(True)
        self._project_tree.setIndentation(20)
        self._project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._project_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self._project_tree.itemSelectionChanged.connect(self._on_tree_item_selected)
        self._project_tree.setStyleSheet("""
            QTreeWidget {
                background-color: transparent;
                color: #f8fafc;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #1e293b;
            }
            QTreeWidget::item:hover {
                background-color: #334155;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: none;
            }
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                border-image: none;
                image: none;
            }
        """)
        layout.addWidget(self._project_tree)

        # 空状态提示
        self._empty_label = QLabel("暂无工程。通过菜单「文件」→「打开工程」或「新建工程」")
        self._empty_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 12px;")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._update_sidebar_empty_state()
        return sidebar

    def _connect_project_signals(self) -> None:
        """连接工程树节点的信号。"""
        # 树形结构使用 itemWidget 和 setItemWidget 管理自定义 widget
        pass  # 在添加节点时动态连接信号

    def _load_steps_from_md(self, node: dict) -> list[str]:
        """从工程 .md 文件读取处理步骤列表。"""
        from .project_file import find_project_path, load_project_md_full
        pdir = node.get("projectPath")
        pid = node.get("id")
        if not pdir or not pid:
            return []
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            return []
        data = load_project_md_full(project_path)
        if not data:
            return []
        steps_str = data.get("处理步骤", "").strip()
        if not steps_str:
            return []
        # 支持逗号或空格分隔
        steps = [s.strip() for s in steps_str.replace(",", " ").split() if s.strip()]
        return steps

    def _save_steps_to_md(self, node: dict, steps: list[str]) -> None:
        """将处理步骤保存到工程 .md 文件。"""
        from .project_file import find_project_path, load_project_md_full, write_project
        pdir = node.get("projectPath")
        pid = node.get("id")
        if not pdir or not pid:
            return
        project_path = find_project_path(Path(pdir), pid)
        if not project_path:
            return
        data = load_project_md_full(project_path)
        if not data:
            return
        data["处理步骤"] = " ".join(steps)
        try:
            write_project(project_path, data)
        except Exception:
            pass

    def _update_sidebar_empty_state(self) -> None:
        has_projects = len(self._projects) > 0
        self._project_tree.setVisible(has_projects)
        self._empty_label.setVisible(not has_projects)

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        placeholder = QWidget()
        pl_layout = QVBoxLayout(placeholder)
        pl_layout.setContentsMargins(24, 24, 24, 24)
        pl_label = QLabel("主内容区 — 选择左侧工程或进行数据处理；双击工程名称打开地图")
        pl_label.setStyleSheet("color: #94a3b8; font-size: 14px;")
        pl_layout.addWidget(pl_label)
        self._tab_widget.addTab(placeholder, "主内容")
        layout.addWidget(self._tab_widget)
        return content

    def _on_tab_close_requested(self, index: int) -> None:
        if index <= 0:
            return
        w = self._tab_widget.widget(index)
        pid = getattr(w, "_map_project_id", None) if w else None
        if pid and pid in self._map_tabs:
            del self._map_tabs[pid]
        self._tab_widget.removeTab(index)

    def _ensure_map_tab(self, node: dict, bbox: tuple[float, float, float, float] | None = None) -> TileMapWidget:
        """打开或复用该工程的地图 Tab；bbox 为 None 时从工程 .md 读取。保存后刷新工作区时传入新 bbox。"""
        pid = node.get("id", "")
        name = node.get("name", "地图")
        tab_title = f"地图 - {name}"
        if bbox is None:
            bbox = get_bbox_from_project(node)
        if pid in self._map_tabs:
            wrapper = self._map_tabs[pid]
            if self._tab_widget.indexOf(wrapper) >= 0:
                self._tab_widget.setCurrentWidget(wrapper)
                wrapper.set_bbox(bbox)
                wrapper.map_widget.viewport().update()
                return wrapper.map_widget
            else:
                del self._map_tabs[pid]
        wrapper = MapWithToolbar()
        wrapper._map_project_id = pid  # type: ignore[attr-defined]
        wrapper.set_bbox(bbox)
        self._tab_widget.addTab(wrapper, tab_title)
        self._tab_widget.setCurrentWidget(wrapper)
        self._map_tabs[pid] = wrapper
        return wrapper.map_widget

    @Slot()
    def _on_new_project(self) -> None:
        dlg = DefineProjectDialog(self)
        if dlg.exec() != DefineProjectDialog.DialogCode.Accepted:
            return
        result = dlg.get_result()
        if not result:
            return
        node = {
            "id": result["id"],
            "name": result["name"],
            "radarType": result["radar_type"],
            "projectPath": result["project_path"],
            "children": [],
        }
        self._projects.append(node)
        self._add_project_to_tree(node)
        self._update_sidebar_empty_state()
        self._select_project_in_tree(node["id"])
        self.statusBar().showMessage(f"已创建工程：{result['name']}")

    @Slot()
    def _on_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开工程",
            "",
            "项目文件 (*.md *.yaml);;所有文件 (*.*)",
        )
        if not path:
            return
        from .project_file import find_project_path, load_and_validate
        data, err = load_and_validate(path)
        if data is None:
            QMessageBox.warning(self, "打开工程失败", err)
            return
        node = {
            "id": data["项目id"],
            "name": data["项目名称"],
            "radarType": data["雷达数据类型"],
            "projectPath": data["项目完整路径"],
            "children": [],
        }
        existing = next((p for p in self._projects if p["id"] == node["id"]), None)
        if existing:
            self._select_project_in_tree(node["id"])
            self.statusBar().showMessage(f"工程已在列表中：{node['name']}")
            return
        self._projects.append(node)
        project_store.add_project_node(node)
        self._add_project_to_tree(node)
        self._update_sidebar_empty_state()
        self._select_project_in_tree(node["id"])
        project_store.set_current_project_path(node["projectPath"])
        self.statusBar().showMessage(f"已打开工程：{node['name']}")

    def _select_project_in_tree(self, project_id: str) -> None:
        """在树形结构中选中指定工程节点。"""
        root = self._project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            data = project_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "project":
                node = data.get("node")
                if node and node.get("id") == project_id:
                    self._project_tree.setCurrentItem(project_item)
                    self._selected_project_id = project_id
                    break

    def _add_project_to_tree(self, node: dict) -> None:
        """添加工程到树形结构，第一级为工程名称（带关闭按钮），第二级为处理步骤，第三级为数据。"""
        # 创建第一级节点（工程名称）
        project_item = QTreeWidgetItem(self._project_tree)
        project_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "node": node})
        project_item.setExpanded(True)
        
        # 设置自定义 widget（工程名称 + 关闭按钮）
        widget = ProjectItemWidget(node, self._project_tree)
        widget.close_clicked.connect(self._on_close_project)
        # 调整 widget 高度
        project_item.setSizeHint(0, QSize(0, 28))
        self._project_tree.setItemWidget(project_item, 0, widget)
        
        # 读取并添加处理步骤（第二级）
        steps = self._load_steps_from_md(node)
        for step in steps:
            step_item = QTreeWidgetItem(project_item)
            step_item.setText(0, step)
            step_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "step", "step_name": step, "project_node": node})
            # 第三级：暂无数据
            data_item = QTreeWidgetItem(step_item)
            data_item.setText(0, "暂无数据")
            data_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "data", "data_name": "暂无数据", "step_name": step, "project_node": node})
            data_item.setForeground(0, Qt.GlobalColor.gray)

    def _on_tree_context_menu(self, pos) -> None:
        """树形结构的右键菜单，根据节点类型显示不同操作。"""
        item = self._project_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        node_type = data.get("type")
        menu = QMenu(self)
        
        if node_type == "project":
            # 工程节点：显示修改、定义工作区、打开 Stack/时间序列（数据导入已整合进 Stack 流程配置）
            node = data.get("node")
            if not node:
                return
            edit_action = QAction(icon_edit(), "修改工程", self)
            edit_action.triggered.connect(lambda: self._on_edit_project(node))
            menu.addAction(edit_action)
            workspace_action = QAction(icon_workspace(), "定义工作区", self)
            workspace_action.triggered.connect(lambda: self._on_define_workspace(node))
            menu.addSeparator()
            stack_init_action = QAction(icon_refresh(), "Stack 流程初始化…", self)
            stack_init_action.setToolTip("打开配置对话框并执行初始化（生成 pipeline.json），未初始化或需重新配置时使用")
            stack_init_action.triggered.connect(lambda: self._on_open_stack_flow_config_for_project(node))
            menu.addAction(stack_init_action)
            stack_flow_action = QAction(icon_stack_flow(), "打开 Stack 流程", self)
            stack_flow_action.triggered.connect(lambda: self._on_open_stack_flow_for_project(node))
            menu.addAction(stack_flow_action)
            mintpy_init_action = QAction(icon_mintpy_config(), "时间序列参数配置…", self)
            mintpy_init_action.triggered.connect(lambda: self._on_open_mintpy_config_for_project(node))
            menu.addAction(mintpy_init_action)
            mintpy_flow_action = QAction(icon_mintpy_flow(), "打开时间序列分析", self)
            mintpy_flow_action.triggered.connect(lambda: self._on_open_mintpy_flow_for_project(node))
            menu.addAction(mintpy_flow_action)
        
        elif node_type == "data":
            # 数据节点：暂无操作
            pass
        
        if menu.actions():
            menu.exec(self._project_tree.mapToGlobal(pos))

    @Slot()
    def _on_edit_project(self, node: dict) -> None:
        dlg = EditProjectDialog(self, node)
        if dlg.exec() != EditProjectDialog.DialogCode.Accepted:
            return
        result = dlg.get_result()
        if not result:
            return
        # 更新内存与本地存储并刷新列表
        node = {
            "id": result["id"],
            "name": result["name"],
            "radarType": result["radarType"],
            "projectPath": result["projectPath"],
            "children": result.get("children", []),
        }
        for i, p in enumerate(self._projects):
            if p["id"] == result["id"]:
                self._projects[i] = node
                break
        project_store.update_project_node(node)
        self._refresh_project_list_ui()
        self._select_project_in_tree(result["id"])
        project_store.set_current_project_path(result["projectPath"])
        self.statusBar().showMessage(f"已保存项目：{result['name']}")

    @Slot()
    def _on_define_workspace(self, node: dict) -> None:
        dlg = DefineWorkspaceDialog(self, node)
        if dlg.exec() == DefineWorkspaceDialog.DialogCode.Accepted:
            self.statusBar().showMessage(f"已保存工作区：{node.get('name', '')}")
            new_bbox = getattr(dlg, "_saved_bbox", None)
            self._ensure_map_tab(node, bbox=new_bbox)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """树形节点双击事件。"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        node_type = data.get("type")
        if node_type == "project":
            node = data.get("node")
            if node:
                self._ensure_map_tab(node)
        # 步骤和数据节点的双击事件后续完善
    
    def _on_tree_item_selected(self) -> None:
        """树形节点选择事件。"""
        items = self._project_tree.selectedItems()
        if not items:
            return
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        node_type = data.get("type")
        if node_type == "project":
            node = data.get("node")
            if node and node.get("projectPath"):
                self._selected_project_id = node["id"]
                project_store.set_current_project_path(node["projectPath"])
                self.statusBar().showMessage(f"当前项目：{node['name']}")
        # 步骤和数据节点的选择事件后续完善

    @Slot()
    def _on_stack_flow(self) -> None:
        """打开 Stack 流程配置对话框（仅能从工程树右键「打开 Stack 流程」进入；菜单已移除）。"""
        default_path = None
        project_node = None
        if self._selected_project_id:
            for p in self._projects:
                if p.get("id") == self._selected_project_id:
                    default_path = p.get("projectPath")
                    project_node = p
                    break
        dlg = StackFlowConfigDialog(self, default_project_path=default_path, project_node=project_node)
        dlg.init_succeeded.connect(self._on_stack_flow_opened)
        dlg.show()

    def _find_project_node_for_stack_work_dir(self, work_dir: str) -> dict | None:
        """若 work_dir 位于某工程目录下，返回该工程节点。"""
        try:
            work = Path(work_dir).resolve().as_posix()
            for node in self._projects:
                pdir = (node.get("projectPath") or "").strip()
                if not pdir:
                    continue
                base = Path(pdir).resolve().as_posix()
                if work == base or work.startswith(base + "/") or work.startswith(base + "\\"):
                    return node
        except Exception:
            pass
        return None

    @Slot(str)
    def _on_stack_flow_opened(self, work_dir: str) -> None:
        """在内容区新 Tab 中打开流程界面；若 work_dir 属于某工程则写回 stack_work_dir。"""
        if not work_dir or not work_dir.strip():
            return
        work_dir = work_dir.strip()
        try:
            wd_resolved = str(Path(work_dir).resolve())
        except Exception:
            wd_resolved = os.path.normcase(os.path.normpath(work_dir))
        for ti in range(self._tab_widget.count()):
            w = self._tab_widget.widget(ti)
            if isinstance(w, StackFlowWidget):
                try:
                    ow = str(Path(w.get_work_dir()).resolve())
                except Exception:
                    ow = os.path.normcase(os.path.normpath(w.get_work_dir()))
                if ow == wd_resolved:
                    w.reload_from_disk()
                    self._tab_widget.setCurrentWidget(w)
                    self.statusBar().showMessage(
                        f"已刷新流程：{work_dir[:60]}…" if len(work_dir) > 60 else f"已刷新流程：{work_dir}"
                    )
                    self._save_stack_work_dir_to_project(work_dir)
                    return
        flow = StackFlowWidget(work_dir, self)
        flow.request_open_mintpy_config.connect(self._on_request_mintpy_config)
        flow.request_stack_flow_config.connect(self._on_request_stack_flow_config)
        tab_title = "Stack 流程"
        self._tab_widget.addTab(flow, tab_title)
        self._tab_widget.setCurrentWidget(flow)
        self.statusBar().showMessage(f"已打开流程：{work_dir[:60]}…" if len(work_dir) > 60 else f"已打开流程：{work_dir}")
        self._save_stack_work_dir_to_project(work_dir)

    @Slot(str)
    def _on_request_stack_flow_config(self, work_dir: str) -> None:
        """从流程页请求打开 Stack 配置（例如缺少 pipeline.json 时）。"""
        wd = (work_dir or "").strip()
        if not wd:
            return
        node = self._find_project_node_for_stack_work_dir(wd)
        pdir = (node.get("projectPath") if node else None) or None
        dlg = StackFlowConfigDialog(
            self,
            default_project_path=pdir,
            project_node=node,
            initial_work_dir=wd,
        )
        dlg.init_succeeded.connect(self._on_stack_flow_opened)
        dlg.show()

    def _on_open_stack_flow_config_for_project(self, node: dict) -> None:
        """工程右键：始终打开 Stack 配置对话框（预填工程中的 stack 工作目录）。"""
        from .project_file import find_project_path, load_project_md_full

        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return
        initial: str | None = None
        proj_path = find_project_path(Path(pdir), pid)
        if proj_path:
            data = load_project_md_full(proj_path) or {}
            initial = (data.get("stack_work_dir") or "").strip() or None
        dlg = StackFlowConfigDialog(
            self,
            default_project_path=pdir,
            project_node=node,
            initial_work_dir=initial,
        )
        dlg.init_succeeded.connect(self._on_stack_flow_opened)
        dlg.show()

    def _save_stack_work_dir_to_project(self, work_dir: str) -> None:
        """若 work_dir 位于某工程目录下，将该工程的 stack_work_dir 写入 YAML。"""
        try:
            work = Path(work_dir).resolve().as_posix()
            for node in self._projects:
                pdir = (node.get("projectPath") or "").strip()
                if not pdir:
                    continue
                base = Path(pdir).resolve().as_posix()
                if work == base or work.startswith(base + "/") or work.startswith(base + "\\"):
                    from .project_file import find_project_path, load_project_md_full, write_project
                    proj_path = find_project_path(Path(pdir), node.get("id", ""))
                    if not proj_path:
                        break
                    data = load_project_md_full(proj_path)
                    if data:
                        data["stack_work_dir"] = work_dir
                        write_project(proj_path, data)
                    break
        except Exception:
            pass

    def _save_mintpy_work_dir_to_project(self, work_dir: str) -> None:
        """若 work_dir 位于某工程目录下，将该工程的 mintpy_work_dir 写入 YAML。"""
        try:
            work = Path(work_dir).resolve().as_posix()
            for node in self._projects:
                pdir = (node.get("projectPath") or "").strip()
                if not pdir:
                    continue
                base = Path(pdir).resolve().as_posix()
                if work == base or work.startswith(base + "/") or work.startswith(base + "\\"):
                    from .project_file import find_project_path, load_project_md_full, write_project
                    proj_path = find_project_path(Path(pdir), node.get("id", ""))
                    if not proj_path:
                        break
                    data = load_project_md_full(proj_path)
                    if data:
                        data["mintpy_work_dir"] = work_dir
                        write_project(proj_path, data)
                    break
        except Exception:
            pass

    @Slot(str)
    def _on_request_mintpy_config(self, stack_work_dir: str) -> None:
        """从 Stack 流程进入时间序列：自动推导目录，后台初始化，直接打开 Flow。"""
        if not stack_work_dir or not stack_work_dir.strip():
            return
        stack_work_dir = stack_work_dir.strip()
        mintpy_dir = os.path.join(stack_work_dir, "mintpy")
        self._auto_init_and_open_mintpy(mintpy_dir, stack_work_dir)

    @Slot()
    def _on_mintpy_flow(self) -> None:
        """打开时间序列配置对话框；初始化成功或点击「打开流程界面」时在 Tab 中打开时间序列流程。"""
        dlg = MintPyConfigDialog(self, default_stack_work_dir=None)
        dlg.init_succeeded.connect(self._on_mintpy_flow_opened)
        dlg.show()

    @Slot(str)
    def _on_mintpy_flow_opened(self, work_dir: str) -> None:
        """在内容区新 Tab 中打开时间序列流程界面；若 work_dir 属于某工程则写回 mintpy_work_dir。"""
        if not work_dir or not work_dir.strip():
            return
        work_dir = work_dir.strip()
        flow = MintPyFlowWidget(work_dir, self)
        tab_title = "时间序列流程"
        self._tab_widget.addTab(flow, tab_title)
        self._tab_widget.setCurrentWidget(flow)
        self.statusBar().showMessage(f"已打开时间序列流程：{work_dir[:60]}…" if len(work_dir) > 60 else f"已打开时间序列流程：{work_dir}")
        self._save_mintpy_work_dir_to_project(work_dir)

    def _auto_init_and_open_mintpy(self, mintpy_dir: str, stack_work_dir: str) -> None:
        """自动初始化 MintPy 工作目录并在完成后打开 Flow Tab。"""
        from .widgets.mintpy_quick_setup_dialog import MintPyInitWorker

        self.statusBar().showMessage(f"正在初始化 MintPy 工作目录: {mintpy_dir}")

        def on_finished(result: dict) -> None:
            worker.deleteLater()
            if result.get("success"):
                wd = result.get("work_dir", mintpy_dir)
                self._on_mintpy_flow_opened(wd)
            else:
                err = result.get("error_message", "未知错误")
                self.statusBar().showMessage("MintPy 初始化失败")
                QMessageBox.warning(self, "初始化失败", f"MintPy 初始化失败:\n{err}")

        worker = MintPyInitWorker(mintpy_dir, stack_work_dir, stack_work_dir, self)
        worker.finished_with_result.connect(on_finished)
        worker.start()

    def _on_open_stack_flow_for_project(self, node: dict) -> None:
        """从工程节点打开 Stack：仅当工作目录存在且已生成 pipeline.json 时直接打开流程页，否则打开配置对话框。"""
        from .project_file import find_project_path, load_project_md_full

        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return
        proj_path = find_project_path(Path(pdir), pid)
        if proj_path:
            data = load_project_md_full(proj_path)
            work_dir = (data.get("stack_work_dir") or "").strip()
            if work_dir and Path(work_dir).exists():
                pipeline_json = os.path.join(work_dir, "pipeline.json")
                if os.path.isfile(pipeline_json):
                    self._on_stack_flow_opened(work_dir)
                    return
        dlg = StackFlowConfigDialog(self, default_project_path=pdir, project_node=node)
        dlg.init_succeeded.connect(self._on_stack_flow_opened)
        dlg.show()

    def _on_open_mintpy_flow_for_project(self, node: dict) -> None:
        """
        从工程节点打开时间序列分析（快速入口）。

        三级自动推导：
        1. mintpy_work_dir 已保存且目录存在 → 直接打开 Flow Tab
        2. stack_work_dir 已保存 → 自动推导 mintpy 目录，后台初始化，完成后打开
        3. 都没有 → 弹出精简版目录选择对话框
        """
        from .project_file import find_project_path, load_project_md_full
        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return

        proj_path = find_project_path(Path(pdir), pid)
        data = load_project_md_full(proj_path) if proj_path else {}

        # 情况1: 已有 mintpy_work_dir 且目录存在
        mintpy_dir = (data.get("mintpy_work_dir") or "").strip()
        if mintpy_dir and Path(mintpy_dir).exists():
            self._on_mintpy_flow_opened(mintpy_dir)
            return

        # 情况2: 有 stack_work_dir → 自动推导并初始化
        stack_dir = (data.get("stack_work_dir") or "").strip()
        if stack_dir:
            mintpy_dir = os.path.join(stack_dir, "mintpy")
            self._auto_init_and_open_mintpy(mintpy_dir, stack_dir)
            return

        # 情况3: 都没有 → 弹出精简对话框
        dlg = MintPyQuickSetupDialog(self, stack_work_dir=None)
        dlg.setup_complete.connect(self._on_mintpy_flow_opened)
        dlg.exec()

    def _on_open_mintpy_config_for_project(self, node: dict) -> None:
        """
        从工程节点打开时间序列初始化/配置对话框（即使已初始化也可重新初始化）。
        若工程已有 stack_work_dir，则预填，便于自动填充 load 路径。
        """
        from .project_file import find_project_path, load_project_md_full
        pdir = node.get("projectPath") or ""
        pid = node.get("id") or ""
        if not pdir or not pid:
            return
        default_stack_work_dir = None
        proj_path = find_project_path(Path(pdir), pid)
        if proj_path:
            data = load_project_md_full(proj_path)
            swd = (data.get("stack_work_dir") or "").strip()
            if swd:
                default_stack_work_dir = swd
        dlg = MintPyConfigDialog(self, default_stack_work_dir=default_stack_work_dir)
        dlg.init_succeeded.connect(self._on_mintpy_flow_opened)
        dlg.show()

    def _on_step_added(self, project_node: dict) -> None:
        """处理步骤添加后的回调，刷新树形结构。"""
        # 刷新当前工程的树形节点
        self._refresh_project_tree_item(project_node)
    
    def _refresh_project_tree_item(self, node: dict) -> None:
        """刷新指定工程的树形节点（重新加载步骤）。"""
        project_id = node.get("id")
        if not project_id:
            return
        # 查找对应的树形节点
        root = self._project_tree.invisibleRootItem()
        for i in range(root.childCount()):
            project_item = root.child(i)
            data = project_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "project":
                proj_node = data.get("node")
                if proj_node and proj_node.get("id") == project_id:
                    # 保存展开状态
                    was_expanded = project_item.isExpanded()
                    # 清空子节点
                    project_item.takeChildren()
                    # 重新加载步骤
                    steps = self._load_steps_from_md(node)
                    for step in steps:
                        step_item = QTreeWidgetItem(project_item)
                        step_item.setText(0, step)
                        step_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "step", "step_name": step, "project_node": node})
                        # 第三级：暂无数据
                        data_item = QTreeWidgetItem(step_item)
                        data_item.setText(0, "暂无数据")
                        data_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "data", "data_name": "暂无数据", "step_name": step, "project_node": node})
                        data_item.setForeground(0, Qt.GlobalColor.gray)
                    # 恢复展开状态
                    project_item.setExpanded(was_expanded)
                    break

    @Slot(dict)
    def _on_close_project(self, node: dict) -> None:
        """关闭工程：从列表中移除并删除持久化数据。"""
        project_name = node.get("name", "该工程")
        reply = QMessageBox.question(
            self,
            "确认关闭",
            f"是否关闭工程「{project_name}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 从内存列表中移除
        project_id = node.get("id")
        self._projects = [p for p in self._projects if p.get("id") != project_id]
        
        # 关闭对应的地图 Tab
        if project_id in self._map_tabs:
            wrapper = self._map_tabs[project_id]
            index = self._tab_widget.indexOf(wrapper)
            if index >= 0:
                self._tab_widget.removeTab(index)
            del self._map_tabs[project_id]
        
        # 从持久化存储中移除
        from .project_store import save_projects
        save_projects(self._projects)
        
        # 刷新 UI
        self._refresh_project_list_ui()
        
        # 清除当前选中状态
        if self._selected_project_id == project_id:
            self._selected_project_id = None
            self.statusBar().showMessage(f"已关闭工程：{project_name}")
    
    def _refresh_project_list_ui(self) -> None:
        self._project_tree.clear()
        for node in self._projects:
            self._add_project_to_tree(node)
        self._update_sidebar_empty_state()

    def _restore_current_project(self) -> None:
        """启动时根据 desktop_current_project.txt 恢复当前选中工程。"""
        current_path = project_store.get_current_project_path()
        if not current_path:
            return
        current_path = current_path.strip().replace("/", "\\").rstrip("\\/")
        for node in self._projects:
            p = (node.get("projectPath") or "").strip().replace("/", "\\").rstrip("\\/")
            if p == current_path:
                self._select_project_in_tree(node["id"])
                break
