"""Reusable compact controls. Parameters are always serializable values."""
import copy
from PySide6.QtCore import Signal,Qt
from PySide6.QtGui import QColor,QPixmap,QIcon
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QComboBox,QDoubleSpinBox,QPushButton,QCheckBox,QListWidget,QColorDialog,QGroupBox,QSlider)
from .effects import DEFAULT_SHADOW,DEFAULT_BACKGROUND
from .number_control import NumberControl


def color_icon(button,color):
    pix=QPixmap(24,16);pix.fill(QColor(color));button.setIcon(QIcon(pix));button.setText(color.upper())


def number(value=0,low=0,high=10000,step=.1):
    return NumberControl(value,low,high,step)


class ShadowControls(QGroupBox):
    changed=Signal()
    def __init__(self,title='悬浮阴影'):
        super().__init__(title);self.setCheckable(True);self.setChecked(False);self.color='#101923'
        f=QFormLayout(self);f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);self.values={}
        for key,label,lo,hi,default in [('opacity','不透明度 %',0,100,25),('blur','模糊',0,500,12),('x','水平偏移',-1000,1000,0),('y','垂直偏移',-1000,1000,6)]:
            spin=number(default,lo,hi);spin.setAccessibleName(label);f.addRow(label,spin);self.values[key]=spin;spin.valueChanged.connect(self.changed)
        self.unit=QComboBox();self.unit.addItems(['像素','短边百分比']);f.addRow('单位',self.unit);self.unit.currentIndexChanged.connect(self.changed)
        self.pick=QPushButton();color_icon(self.pick,self.color);f.addRow('颜色',self.pick);self.pick.clicked.connect(self.choose);self.toggled.connect(self.changed)
    def choose(self):
        c=QColorDialog.getColor(QColor(self.color),self)
        if c.isValid():self.color=c.name();color_icon(self.pick,self.color);self.changed.emit()
    def params(self):return dict(enabled=self.isChecked(),color=self.color,unit='percent' if self.unit.currentIndex() else 'px',**{k:v.value() for k,v in self.values.items()})
    def load(self,p):
        p={**DEFAULT_SHADOW,**p};self.setChecked(p['enabled']);self.color=p['color'];color_icon(self.pick,self.color);self.unit.setCurrentIndex(p['unit']=='percent')
        for k,v in self.values.items():v.setValue(p[k])


class BackgroundControls(QGroupBox):
    changed=Signal()
    def __init__(self):
        super().__init__('背景样式');self.data=copy.deepcopy(DEFAULT_BACKGROUND);self.loading=False
        v=QVBoxLayout(self);f=QFormLayout();f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);v.addLayout(f);self.kind=QComboBox()
        for label,key in [('纯色（使用上方颜色）','solid'),('线性渐变','linear'),('径向渐变','radial')]:self.kind.addItem(label,key)
        f.addRow('类型',self.kind);self.values={}
        for key,label,lo,hi in [('angle','角度',-360,360),('cx','中心 X %',0,100),('cy','中心 Y %',0,100),('radius','半径 %',.1,200)]:
            spin=number(self.data[key],lo,hi);spin.setAccessibleName(label);self.values[key]=spin;f.addRow(label,spin);spin.valueChanged.connect(self.changed)
        self.stops=QListWidget();self.stops.setMaximumHeight(100);v.addWidget(self.stops);row=QHBoxLayout();v.addLayout(row)
        for label,fn in [('＋ 色标',self.add),('删除',self.remove),('颜色',self.choose)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.position=number(0,0,100);self.alpha=number(100,0,100);self.position.setAccessibleName("色标位置");self.alpha.setAccessibleName("色标不透明度");f2=QFormLayout();f2.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);f2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f2.addRow('色标位置 %',self.position);f2.addRow('色标不透明度 %',self.alpha);v.addLayout(f2)
        self.stops.currentRowChanged.connect(self.select);self.position.valueChanged.connect(self.edit);self.alpha.valueChanged.connect(self.edit);self.kind.currentIndexChanged.connect(self.changed);self.refresh()
    def refresh(self,index=0):
        self.stops.blockSignals(True);self.stops.clear()
        for s in self.data['stops']:
            pix=QPixmap(24,16);pix.fill(QColor(s['color']));self.stops.addItem(f"{s['position']:g}% · {s['color']}");self.stops.item(self.stops.count()-1).setIcon(QIcon(pix))
        self.stops.setCurrentRow(min(index,self.stops.count()-1));self.stops.blockSignals(False);self.select(self.stops.currentRow())
    def select(self,i):
        if i<0:return
        self.loading=True;s=self.data['stops'][i];self.position.setValue(s['position']);self.alpha.setValue(s['alpha']);self.loading=False
    def edit(self):
        i=self.stops.currentRow()
        if self.loading or i<0:return
        self.data['stops'][i].update(position=self.position.value(),alpha=self.alpha.value());self.refresh(i);self.changed.emit()
    def add(self):self.data['stops'].append(dict(position=50.,color='#91acc2',alpha=100.));self.refresh(len(self.data['stops'])-1);self.changed.emit()
    def remove(self):
        i=self.stops.currentRow()
        if len(self.data['stops'])>2 and i>=0:self.data['stops'].pop(i);self.refresh();self.changed.emit()
    def choose(self):
        i=self.stops.currentRow()
        if i<0:return
        c=QColorDialog.getColor(QColor(self.data['stops'][i]['color']),self)
        if c.isValid():self.data['stops'][i]['color']=c.name();self.refresh(i);self.changed.emit()
    def params(self):return dict(kind=self.kind.currentData(),stops=copy.deepcopy(self.data['stops']),**{k:v.value() for k,v in self.values.items()})
    def load(self,p):
        self.data=copy.deepcopy({**DEFAULT_BACKGROUND,**p});self.kind.setCurrentIndex(max(0,self.kind.findData(self.data['kind'])))
        for k,v in self.values.items():v.setValue(self.data[k])
        self.refresh()
