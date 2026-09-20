"""Explicit layout constraints, shared by palette and frame editors."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox,QFormLayout,QComboBox,QCheckBox,QLabel
from .effect_controls import number


class LayoutControls(QGroupBox):
    changed=Signal()
    def __init__(self):
        super().__init__('精细布局');self.loading=False;self.source=(1,1);self.captured_ratio=None
        self.setCheckable(True);self.setChecked(False);f=QFormLayout(self);f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.unit=QComboBox();self.unit.addItems(['照片短边 %','像素']);f.addRow('尺寸单位',self.unit)
        self.values={}
        for key,label,value,low,high in [('top','上留边',3,0,10000),('right','右留边',3,0,10000),('bottom','下留边',3,0,10000),('left','左留边',3,0,10000),('gap','间距',2,0,10000),('card_width','色卡宽（0 自动）',0,0,30000),('card_height','色卡高（0 自动）',0,0,30000),('offset','色卡对齐偏移',0,-10000,10000),('outer_scale','外框整体尺寸 %',100,100,1000),('position_x','内容水平位置 %',50,0,100),('position_y','内容垂直位置 %',50,0,100)]:
            spin=number(value,low,high);spin.setAccessibleName(label);self.values[key]=spin;f.addRow(label,spin);spin.valueChanged.connect(lambda _,k=key:self.value_changed(k))
        self.link=QComboBox();self.link.addItems(['四边独立','四边同值','横纵成对']);f.addRow('留边联动',self.link)
        self.actual=QLabel();self.actual.setWordWrap(True);f.addRow(self.actual)
        self.align=QComboBox();self.align.addItems(['起点（左 / 上）','居中','末端（右 / 下）']);self.align.setCurrentIndex(1);f.addRow('色卡对齐',self.align)
        self.ring_lock=QCheckBox('色卡环保持圆形');self.ring_lock.setChecked(True);f.addRow(self.ring_lock)
        self.ratio=QComboBox();self.ratio.addItems(['自由外框','保持当前外框比例','外框匹配图像比例']);f.addRow('比例',self.ratio)
        hint=QLabel('留边值为最小留白；比例约束增加的空间按内容位置分配，下方显示实际像素边距。0 自动继承色卡原尺寸。');hint.setWordWrap(True);f.addRow(hint)
        self.ratio.currentIndexChanged.connect(self.ratio_changed)
        self.unit.currentIndexChanged.connect(self.slider_ranges)
        for c in (self.unit,self.align):c.currentIndexChanged.connect(self.emit_changed)
        self.ring_lock.toggled.connect(self.emit_changed);self.toggled.connect(self.emit_changed)
    def slider_ranges(self,*_):
        span=1200 if self.unit.currentIndex() else 100
        for key in ('top','right','bottom','left','gap','card_width','card_height','offset'):
            self.values[key].setSliderRange(-span if key=='offset' else 0,span)
    def value_changed(self,key):
        if self.loading:return
        if key in ('top','right','bottom','left') and self.link.currentIndex():
            keys=('top','right','bottom','left') if self.link.currentIndex()==1 else ('top','bottom') if key in ('top','bottom') else ('left','right')
            for k in keys:
                self.values[k].blockSignals(True);self.values[k].setValue(self.values[key].value());self.values[k].blockSignals(False)
        self.emit_changed()
    def emit_changed(self,*_):
        if not self.loading:
            for key,spin in self.values.items():spin.setSingleStep(1 if self.unit.currentIndex() and key not in ('outer_scale','position_x','position_y') else .1)
            self.changed.emit()
    def ratio_changed(self,index):
        if self.loading:return
        if index==1:self.captured_ratio=None
        self.changed.emit()
    def params(self):
        return dict(enabled=self.isChecked(),unit='px' if self.unit.currentIndex() else 'percent',align=self.align.currentIndex(),ring_lock=self.ring_lock.isChecked(),ratio_mode=self.ratio.currentIndex(),ratio=self.captured_ratio,**{k:v.value() for k,v in self.values.items()})
    def load(self,p):
        self.loading=True;self.setChecked(p.get('enabled',False));self.unit.setCurrentIndex(p.get('unit')=='px');self.align.setCurrentIndex(p.get('align',1));self.ring_lock.setChecked(p.get('ring_lock',True));self.ratio.setCurrentIndex(p.get('ratio_mode',0));self.captured_ratio=p.get('ratio')
        defaults=dict(top=3,right=3,bottom=3,left=3,gap=2,card_width=0,card_height=0,offset=0,outer_scale=100,position_x=50,position_y=50)
        for k,v in self.values.items():v.setValue(p.get(k,defaults[k]))
        self.slider_ranges();self.loading=False
