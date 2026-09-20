import copy
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from blockstudio.number_control import NumberControl


def test_slider_exact_input_keyboard_and_signal_blocking(app):
    c=NumberControl(3,0,10000);c.show();seen=[];c.valueChanged.connect(seen.append)
    c.slider.setValue(47)
    assert c.value()==4.7 and seen==[4.7]
    c.spin.setValue(1800.3)
    assert c.slider.value()==18003 and c.slider.maximum()==18003
    c.slider.setFocus();QTest.keyClick(c.slider,Qt.Key.Key_Left)
    assert c.value()==1800.2 and c.slider.maximum()==18003
    c.blockSignals(True);c.setValue(9.2);c.blockSignals(False)
    assert c.slider.value()==92 and seen[-1]==1800.2
    c.setEnabled(False);assert not c.spin.isEnabled() and not c.slider.isEnabled()


def test_ratio_precision_and_entered_negative_values(app):
    c=NumberControl(3,.001,10000);c.setDecimals(3);c.setValue(.001)
    assert c.value()==.001 and c.slider.minimum()==1
    c.setValue(7.123);assert c.slider.value()==7123
    signed=NumberControl(0,-10000,10000);signed.setValue(-2000.7)
    signed.slider.setValue(-19);assert signed.value()==-1.9


def test_decimal_palette_and_linked_border_sliders_roundtrip(app):
    from blockstudio.palette_widgets import PaletteControls
    from blockstudio.border_widgets import BorderControls
    palette=PaletteControls();palette.numbers['gap'].slider.setValue(17)
    assert palette.params()['gap']==1.7
    border=BorderControls();border.link.setCurrentIndex(1);border.values['top'].slider.setValue(47)
    assert all(border.values[k].value()==4.7 and border.values[k].slider.value()==47 for k in ('top','right','bottom','left'))
    original=copy.deepcopy(border.params());border.unit.setCurrentIndex(1)
    assert border.values['top'].slider.maximum()==12000
    border.load(original);assert border.params()==original
    assert border.values['top'].slider.maximum()==1000


def test_watermark_layout_effect_sliders_preserve_loaded_parameters(app):
    from blockstudio.watermark_widgets import WatermarkControls
    from blockstudio.layout_controls import LayoutControls
    from blockstudio.effect_controls import BackgroundControls,ShadowControls
    for c in [WatermarkControls(),LayoutControls(),BackgroundControls(),ShadowControls()]:
        before=copy.deepcopy(c.params());c.load(before);assert c.params()==before
    watermark=WatermarkControls();watermark.values['opacity'].slider.setValue(425)
    assert watermark.params()['layers'][0]['opacity']==42.5
    background=BackgroundControls();background.position.slider.setValue(175)
    assert background.params()['stops'][0]['position']==17.5
    shadow=ShadowControls();shadow.setChecked(True);shadow.values['x'].slider.setValue(-35)
    assert shadow.params()['x']==-3.5
