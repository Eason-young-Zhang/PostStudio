"""Capture collage UI with derivatives of the licensed public manual fixture."""
import tempfile
from pathlib import Path
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from blockstudio.app import STYLE
from blockstudio.project import Project
from blockstudio.collage_widgets import CollageEditor
from blockstudio.collage import template
app=QApplication([]);app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as temp:
    folder=Path(temp);project=Project(folder/'session');image=QImage('artifacts/fixtures/Fronalpstock_big.jpg');ids=[]
    for i,rect in enumerate([(0,0,image.width(),image.height()),(0,0,image.width()//2,image.height()),(image.width()//2,0,image.width()//2,image.height())]):
        path=folder/f'山间 {i+1}.png';image.copy(*rect).scaledToWidth(1200).save(str(path));ids.append(project.import_image(path)['id'])
    w=CollageEditor(project,ids);w.resize(1190,790)
    w.params['tree']=template(3,'hero');w.params['width']=2400;w.params['height']=2400
    for slot in w.params['slots']:slot['fit']='cover'
    w.changed();w.load_controls();w.tabs.setCurrentIndex(2);w.show();app.processEvents()
    w.grab().save('docs/images/collage.png');w.deleteLater();app.processEvents()
