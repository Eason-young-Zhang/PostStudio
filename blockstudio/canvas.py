from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPen, QBrush, QPixmap, QPainter, QFont
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem

ACCENT = QColor('#829fb9')


def checker_brush(size=18,first='#343638',second='#414345'):
    tile=QPixmap(size*2,size*2);tile.fill(QColor(first))
    painter=QPainter(tile);painter.fillRect(0,0,size,size,QColor(second));painter.fillRect(size,size,size,size,QColor(second));painter.end()
    return QBrush(tile)



class PhotoItem(QGraphicsItem):
    def __init__(self, record, asset, pixmap, on_change):
        super().__init__()
        self.record, self.asset, self.pixmap, self.on_change = record, asset, pixmap, on_change
        self.version_count=1;self.checker=checker_brush()
        self.w = record['width']; self.h = self.w*asset['height']/asset['width']
        self.resizing = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setPos(record['x'],record['y'])
        self.setToolTip(f"{asset['name']}\n{asset['width']} × {asset['height']} px\n拖动移动 · 拖右下角缩放 · Shift 多选")

    def boundingRect(self): return QRectF(-3,-25,self.w+14,self.h+39)

    def paint(self,p,option,widget=None):
        rect=QRectF(0,0,self.w,self.h)
        if self.record.get('view')=='stack':
            p.fillRect(rect.translated(8,8),QColor('#354550'))
            p.fillRect(rect.translated(4,4),QColor('#526879'))
        p.fillRect(rect,self.checker)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(rect,self.pixmap,QRectF(self.pixmap.rect()))
        p.setPen(QColor('#c5c5c3') if self.isSelected() else QColor('#929492'))
        p.setFont(QFont('Helvetica Neue',10))
        p.drawText(QRectF(0,-24,self.w,20),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.asset['name'] + (f'  /  {self.version_count} 个版本' if self.record.get('view')=='stack' else ''))
        if self.isSelected():
            p.setPen(QPen(ACCENT,1.5)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(rect)
            p.fillRect(QRectF(self.w-5,self.h-5,10,10),ACCENT)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and (event.pos()-QPointF(self.w,self.h)).manhattanLength()<22:
            self.resizing=True; self.setSelected(True); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.resizing:
            self.prepareGeometryChange()
            self.w=max(40,event.pos().x()); self.h=self.w*self.asset['height']/self.asset['width']
            self.record['width']=self.w; self.update(); event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self.resizing=False
        super().mouseReleaseEvent(event)
        # Qt may move all selected items together.
        for item in self.scene().selectedItems():
            if isinstance(item,(PhotoItem,FrameItem)):
                item.record['x']=item.pos().x(); item.record['y']=item.pos().y()
        self.record.update(x=self.pos().x(),y=self.pos().y(),width=self.w)
        self.on_change()

    def hoverMoveEvent(self,event):
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if (event.pos()-QPointF(self.w,self.h)).manhattanLength()<22 else Qt.CursorShape.OpenHandCursor)


class FrameItem(QGraphicsRectItem):
    def __init__(self,record,on_change):
        super().__init__(0,0,record['width'],record['height'])
        self.record,self.on_change=record,on_change
        self.setPos(record['x'],record['y']); self.setZValue(-1)
        self.setPen(QPen(QColor('#a5b2ad'),1.5,Qt.PenStyle.DashLine))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setToolTip(record['name']+' · 可移动；右侧修改尺寸或导出')

    def paint(self,p,option,widget=None):
        self.setPen(QPen(ACCENT if self.isSelected() else QColor('#9ba8a3'),1.5,Qt.PenStyle.DashLine))
        super().paint(p,option,widget)
        p.setPen(QColor('#a5b2ad')); p.drawText(QPointF(0,-9),self.record['name'])

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        self.record.update(x=self.pos().x(),y=self.pos().y()); self.on_change()


class WorkView(QGraphicsView):
    frameCreated=Signal(object)
    filesDropped=Signal(list)
    changed=Signal()
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setSceneRect(-20000,-20000,40000,40000)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor('#242729'))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frame_mode=False; self.frame_start=None; self.rubber=None; self.pan=None; self.space=False
        self.centerOn(400,280)

    def drawBackground(self,p,rect):
        p.fillRect(rect,QColor('#242729'))
        if self.transform().m11()<.2: return
        p.setPen(QPen(QColor('#323638'),0))
        step=40
        # Only visible dots, bounded by viewport; no full-scene texture allocation.
        for x in range(int(rect.left()//step)*step,int(rect.right())+step,step):
            for y in range(int(rect.top()//step)*step,int(rect.bottom())+step,step): p.drawPoint(QPointF(x,y))

    def drawForeground(self,p,rect):
        if any(isinstance(i,PhotoItem) for i in self.scene().items()):return
        p.save();p.resetTransform()
        center=self.viewport().rect().center()
        p.setPen(QColor('#a9aeac'));p.setFont(QFont('Helvetica Neue',22))
        p.drawText(QRectF(center.x()-220,center.y()-48,440,44),Qt.AlignmentFlag.AlignCenter,'把照片放在这里')
        p.setPen(QColor('#768083'));p.setFont(QFont('Helvetica Neue',12))
        p.drawText(QRectF(center.x()-260,center.y()+5,520,36),Qt.AlignmentFlag.AlignCenter,'拖入 TIFF、JPEG 或 PNG · 或点击上方“导入图像”')
        p.restore()

    def wheelEvent(self,event):
        factor=1.15 if event.angleDelta().y()>0 else 1/1.15
        target=self.transform().m11()*factor
        if .04<target<12: self.scale(factor,factor)
        event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Space:
            self.space=True; self.setCursor(Qt.CursorShape.OpenHandCursor); event.accept()
        else: super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space:
            self.space=False; self.unsetCursor(); event.accept()
        else: super().keyReleaseEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton or (self.space and event.button()==Qt.MouseButton.LeftButton):
            self.pan=event.position(); self.setCursor(Qt.CursorShape.ClosedHandCursor); event.accept(); return
        if self.frame_mode and event.button()==Qt.MouseButton.LeftButton:
            self.frame_start=self.mapToScene(event.position().toPoint())
            self.rubber=self.scene().addRect(QRectF(self.frame_start,self.frame_start),QPen(ACCENT,1,Qt.PenStyle.DashLine))
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.pan is not None:
            delta=event.position()-self.pan; self.pan=event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-int(delta.y()))
            return
        if self.frame_start is not None:
            self.rubber.setRect(QRectF(self.frame_start,self.mapToScene(event.position().toPoint())).normalized()); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.pan is not None:
            self.pan=None; self.unsetCursor(); return
        if self.frame_start is not None:
            rect=self.rubber.rect(); self.scene().removeItem(self.rubber)
            self.rubber=None; self.frame_start=None; self.frame_mode=False; self.unsetCursor()
            if rect.width()>10 and rect.height()>10: self.frameCreated.emit(rect)
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self,event): event.acceptProposedAction()
    def dropEvent(self,event):
        self.filesDropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    def fit_content(self):
        if self.scene().items(): self.fitInView(self.scene().itemsBoundingRect().adjusted(-70,-70,70,70),Qt.AspectRatioMode.KeepAspectRatio)

    def start_frame(self):
        self.frame_mode=True; self.setCursor(Qt.CursorShape.CrossCursor)
