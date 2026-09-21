"""Compact extraction and layout controls for the dedicated palette editor."""
import copy
from PySide6.QtCore import Qt,Signal,QSize
from PySide6.QtGui import QColor,QIcon,QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QSpinBox,QDoubleSpinBox,QSlider,QListWidget,QListWidgetItem,QAbstractItemView,QPushButton,QCheckBox,
    QTabBar,QColorDialog)
from .palette_render import DEFAULT_PALETTE
from .palette import hex_color
from .effect_controls import ShadowControls
from .layout_controls import LayoutControls


def push(text,fn):
    b=QPushButton(text);b.clicked.connect(fn);return b


class PaletteControls(QWidget):
    changed=Signal()
    pickRequested=Signal()
    def __init__(self):
        super().__init__();self.loading=False;self.manual=False;self.swatches=[];self.locked=[];self.background='#f1ede5';self.pick_target='swatch'
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.tabs=QTabBar();self.tabs.addTab("提色");self.tabs.addTab("排版");root.addWidget(self.tabs)
        extraction=QWidget();el=QVBoxLayout(extraction);el.setContentsMargins(0,12,0,0)
        row=QHBoxLayout();row.addWidget(QLabel('颜色数量'),1)
        self.count=QSpinBox();self.count.setRange(2,12);self.count.setValue(5);self.count.setKeyboardTracking(False);row.addWidget(self.count);el.addLayout(row)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(2,12);self.slider.setValue(5);self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus);el.addWidget(self.slider)
        self.slider.valueChanged.connect(self.count.setValue);self.count.valueChanged.connect(self.count_changed)
        self.mode=QComboBox();self.mode.addItem('面积主色','area');self.mode.addItem('特色配色','distinctive');self.mode.currentIndexChanged.connect(self.reextract);el.addWidget(self.mode)
        self.list=QListWidget();self.list.setMinimumHeight(150);self.list.setMaximumHeight(190);self.list.setIconSize(QSize(50,28));self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.model().rowsMoved.connect(self.reordered);self.list.itemChanged.connect(self.lock_changed);el.addWidget(self.list)
        hint=QLabel('勾选锁色 · 拖动排序 · 占比为估算值');hint.setObjectName('muted');hint.setWordWrap(True);el.addWidget(hint)
        row=QHBoxLayout();row.addWidget(push('图内取色',self.start_pick));row.addWidget(push('自选颜色',self.choose));el.addLayout(row)
        el.addWidget(push('保留锁色 · 重新提取',self.reextract));self.note=QLabel();self.note.setWordWrap(True);self.note.setObjectName('muted');el.addWidget(self.note)
        el.addStretch();root.addWidget(extraction)
        page=QWidget();pl=QVBoxLayout(page);pl.setContentsMargins(0,12,0,0);form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);pl.addLayout(form)
        self.style=QComboBox();self.style.addItem('色条','strip');self.style.addItem('色卡环','ring');form.addRow('形态',self.style)
        self.proportional=QCheckBox('按颜色占比分段');form.addRow(self.proportional)
        self.side=QComboBox()
        for label,value in [('下方','bottom'),('上方','top'),('左侧','left'),('右侧','right')]:self.side.addItem(label,value)
        form.addRow('位置',self.side);self.numbers={}
        for key,label,low,high,value in [('size','色卡尺寸',4,60,16),('gap','间距',0,20,2),('margin','留边',0,20,3)]:
            from .effect_controls import number
            spin=number(value,low,high);spin.setSuffix(' %');spin.setAccessibleName(label)
            spin.valueChanged.connect(self.emit_changed)
            form.addRow(spin);self.numbers[key]=spin
        hint=QLabel('尺寸、间距与留边以照片短边为基准。');hint.setWordWrap(True);hint.setObjectName('muted');pl.addWidget(hint)
        self.transparent=QCheckBox('背景透明');pl.addWidget(self.transparent)
        self.bg=push('背景 · #F1EDE5',self.choose_background);pl.addWidget(self.bg);pl.addWidget(push('从图片取背景色',self.start_background_pick))
        self.labels=QCheckBox('在色卡上显示色值与占比');pl.addWidget(self.labels)
        label_hint=QLabel('空间不足时省略文字，可增大色卡尺寸。');label_hint.setObjectName('muted');label_hint.setWordWrap(True);pl.addWidget(label_hint)
        self.output=QComboBox();self.output.addItem('照片＋色卡组合','composition');self.output.addItem('仅色卡','palette');pl.addWidget(self.output)
        self.source_size=(1,1);self.layout_controls=LayoutControls();pl.addWidget(self.layout_controls);self.layout_controls.changed.connect(self.emit_changed)
        self.photo_shadow=ShadowControls('照片悬浮阴影');pl.addWidget(self.photo_shadow);self.photo_shadow.changed.connect(self.emit_changed)
        self.card_shadow=ShadowControls('色卡悬浮阴影');pl.addWidget(self.card_shadow);self.card_shadow.changed.connect(self.emit_changed)
        pl.addStretch();root.addWidget(page);page.hide()
        self.pages=(extraction,page)
        self.tabs.currentChanged.connect(self.switch_page)
        for c in [self.style,self.side,self.output]:c.currentIndexChanged.connect(self.emit_changed)
        for c in [self.proportional,self.transparent,self.labels]:c.toggled.connect(self.emit_changed)
    def switch_page(self,index):
        for i,page in enumerate(self.pages):page.setVisible(i==index)
        self.updateGeometry()
    def sync_slider(self,slider,value):
        slider.blockSignals(True);slider.setValue(round(value));slider.blockSignals(False)
    def emit_changed(self,*_):
        if not self.loading:self.changed.emit()
    def count_changed(self,value):
        if value<len(self.locked):
            self.count.blockSignals(True);self.count.setValue(len(self.locked));self.count.blockSignals(False);value=len(self.locked)
            self.note.setText('颜色数量不能少于锁定颜色数量。')
        self.slider.blockSignals(True);self.slider.setValue(value);self.slider.blockSignals(False)
        self.reextract()
    def reextract(self,*_):
        if self.loading:return
        self.manual=False;self.note.setText('正在提取…');self.emit_changed()
    def params(self):
        p=dict(count=self.count.value(),mode=self.mode.currentData(),locked=copy.deepcopy(self.locked),
                    colors=[s['rgb16'] for s in self.swatches] if self.manual else [],style=self.style.currentData(),
                    proportional=self.proportional.isChecked(),side=self.side.currentData(),
                    **{k:s.value() for k,s in self.numbers.items()},transparent=self.transparent.isChecked(),
                    background=self.background,labels=self.labels.isChecked(),output=self.output.currentData(),
                    layout_options=self.layout_controls.params(),photo_shadow=self.photo_shadow.params(),card_shadow=self.card_shadow.params())
        from .palette_render import layout
        opts=p['layout_options']
        if opts['enabled'] and opts['ratio_mode']==1 and opts['ratio'] is None:
            from .palette_render import layout
            free=copy.deepcopy(p);free['layout_options']['ratio_mode']=0;free['layout_options']['outer_scale']=100
            g=layout(*self.source_size,free);opts['ratio']=g['width']/g['height'];self.layout_controls.captured_ratio=opts['ratio']
        if opts.get('enabled'):
            g=layout(*self.source_size,p)
            rects=[r for r in (g['photo'],g['card']) if r is not None]
            left=min(r[0] for r in rects);top=min(r[1] for r in rects)
            right=g['width']-max(r[0]+r[2] for r in rects);bottom=g['height']-max(r[1]+r[3] for r in rects)
            self.layout_controls.actual.setText(f"实际外框 {g['width']} × {g['height']} px；留边 上 {top} / 右 {right} / 下 {bottom} / 左 {left} px")
        return p
    def load(self,params):
        p={**DEFAULT_PALETTE,**params};self.loading=True;self.locked=copy.deepcopy(p['locked']);self.manual=bool(p['colors'])
        self.count.setValue(p['count']);self.slider.setValue(p['count'])
        for key in ('mode','style','side','output'):
            control=getattr(self,key);control.setCurrentIndex(control.findData(p[key]))
        for key,control in self.numbers.items():control.setValue(p[key])
        for key in ('proportional','transparent','labels'):getattr(self,key).setChecked(p[key])
        self.layout_controls.load(p.get('layout_options',{}));self.photo_shadow.load(p.get('photo_shadow',{}));self.card_shadow.load(p.get('card_shadow',{}))
        self.background=p['background'];self.bg.setText('背景 · '+self.background.upper())
        self.swatches=[dict(rgb16=c,hex=hex_color(c),weight=0,locked=c in self.locked) for c in p['colors']]
        self.refresh();self.loading=False
    def set_result(self,result):
        self.swatches=copy.deepcopy(result['swatches']);self.note.setText(result.get('note',''));self.refresh()
    def refresh(self):
        selected=self.list.currentRow();self.list.blockSignals(True);self.list.clear()
        for s in self.swatches:
            item=QListWidgetItem(f"{hex_color(s['rgb16'])}   {s['weight']:.1%}")
            pixmap=QPixmap(50,28);pixmap.fill(QColor(hex_color(s['rgb16'])));icon=QIcon()
            for mode in (QIcon.Mode.Normal,QIcon.Mode.Selected,QIcon.Mode.Active,QIcon.Mode.Disabled):icon.addPixmap(pixmap,mode)
            item.setIcon(icon);item.setData(Qt.ItemDataRole.UserRole,s)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if s['rgb16'] in self.locked else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        if self.swatches:self.list.setCurrentRow(min(max(0,selected),len(self.swatches)-1))
        self.list.blockSignals(False)
    def lock_changed(self,item):
        if self.loading:return
        c=item.data(Qt.ItemDataRole.UserRole)['rgb16']
        if item.checkState()==Qt.CheckState.Checked:
            if c not in self.locked:self.locked.append(c)
        elif c in self.locked:self.locked.remove(c)
        self.manual=True;self.emit_changed()
    def reordered(self,*_):
        if self.loading:return
        self.swatches=[self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.manual=True;self.emit_changed()
    def start_pick(self):
        if self.list.currentRow()<0:return
        self.pick_target='swatch';self.pickRequested.emit()
    def start_background_pick(self):self.pick_target='background';self.pickRequested.emit()
    def picked(self,rgb):
        if self.pick_target=='background':
            self.background=hex_color(rgb);self.bg.setText('背景 · '+self.background);self.transparent.setChecked(False);self.emit_changed();return
        i=self.list.currentRow()
        if i<0:return
        old=self.swatches[i]['rgb16'];rgb=[int(v) for v in rgb]
        if old in self.locked:self.locked[self.locked.index(old)]=rgb
        self.swatches[i]['rgb16']=rgb;self.manual=True;self.refresh();self.emit_changed()
    def choose(self):
        if self.list.currentRow()<0:return
        self.pick_target='swatch';c=QColorDialog.getColor(QColor(hex_color(self.swatches[self.list.currentRow()]['rgb16'])),self,'色卡颜色')
        if c.isValid():self.picked([round(c.redF()*65535),round(c.greenF()*65535),round(c.blueF()*65535)])
    def choose_background(self):
        c=QColorDialog.getColor(QColor(self.background),self,'排版背景')
        if c.isValid():self.background=c.name();self.bg.setText('背景 · '+self.background.upper());self.transparent.setChecked(False);self.emit_changed()
