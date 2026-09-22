"""Manual multi-source collage page, with cached previews and full-width sliders."""
import copy
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSignalBlocker
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
                             QScrollArea,QColorDialog,QTabBar)
from .number_control import NumberControl
from .history import History
from .collage import defaults,template,geometry,paint,validate


class CollagePreview(QWidget):
    changed=Signal()
    selected=Signal(int)
    def __init__(self,editor):
        super().__init__();self.editor=editor;self.setMinimumSize(280,260);self.setMouseTracking(True)
        self.drag=None;self.scale=1.;self.origin=QPointF();self.cells={};self.handles=[]
    def paintEvent(self,event):
        p=self.editor.params;qp=QPainter(self);qp.fillRect(self.rect(),QColor('#181d20'))
        self.scale=max(.001,min((self.width()-48)/p['width'],(self.height()-48)/p['height']))
        self.origin=QPointF((self.width()-p['width']*self.scale)/2,(self.height()-p['height']*self.scale)/2)
        qp.translate(self.origin);qp.scale(self.scale,self.scale)
        try:
            self.cells,_,self.handles=geometry(p);paint(qp,p,lambda id:self.editor.images[id])
            qp.setPen(QPen(QColor('#9dbed8'),2/self.scale));qp.setBrush(Qt.BrushStyle.NoBrush)
            qp.drawRect(self.cells[self.editor.index].adjusted(1/self.scale,1/self.scale,-1/self.scale,-1/self.scale))
        except ValueError:
            self.cells={};self.handles=[]
        qp.end()
    def point(self,event):return (event.position()-self.origin)/self.scale
    def hit(self,pos):return next((i for i,r in self.cells.items() if r.contains(pos)),None)
    def divider(self,pos):
        for path,axis,rect,offset in reversed(self.handles):
            center=rect.x()+offset if axis=='x' else rect.y()+offset
            distance=abs((pos.x() if axis=='x' else pos.y())-center)*self.scale
            if rect.contains(pos) and distance<7:return path,axis,rect
    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        pos=self.point(event);hit=self.divider(pos)
        self.before=copy.deepcopy(self.editor.params)
        if hit:self.drag=('divider',hit);return
        index=self.hit(pos)
        if index is not None:
            self.editor.index=index;self.selected.emit(index);self.update()
            self.drag=('image',index,pos)
    def mouseMoveEvent(self,event):
        pos=self.point(event)
        if not self.drag:
            hit=self.divider(pos)
            self.setCursor((Qt.CursorShape.SplitHCursor if hit[1]=='x' else Qt.CursorShape.SplitVCursor) if hit else Qt.CursorShape.OpenHandCursor);return
        p=self.editor.params
        if self.drag[0]=='divider':
            path,axis,rect=self.drag[1];node=p['tree']
            for key in path:node=node[key]
            old=node['ratio'];node['ratio']=max(.05,min(.95,((pos.x()-rect.x())/rect.width() if axis=='x' else (pos.y()-rect.y())/rect.height())))
            try:geometry(p)
            except ValueError:node['ratio']=old
            self.update()
        elif self.editor.drag_mode.currentIndex()==1:
            index,start=self.drag[1:];cell=self.cells[index];slot=p['slots'][index]
            from .collage import image_rect
            im=self.editor.images[slot['asset']];dest=image_rect(im,cell,slot)
            original=self.before['slots'][index]
            for key,delta,space in [('x',pos.x()-start.x(),cell.width()-dest.width()),('y',pos.y()-start.y(),cell.height()-dest.height())]:
                if abs(space)>.001:slot[key]=max(0,min(100,original[key]+delta/space*100))
            self.editor.load_slot();self.update()
    def mouseReleaseEvent(self,event):
        if not self.drag:return
        if self.drag[0]=='image' and self.editor.drag_mode.currentIndex()==0:
            dest=self.hit(self.point(event));src=self.drag[1]
            if dest is not None and src!=dest:
                slots=self.editor.params['slots'];slots[src],slots[dest]=slots[dest],slots[src];self.editor.index=dest
        self.drag=None;self.editor.load_slot();self.changed.emit();self.update()


class CollageEditor(QWidget):
    back=Signal()
    submit=Signal(bool)
    def __init__(self,project,ids,target=None):
        super().__init__();self.project=project;self.target=target;self.index=0;self.loading=True
        self.params=copy.deepcopy(project.asset(target)['step']['params']) if target else defaults(ids)
        self.images={s['asset']:QImage(str(project.root/project.asset(s['asset'])['thumb'])) for s in self.params['slots']}
        self.history=History(self.params)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0)
        header=QHBoxLayout();header.setContentsMargins(18,12,18,12)
        back=QPushButton('← 返回画布');back.clicked.connect(self.back);header.addWidget(back)
        title=QLabel('画布 / 拼图');title.setObjectName('sectionTitle');header.addWidget(title,1)
        header.addWidget(QLabel(f"{len(self.params['slots'])} 张图片 → 1 张作品"));root.addLayout(header)
        body=QHBoxLayout();body.setSpacing(0);root.addLayout(body,1)
        area=QVBoxLayout();self.preview=CollagePreview(self);area.addWidget(self.preview,1)
        tip=QLabel('拖动图片交换位置 · 拖动分隔线调整布局 · 选择图片后可调整完整显示 / 裁切填满');tip.setObjectName('muted');tip.setWordWrap(True);area.addWidget(tip);body.addLayout(area,1)
        side=QWidget();side.setFixedWidth(320);body.addWidget(side);side_layout=QVBoxLayout(side);side_layout.setContentsMargins(16,16,16,16)
        self.tabs=QTabBar();self.tabs.addTab('布局');self.tabs.addTab('图片');self.tabs.addTab('框线');side_layout.addWidget(self.tabs)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);side_layout.addWidget(scroll,1)
        content=QWidget();scroll.setWidget(content);contents=QVBoxLayout(content);contents.setContentsMargins(0,10,0,10)
        self.pages=[]
        for _ in range(3):
            page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(14);contents.addWidget(page);self.pages.append(page)
        contents.addStretch();self.tabs.currentChanged.connect(self.switch_tab);self.switch_tab(0)
        layout=self.pages[0].layout()
        self.templates=QComboBox();self.templates.addItems(['网格','竖向排列','横向排列','主图＋辅图']);layout.addWidget(QLabel('起始布局'));layout.addWidget(self.templates)
        reset=QPushButton('使用此布局');layout.addWidget(reset);reset.clicked.connect(self.reset_template)
        self.ratio=QComboBox();self.ratio.addItems(['自定义','3:4','4:5','1:1','4:3']);layout.addWidget(QLabel('画面比例 · 宽 : 高'));layout.addWidget(self.ratio)
        self.controls={}
        self.add_number(layout,'width','输出宽度',1,20000,0,lambda v:self.resize_output('width',v))
        self.add_number(layout,'height','输出高度',1,20000,0,lambda v:self.resize_output('height',v))
        self.ratio.currentIndexChanged.connect(self.set_ratio)
        note=QLabel('尺寸包含外框；默认保留整张照片。比例可自由设置，不绑定平台上传规则。');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note)
        layout=self.pages[1].layout();self.slot_label=QLabel();layout.addWidget(self.slot_label)
        self.fit=QComboBox();self.fit.addItems(['完整显示（不裁切）','裁切填满']);layout.addWidget(self.fit);self.fit.currentIndexChanged.connect(self.slot_changed)
        self.drag_mode=QComboBox();self.drag_mode.addItems(['拖动：交换图片','拖动：调整图片位置']);layout.addWidget(self.drag_mode)
        self.add_number(layout,'x','水平位置 %',0,100,1,self.position_changed)
        self.add_number(layout,'y','垂直位置 %',0,100,1,self.position_changed)
        layout=self.pages[2].layout()
        label=QLabel('统一内框');label.setObjectName('sectionTitle');layout.addWidget(label)
        self.add_number(layout,'gap','分隔宽度',0,1000,1,lambda v:self.set_param('gap',v))
        self.add_color(layout,'line_color','框线颜色')
        self.add_number(layout,'line_opacity','框线不透明度 %',0,100,1,lambda v:self.set_param('line_opacity',v))
        label=QLabel('外框与留白');label.setObjectName('sectionTitle');layout.addWidget(label)
        self.add_color(layout,'background','底色 / 外框颜色')
        self.link=QComboBox();self.link.addItems(['四边独立','四边同步']);layout.addWidget(self.link)
        for i,name in enumerate(['上','右','下','左']):
            key=f'margin{i}';self.add_number(layout,key,name+'侧外框',0,2000,1,lambda v,i=i:self.margin_changed(i,v))
        self.error=QLabel();self.error.setWordWrap(True);self.error.setObjectName('muted');side_layout.addWidget(self.error)
        row=QHBoxLayout();undo=QPushButton('撤销');redo=QPushButton('重做');row.addWidget(undo);row.addWidget(redo);side_layout.addLayout(row)
        undo.clicked.connect(lambda:self.move_history(-1));redo.clicked.connect(lambda:self.move_history(1))
        self.save=QPushButton('保存修改 · 返回画布');self.save.setVisible(bool(target));self.save.clicked.connect(lambda:self.submit.emit(True));side_layout.addWidget(self.save)
        self.generate=QPushButton('生成拼图 · 返回画布');self.generate.setObjectName('primary');self.generate.clicked.connect(lambda:self.submit.emit(False));side_layout.addWidget(self.generate)
        self.preview.selected.connect(lambda _:self.load_slot());self.preview.changed.connect(self.changed)
        self.loading=False;self.load_controls();self.changed()
    def switch_tab(self,index):
        for i,page in enumerate(self.pages):page.setVisible(i==index)
    def add_number(self,layout,key,label,low,high,decimals,callback):
        c=NumberControl(0,low,high,.1 if decimals else 1);c.setDecimals(decimals);c.setAccessibleName(label)
        if key not in ('x','y','line_opacity'):c.setSuffix(' px')
        c.setSliderRange(low,min(high,6000 if key in ('width','height') else 300 if key.startswith('margin') or key=='gap' else high))
        layout.addWidget(c);self.controls[key]=c;c.valueChanged.connect(callback)
    def add_color(self,layout,key,label):
        button=QPushButton(label);layout.addWidget(button);button.clicked.connect(lambda:self.choose_color(key))
        setattr(self,key+'_button',button)
    def choose_color(self,key):
        color=QColorDialog.getColor(QColor(self.params[key]),self,'选择颜色')
        if color.isValid():self.params[key]=color.name();self.load_controls();self.changed()
    def set_param(self,key,value):
        if self.loading:return
        self.params[key]=value;self.changed()
    def margin_changed(self,index,value):
        if self.loading:return
        if self.link.currentIndex():self.params['margins']=[value]*4
        else:self.params['margins'][index]=value
        self.load_controls();self.changed()
    def resize_output(self,key,value):
        if self.loading:return
        self.params[key]=int(value)
        if self.ratio.currentIndex():
            a,b=map(int,self.ratio.currentText().split(':'))
            other='height' if key=='width' else 'width';self.params[other]=max(1,round(value*b/a if key=='width' else value*a/b))
        self.load_controls();self.changed()
    def set_ratio(self,index):
        if index:self.resize_output('width',self.params['width'])
    def reset_template(self):
        self.params['tree']=template(len(self.params['slots']),['grid','rows','columns','hero'][self.templates.currentIndex()]);self.changed()
    def slot_changed(self,index):
        if self.loading:return
        self.params['slots'][self.index]['fit']=['contain','cover'][index];self.changed()
    def position_changed(self,_):
        if self.loading:return
        slot=self.params['slots'][self.index]
        for key in ('x','y'):slot[key]=self.controls[key].value()
        self.changed()
    def load_slot(self):
        self.loading=True;slot=self.params['slots'][self.index]
        self.slot_label.setText('所选图片 · '+self.project.asset(slot['asset'])['name'])
        self.slot_label.setWordWrap(True);self.fit.setCurrentIndex(slot['fit']=='cover')
        for key in ('x','y'):self.controls[key].setValue(slot[key])
        self.loading=False
    def load_controls(self):
        self.loading=True
        for key,c in self.controls.items():
            if key in self.params:c.setValue(self.params[key])
            elif key.startswith('margin'):c.setValue(self.params['margins'][int(key[-1])])
        for key in ('line_color','background'):
            from .effect_controls import color_icon
            b=getattr(self,key+'_button');color_icon(b,self.params[key]);b.setText(('框线颜色' if key=='line_color' else '底色 / 外框颜色')+'  '+self.params[key].upper())
        self.loading=False;self.load_slot();self.preview.update()
    def changed(self):
        if self.loading:return
        message='';valid=True
        try:validate(self.params)
        except (ValueError,KeyError) as e:message=str(e);valid=False
        reason=self.project.revision_blocker(self.target) if self.target else None
        self.error.setText(message or reason or f"输出 {self.params['width']} × {self.params['height']} px · 保留独立原图")
        self.generate.setEnabled(valid);self.save.setEnabled(valid and not reason)
        self.history.record(self.params);self.preview.update()
    def move_history(self,delta):
        state=self.history.move(delta)
        if state is not None:
            self.params=state
            with QSignalBlocker(self.ratio):self.ratio.setCurrentIndex(0)
            self.load_controls();self.changed()
