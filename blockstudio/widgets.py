from __future__ import annotations
import copy
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QIcon, QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QSpinBox,QSlider,
    QCheckBox,QFormLayout,QColorDialog,QGroupBox,QDialog,QDialogButtonBox,QLineEdit,QListWidget,QSizePolicy)
from .tools import TOOLS, block_at, block_rect
from .canvas import checker_brush
from .palette_widgets import PaletteControls
from .watermark_widgets import WatermarkControls
from .border_widgets import BorderControls
from .effect_controls import BackgroundControls,ShadowControls


def button(text, callback=None):
    b=QPushButton(text)
    if callback: b.clicked.connect(callback)
    return b


class Preview(QWidget):
    picked=Signal(str)
    pickedPosition=Signal(float,float)
    offsetDragged=Signal(int,int)
    blockDragged=Signal(str,int,int)
    nudge=Signal(int,int)
    watermarkDragged=Signal(int,int)
    def __init__(self):
        super().__init__()
        self.image=QImage();self.pick_image=QImage();self.picking=False;self.checker=checker_brush(14,'#363a3c','#484d50')
        self.source_width=1;self.source_height=1;self.drag_enabled=False
        self.drag_start=None;self.drag_offsets=(0,0);self.offsets=(0,0)
        self.show_source=False;self.grid=None;self.show_grid=True
        self.watermark_mode=False;self.watermark_boxes=[];self.active_watermark=0
        self.move_mode='grid';self.selected_block=None;self.block_delta=(0,0)
        self.setMinimumSize(260,220);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    def image_rect(self):
        image=self.pick_image if (self.show_source or self.picking) else self.image
        if image.isNull():return QRectF()
        r=QRectF(self.rect()).adjusted(28,28,-28,-28)
        size=image.size().scaled(r.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#1b1e20'))
        image=self.pick_image if (self.show_source or self.picking) else self.image
        if image.isNull():
            p.setPen(QColor('#8e9497'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'正在准备图像…');return
        r=self.image_rect();p.setClipRect(r)
        p.fillRect(r,self.checker)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(r,image)
        if self.watermark_mode and not self.picking:
            p.setPen(QPen(QColor('#a7c7df'),1));p.setBrush(Qt.BrushStyle.NoBrush)
            for box in self.watermark_boxes:
                if box['index']!=self.active_watermark:continue
                x,y,w,h=box['rect'];p.drawRect(QRectF(r.x()+x/self.source_width*r.width(),r.y()+y/self.source_height*r.height(),w/self.source_width*r.width(),h/self.source_height*r.height()))
        if self.show_grid and self.grid and not self.picking:
            import math
            params=self.grid;bx,by=params['block_x'],params['block_y'];px=bx+params['gap_x'];py=by+params['gap_y']
            sx,sy=r.width()/self.source_width,r.height()/self.source_height
            ox,oy=self.offsets;keys=set(params.get('moved_blocks',{}))
            if min(px*sx,py*sy)>=9:
                for row in range(math.floor((-oy-by)/py),math.ceil((self.source_height-oy)/py)+1):
                    for col in range(math.floor((-ox-bx)/px),math.ceil((self.source_width-ox)/px)+1):keys.add(f'{col},{row}')
            if self.selected_block:keys.add(self.selected_block)
            for key in keys:
                x,y,bw,bh=block_rect(params,key)
                selected=key==self.selected_block
                p.setPen(QPen(QColor('#b4d0e6') if selected else QColor(137,177,209,115),2 if selected else .7))
                p.drawRect(QRectF(r.x()+x*sx,r.y()+y*sy,bw*sx,bh*sy))
    def mousePressEvent(self,event):
        r=self.image_rect()
        if event.button()!=Qt.MouseButton.LeftButton or not r.contains(event.position()):return
        self.setFocus()
        if self.picking and not self.pick_image.isNull():
            x=min(self.pick_image.width()-1,int((event.position().x()-r.x())/r.width()*self.pick_image.width()))
            y=min(self.pick_image.height()-1,int((event.position().y()-r.y())/r.height()*self.pick_image.height()))
            self.picking=False;self.setCursor(Qt.CursorShape.OpenHandCursor if self.drag_enabled else Qt.CursorShape.ArrowCursor)
            self.pickedPosition.emit((event.position().x()-r.x())/r.width(),(event.position().y()-r.y())/r.height())
            self.picked.emit(self.pick_image.pixelColor(x,y).name());self.update();return
        if self.watermark_mode:
            self.drag_start=event.position();return
        if self.drag_enabled:
            if self.move_mode=='block':
                x=(event.position().x()-r.x())/r.width()*self.source_width
                y=(event.position().y()-r.y())/r.height()*self.source_height
                self.selected_block=block_at(self.grid,x,y) if self.grid else None
                self.update()
                if self.selected_block is None:return
                self.block_delta=tuple(self.grid.get('moved_blocks',{}).get(self.selected_block,(0,0)))
            self.drag_start=event.position();self.drag_offsets=self.offsets;self.setCursor(Qt.CursorShape.ClosedHandCursor)
    def mouseMoveEvent(self,event):
        if self.drag_start is None:return
        r=self.image_rect();delta=event.position()-self.drag_start
        dx=round(delta.x()/r.width()*self.source_width);dy=round(delta.y()/r.height()*self.source_height)
        if self.watermark_mode:
            self.watermarkDragged.emit(dx,dy);self.drag_start=event.position();return
        if self.move_mode=='block' and self.selected_block:
            self.blockDragged.emit(self.selected_block,self.block_delta[0]+dx,self.block_delta[1]+dy)
        else:self.offsetDragged.emit(self.drag_offsets[0]+dx,self.drag_offsets[1]+dy)
    def mouseReleaseEvent(self,event):
        self.drag_start=None;self.setCursor(Qt.CursorShape.OpenHandCursor if self.drag_enabled else Qt.CursorShape.ArrowCursor)
    def keyPressEvent(self,event):
        offsets={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
        if (self.drag_enabled or self.watermark_mode) and event.key() in offsets:
            dx,dy=offsets[event.key()];step=10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            self.nudge.emit(dx*step,dy*step);event.accept()
        else:super().keyPressEvent(event)


class ParameterControl(QWidget):
    def __init__(self,label,minimum,value):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        row=QHBoxLayout();row.addWidget(QLabel(label),1)
        self.spin=QSpinBox();self.spin.setRange(minimum,100000);self.spin.setValue(value);self.spin.setSuffix(' px');self.spin.setKeyboardTracking(False);self.spin.setFixedWidth(116)
        self.spin.setAccessibleName(label+'精确值');row.addWidget(self.spin);layout.addLayout(row)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(minimum if minimum>=0 else -1200,1200);self.slider.setSingleStep(1);self.slider.setPageStep(10);self.slider.setValue(value)
        self.slider.setAccessibleName(label+'滑块');self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.spin.setValue);self.spin.valueChanged.connect(self.sync)
    def sync(self,value):
        self.slider.blockSignals(True)
        if value<self.slider.minimum():self.slider.setMinimum(value)
        if value>self.slider.maximum():self.slider.setMaximum(value)
        self.slider.setValue(value);self.slider.blockSignals(False)
    def configure(self,dimension):
        self.slider.blockSignals(True)
        low=-dimension if self.spin.minimum()<0 else self.spin.minimum()
        self.slider.setRange(min(low,self.spin.value()),max(dimension,self.spin.value()))
        self.slider.setValue(self.spin.value());self.slider.blockSignals(False)


class ToolPanel(QWidget):
    changed=Signal()
    pickModeChanged=Signal(bool)
    applyRequested=Signal()
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(18,14,18,14);layout.setSpacing(12)
        title=QLabel('参数');title.setObjectName('sectionTitle');layout.addWidget(title)
        self.tool=QComboBox()
        for id,t in TOOLS.items():self.tool.addItem(t.label,id)
        layout.addWidget(self.tool)
        self.preview=Preview()  # Placed in the editor's main area by Window.
        self.sample_box=QWidget();form=QVBoxLayout(self.sample_box);form.setContentsMargins(0,0,0,0);form.setSpacing(10)
        self.spins={};self.sliders={};self.controls={};self.moved_blocks={}
        for key,label,low,default in [('block_x','保留宽度',1,64),('block_y','保留高度',1,64),('gap_x','横向间隔',0,64),('gap_y','纵向间隔',0,64),('offset_x','横向偏移',-100000,0),('offset_y','纵向偏移',-100000,0)]:
            control=ParameterControl(label,low,default);form.addWidget(control)
            self.controls[key]=control;self.spins[key]=control.spin;self.sliders[key]=control.slider
            control.spin.valueChanged.connect(self.changed)
        self.transparent=QCheckBox('空缺透明');self.transparent.setChecked(True);self.transparent.toggled.connect(self.changed);form.addWidget(self.transparent)
        self.color='#f1ede5';row=QHBoxLayout();self.color_button=button('背景色',self.choose_color);row.addWidget(self.color_button);row.addWidget(button('图内取色',self.start_pick));form.addLayout(row);layout.addWidget(self.sample_box)
        self.watermark=WatermarkControls();self.watermark.hide();self.watermark.changed.connect(self.changed);layout.addWidget(self.watermark)
        self.border=BorderControls();self.border.hide();self.border.changed.connect(self.changed);layout.addWidget(self.border)
        self.palette=PaletteControls();self.palette.hide();self.palette.changed.connect(self.changed);self.palette.pickRequested.connect(self.start_pick);layout.addWidget(self.palette)
        self.candidates=QComboBox();self.candidates.addItem('使用项目中的色卡颜色…',None);self.candidates.activated.connect(self.use_candidate);form.addWidget(self.candidates)
        self.background_controls=BackgroundControls();form.addWidget(self.background_controls);self.background_controls.changed.connect(self.changed)
        self.background_controls.kind.currentIndexChanged.connect(lambda:self.transparent.setChecked(False))
        self.shadow_controls=ShadowControls('取样块悬浮阴影');form.addWidget(self.shadow_controls);self.shadow_controls.changed.connect(self.changed)
        self.mode=QComboBox();self.mode.addItems(['旁边新增修改稿','原位置显示修改稿','收入版本集合'])
        self.apply=button('生成修改稿 · 返回画布',self.applyRequested.emit);self.apply.setObjectName('primary')
        self.tool.currentIndexChanged.connect(self.tool_changed);self.preview.picked.connect(self.preview_color);self.preview.picked.connect(lambda _:self.pickModeChanged.emit(False))
        self.set_color(self.color,emit=False);layout.addStretch()
    def tool_changed(self):
        self.watermark.setVisible(self.tool.currentData()=='watermark')
        self.border.setVisible(self.tool.currentData()=='border')
        self.sample_box.setVisible(self.tool.currentData()=='sample');self.palette.setVisible(self.tool.currentData()=='palette');self.changed.emit()
    def preview_color(self,color):
        if self.tool.currentData()=='sample':self.set_color(color)
    def use_candidate(self,index):
        color=self.candidates.itemData(index)
        if color:self.set_color(color)
    def load_candidates(self,assets):
        self.candidates.clear();self.candidates.addItem('使用项目中的色卡颜色…',None)
        seen=set()
        for asset in assets:
            if asset.get('trashed'):continue
            for swatch in asset.get('palette',{}).get('swatches',[]):
                color=swatch['hex']
                if color not in seen:
                    pix=QPixmap(36,20);pix.fill(QColor(color));self.candidates.addItem(QIcon(pix),asset['name']+' · '+color,color);seen.add(color)
    def configure_dimensions(self,width,height):
        for key,control in self.controls.items():control.configure(width if key.endswith('_x') else height)
        self.preview.source_width=width;self.preview.source_height=height;self.palette.source_size=(width,height);self.border.source_size=(width,height)
    def choose_color(self):
        c=QColorDialog.getColor(QColor(self.color),self,'空缺颜色')
        if c.isValid():self.set_color(c.name())
    def set_color(self,color,emit=True):
        self.color=color;self.color_button.setText(color.upper());self.color_button.setStyleSheet('')
        pix=QPixmap(22,16);pix.fill(QColor(color));self.color_button.setIcon(QIcon(pix));self.color_button.setIconSize(QSize(22,16))
        if emit:self.transparent.setChecked(False);self.changed.emit()
    def cancel_pick(self):
        self.preview.picking=False;self.preview.setCursor(Qt.CursorShape.OpenHandCursor if self.preview.drag_enabled else Qt.CursorShape.ArrowCursor);self.preview.update();self.pickModeChanged.emit(False)
    def start_pick(self):
        self.preview.setFocus();self.preview.picking=True;self.preview.setCursor(Qt.CursorShape.CrossCursor);self.preview.update();self.pickModeChanged.emit(True)
    def step(self):
        id=self.tool.currentData();params={k:v.value() for k,v in self.spins.items()} if id=='sample' else {}
        if id=='sample':params.update(transparent=self.transparent.isChecked(),color=self.color,moved_blocks=copy.deepcopy(self.moved_blocks))
        if id=='sample':params.update(background_spec=self.background_controls.params(),shadow=self.shadow_controls.params())
        if id=='palette':params=self.palette.params()
        if id=='border':params=self.border.params()
        if id=='watermark':params=self.watermark.params()
        return dict(tool=id,version=TOOLS[id].version,params=params)
    def load_step(self,step):
        self.tool.blockSignals(True);self.tool.setCurrentIndex(self.tool.findData(step['tool']));self.tool.blockSignals(False)
        for k,v in step.get('params',{}).items():
            if k in self.spins:self.spins[k].setValue(v)
        if step['tool']=='sample':
            self.moved_blocks=copy.deepcopy(step['params'].get('moved_blocks',{}))
            self.background_controls.load(step['params'].get('background_spec',{}));self.shadow_controls.load(step['params'].get('shadow',{}))
            self.set_color(step['params'].get('color','#f1ede5'),emit=False);self.transparent.setChecked(step['params'].get('transparent',True))
        self.watermark.setVisible(step['tool']=='watermark')
        if step['tool']=='watermark':self.watermark.load(step.get('params',{}))
        self.border.setVisible(step['tool']=='border')
        if step['tool']=='border':self.border.load(step.get('params',{}))
        if step['tool']=='palette':self.palette.load(step.get('params',{}))
        self.palette.setVisible(step['tool']=='palette');self.sample_box.setVisible(step['tool']=='sample');self.changed.emit()


class ImportDialog(QDialog):
    def __init__(self,count,parent=None):
        super().__init__(parent);self.setWindowTitle('导入图像');self.setMinimumWidth(380)
        layout=QVBoxLayout(self);layout.addWidget(QLabel(f'导入 {count} 张图像'))
        self.half=QCheckBox('2×2 降采样 · 宽高各减半');layout.addWidget(self.half)
        self.retain=QCheckBox('同时保留全尺寸原文件');self.retain.setEnabled(False);layout.addWidget(self.retain)
        self.half.toggled.connect(self.retain.setEnabled)
        note=QLabel('降采样后默认仅保存工作图像。电脑上的源文件不会被修改。');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(self.accept);bb.rejected.connect(self.reject);layout.addWidget(bb)


class ExportDialog(QDialog):
    def __init__(self,is_frame=False,parent=None):
        super().__init__(parent);self.setWindowTitle('导出作品' if is_frame else '导出图像');self.setMinimumWidth(390)
        layout=QVBoxLayout(self);f=QFormLayout();layout.addLayout(f)
        self.format=QComboBox();self.format.addItems(['JPEG','PNG','TIFF']);f.addRow('格式',self.format)
        self.quality=QSpinBox();self.quality.setRange(1,100);self.quality.setValue(95);f.addRow('JPEG 质量',self.quality)
        self.compress=QCheckBox('TIFF 无损压缩');self.compress.setChecked(True);f.addRow(self.compress)
        self.half=QCheckBox('导出时 2×2 降采样');f.addRow(self.half)
        self.width=QSpinBox();self.width.setRange(16,30000);self.width.setValue(4000)
        if is_frame:f.addRow('作品宽度 / px',self.width)
        self.transparent=QCheckBox('作品底透明');self.transparent.setChecked(True)
        if is_frame:f.addRow(self.transparent)
        self.color='#ffffff';self.bg=button('JPEG / 作品底色 · #FFFFFF',self.pick);f.addRow(self.bg)
        note=QLabel('JPEG 合成底色并输出 8 位；PNG 和 TIFF 保留 16 位与透明度。降采样会再次将当前尺寸减半。');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        self.format.currentTextChanged.connect(self.update_fields);self.update_fields()
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(self.accept);bb.rejected.connect(self.reject);layout.addWidget(bb)
    def update_fields(self):
        self.quality.setEnabled(self.format.currentText()=='JPEG');self.compress.setEnabled(self.format.currentText()=='TIFF')
    def pick(self):
        c=QColorDialog.getColor(QColor(self.color),self,'导出背景')
        if c.isValid():self.color=c.name();self.bg.setText('底色 · '+self.color.upper())
    def options(self):
        return dict(fmt=self.format.currentText(),quality=self.quality.value(),half=self.half.isChecked(),background=self.color,compress=self.compress.isChecked())


class WorkflowDialog(QDialog):
    def __init__(self,current_step,existing=None,parent=None):
        super().__init__(parent);self.setWindowTitle('步骤工作流');self.resize(460,420)
        self.steps=copy.deepcopy(existing or [current_step]);self.current=copy.deepcopy(current_step)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('按顺序执行，每一步都产生独立结果。'))
        self.list=QListWidget();layout.addWidget(self.list)
        row=QHBoxLayout()
        row.addWidget(button('加入当前工具',self.add));row.addWidget(button('上移',lambda:self.move(-1)));row.addWidget(button('下移',lambda:self.move(1)));row.addWidget(button('移除',self.remove));layout.addLayout(row)
        note=QLabel('先在右侧工具面板设置参数，再加入步骤。选中步骤可在下方查看参数。');note.setWordWrap(True);layout.addWidget(note)
        self.details=QLabel();self.details.setWordWrap(True);self.details.setObjectName('muted');layout.addWidget(self.details)
        self.list.currentRowChanged.connect(self.detail)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(self.accept);bb.rejected.connect(self.reject);layout.addWidget(bb);self.refresh()
    def refresh(self):
        self.list.clear()
        for n,s in enumerate(self.steps):self.list.addItem(f"{n+1:02}  {TOOLS.get(s['tool']).label if s['tool'] in TOOLS else s['tool']}")
    def detail(self,row):
        self.details.setText(str(self.steps[row]['params']) if 0<=row<len(self.steps) else '')
    def add(self):self.steps.append(copy.deepcopy(self.current));self.refresh()
    def remove(self):
        row=self.list.currentRow()
        if row>=0:self.steps.pop(row);self.refresh()
    def move(self,d):
        i=self.list.currentRow();j=i+d
        if 0<=i<len(self.steps) and 0<=j<len(self.steps):self.steps[i],self.steps[j]=self.steps[j],self.steps[i];self.refresh();self.list.setCurrentRow(j)
