"""Decimal slider plus exact entry; the spin box is the value authority."""
import math
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QSlider, QSizePolicy


class NumberControl(QWidget):
    valueChanged = Signal(float)

    def __init__(self, value=0, low=0, high=10000, step=.1):
        super().__init__()
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.spin = QDoubleSpinBox()
        # Set precision before bounds: custom aspect ratios may start at .001.
        self.spin.setDecimals(max(1, min(3, -math.floor(math.log10(low)))) if 0 < low < .1 else 1)
        self.spin.setRange(low, high)
        self.spin.setSingleStep(step)
        self.spin.setKeyboardTracking(False)
        self.spin.setValue(value)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setBuddy(self.spin)
        self.spin.setFixedWidth(116)
        header = QHBoxLayout()
        header.addWidget(self.label, 1)
        header.addWidget(self.spin)
        layout.addLayout(header)
        layout.addWidget(self.slider)
        self.setFocusProxy(self.spin)
        self.preferred = (max(low, -100), min(high, 100)) if high >= 10000 else (low, high)
        self.slider.valueChanged.connect(self._drag)
        self.spin.valueChanged.connect(self._changed)
        self._sync()

    def _sync(self):
        factor = 10 ** self.spin.decimals()
        low, high = self.preferred
        value = self.value()
        low, high = min(low, value), max(high, value)
        with QSignalBlocker(self.slider):
            self.slider.setRange(round(low * factor), round(high * factor))
            self.slider.setSingleStep(max(1, round(self.spin.singleStep() * factor)))
            self.slider.setPageStep(max(1, round(self.spin.singleStep() * factor * 10)))
            self.slider.setValue(round(value * factor))
        self.slider.setToolTip(f'滑动范围 {low:g}–{high:g}；可在输入框中输入完整范围内的数值。方向键微调，Page Up / Down 加大步幅。')

    def _drag(self, value):
        # Freeze the range throughout a gesture, including a keyboard gesture.
        self.preferred = (self.slider.minimum() / 10 ** self.spin.decimals(),
                          self.slider.maximum() / 10 ** self.spin.decimals())
        self.spin.setValue(value / 10 ** self.spin.decimals())

    def _changed(self, value):
        self._sync()
        self.valueChanged.emit(value)

    def setSliderRange(self, low, high):
        self.preferred = (max(self.spin.minimum(), low), min(self.spin.maximum(), high))
        self._sync()

    def value(self): return self.spin.value()
    def setValue(self, value): self.spin.setValue(value)
    def setDecimals(self, value): self.spin.setDecimals(value); self._sync()
    def decimals(self): return self.spin.decimals()
    def setSingleStep(self, value): self.spin.setSingleStep(value); self._sync()
    def singleStep(self): return self.spin.singleStep()
    def setSuffix(self, value): self.spin.setSuffix(value)
    def setAccessibleName(self, name):
        super().setAccessibleName(name)
        self.label.setText(name)
        self.spin.setAccessibleName(name + '精确值')
        self.slider.setAccessibleName(name + '滑动条')
