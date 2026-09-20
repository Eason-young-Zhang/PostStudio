import copy
from PySide6.QtCore import Signal,Qt
from PySide6.QtGui import QFont,QColor,QFontDatabase
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,QListWidgetItem,QPushButton,QComboBox,QCheckBox,QFontComboBox,QPlainTextEdit,QLineEdit,QColorDialog,QLabel,QAbstractItemView)
from .effect_controls import number,color_icon,ShadowControls
from .watermark import DEFAULT_MARK
from .metadata import FIELDS


class WatermarkControls(QWidget):
    changed=Signal()
    resourceRequested=Signal()
    def __init__(self):
        super().__init__();self.layers=[copy.deepcopy(DEFAULT_MARK)];self.loading=False;self.index=0;self.resources={}
        v=QVBoxLayout(self);self.list=QListWidget();self.list.setMaximumHeight(115);self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);v.addWidget(self.list)
        self.list.model().rowsMoved.connect(self.reorder);self.list.currentRowChanged.connect(self.select)
        row=QHBoxLayout();v.addLayout(row)
        for i,(label,fn) in enumerate([('＋ 文字',self.add),('＋ 图片',self.resourceRequested.emit),('复制',self.duplicate),('删除',self.remove)]):
            if i==2:row=QHBoxLayout();v.addLayout(row)
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.enabled=QCheckBox('启用此水印');v.addWidget(self.enabled);self.enabled.toggled.connect(self.change)
        self.name=QLineEdit();self.name.textEdited.connect(self.change);v.addWidget(self.name)
        self.text=QPlainTextEdit();self.text.setMaximumHeight(95);self.text.textChanged.connect(self.change);v.addWidget(self.text)
        self.fields=QComboBox();self.fields.addItem('插入照片字段…',None)
        for key,label in FIELDS.items():self.fields.addItem(label,key)
        self.fields.activated.connect(self.insert_field);v.addWidget(self.fields)
        self.resolved_text=QLabel();self.resolved_text.setWordWrap(True);v.addWidget(self.resolved_text)
        f=QFormLayout();f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);v.addLayout(f);self.font=QFontComboBox();self.font.currentFontChanged.connect(self.font_changed);f.addRow('字体',self.font);self.font_note=QLabel();self.font_note.setWordWrap(True);f.addRow(self.font_note)
        self.bold=QCheckBox('粗体');self.bold.toggled.connect(self.change);f.addRow(self.bold)
        self.combos={}
        for key,label,options in [('unit','尺寸单位',[('短边百分比','percent'),('像素','px')]),('reference','定位参考',[('整张图像','image'),('原照片区域','photo'),('下边框区域','bottom')]),('align','文字对齐',[('左','left'),('中','center'),('右','right')]),('blend','混合模式',[('正常','normal'),('正片叠底','multiply'),('滤色','screen'),('叠加','overlay'),('柔光','softlight'),('差值','difference')]),('missing','缺失字段',[('隐藏片段','hide'),('显示占位符','placeholder'),('跳过本张并报告','error')])]:
            c=QComboBox()
            for title,value in options:c.addItem(title,value)
            self.combos[key]=c;f.addRow(label,c);c.currentIndexChanged.connect(self.change)
        self.anchor=QComboBox();self.anchor.addItems(['左上','上中','右上','左中','居中','右中','左下','下中','右下']);f.addRow('锚点',self.anchor);self.anchor.currentIndexChanged.connect(self.change)
        self.values={}
        for key,label,lo,hi in [('size','字号',.1,1000),('width','水印宽度 %',.1,200),('x','水平偏移',-10000,10000),('y','垂直偏移',-10000,10000),('opacity','不透明度 %',0,100),('rotation','旋转 °',-360,360),('spacing','字距（字号 %）',-50,200),('line_height','行距 %',50,300),('stroke','描边（字号 %）',0,100)]:
            n=number(0,lo,hi);n.setAccessibleName(label);self.values[key]=n;f.addRow(label,n);n.valueChanged.connect(self.change)
        self.color_buttons={}
        for key,label in [('color','文字颜色'),('stroke_color','描边颜色')]:
            b=QPushButton();b.clicked.connect(lambda _,k=key:self.choose(k));f.addRow(label,b);self.color_buttons[key]=b
        self.shadow=ShadowControls();v.addWidget(self.shadow);self.shadow.changed.connect(self.change)
        hint=QLabel('在预览中拖动当前水印；箭头微移，Shift 加大步幅。字号单位相对定位区域短边。');hint.setWordWrap(True);v.addWidget(hint);self.combos['unit'].currentIndexChanged.connect(self.slider_ranges);self.refresh()
    def slider_ranges(self,*_):
        pixels=self.combos['unit'].currentData()=='px'
        self.values['size'].setSliderRange(.1,300 if pixels else 100)
        for key in ('x','y'):self.values[key].setSliderRange(-1200 if pixels else -100,1200 if pixels else 100)
    def refresh(self):
        self.list.blockSignals(True);self.list.clear()
        for i,p in enumerate(self.layers):
            item=QListWidgetItem(p['name']);item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(p));self.list.addItem(item)
        self.index=min(self.index,len(self.layers)-1);self.list.setCurrentRow(self.index);self.list.blockSignals(False);self.select(self.index)
    def select(self,i):
        if i<0:return
        self.loading=True;self.index=i;p={**DEFAULT_MARK,**self.layers[i]};self.name.setText(p['name']);self.enabled.setChecked(p['enabled']);self.text.setPlainText(p['text']);self.text.setEnabled(p['kind']=='text');self.fields.setEnabled(p['kind']=='text');self.font.setCurrentFont(QFont(p['font']));self.font_note.setText('缺少字体：'+p['font']+'。请选择替代字体；生成前会再次检查。' if p['font'] not in QFontDatabase.families() else '');self.bold.setChecked(p['bold']);self.anchor.setCurrentIndex(p['anchor'])
        for k,c in self.combos.items():c.setCurrentIndex(c.findData(p[k]))
        for k,c in self.values.items():c.setValue(p[k])
        for k,b in self.color_buttons.items():color_icon(b,p[k])
        self.shadow.load(p['shadow']);self.slider_ranges();self.loading=False
    def font_changed(self,font):
        if self.loading:return
        self.layers[self.index]['font']=font.family();self.font_note.clear();self.change()
    def change(self,*_):
        if self.loading:return
        p=self.layers[self.index];p.update(name=self.name.text(),enabled=self.enabled.isChecked(),text=self.text.toPlainText(),bold=self.bold.isChecked(),anchor=self.anchor.currentIndex(),shadow=self.shadow.params(),**{k:c.currentData() for k,c in self.combos.items()},**{k:v.value() for k,v in self.values.items()})
        item=self.list.item(self.index)
        if item:item.setText(p['name']);item.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(p))
        self.changed.emit()
    def reorder(self,*_):
        if self.loading:return
        self.layers=[copy.deepcopy(self.list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.list.count())];self.index=max(0,self.list.currentRow());self.select(self.index);self.changed.emit()
    def insert_field(self,i):
        if i:self.text.insertPlainText('{'+self.fields.itemText(i)+'}');self.fields.setCurrentIndex(0)
    def choose(self,k):
        c=QColorDialog.getColor(QColor(self.layers[self.index][k]),self)
        if c.isValid():self.layers[self.index][k]=c.name();color_icon(self.color_buttons[k],c.name());self.change()
    def add(self):self.layers.append(copy.deepcopy(DEFAULT_MARK));self.index=len(self.layers)-1;self.refresh();self.changed.emit()
    def add_image(self,resource,name):
        p=copy.deepcopy(DEFAULT_MARK);p.update(kind='image',resource=resource,name=name);self.layers.append(p);self.index=len(self.layers)-1;self.refresh();self.changed.emit()
    def duplicate(self):self.layers.append(copy.deepcopy(self.layers[self.index]));self.index=len(self.layers)-1;self.refresh();self.changed.emit()
    def remove(self):
        if len(self.layers)>1:self.layers.pop(self.index);self.refresh();self.changed.emit()
        else:self.enabled.setChecked(False)
    def params(self):return dict(layers=copy.deepcopy(self.layers))
    def load(self,p):self.layers=copy.deepcopy(p.get('layers') or [DEFAULT_MARK]);self.index=0;self.refresh()
