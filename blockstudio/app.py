from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import traceback
import uuid
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QStandardPaths
from PySide6.QtGui import QAction,QKeySequence,QPixmap,QImage,QIcon,QColor,QShortcut,QFontDatabase
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QSplitter,QListWidget,QListWidgetItem,QComboBox,QFileDialog,QMessageBox,QInputDialog,QProgressBar,
 QToolBar,QStackedWidget,QTabWidget,QAbstractItemView,QScrollArea,QDialog,QSpinBox,QFormLayout,QCheckBox,QMenu,QLineEdit,QTextEdit,QPlainTextEdit)
from .qt_runtime import prepare_qt
prepare_qt()
from .project import Project,blank_board,uid,render_frame
from .imaging import read_image,export_image,from_qimage,to_qimage
from .tools import TOOLS,apply_tool,resolve_input
from .editor import PreviewWorker
from .history import History
from . import trash
from .metadata_widgets import MetadataDialog
from .workflow import execute_chain,preflight
from .workflow_widgets import WorkflowEditor
from .canvas import WorkView,PhotoItem,FrameItem
from .widgets import ToolPanel,ImportDialog,ExportDialog,WorkflowDialog,button

STYLE='''
QWidget { color:#d5d8d7; background:#202325; font-family:"Helvetica Neue"; font-size:12px; }
QMainWindow,QDialog { background:#202325; }
QToolBar { background:#1c1f21; border:0; border-bottom:1px solid #383c3e; padding:8px; spacing:8px; }
QToolButton,QPushButton { background:#303538; border:1px solid #42484b; border-radius:5px; padding:7px 10px; }
QPushButton:hover,QToolButton:hover { background:#41484b; }
QPushButton:disabled,QToolButton:disabled { color:#717779; background:#282d2f; }
QWidget#toolRail { background:#1c2227; }
QPushButton#toolEntry { text-align:left; padding:9px 12px; }
QPushButton#toolEntry:hover { background:#344e63; border-color:#6e8ca5; }
QPushButton#primary { background:#829fb9; color:#242729; border:0; font-weight:600; padding:10px; }
QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QPlainTextEdit { background:#292e31; border:1px solid #42484b; border-radius:4px; padding:5px; min-height:21px; }
QComboBox QAbstractItemView { background:#292e31; selection-background-color:#344654; }
QListWidget { background:#202325; border:0; outline:0; }
QListWidget::item { padding:7px; border-radius:3px; }
QListWidget::item:selected { background:#344654; color:#c4d6e5; }
QLabel#muted { color:#8e989a; font-size:11px; }
QLabel#sectionTitle { font-size:16px; font-weight:600; padding-bottom:5px; }
QLabel#brand { font-size:20px; color:#eeeae2; font-weight:600; padding:4px 16px 4px 5px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#202325; color:#919b9d; padding:10px 16px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#b4cbdc; border-bottom:2px solid #829fb9; }
QSlider::groove:horizontal { height:4px; background:#40484c; border-radius:2px; }
QSlider::sub-page:horizontal { background:#829fb9; border-radius:2px; }
QSlider::handle:horizontal { background:#a7bfd2; border:1px solid #6e8ca5; width:13px; margin:-5px 0; border-radius:6px; }
QSlider:focus { border:1px solid #64849e; border-radius:3px; }
QScrollArea { border:0; }
QStatusBar { background:#1c1f21; color:#98a1a3; }
QProgressBar { border:0; background:#343a3d; max-height:8px; min-width:160px; } QProgressBar::chunk { background:#829fb9; }
QSplitter::handle { background:#363c3e; width:1px; }
QCheckBox { spacing:8px; padding:3px 0; }
QScrollBar:vertical { background:#202325; width:8px; margin:0; } QScrollBar::handle:vertical { background:#525b5f; border-radius:4px; min-height:25px; } QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QWidget:focus { selection-background-color:#344e63; }
QMenu { background:#282d2f; border:1px solid #4a5255; } QMenu::item:selected { background:#344654; }
'''


class Job(QThread):
    progress=Signal(int,int,str)
    result=Signal(object)
    failed=Signal(str)
    def __init__(self,fn):super().__init__();self.fn=fn;self.cancel=threading.Event()
    def run(self):
        try:self.result.emit(self.fn(self))
        except Exception as e:self.failed.emit(f'{e}\n\n{traceback.format_exc()}')


class Window(QMainWindow):
    def __init__(self,session_base=None):
        super().__init__();self.setWindowTitle('PostStudio · 图像取样工作台');self.resize(1320,820)
        self.session_base=Path(session_base or (Path.home()/'Library/Application Support/BlockStudio/Block Studio/sessions'))
        self.session_base.mkdir(parents=True,exist_ok=True)
        self.project=Project(self.session_base/uid());self.board_id=self.project.data['boards'][0]['id']
        self.dirty=False;self.job=None;self.edit_source=None;self.refreshing=False;self.preview_key=None;self.preview_pixels=None
        self.editor_selection=[];self.editor_inputs=[];self.editor_worker=None;self.preview_generation=0;self.editor_loading=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(700);self.timer.timeout.connect(self.checkpoint)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(False);self.preview_timer.setInterval(24);self.preview_timer.timeout.connect(self.update_preview)
        self.refine_timer=QTimer(self);self.refine_timer.setSingleShot(True);self.refine_timer.setInterval(220);self.refine_timer.timeout.connect(self.refine_preview)
        self.preview_floor=0;self.preview_displayed=-1;self.preview_exact=False;self.retiring_workers=[];self.preview_requested=-1
        self.history=History(self.project.data);self.history_loading=False;self.tool_history=None
        self.history_timer=QTimer(self);self.history_timer.setSingleShot(True);self.history_timer.setInterval(240);self.history_timer.timeout.connect(self.record_tool_history)
        self.build_ui();self.refresh_all();self.bind_shortcuts()
        self.undo_shortcut=QShortcut(QKeySequence("Ctrl+Z"),self,activated=lambda:self.undo_state(-1))
        self.redo_shortcut=QShortcut(QKeySequence("Ctrl+Shift+Z"),self,activated=lambda:self.undo_state(1))

    @property
    def board(self):return next(b for b in self.project.data['boards'] if b['id']==self.board_id)

    def build_ui(self):
        self.toolbar=QToolBar();self.toolbar.setMovable(False);self.addToolBar(self.toolbar)
        brand=QLabel('PostStudio');brand.setObjectName('brand');self.toolbar.addWidget(brand)
        for text,fn in [('新建',self.new_project),('打开',self.open_project),('保存',self.save_project),('导入图像',self.import_dialog)]:
            self.toolbar.addWidget(button(text,fn))
        self.toolbar.addSeparator();self.toolbar.addWidget(button('框出作品',self.start_frame));self.toolbar.addWidget(button('适合视图',self.fit));self.toolbar.addWidget(button('导出',self.export_selected))
        self.toolbar.addSeparator()
        self.title_label=QLabel('未命名项目');self.title_label.setObjectName('muted');self.toolbar.addWidget(self.title_label)
        self.pages=QStackedWidget();self.setCentralWidget(self.pages)
        split=QSplitter();self.workspace=split;self.pages.addWidget(split)
        self.sidebar=QWidget();self.sidebar.setMinimumWidth(190);self.sidebar.setMaximumWidth(310)
        side=QVBoxLayout(self.sidebar);side.setContentsMargins(15,18,15,12);side.setSpacing(12)
        self.tabs=QTabWidget();side.addWidget(self.tabs)
        boards_page=QWidget();bl=QVBoxLayout(boards_page);bl.setContentsMargins(0,6,0,0)
        self.boards=QListWidget();self.boards.currentRowChanged.connect(self.change_board);bl.addWidget(self.boards)
        bl.addWidget(button('＋ 新画布',self.add_board));bl.addWidget(button('重命名画布',self.rename_board));bl.addWidget(button('删除画布',self.delete_board))
        self.boards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.boards.customContextMenuRequested.connect(self.board_context)
        self.tabs.addTab(boards_page,'画布')
        assets_page=QWidget();al=QVBoxLayout(assets_page);al.setContentsMargins(0,6,0,0)
        self.assets=QListWidget();self.assets.setIconSize(QSize(100,70));self.assets.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.assets.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.assets.customContextMenuRequested.connect(self.asset_context)
        self.assets.itemSelectionChanged.connect(self.asset_selection);al.addWidget(self.assets)
        al.addWidget(button('将所选放入当前画布',self.place_assets));al.addWidget(button('删除所选图像',self.delete_assets));al.addWidget(button('照片 / 胶片资料',self.edit_metadata));self.tabs.addTab(assets_page,'总览')
        side.addWidget(button('项目回收站',self.show_trash))
        self.count=QLabel();self.count.setObjectName('muted');side.addWidget(self.count)
        side.addWidget(QLabel('参数预设'));self.presets=QComboBox();side.addWidget(self.presets)
        pr=QHBoxLayout();pr.addWidget(button('打开调整',self.load_preset));pr.addWidget(button('保存',self.save_preset));side.addLayout(pr)
        side.addWidget(button('应用预设到所选',self.apply_preset));side.addWidget(button('管理预设',lambda:self.manage_saved('presets')))
        side.addWidget(QLabel('步骤工作流'));self.workflows=QComboBox();side.addWidget(self.workflows)
        wr=QHBoxLayout();wr.addWidget(button('编辑',self.edit_workflow));wr.addWidget(button('运行',self.run_workflow));side.addLayout(wr)
        side.addWidget(button('＋ 新工作流',lambda:self.edit_workflow(new=True)))
        side.addWidget(button('管理工作流',lambda:self.manage_saved('workflows')))
        hint=QLabel('滚轮缩放 · 空格拖动平移\nShift 多选 · 拖右下角缩放\n⌘S 保存 · ⌘I 导入');hint.setObjectName('muted');hint.setWordWrap(True);side.addWidget(hint)
        side_scroll=QScrollArea();side_scroll.setWidgetResizable(True);side_scroll.setWidget(self.sidebar);side_scroll.setMinimumWidth(220);split.addWidget(side_scroll)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(0,0,0,0);cl.setSpacing(0)
        self.contextbar=QWidget();cr=QHBoxLayout(self.contextbar);cr.setContentsMargins(16,8,16,8)
        self.selection_label=QLabel('导入图像，开始自由摆放');self.selection_label.setObjectName('muted');cr.addWidget(self.selection_label,1)
        self.versions=QComboBox();self.versions.setMinimumWidth(180);self.versions.currentIndexChanged.connect(self.switch_version);cr.addWidget(self.versions)
        self.split_button=button('拆分组合',self.split_selected);cr.addWidget(self.split_button);cr.addWidget(button('重新编辑',self.reload_step));self.remove_button=button('移出画布',self.remove_placements);cr.addWidget(self.remove_button);cl.addWidget(self.contextbar)
        self.view=WorkView();self.canvas_pages=QStackedWidget();cl.addWidget(self.canvas_pages,1);self.canvas_pages.addWidget(self.view)
        self.overview=QListWidget();self.overview.setViewMode(QListWidget.ViewMode.IconMode);self.overview.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.overview.setMovement(QListWidget.Movement.Static);self.overview.setIconSize(QSize(180,135));self.overview.setGridSize(QSize(216,196));self.overview.setSpacing(12);self.overview.setWordWrap(True)
        self.overview.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.canvas_pages.addWidget(self.overview)
        self.overview.itemSelectionChanged.connect(self.overview_selection);self.overview.itemDoubleClicked.connect(lambda _:self.reload_step())
        self.overview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.overview.customContextMenuRequested.connect(lambda pos:self.asset_context(pos,self.overview))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.view.customContextMenuRequested.connect(self.canvas_context)
        self.tabs.currentChanged.connect(self.workspace_mode)
        self.view.scene().selectionChanged.connect(self.selection_changed)
        self.view.frameCreated.connect(self.create_frame);self.view.filesDropped.connect(self.import_paths);self.view.changed.connect(self.mark_dirty)
        split.addWidget(center)
        self.tool_rail=QWidget();self.tool_rail.setObjectName('toolRail');self.tool_rail.setFixedWidth(160)
        rail=QVBoxLayout(self.tool_rail);rail.setContentsMargins(14,20,14,16);rail.setSpacing(10)
        title=QLabel('创作工具');title.setObjectName('sectionTitle');rail.addWidget(title)
        hint=QLabel('选中图像，点击工具');hint.setObjectName('muted');hint.setWordWrap(True);rail.addWidget(hint);rail.addSpacing(8)
        self.tool_buttons={}
        for tool_id,tool in TOOLS.items():
            entry=button(tool.label,lambda checked=False,key=tool_id:self.open_tool(tool_id=key))
            entry.setObjectName('toolEntry');entry.setMinimumHeight(40);entry.setToolTip('处理所选图像 · '+tool.label)
            rail.addWidget(entry);self.tool_buttons[tool_id]=entry
        rail.addStretch();split.addWidget(self.tool_rail)
        split.setCollapsible(2,False);split.setStretchFactor(1,1);split.setSizes([225,805,160])
        self.panel=ToolPanel();self.panel.changed.connect(self.schedule_preview);self.panel.applyRequested.connect(self.apply_current)
        self.editor_page=QWidget();editor_layout=QVBoxLayout(self.editor_page);editor_layout.setContentsMargins(0,0,0,0);editor_layout.setSpacing(0)
        header=QWidget();header_layout=QHBoxLayout(header);header_layout.setContentsMargins(18,12,18,12)
        header_layout.addWidget(button('← 返回画布',self.leave_editor));self.editor_title=QLabel('画布 / 分块取样');self.editor_title.setObjectName('sectionTitle');header_layout.addWidget(self.editor_title,1)
        self.source_mode=QComboBox();self.source_mode.addItems(['修改已有步骤（默认）','在当前产物上追加处理']);self.source_mode.currentIndexChanged.connect(self.change_source_mode);header_layout.addWidget(self.source_mode)
        editor_layout.addWidget(header)
        content=QSplitter();editor_layout.addWidget(content,1)
        preview_area=QWidget();pv=QVBoxLayout(preview_area);pv.setContentsMargins(16,10,16,14);pv.setSpacing(9)
        self.editor_source=QLabel();self.editor_source.setObjectName('muted');self.editor_source.setWordWrap(True);pv.addWidget(self.editor_source)
        pv.addWidget(self.panel.preview,1)
        actions=QHBoxLayout();actions.setSpacing(14);self.move_mode=QComboBox();self.move_mode.addItems(['拖动整组网格','拖动单个取样块']);self.move_mode.currentIndexChanged.connect(self.change_move_mode);actions.addWidget(self.move_mode)
        self.compare=QCheckBox('查看输入图');self.compare.toggled.connect(self.compare_source);actions.addWidget(self.compare)
        self.grid_toggle=QCheckBox('取样边框');self.grid_toggle.setChecked(True);self.grid_toggle.toggled.connect(self.grid_changed);actions.addWidget(self.grid_toggle)
        self.reset_blocks_button=button('重置单块移动',self.reset_blocks);actions.addWidget(self.reset_blocks_button);actions.addStretch();pv.addLayout(actions)
        self.preview_status=QLabel('拖动改变取样位置 · 方向键 1 px · Shift＋方向键 10 px');self.preview_status.setObjectName('muted');pv.addWidget(self.preview_status)
        content.addWidget(preview_area)
        controls=QWidget();controls.setMinimumWidth(300);controls.setMaximumWidth(380);control_layout=QVBoxLayout(controls);control_layout.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.panel);control_layout.addWidget(scroll,1)
        footer=QWidget();footer_layout=QVBoxLayout(footer);footer_layout.setContentsMargins(18,8,18,14)
        self.reedit_target=None
        self.save_revision_button=button('保存修改 · 返回工作台',self.save_revision);self.save_revision_button.hide();footer_layout.addWidget(self.save_revision_button)
        self.revision_note=QLabel();self.revision_note.setObjectName('muted');self.revision_note.setWordWrap(True);self.revision_note.hide();footer_layout.addWidget(self.revision_note)
        footer_layout.addWidget(self.panel.mode);footer_layout.addWidget(button('保存当前参数为预设',self.save_preset));footer_layout.addWidget(self.panel.apply);control_layout.addWidget(footer)
        content.addWidget(controls);content.setStretchFactor(0,1);content.setSizes([940,330])
        self.pages.addWidget(self.editor_page)
        self.panel.tool.currentIndexChanged.connect(self.editor_tool_changed)
        self.panel.watermark.resourceRequested.connect(self.import_watermark)
        self.panel.preview.watermarkDragged.connect(self.move_watermark)
        self.panel.preview.pickedPosition.connect(self.pick_palette_color)
        self.cancel_pick=button('点击图像取色 · Esc 取消',self.panel.cancel_pick);pv.addWidget(self.cancel_pick,0,Qt.AlignmentFlag.AlignRight);self.cancel_pick.hide();self.panel.pickModeChanged.connect(self.cancel_pick.setVisible)
        for control in (self.compare,self.grid_toggle,self.move_mode):control.setMinimumWidth(control.sizeHint().width()+20)
        self.escape_shortcut=QShortcut(QKeySequence('Escape'),self.editor_page,activated=self.panel.cancel_pick)
        self.panel.preview.offsetDragged.connect(self.move_grid);self.panel.preview.blockDragged.connect(self.move_block);self.panel.preview.nudge.connect(self.nudge_sampling)
        self.progress=QProgressBar();self.progress.hide();self.statusBar().addPermanentWidget(self.progress)
        self.cancel_button=button('取消任务',self.cancel_job);self.cancel_button.hide();self.statusBar().addPermanentWidget(self.cancel_button)
        self.statusBar().showMessage('本地离线 · 16 位中间产物 · 手动执行，不联动已有结果')

    def bind_shortcuts(self):
        for seq,fn in [('Ctrl+S',self.save_project),('Ctrl+Shift+S',lambda:self.save_project(as_new=True)),('Ctrl+O',self.open_project),('Ctrl+I',self.import_dialog),('Ctrl+N',self.new_project),('Ctrl+E',self.export_selected),('Ctrl+0',self.fit)]:
            a=QAction(self);a.setShortcut(QKeySequence(seq));a.triggered.connect(fn);self.addAction(a)
        menu=self.menuBar().addMenu('项目')
        for title,fn in [('打开恢复副本…',self.recover_dialog),('另存为…',lambda:self.save_project(as_new=True)),('导入所选的全尺寸原文件',self.restore_original),('重命名项目',self.rename_project)]:
            a=menu.addAction(title);a.triggered.connect(fn)
        edit=self.menuBar().addMenu('画布')
        a=edit.addAction('修改作品框尺寸…');a.triggered.connect(self.edit_frame)
        a=edit.addAction('所选置于顶层');a.triggered.connect(self.bring_front)
        helpmenu=self.menuBar().addMenu('帮助');a=helpmenu.addAction('使用说明');a.triggered.connect(self.show_help)

    def show_help(self):
        QMessageBox.information(self,'使用说明','导入后，拖动照片摆放；拖右下角缩放。\n滚轮缩放视图，空格＋拖动平移，Shift 多选。\n\n在画布选择图像，点击右侧工具按钮进入二级页面。滑块或精确输入调整参数；拖动整组网格或单块，方向键微调。生成修改稿后返回画布。\n选择处理结果，点击“重新编辑”可回到它的输入与参数。\n\n“框出作品”后在画布拖出范围，选择作品框并导出。\n预设保存单工具参数，工作流保存有序步骤。\n\n项目完全保存在本机。窗口关闭前可保存，异常中断可恢复。')
    def open_tool(self,checked=False,tool_id=None,append=False):
        if self.job:return
        ids=self.selected_ids()
        if not ids:QMessageBox.information(self,'选择图像','请先在画布或总览中选择要处理的图像。');return
        if len(ids)>10:QMessageBox.information(self,'批处理','一次请选择最多 10 张图像。');return
        self.reedit_target=None;self.editor_selection=list(ids);self.editor_loading=True
        self.panel.tool.setCurrentIndex(self.panel.tool.findData(tool_id or self.panel.tool.currentData()))
        self.source_mode.blockSignals(True);self.source_mode.setCurrentIndex(1 if append else 0);self.source_mode.blockSignals(False)
        self.editor_loading=False;self.pages.setCurrentWidget(self.editor_page);self.toolbar.hide()
        self.compare.setChecked(False);self.panel.preview.selected_block=None
        self.configure_editor(load_params=True)
        self.tool_history=History(self.panel.step());self.history_timer.stop()
        self.update_editor_actions()

    def update_editor_actions(self):
        editing=self.pages.currentWidget()==self.editor_page
        for action in self.actions():action.setEnabled(not editing and not self.job)
        self.menuBar().setEnabled(not editing and not self.job)

    def configure_editor(self,load_params=False):
        if not self.editor_selection:return
        self.panel.cancel_pick()
        tool_id=self.panel.tool.currentData();append=self.source_mode.currentIndex()==1
        pairs=[resolve_input(self.project,id,tool_id,append) for id in self.editor_selection]
        self.editor_inputs=[source for source,_ in pairs];self.edit_source=self.editor_inputs[0]
        self.editor_loading=True
        source_asset=self.project.asset(self.edit_source);self.panel.configure_dimensions(source_asset['width'],source_asset['height'])
        if load_params:
            step=pairs[0][1] or dict(tool=tool_id,version=1,params=copy.deepcopy(TOOLS[tool_id].defaults))
            self.panel.load_step(step)
        a=self.project.asset(self.edit_source);self.panel.configure_dimensions(a['width'],a['height']);self.panel.load_candidates(self.project.data['assets'])
        self.panel.preview.pick_image=QImage(str(self.project.root/a['thumb']))
        self.panel.preview.image=QImage();self.preview_generation+=1;self.preview_floor=self.preview_generation;self.preview_displayed=-1;self.preview_exact=False
        revised=sum(source!=selected for source,selected in zip(self.editor_inputs,self.editor_selection))
        mode='修改已有步骤' if revised else '新建处理步骤'
        if append:mode='明确追加处理'
        self.editor_title.setText('画布 / '+TOOLS[tool_id].label)
        batch=f" · 已选 {len(self.editor_inputs)} 张，预览第一张" if len(self.editor_inputs)>1 else ''
        self.editor_source.setText(f"{mode} · 输入：{a['name']} · {a['width']} × {a['height']} px{batch}")
        self.tool_history=History(self.panel.step());self.history_timer.stop()
        self.editor_loading=False;self.panel.preview.drag_enabled=tool_id=='sample';self.panel.preview.watermark_mode=tool_id=='watermark'
        self.move_mode.setVisible(tool_id=='sample');self.grid_toggle.setVisible(tool_id=='sample');self.reset_blocks_button.setVisible(tool_id=='sample')
        self.panel.preview.setCursor(Qt.CursorShape.OpenHandCursor if tool_id=='sample' else Qt.CursorShape.ArrowCursor)
        self.update_revision_action();self.schedule_preview()

    def editor_tool_changed(self):
        if self.editor_loading or not self.editor_selection:return
        self.panel.preview.selected_block=None;self.configure_editor(load_params=True)
    def change_source_mode(self):
        if self.editor_loading or not self.editor_selection:return
        self.configure_editor(load_params=False)
    def change_move_mode(self,index):
        self.panel.preview.move_mode='block' if index else 'grid';self.panel.preview.selected_block=None;self.panel.preview.update()
    def compare_source(self,checked):self.panel.preview.show_source=checked;self.panel.preview.update()
    def grid_changed(self,checked):self.panel.preview.show_grid=checked;self.panel.preview.update()
    def reset_blocks(self):self.panel.moved_blocks={};self.panel.preview.selected_block=None;self.schedule_preview()
    def move_grid(self,x,y):
        self.panel.spins['offset_x'].setValue(x);self.panel.spins['offset_y'].setValue(y)
    def move_block(self,key,x,y):
        self.panel.moved_blocks[key]=[int(x),int(y)];self.schedule_preview()
    def nudge_sampling(self,dx,dy):
        if self.panel.tool.currentData()=='watermark':self.move_watermark(dx,dy);return
        preview=self.panel.preview
        if preview.move_mode=='block':
            if preview.selected_block:
                x,y=self.panel.moved_blocks.get(preview.selected_block,(0,0));self.move_block(preview.selected_block,x+dx,y+dy)
        else:self.move_grid(self.panel.spins['offset_x'].value()+dx,self.panel.spins['offset_y'].value()+dy)
    def stop_preview(self):
        self.preview_timer.stop();self.refine_timer.stop();self.preview_generation+=1;self.preview_floor=self.preview_generation
        if self.editor_worker:
            worker=self.editor_worker;self.editor_worker=None;worker.stop()
            self.retiring_workers.append(worker)
            worker.finished.connect(lambda w=worker:self.release_preview_worker(w))
            if worker.isFinished():self.release_preview_worker(worker)
    def release_preview_worker(self,worker):
        if worker in self.retiring_workers:self.retiring_workers.remove(worker);worker.deleteLater()
    def leave_editor(self):
        if self.job:return
        self.panel.cancel_pick();self.history_timer.stop();self.stop_preview();self.pages.setCurrentWidget(self.workspace);self.toolbar.show()
        self.editor_selection=[];self.editor_inputs=[];self.edit_source=None;self.panel.preview.picking=False
        self.update_editor_actions();self.selection_changed()
        self.statusBar().showMessage('已返回画布；只有“生成修改稿”才会新增产物。')
    def fit(self):self.view.fit_content()
    def start_frame(self):self.tabs.setCurrentIndex(0);self.view.start_frame();self.statusBar().showMessage('在画布上拖出要导出的作品范围。')
    def checkpoint(self):
        try:self.project.checkpoint()
        except Exception as e:self.statusBar().showMessage('恢复副本保存失败：'+str(e))
    def mark_dirty(self):
        self.dirty=True;self.timer.start()
        if not self.history_loading:self.history.record(self.project.data)
        self.title_label.setText(self.project.data['name']+' •')

    def selected_items(self):return [i for i in self.view.scene().selectedItems() if isinstance(i,PhotoItem)]
    def selected_ids(self):
        if self.tabs.currentIndex()==1:return [i.data(Qt.ItemDataRole.UserRole) for i in self.assets.selectedItems()]
        return list(dict.fromkeys(i.asset['id'] for i in self.selected_items()))
    def active_id(self):
        return self.editor_inputs[0] if self.editor_inputs else None
    def sync_asset_selection(self,source,target):
        ids={i.data(Qt.ItemDataRole.UserRole) for i in source.selectedItems()}
        target.blockSignals(True)
        for n in range(target.count()):target.item(n).setSelected(target.item(n).data(Qt.ItemDataRole.UserRole) in ids)
        target.blockSignals(False)
    def asset_selection(self):
        if self.refreshing:return
        self.sync_asset_selection(self.assets,self.overview);self.update_selection_label()
    def overview_selection(self):
        if self.refreshing:return
        self.sync_asset_selection(self.overview,self.assets);self.update_selection_label()
    def workspace_mode(self,index):
        self.canvas_pages.setCurrentIndex(index);self.contextbar.setVisible(True)
        self.versions.setVisible(index==0);self.split_button.setVisible(index==0);self.remove_button.setVisible(index==0)
        self.selection_changed()
    def update_selection_label(self):
        ids=self.selected_ids()
        if ids:
            a=self.project.asset(ids[0]);self.selection_label.setText(f"已选 {len(ids)} 张 · {a['width']} × {a['height']} px")
        else:self.selection_label.setText('全部图像 · 选择缩略图以编辑或删除' if self.tabs.currentIndex()==1 else '自由摆放 · 选中图像后应用工具')
    def selection_changed(self):
        if self.refreshing:return
        items=self.selected_items();self.versions.blockSignals(True);self.versions.clear()
        if len(items)==1:
            root=items[0].asset['root']
            for a in self.project.data['assets']:
                if a['root']==root and not a.get('trashed'):self.versions.addItem(a['name'],a['id'])
            self.versions.setCurrentIndex(self.versions.findData(items[0].asset['id']))
        self.versions.blockSignals(False);self.versions.setEnabled(len(items)==1)
        self.split_button.setEnabled(any(i.asset.get('kind')=='composition' for i in items))
        self.update_selection_label();self.schedule_preview()
    def switch_version(self,index):
        if self.refreshing or index<0:return
        items=self.selected_items()
        if len(items)==1:
            id=items[0].record['id'];items[0].record['asset']=self.versions.itemData(index)
            self.mark_dirty();self.refresh_scene([id])

    def refresh_scene(self,select=None):
        self.refreshing=True;self.view.scene().clear()
        for f in self.board['frames']:self.view.scene().addItem(FrameItem(f,self.mark_dirty))
        for n,r in enumerate(self.board['items']):
            a=self.project.asset(r['asset']);item=PhotoItem(r,a,QPixmap(str(self.project.root/a['thumb'])),self.mark_dirty)
            item.version_count=sum(1 for version in self.project.data['assets'] if version['root']==a['root'] and not version.get('trashed'))
            item.setZValue(n);self.view.scene().addItem(item)
            if select and r['id'] in select:item.setSelected(True)
        self.refreshing=False;self.selection_changed()
    def refresh_all(self,select=None):
        self.refreshing=True
        self.boards.clear()
        for b in self.project.data['boards']:self.boards.addItem(b['name'])
        self.boards.setCurrentRow(next(i for i,b in enumerate(self.project.data['boards']) if b['id']==self.board_id))
        selected_assets={i.data(Qt.ItemDataRole.UserRole) for i in self.assets.selectedItems()}
        self.assets.clear();self.overview.clear()
        for a in self.project.data['assets']:
            if a.get('trashed'):continue
            item=QListWidgetItem(QIcon(str(self.project.root/a['thumb'])),f"{a['name']}\n{a['width']} × {a['height']}")
            item.setData(Qt.ItemDataRole.UserRole,a['id']);self.assets.addItem(item)
            tile=QListWidgetItem(item);tile.setToolTip(item.text());self.overview.addItem(tile)
            if a['id'] in selected_assets:item.setSelected(True);tile.setSelected(True)
        self.count.setText(f"{sum(not a.get('trashed') for a in self.project.data['assets'])} 张图像 · {len(self.project.data['boards'])} 张画布")
        for combo,key in [(self.presets,'presets'),(self.workflows,'workflows')]:
            idx=combo.currentIndex();combo.clear()
            for p in self.project.data[key]:combo.addItem(p['name'])
            if combo.count():combo.setCurrentIndex(max(0,min(idx,combo.count()-1)))
        self.refreshing=False;self.refresh_scene(select)
        self.title_label.setText(self.project.data['name']+(' •' if self.dirty else ''))
    def change_board(self,row):
        if self.refreshing or row<0:return
        self.board_id=self.project.data['boards'][row]['id'];self.refresh_scene();self.fit()
    def add_board(self):
        b=blank_board(f"画布 {len(self.project.data['boards'])+1:02}");self.project.data['boards'].append(b);self.board_id=b['id'];self.mark_dirty();self.refresh_all()
    def rename_board(self):
        name,ok=QInputDialog.getText(self,'画布名称','名称',text=self.board['name'])
        if ok and name.strip():self.board['name']=name.strip();self.mark_dirty();self.refresh_all()
    def rename_project(self):
        name,ok=QInputDialog.getText(self,'项目名称','名称',text=self.project.data['name'])
        if ok and name.strip():self.project.data['name']=name.strip();self.mark_dirty()
    def place_assets(self):
        selected=[]
        for id in self.selected_ids():selected.append(self.project.placement(self.project.asset(id),self.board)['id'])
        self.mark_dirty();self.tabs.setCurrentIndex(0);self.refresh_scene(selected);self.fit()
    def remove_placements(self):
        photos={i.record['id'] for i in self.selected_items()};frames={i.record['id'] for i in self.view.scene().selectedItems() if isinstance(i,FrameItem)}
        self.board['items']=[r for r in self.board['items'] if r['id'] not in photos]
        self.board['frames']=[f for f in self.board['frames'] if f['id'] not in frames]
        self.mark_dirty();self.refresh_scene()
    def bring_front(self):
        ids={i.record['id'] for i in self.selected_items()};self.board['items'].sort(key=lambda r:r['id'] in ids);self.mark_dirty();self.refresh_scene(list(ids))
    def create_frame(self,rect):
        f=dict(id=uid(),name=f"作品 {len(self.board['frames'])+1:02}",x=rect.x(),y=rect.y(),width=rect.width(),height=rect.height())
        self.board['frames'].append(f);self.mark_dirty();self.refresh_scene()
        for item in self.view.scene().items():
            if isinstance(item,FrameItem) and item.record['id']==f['id']:item.setSelected(True)
    def edit_frame(self):
        frames=[i for i in self.view.scene().selectedItems() if isinstance(i,FrameItem)]
        if not frames:return
        f=frames[0].record
        w,ok=QInputDialog.getDouble(self,'作品框','画布宽度',f['width'],10,100000,1)
        if not ok:return
        h,ok=QInputDialog.getDouble(self,'作品框','画布高度',f['height'],10,100000,1)
        if ok:f.update(width=w,height=h);self.mark_dirty();self.refresh_scene()

    def schedule_preview(self):
        if self.editor_loading or not self.editor_inputs or self.pages.currentWidget()!=self.editor_page:return
        if not self.history_loading:self.history_timer.start()
        self.panel.preview.active_watermark=self.panel.watermark.index
        step=self.panel.step();self.panel.preview.grid=step['params'] if step['tool']=='sample' else None
        self.panel.preview.offsets=(self.panel.spins['offset_x'].value(),self.panel.spins['offset_y'].value())
        self.panel.preview.update();self.preview_generation+=1
        self.preview_status.setText('正在更新交互预览… · 停手后精细化')
        if not self.preview_timer.isActive():self.preview_timer.start()
        self.refine_timer.start()
    def refine_preview(self):
        self.preview_timer.stop();self.update_preview(exact=True)
    def update_preview(self,exact=False):
        if not exact and self.preview_requested==self.preview_generation:return
        id=self.active_id()
        if not id or self.pages.currentWidget()!=self.editor_page:return
        if self.editor_worker is None:
            self.editor_worker=PreviewWorker();self.editor_worker.ready.connect(self.preview_ready);self.editor_worker.failed.connect(self.preview_failed);self.editor_worker.start()
        self.preview_requested=self.preview_generation
        self.editor_worker.request(self.preview_generation,(self.project,id),self.panel.step(),exact=exact)
    def preview_ready(self,generation,image):
        exact=True
        payload=image if isinstance(image,dict) else {}
        if payload:exact=payload['exact'];image=payload['image']
        if self.pages.currentWidget()!=self.editor_page or generation<self.preview_floor or generation<self.preview_displayed:return
        if generation==self.preview_displayed and self.preview_exact and not exact:return
        if 'watermark_boxes' in payload:self.panel.preview.watermark_boxes=payload['watermark_boxes']
        if 'palette' in payload and generation==self.preview_generation:self.panel.palette.set_result(payload['palette'])
        self.preview_displayed=generation;self.preview_exact=exact
        self.panel.preview.image=image;self.panel.preview.update()
        count=len(self.panel.moved_blocks)
        state='精细预览' if exact else '交互预览'
        if generation<self.preview_generation:state+=' · 正在更新'
        self.preview_status.setText(f'{state} · {count} 个块单独移动 · 方向键 1 px / Shift＋方向键 10 px' if self.panel.tool.currentData()=='sample' else f'{state} · 拖动调整当前水印位置' if self.panel.tool.currentData()=='watermark' else state)
        if 'watermark_text' in payload:
            self.panel.watermark.resolved_text.setText('当前预览：'+(payload['watermark_text'] or '无可显示文字'))
            if payload.get('watermark_clipped'):self.preview_status.setText(state+' · 水印超出输出边界，超出部分会裁切；请调整位置或字号。')
        if 'layout' in payload:
            g=payload['layout'];self.preview_status.setText(f"{state} · 输出 {g['width']} × {g['height']} px · 色卡占比为估算")
    def preview_failed(self,generation,error):
        if generation==self.preview_generation:self.preview_status.setText('预览失败：'+error)
    def pick_palette_color(self,x,y):
        if self.panel.tool.currentData()!='palette':return
        if not self.editor_worker or self.editor_worker.source_path!=(self.project,self.edit_source):
            self.preview_status.setText('输入图仍在读取，请稍后取色。');return
        color=self.editor_worker.pick(x,y)
        if color is not None:self.panel.palette.picked(color)
    def split_selected(self):
        selected=[]
        for record in [i.record for i in self.view.scene().selectedItems() if isinstance(i,PhotoItem)]:
            if self.project.asset(record['asset']).get('kind')=='composition':
                selected.extend(r['id'] for r in self.project.split_composition(record,self.board))
        if selected:self.mark_dirty();self.refresh_all(selected)
        else:self.statusBar().showMessage('请选择照片与色卡组合。')
    def reload_step(self):
        ids=self.selected_ids()
        if len(ids)!=1:return
        a=self.project.asset(ids[0])
        if not a.get('step'):self.statusBar().showMessage('源图尚无工具步骤，请选择工具开始处理。');return
        self.open_tool(tool_id=a['step']['tool']);self.reedit_target=a['id'];self.update_revision_action()

    def revision_reason(self):
        target=self.reedit_target
        if not target:return '请先选择产物并点击重新编辑。'
        old=self.project.asset(target)
        if self.source_mode.currentIndex()!=0 or self.panel.tool.currentData()!=old['step']['tool'] or self.editor_inputs!=[old['parent']]:return '保存修改仅适用于当前产物的最后一个原有步骤。'
        return self.project.revision_blocker(target)
    def update_revision_action(self):
        visible=bool(self.reedit_target);self.save_revision_button.setVisible(visible);self.revision_note.setVisible(visible)
        reason=self.revision_reason() if visible else None
        self.save_revision_button.setEnabled(visible and reason is None)
        self.revision_note.setText(reason or '保存将更新此末端产物及其所有摆放；也可在下方生成新版本。')
    def save_revision(self):
        reason=self.revision_reason()
        if reason:QMessageBox.information(self,'无法保存修改',reason);return
        target=self.reedit_target;step=self.panel.step();step['intent']='revise'
        if not self.check_fonts([step]):return
        selected_records=[i.record['id'] for i in self.selected_items()]
        self.history.record(self.project.data);self.stop_preview()
        retiring=list(self.retiring_workers)
        def work(job):
            from shiboken6 import isValid
            for worker in retiring:
                if isValid(worker):worker.wait()
            return self.project.revise_leaf(target,step)
        def done(asset):
            self.mark_dirty();self.leave_editor_after_save();self.refresh_all(selected_records)
            self.statusBar().showMessage('已保存修改 · 未新增此图像的版本，可在工作台撤销')
        self.start_job(work,done,cancellable=False)
    def leave_editor_after_save(self):
        self.panel.cancel_pick();self.history_timer.stop();self.pages.setCurrentWidget(self.workspace);self.toolbar.show()
        self.editor_selection=[];self.editor_inputs=[];self.edit_source=None;self.reedit_target=None

    def set_busy(self,busy):
        for widget in (self.toolbar,self.pages,self.menuBar()):widget.setEnabled(not busy)
        for a in self.actions():a.setEnabled(not busy and self.pages.currentWidget()==self.workspace)
        if not busy:self.update_editor_actions()
        self.progress.setVisible(busy);self.cancel_button.setVisible(busy)
    def start_job(self,fn,done,cancellable=True):
        if self.job:return
        self.preview_timer.stop();self.refine_timer.stop();self.timer.stop();self.set_busy(True);self.progress.setRange(0,0)
        self.cancel_button.setEnabled(cancellable)
        self.job=Job(fn)
        self.job.progress.connect(self.job_progress)
        self.job.result.connect(done)
        self.job.failed.connect(self.job_error)
        self.job.finished.connect(self.job_finished)
        self.job.start()
    def job_progress(self,n,total,text):self.progress.setRange(0,max(1,total));self.progress.setValue(n);self.statusBar().showMessage(text)
    def job_error(self,text):
        self.statusBar().showMessage(text.splitlines()[0]);QMessageBox.warning(self,'任务未完成',text.split('\n\n')[0])
    def job_finished(self):
        old=self.job;self.job=None;self.set_busy(False);old.deleteLater();self.checkpoint();self.schedule_preview()
    def cancel_job(self):
        if self.job:self.job.cancel.set();self.statusBar().showMessage('将在当前步骤结束后取消；已经完成的结果保留。')
    def import_dialog(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入图像','','图像 (*.tif *.tiff *.jpg *.jpeg *.png)')
        if paths:self.import_paths(paths)
    def import_paths(self,paths):
        if self.job or not paths:return
        d=ImportDialog(len(paths),self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        half,retain=d.half.isChecked(),d.retain.isChecked()
        def work(job):
            results=[];errors=[]
            for i,path in enumerate(paths):
                if job.cancel.is_set():break
                job.progress.emit(i,len(paths),'正在导入 '+Path(path).name)
                try:results.append(self.project.import_image(path,half,retain))
                except Exception as e:errors.append(Path(path).name+'：'+str(e))
            return results,errors
        def done(result):
            assets,errors=result;selected=[]
            for a in assets:selected.append(self.project.placement(a,self.board)['id'])
            self.mark_dirty();self.refresh_all(selected);self.fit();self.statusBar().showMessage(f'已导入 {len(assets)} 张图像')
            if errors:QMessageBox.warning(self,'部分图像未导入','\n'.join(errors))
        self.start_job(work,done)
    def restore_original(self):
        ids=self.selected_ids()
        if len(ids)!=1:return
        a=self.project.asset(ids[0]);rel=a.get('original')
        if not rel:QMessageBox.information(self,'全尺寸原文件','导入此图像时未保留全尺寸原文件。');return
        self.import_paths([str(self.project.root/rel)])

    def apply_current(self):
        if not self.editor_inputs:return
        step=self.panel.step()
        if not self.check_fonts([step]):return
        step['intent']='append' if self.source_mode.currentIndex()==1 else 'revise'
        self.stop_preview();self.run_steps([step],from_editor=True)
    def run_steps(self,steps,from_editor=False,display=None):
        ids=list(self.editor_inputs) if from_editor else self.selected_ids()
        if not ids:QMessageBox.information(self,'选择图像','请先选择要处理的图像。');return
        if len(ids)>10:QMessageBox.information(self,'批处理','一次请选择最多 10 张图像。');return
        if not steps:return
        steps=copy.deepcopy([s for s in steps if s.get('enabled',True)])
        if not steps:return
        if not self.check_fonts(steps):return
        for node in steps:
            if node.get('action')=='export':
                directory=node['params'].get('directory','')
                if not directory or not Path(directory).is_dir():
                    directory=QFileDialog.getExistingDirectory(self,'请选择本次流程的导出目录')
                    if not directory:return
                    node['params']['directory']=directory
                if not QColor(node['params'].get('options',{}).get('background','#ffffff')).isValid():
                    QMessageBox.warning(self,'导出底色','请输入有效的底色，例如 #FFFFFF。');return
        if display is not None:
            inspection=preflight(self.project,ids,steps)
            if inspection['errors']:
                QMessageBox.warning(self,'流程需要修正','\n'.join(inspection['errors']));return
            box=QMessageBox(self);box.setWindowTitle('运行流程')
            box.setText(f"{inspection['inputs']} 张图像 · 每张 {inspection['nodes']} 个顺序节点")
            box.setInformativeText(f"预计生成 {inspection['outputs']} 个独立产物、导出 {inspection['exports']} 个文件。"+('\n存在缺失字段，请展开详细信息核对。' if inspection['warnings'] else ''))
            if inspection['warnings']:box.setDetailedText('\n'.join(inspection['warnings']))
            run=box.addButton('开始运行',QMessageBox.ButtonRole.AcceptRole);box.addButton(QMessageBox.StandardButton.Cancel);box.exec()
            if box.clickedButton()!=run:return
        mode=self.panel.mode.currentIndex() if display is None else {0:0,1:0,2:1,3:2}[display];board=self.board
        origin_ids=list(self.editor_selection) if from_editor else list(ids)
        origins={id:next((r for r in board['items'] if r['asset']==id),None) for id in origin_ids}
        def work(job):
            report=execute_chain(self.project,ids,steps,job.cancel,job.progress.emit)
            report['records']=[(origin_ids[ids.index(origin)],asset) for origin,asset in report['records']]
            return report
        def done(result):
            records=result['records'];errors=result['errors'];select=[];last={};offsets={}
            for origin,asset in records:last[origin]=asset
            for origin,a in records:
                r=origins[origin]
                if mode==0 and (display!=0 or last[origin]['id']==a['id']):
                    offset=offsets.get(origin,0)+1;offsets[origin]=offset
                    new=self.project.placement(a,board,(r['x']+(r['width']+40)*offset) if r else None,r['y'] if r else None,r['width'] if r else 440)
                    if r:new['width']=r['width']
                    select.append(new['id'])
            if mode in (1,2):
                for origin,a in last.items():
                    r=origins[origin]
                    if r:r['asset']=a['id'];r['view']='stack' if mode==2 else 'single';select.append(r['id'])
                    else:select.append(self.project.placement(a,board)['id'])
            if from_editor:
                self.pages.setCurrentWidget(self.workspace);self.toolbar.show();self.editor_selection=[];self.editor_inputs=[];self.edit_source=None
            self.mark_dirty();self.tabs.setCurrentIndex(0);self.refresh_all(select)
            self.statusBar().showMessage(f"{'已取消 · ' if result['cancelled'] else ''}已生成 {len(records)} 个产物 · 导出 {len(result['files'])} 个文件")
            self.last_run_report=copy.deepcopy(result)
            if display is not None:
                message=f"完成 {result['completed']}/{result['inputs']} 张 · 导出 {len(result['files'])} 个文件"
                details='\n'.join(result['files']+result['warnings']+errors)
                box=QMessageBox(self);box.setWindowTitle('流程运行报告');box.setText(message+(' · 已取消' if result['cancelled'] else ''));box.setDetailedText(details or '无警告');box.open();self.run_report_dialog=box
            if mode==0:self.fit()
            if errors:QMessageBox.warning(self,'部分处理未完成','\n'.join(errors))
        self.start_job(work,done)

    def record_tool_history(self):
        if not self.tool_history or self.history_loading:return
        if QApplication.mouseButtons()!=Qt.MouseButton.NoButton:
            self.history_timer.start();return
        self.tool_history.record(self.panel.step())

    def undo_state(self,delta):
        if self.job:return
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QTextEdit,QPlainTextEdit)):
            if delta<0:focus.undo()
            else:focus.redo()
            return
        editing=self.pages.currentWidget()==self.editor_page
        history=self.tool_history if editing else self.history
        if history is None:return
        if editing:
            self.history_timer.stop();history.record(self.panel.step())
        state=history.move(delta)
        if state is None:return
        self.history_loading=True
        try:
            if editing:self.panel.load_step(state);self.schedule_preview()
            else:
                self.project.data=state
                if not any(b['id']==self.board_id for b in state['boards']):self.board_id=state['boards'][0]['id']
                self.mark_dirty();self.refresh_all()
        finally:self.history_loading=False

    def board_context(self,pos):
        item=self.boards.itemAt(pos)
        if item:self.boards.setCurrentItem(item)
        menu=QMenu(self);menu.addAction('重命名画布',self.rename_board);menu.addAction('删除画布',self.delete_board);menu.exec(self.boards.mapToGlobal(pos))

    def asset_context(self,pos,listing=None):
        listing=listing or self.assets;item=listing.itemAt(pos)
        if item is None:return
        if not item.isSelected():listing.clearSelection();listing.setCurrentItem(item)
        menu=QMenu(self);menu.addAction('重新编辑',self.reload_step);menu.addAction('放入当前画布',self.place_assets);menu.addAction('照片 / 胶片资料',self.edit_metadata);menu.addAction('删除图像',self.delete_assets);menu.exec(listing.viewport().mapToGlobal(pos))

    def canvas_context(self,pos):
        item=self.view.itemAt(pos)
        if not isinstance(item,PhotoItem):return
        if not item.isSelected():self.view.scene().clearSelection();item.setSelected(True)
        menu=QMenu(self);menu.addAction('重新编辑',self.reload_step);menu.addAction('删除图像 · 移入回收站',self.delete_assets);menu.addAction('仅移出当前画布',self.remove_placements);menu.exec(self.view.viewport().mapToGlobal(pos))

    def delete_board(self):
        if QMessageBox.question(self,'删除画布',f"将「{self.board['name']}」移入回收站？图像素材仍保留。")!=QMessageBox.StandardButton.Yes:return
        trash.remove_board(self.project,self.board_id);self.board_id=self.project.data['boards'][0]['id'];self.mark_dirty();self.refresh_all()

    def delete_assets(self):
        ids=self.selected_ids()
        if not ids:return
        if QMessageBox.question(self,'删除图像',f'将 {len(ids)} 张图像移入项目回收站，并移出所有画布？已有处理结果不受影响，磁盘原文件不变。')!=QMessageBox.StandardButton.Yes:return
        trash.remove_assets(self.project,ids);self.mark_dirty();self.refresh_all()

    def show_trash(self):
        dialog=QDialog(self);dialog.setWindowTitle('项目回收站');dialog.resize(560,420);layout=QVBoxLayout(dialog)
        listing=QListWidget();layout.addWidget(listing)
        note=QLabel('清理仅释放无依赖图像。被结果或已删除画布引用的图像保留。');note.setWordWrap(True);layout.addWidget(note)
        def refresh():
            listing.clear()
            for entry in self.project.data.get('trash',[]):
                item=QListWidgetItem(('画布 · ' if entry['kind']=='board' else '图像 · ')+entry['name']);item.setData(Qt.ItemDataRole.UserRole,entry['id']);listing.addItem(item)
        def restore():
            if listing.currentItem():
                trash.restore(self.project,listing.currentItem().data(Qt.ItemDataRole.UserRole));self.mark_dirty();self.refresh_all();refresh()
        def clear():
            summary=trash.purge_summary(self.project);count=summary['count']
            if not count:note.setText('没有可清理的图像；剩余项仍被引用。');return
            box=QMessageBox(dialog);box.setWindowTitle('永久清理');box.setText(f"永久清理 {count} 张无引用图像？约释放 {summary['bytes']/1024**2:.1f} MiB。此操作不可撤销。")
            box.setDetailedText('可释放：\n'+'\n'.join(summary['releasable'])+'\n\n仍被引用、继续保留：\n'+('\n'.join(summary['protected']) or '无'))
            box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel);box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if box.exec()!=QMessageBox.StandardButton.Yes:return
            trash.purge(self.project);self.history.reset(self.project.data);self.mark_dirty();self.refresh_all();refresh()
        def forget_board():
            item=listing.currentItem()
            if not item:return
            entry=next(e for e in self.project.data.get('trash',[]) if e['id']==item.data(Qt.ItemDataRole.UserRole))
            if entry['kind']!='board':return
            if QMessageBox.question(dialog,'清理画布记录','永久删除此画布的恢复记录？图像素材仍按依赖保留。')!=QMessageBox.StandardButton.Yes:return
            self.project.data['trash'].remove(entry);self.history.reset(self.project.data);self.mark_dirty();refresh()
        row=QHBoxLayout();row.addWidget(button('恢复所选',restore));row.addWidget(button('清理画布记录',forget_board));row.addWidget(button('清理无引用图像',clear));row.addWidget(button('关闭',dialog.accept));layout.addLayout(row);refresh();dialog.exec()

    def import_watermark(self):
        path,_=QFileDialog.getOpenFileName(self,'导入图片水印','','图像 (*.png *.tif *.tiff *.jpg *.jpeg)')
        if not path:return
        def work(job):return self.project.add_resource(path)
        def done(resource):
            self.panel.watermark.add_image(resource['id'],resource['name']);self.mark_dirty()
        self.start_job(work,done)

    def move_watermark(self,dx,dy):
        from .watermark import reference_rect
        w=self.panel.watermark;p=w.layers[w.index];asset=self.project.asset(self.editor_inputs[0])
        try:rect=reference_rect(asset['width'],asset['height'],{**p,'_regions':asset.get('regions')})
        except ValueError:return
        unit=min(rect[2:])/100 if p['unit']=='percent' else 1
        w.values['x'].setValue(p['x']+dx/unit);w.values['y'].setValue(p['y']+dy/unit)

    def check_fonts(self,steps):
        available=set(QFontDatabase.families())
        for step in steps:
            if step.get('tool')!='watermark':continue
            for layer in step.get('params',{}).get('layers',[]):
                if not layer.get('enabled',True) or layer.get('kind')=='image':continue
                font=layer.get('font','Helvetica Neue')
                if font not in available:
                    replacement,ok=QInputDialog.getItem(self,'缺失字体',f'缺少 {font}，请选择替代字体',sorted(available),0,False)
                    if not ok:return False
                    layer['font']=replacement
        return True

    def edit_metadata(self):
        ids=self.selected_ids()
        if not ids:return
        def work(job):
            for id in ids:self.project.ensure_metadata(id)
        def done(_):
            if MetadataDialog(self.project,ids,self).exec()==QDialog.DialogCode.Accepted:self.mark_dirty()
        self.start_job(work,done)

    def apply_preset(self):
        index=self.presets.currentIndex()
        if index<0:return
        step=copy.deepcopy(self.project.data['presets'][index]['step']);step['intent']='append';self.run_steps([step])

    def manage_saved(self,key):
        dialog=QDialog(self);dialog.setWindowTitle('管理预设' if key=='presets' else '管理工作流');dialog.resize(520,390)
        layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
        def refresh():
            listing.clear()
            for entry in self.project.data[key]:listing.addItem(entry['name'])
        def act(kind):
            i=listing.currentRow()
            if i<0:return
            entries=self.project.data[key];entry=entries[i]
            if kind=='delete':entries.pop(i)
            elif kind=='copy':new=copy.deepcopy(entry);new['name']+=' · 副本';entries.append(new)
            else:
                text,ok=QInputDialog.getText(dialog,'名称','新名称',text=entry['name'])
                if not ok or not text.strip():return
                entry['name']=text.strip()
            self.mark_dirty();self.refresh_all();refresh()
        row=QHBoxLayout()
        for label,kind in [('重命名','rename'),('复制','copy'),('删除','delete')]:row.addWidget(button(label,lambda _,k=kind:act(k)))
        layout.addLayout(row);layout.addWidget(button('关闭',dialog.accept));refresh();dialog.exec()

    def save_preset(self):
        name,ok=QInputDialog.getText(self,'保存预设','预设名称')
        if ok and name.strip():self.project.data['presets'].append(dict(name=name.strip(),step=self.panel.step()));self.mark_dirty();self.refresh_all()
    def load_preset(self):
        i=self.presets.currentIndex()
        if i>=0:
            step=copy.deepcopy(self.project.data['presets'][i]['step']);self.open_tool(tool_id=step['tool'])
            if self.editor_inputs:self.panel.load_step(step)
    def edit_workflow(self,checked=False,new=False):
        i=-1 if new else self.workflows.currentIndex();existing=self.project.data['workflows'][i] if i>=0 else None
        dialog=WorkflowEditor(self.project,self.panel.step(),existing['steps'] if existing else None,self)
        if existing:dialog.display.setCurrentIndex(existing.get('display',1))
        if dialog.exec()!=QDialog.DialogCode.Accepted or not dialog.steps:return
        name,ok=QInputDialog.getText(self,'保存工作流','名称',text=existing['name'] if existing else '')
        if ok and name.strip():
            w=dict(name=name.strip(),steps=dialog.steps,display=dialog.display.currentIndex());self.project.data['schema']=3
            if existing:self.project.data['workflows'][i]=w
            else:self.project.data['workflows'].append(w)
            self.mark_dirty();self.refresh_all()
    def run_workflow(self):
        i=self.workflows.currentIndex()
        if i>=0:
            steps=copy.deepcopy(self.project.data['workflows'][i]['steps'])
            for step in steps:step['intent']='append'
            self.run_steps(steps,display=self.project.data['workflows'][i].get('display',1))

    def export_selected(self):
        ids=self.selected_ids();frames=[i.record for i in self.view.scene().selectedItems() if isinstance(i,FrameItem)] if self.tabs.currentIndex()==0 else []
        if not ids and not frames:QMessageBox.information(self,'导出','请选择图像或作品框。');return
        frame=copy.deepcopy(frames[0]) if frames else None
        dialog=ExportDialog(bool(frame),self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        options=dialog.options();ext={'JPEG':'jpg','PNG':'png','TIFF':'tiff'}[options['fmt']]
        width=dialog.width.value();bg=None if dialog.transparent.isChecked() else dialog.color
        paths=[]
        if frame or len(ids)==1:
            name=frame['name'] if frame else self.project.asset(ids[0])['name']
            path,_=QFileDialog.getSaveFileName(self,'导出',name+'.'+ext,f'{options["fmt"]} (*.{ext})')
            if not path:return
            paths=[Path(path) if Path(path).suffix else Path(path+'.'+ext)]
        else:
            folder=QFileDialog.getExistingDirectory(self,'导出所选图像到文件夹')
            if not folder:return
            for n,id in enumerate(ids):
                safe=''.join(c for c in self.project.asset(id)['name'] if c not in '/\\:')[:100]
                path=Path(folder)/f'{n+1:02}-{safe}.{ext}';count=1
                while path.exists():path=Path(folder)/f'{n+1:02}-{safe}-{count}.{ext}';count+=1
                paths.append(path)
        board=copy.deepcopy(self.board)
        def work(job):
            done=[];errors=[]
            for i,path in enumerate(paths):
                if job.cancel.is_set():break
                job.progress.emit(i,len(paths),'正在导出 '+path.name)
                temp=path.with_name('.'+path.stem+'-'+uid()+'.'+ext)
                try:
                    a=render_frame(self.project,board,frame,width,bg,job.cancel) if frame else read_image(self.project.file(self.project.asset(ids[i])))
                    export_image(temp,a,**options);os.replace(temp,path);done.append(str(path))
                except Exception as e:errors.append(path.name+'：'+str(e))
                finally:temp.unlink(missing_ok=True)
            return done,errors
        def done(result):
            paths,errors=result;self.statusBar().showMessage(f'已导出 {len(paths)} 个文件')
            if errors:QMessageBox.warning(self,'导出结果','\n'.join(errors))
        self.start_job(work,done)

    def save_project(self,checked=False,as_new=False,after=None):
        if self.job:return
        path=None if as_new else self.project.path
        if not path:
            value,_=QFileDialog.getSaveFileName(self,'保存完整项目',self.project.data['name']+'.blockproj','PostStudio (*.blockproj)')
            if not value:return
            path=Path(value)
            if path.suffix!='.blockproj':path=path.with_suffix('.blockproj')
        self.project.data['name']=Path(path).stem
        def work(job):job.progress.emit(0,1,'正在保存完整项目…');self.project.save(path);return str(path)
        def done(result):
            self.dirty=False;self.title_label.setText(self.project.data['name']);self.statusBar().showMessage('已保存 '+result)
            if after:QTimer.singleShot(100,after)
        self.start_job(work,done,cancellable=False)
    def guard_replace(self,action):
        if self.job:return
        if not self.dirty:action();return
        choice=QMessageBox.question(self,'保存当前项目？','当前项目有尚未保存的修改。',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if choice==QMessageBox.StandardButton.Save:self.save_project(after=action)
        elif choice==QMessageBox.StandardButton.Discard:action()
    def new_project(self):
        def action():
            old=self.project.root;self.project=Project(self.session_base/uid());self.board_id=self.project.data['boards'][0]['id'];self.dirty=False;self.preview_key=None;self.history.reset(self.project.data);self.refresh_all();shutil.rmtree(old,ignore_errors=True)
        self.guard_replace(action)
    def open_project_path(self,path):
        old=self.project.root;root=self.session_base/uid()
        def work(job):
            job.progress.emit(0,1,'正在打开项目…')
            return Project.open(path,root)
        def done(project):
            self.project=project;self.board_id=project.data['boards'][0]['id'];self.dirty=False;self.preview_key=None
            self.history.reset(self.project.data);self.refresh_all();self.fit();shutil.rmtree(old,ignore_errors=True)
            self.statusBar().showMessage('已打开 '+Path(path).name)
        self.start_job(work,done,cancellable=False)
    def open_project(self):
        def action():
            path,_=QFileDialog.getOpenFileName(self,'打开项目','','PostStudio (*.blockproj)')
            if path:self.open_project_path(path)
        self.guard_replace(action)
    def recover_dialog(self):
        roots=sorted([p for p in self.session_base.iterdir() if p.is_dir() and p!=self.project.root and (p/'manifest.json').exists()],key=lambda p:p.stat().st_mtime,reverse=True)
        if not roots:QMessageBox.information(self,'恢复','没有可恢复的副本。');return
        from datetime import datetime
        labels=[datetime.fromtimestamp(p.stat().st_mtime).strftime('%m-%d %H:%M')+' · '+p.name[:8] for p in roots]
        name,ok=QInputDialog.getItem(self,'恢复副本','选择恢复点',labels,0,False)
        if not ok:return
        def action():
            try:
                source=roots[labels.index(name)];target=self.session_base/uid();shutil.copytree(source,target)
                p=Project.recover(target);old=self.project.root;self.project=p;self.board_id=p.data['boards'][0]['id'];self.dirty=True;self.history.reset(self.project.data);self.refresh_all();self.fit();shutil.rmtree(old,ignore_errors=True)
            except Exception as e:QMessageBox.warning(self,'恢复失败',str(e))
        self.guard_replace(action)
    def closeEvent(self,event):
        self.stop_preview()
        if self.job:QMessageBox.information(self,'任务进行中','请等待当前任务完成，或取消后再关闭。');event.ignore();return
        if self.dirty:
            event.ignore();self.guard_replace(self.finish_close)
        else:self.finish_close(event)
    def finish_close(self,event=None):
        if any(w.isRunning() for w in self.retiring_workers):
            if event:event.ignore()
            QTimer.singleShot(30,self.finish_close);return
        self.timer.stop();self.dirty=False;shutil.rmtree(self.project.root,ignore_errors=True)
        if event:event.accept()
        else:QTimer.singleShot(0,self.close)


def main():
    app=QApplication(sys.argv);app.setApplicationName('PostStudio');app.setOrganizationName('BlockStudio');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=Window();window.show()
    if len(sys.argv)>1 and Path(sys.argv[1]).suffix=='.blockproj':
        # The event loop must run before any permission-sensitive file access.
        QTimer.singleShot(0,lambda:window.open_project_path(sys.argv[1]))
    else:
        roots=[p for p in window.session_base.iterdir() if p!=window.project.root and (p/'manifest.json').exists()]
        if roots:window.statusBar().showMessage('发现恢复副本，可从“项目 → 打开恢复副本”找回未保存内容。')
    result=app.exec()
    # Dispose parent trees before PySide's arbitrary wrapper shutdown order.
    from PySide6.QtCore import QCoreApplication,QEvent
    for widget in list(app.topLevelWidgets()):widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    sys.exit(result)

if __name__=='__main__':main()
