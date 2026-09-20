"""Drag presets into a single ordered node chain; no hidden graph semantics."""
import copy,json
from PySide6.QtCore import Qt,QMimeData,Signal,QSize
from PySide6.QtGui import QDrag,QColor,QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QAbstractItemView,QSplitter,QWidget,QStackedWidget,QFormLayout,QLineEdit,QComboBox,QSpinBox,QCheckBox,QFileDialog,QDialogButtonBox,QScrollArea,QStyledItemDelegate)
from .workflow import node_label
from .tools import TOOLS

MIME='application/x-poststudio-step'


class PresetLibrary(QListWidget):
    def __init__(self):super().__init__();self.setDragEnabled(True)
    def startDrag(self,actions):
        if not self.currentItem():return
        mime=QMimeData();mime.setData(MIME,json.dumps(self.currentItem().data(Qt.ItemDataRole.UserRole)).encode());drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction)


class NodeDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return QSize(240,90)
    def paint(self,painter,option,index):
        painter.save();r=option.rect.adjusted(8,5,-8,-14);selected=bool(option.state & __import__('PySide6.QtWidgets',fromlist=['QStyle']).QStyle.StateFlag.State_Selected)
        painter.setBrush(QColor('#344e63' if selected else '#28343f'));painter.setPen(QPen(QColor('#83a8c7' if selected else '#455664'),1));painter.drawRoundedRect(r,6,6)
        painter.setPen(QColor('#d3e1ec'));painter.drawText(r.adjusted(12,4,-12,-4),Qt.AlignmentFlag.AlignVCenter,index.data())
        x=option.rect.center().x();y=r.bottom();painter.setPen(QPen(QColor('#71899e'),1));painter.drawLine(x,y+2,x,y+12);painter.drawLine(x,y+12,x-3,y+8);painter.drawLine(x,y+12,x+3,y+8);painter.restore()


class NodeChain(QListWidget):
    changed=Signal()
    def __init__(self):
        super().__init__();self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop);self.setDefaultDropAction(Qt.DropAction.MoveAction);self.setItemDelegate(NodeDelegate(self));self.model().rowsMoved.connect(self.changed)
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(MIME):event.acceptProposedAction()
        else:super().dragEnterEvent(event)
    def dragMoveEvent(self,event):
        if event.mimeData().hasFormat(MIME):event.acceptProposedAction()
        else:super().dragMoveEvent(event)
    def dropEvent(self,event):
        if event.mimeData().hasFormat(MIME):
            step=json.loads(bytes(event.mimeData().data(MIME)));row=self.indexAt(event.position().toPoint()).row();self.add_step(step,row);event.acceptProposedAction()
        else:super().dropEvent(event);self.changed.emit()
    def add_step(self,step,row=-1):
        item=QListWidgetItem();item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(step));self.insertItem(self.count() if row<0 else row,item);self.setCurrentItem(item);self.changed.emit()


class WorkflowEditor(QDialog):
    def __init__(self,project,current_step,existing=None,parent=None):
        super().__init__(parent);self.setWindowTitle('单条批量流程');self.resize(1180,760);self.project=project;self.loading=False
        v=QVBoxLayout(self);v.addWidget(QLabel('拖入预设 → 排序节点 → 运行时逐张顺序执行。每个图像步骤保留独立结果。'))
        split=QSplitter();v.addWidget(split,1);left=QWidget();lv=QVBoxLayout(left);lv.addWidget(QLabel('预设与动作'));self.library=PresetLibrary();lv.addWidget(self.library)
        for preset in project.data['presets']:self.library.addItem(preset['name']);self.library.item(self.library.count()-1).setData(Qt.ItemDataRole.UserRole,copy.deepcopy(preset['step']))
        for label,step in [('当前工具',current_step),('命名',dict(action='name',params=dict(template='{原文件名}-{序号}'))),('导出',dict(action='export',params=dict(template='{name}',directory='',options={})))]:
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(step));self.library.addItem(item)
        self.library.itemDoubleClicked.connect(lambda item:self.chain.add_step(item.data(Qt.ItemDataRole.UserRole)))
        b=QPushButton('加入选中预设 / 动作');b.clicked.connect(lambda:self.chain.add_step(self.library.currentItem().data(Qt.ItemDataRole.UserRole)) if self.library.currentItem() else None);lv.addWidget(b)
        b=QPushButton('用左侧预设更新当前节点');b.clicked.connect(self.update_from_library);lv.addWidget(b)
        split.addWidget(left);middle=QWidget();mv=QVBoxLayout(middle);self.chain=NodeChain();mv.addWidget(self.chain)
        row=QHBoxLayout();mv.addLayout(row)
        for label,fn in [('复制',self.duplicate),('删除',self.remove),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1))]:b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.display=QComboBox();self.display.addItems(['旁边展示最终结果','旁边展示所有步骤','原位置显示最终结果','收入版本集合']);mv.addWidget(self.display);split.addWidget(middle)
        right=QWidget();rv=QVBoxLayout(right);self.enabled=QCheckBox('启用此节点');rv.addWidget(self.enabled);self.enabled.toggled.connect(self.edit)
        self.pages=QStackedWidget();rv.addWidget(self.pages,1)
        from .widgets import ToolPanel
        self.panel=ToolPanel();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.panel);self.pages.addWidget(scroll)
        # Selection of a different tool is explicit; parameters editable inline.
        self.panel.changed.connect(self.edit)
        self.panel.apply.hide()
        for b in self.panel.findChildren(QPushButton):
            if b.text()=='图内取色':b.setEnabled(False);b.setToolTip('请在图像工具页面取色并保存为预设，再更新此节点。')
        self.panel.watermark.resourceRequested.connect(self.import_resource)
        self.panel.load_candidates(project.data['assets']);self.panel.configure_dimensions(1200,800)
        action=QWidget();f=QFormLayout(action);self.template=QLineEdit();f.addRow('命名模板',self.template);self.template.textChanged.connect(self.edit)
        self.directory=QLineEdit();f.addRow('导出目录',self.directory);self.directory.textChanged.connect(self.edit)
        self.browse=QPushButton('选择目录');self.browse.clicked.connect(self.choose_directory);f.addRow(self.browse)
        self.format=QComboBox();self.format.addItems(['JPEG','PNG','TIFF']);f.addRow('导出格式',self.format);self.format.currentIndexChanged.connect(self.edit)
        self.quality=QSpinBox();self.quality.setRange(1,100);self.quality.setValue(95);self.quality.valueChanged.connect(self.edit);f.addRow('JPEG 质量',self.quality)
        self.half=QCheckBox('导出 2×2 降采样');f.addRow(self.half);self.half.toggled.connect(self.edit)
        self.compress=QCheckBox('TIFF 无损压缩');self.compress.setChecked(True);f.addRow(self.compress);self.compress.toggled.connect(self.edit)
        self.background=QLineEdit('#ffffff');self.background.textChanged.connect(self.edit);f.addRow('JPEG 底色 HEX',self.background)
        note=QLabel('字段：{原文件名}、{序号}、{拍摄日期}、{胶卷型号}。\n导出模板 {name} 使用前面命名节点的结果。');note.setWordWrap(True);f.addRow(note);self.pages.addWidget(action);split.addWidget(right);split.setSizes([230,340,480])
        self.chain.currentRowChanged.connect(self.select);self.chain.changed.connect(self.refresh_labels)
        for step in (existing if existing is not None else [current_step]):self.chain.add_step(step)
        self.chain.setCurrentRow(0)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);v.addWidget(buttons)
    @property
    def steps(self):return [copy.deepcopy(self.chain.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.chain.count())]
    def refresh_labels(self):
        for i in range(self.chain.count()):
            item=self.chain.item(i);step=item.data(Qt.ItemDataRole.UserRole);item.setText(f"{i+1:02}  {node_label(step)}\n{'启用' if step.get('enabled',True) else '已停用'}")
    def select(self,row):
        if row<0:return
        self.loading=True;p=self.chain.item(row).data(Qt.ItemDataRole.UserRole);self.enabled.setChecked(p.get('enabled',True));is_action='action' in p;self.pages.setCurrentIndex(int(is_action))
        if not is_action:self.panel.load_step(p)
        else:
            params=p['params'];self.template.setText(params.get('template',''));self.directory.setText(params.get('directory',''));opts=params.get('options',{});self.format.setCurrentText(opts.get('fmt','JPEG'));self.quality.setValue(opts.get('quality',95));self.half.setChecked(opts.get('half',False));self.compress.setChecked(opts.get('compress',True));self.background.setText(opts.get('background','#ffffff'))
            for c in (self.directory,self.browse,self.format,self.quality,self.half,self.compress,self.background):c.setEnabled(p['action']=='export')
        self.loading=False
    def edit(self,*_):
        item=self.chain.currentItem()
        if self.loading or item is None:return
        old=item.data(Qt.ItemDataRole.UserRole)
        if 'action' in old:
            p=dict(action=old['action'],params=dict(template=self.template.text(),directory=self.directory.text(),options=dict(fmt=self.format.currentText(),quality=self.quality.value(),half=self.half.isChecked(),compress=self.compress.isChecked(),background=self.background.text())))
        else:p=self.panel.step()
        p['enabled']=self.enabled.isChecked();item.setData(Qt.ItemDataRole.UserRole,p);self.refresh_labels()
    def update_from_library(self):
        item=self.chain.currentItem();source=self.library.currentItem()
        if item is None or source is None:return
        step=copy.deepcopy(source.data(Qt.ItemDataRole.UserRole));step['enabled']=item.data(Qt.ItemDataRole.UserRole).get('enabled',True)
        item.setData(Qt.ItemDataRole.UserRole,step);self.select(self.chain.currentRow());self.refresh_labels()
    def choose_directory(self):
        path=QFileDialog.getExistingDirectory(self,'导出目录')
        if path:self.directory.setText(path)
    def import_resource(self):
        path,_=QFileDialog.getOpenFileName(self,'导入水印图片','','图像 (*.png *.tiff *.tif *.jpg *.jpeg)')
        if path:
            resource=self.project.add_resource(path);self.panel.watermark.add_image(resource['id'],resource['name'])
    def duplicate(self):
        if self.chain.currentItem():self.chain.add_step(self.chain.currentItem().data(Qt.ItemDataRole.UserRole))
    def remove(self):self.chain.takeItem(self.chain.currentRow());self.refresh_labels()
    def move(self,delta):
        i=self.chain.currentRow();j=i+delta
        if 0<=j<self.chain.count():item=self.chain.takeItem(i);self.chain.insertItem(j,item);self.chain.setCurrentRow(j);self.refresh_labels()
