import copy
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,QPushButton,QComboBox,QCheckBox,QColorDialog,QAbstractItemView
from PySide6.QtGui import QColor
from .border import DEFAULT_LAYER
from .effect_controls import number,BackgroundControls,ShadowControls,color_icon


class BorderControls(QWidget):
    changed=Signal()
    def __init__(self):
        super().__init__();self.layers=[copy.deepcopy(DEFAULT_LAYER)];self.loading=False;self.index=0;self.color='#f1ede5';self.source_size=(1200,800)
        v=QVBoxLayout(self)
        self.template=QComboBox();self.template.addItems(['选择边框起点…','细线框','四周留白','下方题注框','双层边框']);self.template.activated.connect(self.apply_template);v.addWidget(self.template)
        self.list=QListWidget();self.list.setMaximumHeight(110);self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.list.model().rowsMoved.connect(self.reorder);v.addWidget(self.list)
        row=QHBoxLayout();v.addLayout(row)
        for label,fn in [('＋',self.add),('复制',self.duplicate),('删除',self.remove),('↑',lambda:self.move(-1)),('↓',lambda:self.move(1))]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        self.enabled=QCheckBox('启用此层');v.addWidget(self.enabled);self.enabled.toggled.connect(self.change)
        f=QFormLayout();f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);v.addLayout(f);self.mode=QComboBox();self.mode.addItems(['外扩','内遮']);f.addRow('方式',self.mode);self.mode.currentIndexChanged.connect(self.change)
        self.unit=QComboBox();self.unit.addItems(['短边百分比','像素']);f.addRow('单位',self.unit);self.unit.currentIndexChanged.connect(self.change)
        self.values={}
        for key,label,hi in [('top','上边宽',10000),('right','右边宽',10000),('bottom','下边宽',10000),('left','左边宽',10000),('radius','圆角',10000),('opacity','不透明度 %',100),('outer_scale','外框整体尺寸 %',1000),('position_x','内容水平位置 %',100),('position_y','内容垂直位置 %',100),('stroke','描边宽',10000)]:
            spin=number(100 if key=='outer_scale' else 0,100 if key=='outer_scale' else 0,hi);spin.setAccessibleName(label);f.addRow(label,spin);self.values[key]=spin;spin.valueChanged.connect(lambda _,k=key:self.change(k))
        self.link=QComboBox();self.link.addItems(['四边独立','四边同值','横纵成对']);f.addRow('留边联动',self.link)
        self.ratio=QComboBox();self.ratio.addItems(['自由外框','保持当前外框比例','外框匹配图像比例','指定外框比例']);f.addRow('外框比例',self.ratio);self.ratio.currentIndexChanged.connect(self.ratio_change)
        self.ratio_options=QWidget();rv=QVBoxLayout(self.ratio_options);rv.setContentsMargins(0,0,0,0)
        self.ratio_presets=QComboBox()
        for label,pair in [('1:1',(1,1)),('3:2',(3,2)),('2:3',(2,3)),('4:3',(4,3)),('3:4',(3,4)),('16:9',(16,9)),('9:16',(9,16)),('5:4',(5,4)),('4:5',(4,5)),('自定义',None)]:self.ratio_presets.addItem(label,pair)
        rv.addWidget(self.ratio_presets);ratio_row=QFormLayout();ratio_row.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);ratio_row.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);rv.addLayout(ratio_row)
        self.ratio_width=number(3,.001,10000);self.ratio_height=number(2,.001,10000)
        for control,label in [(self.ratio_width,'比例宽'),(self.ratio_height,'比例高')]:control.setDecimals(3);control.setSingleStep(.1);control.setAccessibleName(label)
        ratio_row.addRow('比例宽',self.ratio_width);ratio_row.addRow('比例高',self.ratio_height)
        hint=QLabel('宽 : 高。扩展外围留白以容纳图像，不裁切或拉伸照片。');hint.setWordWrap(True);rv.addWidget(hint)
        f.addRow(self.ratio_options);self.ratio_presets.activated.connect(self.choose_ratio)
        self.ratio_width.valueChanged.connect(self.custom_ratio_changed);self.ratio_height.valueChanged.connect(self.custom_ratio_changed)
        self.style=QComboBox();self.style.addItems(['填充','描边']);f.addRow('形式',self.style);self.style.currentIndexChanged.connect(self.change)
        self.color_button=QPushButton();self.color_button.clicked.connect(self.choose);f.addRow('边框颜色',self.color_button)
        self.background=BackgroundControls();v.addWidget(self.background);self.background.changed.connect(self.change)
        self.shadow=ShadowControls();v.addWidget(self.shadow);self.shadow.changed.connect(self.change)
        self.unit.currentIndexChanged.connect(self.slider_ranges);self.list.currentRowChanged.connect(self.select);self.refresh()
    def slider_ranges(self,*_):
        span=1200 if self.unit.currentIndex() else 100
        for key in ('top','right','bottom','left','radius','stroke'):self.values[key].setSliderRange(0,span)
    def choose(self):
        c=QColorDialog.getColor(QColor(self.color),self)
        if c.isValid():self.color=c.name();color_icon(self.color_button,self.color);self.change()
    def change(self,key=None):
        if self.loading:return
        if key in ('top','right','bottom','left') and self.link.currentIndex():
            keys=('top','right','bottom','left') if self.link.currentIndex()==1 else ('top','bottom') if key in ('top','bottom') else ('left','right')
            for k in keys:
                self.values[k].blockSignals(True);self.values[k].setValue(self.values[key].value());self.values[k].blockSignals(False)
        ratio=self.ratio_width.value()/self.ratio_height.value() if self.ratio.currentIndex()==3 else self.layers[self.index].get('ratio')
        self.layers[self.index]=dict(ratio_mode=self.ratio.currentIndex(),ratio=ratio,custom_ratio=[self.ratio_width.value(),self.ratio_height.value()],style='stroke' if self.style.currentIndex() else 'fill',mode='outer' if self.mode.currentIndex()==0 else 'inner',unit='percent' if self.unit.currentIndex()==0 else 'px',enabled=self.enabled.isChecked(),background={**self.background.params(),'color':self.color},shadow=self.shadow.params(),**{k:v.value() for k,v in self.values.items()});self.list.item(self.index).setData(Qt.ItemDataRole.UserRole,copy.deepcopy(self.layers[self.index]));self.ratio.setEnabled(self.mode.currentIndex()==0);self.ratio_options.setVisible(self.ratio.currentIndex()==3);self.ratio_options.setEnabled(self.mode.currentIndex()==0);self.values['outer_scale'].setEnabled(self.mode.currentIndex()==0);self.changed.emit()
    def refresh(self):
        self.list.blockSignals(True);self.list.clear()
        for i,p in enumerate(self.layers):self.list.addItem(f"{i+1:02} · {'外扩' if p['mode']=='outer' else '内遮'}边框");self.list.item(i).setData(Qt.ItemDataRole.UserRole,copy.deepcopy(p))
        self.index=min(self.index,len(self.layers)-1);self.list.setCurrentRow(self.index);self.list.blockSignals(False);self.select(self.index)
    def select(self,i):
        if i<0:return
        self.loading=True;self.index=i;p={**DEFAULT_LAYER,**self.layers[i]};self.mode.setCurrentIndex(p['mode']!='outer');self.unit.setCurrentIndex(p['unit']=='px');self.enabled.setChecked(p['enabled'])
        for k,v in self.values.items():v.setValue(p[k])
        pair=p.get('custom_ratio',[3,2]);self.ratio_width.setValue(pair[0]);self.ratio_height.setValue(pair[1]);self.sync_ratio_preset()
        self.ratio_options.setVisible(p['ratio_mode']==3);self.ratio_options.setEnabled(p['mode']=='outer')
        self.ratio.setCurrentIndex(p['ratio_mode']);self.ratio.setEnabled(p['mode']=='outer');self.values['outer_scale'].setEnabled(p['mode']=='outer');self.style.setCurrentIndex(p['style']=='stroke')
        self.color=p['background'].get('color','#f1ede5');color_icon(self.color_button,self.color);self.background.load(p['background']);self.shadow.load(p['shadow']);self.slider_ranges();self.loading=False
    def add(self):self.layers.append(copy.deepcopy(DEFAULT_LAYER));self.index=len(self.layers)-1;self.refresh();self.changed.emit()
    def duplicate(self):self.layers.append(copy.deepcopy(self.layers[self.index]));self.index=len(self.layers)-1;self.refresh();self.changed.emit()
    def remove(self):
        if len(self.layers)>1:self.layers.pop(self.index);self.refresh();self.changed.emit()
    def move(self,d):
        j=self.index+d
        if 0<=j<len(self.layers):self.layers[self.index],self.layers[j]=self.layers[j],self.layers[self.index];self.index=j;self.refresh();self.changed.emit()
    def params(self):return dict(layers=copy.deepcopy(self.layers))
    def load(self,p):self.layers=copy.deepcopy(p.get('layers',[DEFAULT_LAYER]));self.index=0;self.refresh()

    def sync_ratio_preset(self):
        pair=(self.ratio_width.value(),self.ratio_height.value())
        match=next((i for i in range(self.ratio_presets.count()-1) if tuple(self.ratio_presets.itemData(i))==pair),self.ratio_presets.count()-1)
        self.ratio_presets.setCurrentIndex(match)
    def choose_ratio(self,index):
        pair=self.ratio_presets.itemData(index)
        if pair is None:return
        self.loading=True;self.ratio_width.setValue(pair[0]);self.ratio_height.setValue(pair[1]);self.loading=False;self.change()
    def custom_ratio_changed(self,*_):
        if self.loading:return
        self.sync_ratio_preset();self.change()

    def ratio_change(self,index):
        if self.loading:return
        if index==1:
            from .border import geometry
            layers=copy.deepcopy(self.layers[:self.index+1]);layers[-1].update(ratio_mode=0,outer_scale=100)
            g=geometry(*self.source_size,dict(layers=layers));self.layers[self.index]['ratio']=g['width']/g['height']
        self.change()
    def reorder(self,*_):
        if self.loading:return
        self.layers=[copy.deepcopy(self.list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.list.count())];self.index=max(0,self.list.currentRow());self.select(self.index);self.changed.emit()
    def apply_template(self,index):
        if not index:return
        base=copy.deepcopy(DEFAULT_LAYER)
        if index==1:base.update(top=.2,right=.2,bottom=.2,left=.2,background=dict(kind='solid',color='#26333f'))
        if index==3:base.update(top=4,right=4,bottom=14,left=4)
        self.layers=[base]
        if index==4:self.layers=[{**copy.deepcopy(DEFAULT_LAYER),'top':.2,'right':.2,'bottom':.2,'left':.2,'background':dict(kind='solid',color='#26333f')},base]
        self.index=0;self.refresh();self.template.setCurrentIndex(0);self.changed.emit()
