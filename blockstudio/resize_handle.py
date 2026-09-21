"""Visible height grip for a list inside a scrolling tool panel."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QWidget


class ListHeightHandle(QWidget):
    def __init__(self, target, default=190, minimum=120, maximum=1200):
        super().__init__(target.parentWidget())
        self.target=target;self.default=default;self.minimum=minimum;self.maximum=maximum
        self.origin=None
        target.setFixedHeight(default)
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('调整色卡列表高度')
        self.setToolTip('上下拖动调整色卡列表高度；双击恢复默认。方向键微调，Shift 加大步幅。')
    def resize_list(self,height):
        self.target.setFixedHeight(max(self.minimum,min(self.maximum,round(height))))
        self.target.updateGeometry()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.origin=(event.globalPosition().y(),self.target.height());self.setFocus();event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.origin is not None:
            self.resize_list(self.origin[1]+event.globalPosition().y()-self.origin[0]);event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=None;event.accept()
        else:super().mouseReleaseEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.origin=None;self.resize_list(self.default);event.accept()
        else:super().mouseDoubleClickEvent(event)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Up,Qt.Key.Key_Down):
            step=40 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 10
            self.resize_list(self.target.height()+step*(1 if event.key()==Qt.Key.Key_Down else -1));event.accept()
        else:super().keyPressEvent(event)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#a7bfd2' if self.hasFocus() or self.underMouse() else '#64849e'))
        painter.drawRoundedRect((self.width()-48)//2,7,48,4,2,2)
