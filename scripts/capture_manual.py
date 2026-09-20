"""Capture current Qt widgets using the public, licensed fixture only."""
import copy,tempfile,time
from pathlib import Path
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from blockstudio.app import Window,STYLE
from blockstudio.workflow_widgets import WorkflowEditor
from blockstudio.watermark import DEFAULT_MARK
app=QApplication([]);app.setStyleSheet(STYLE)
out=Path('docs/images');out.mkdir(exist_ok=True)
def wait(predicate):
    until=time.monotonic()+40
    while not predicate():
        if time.monotonic()>until:raise RuntimeError('preview timeout')
        app.processEvents();time.sleep(.005)
def capture(name):
    wait(lambda:w.preview_exact and w.preview_displayed==w.preview_generation)
    app.processEvents();w.grab().save(str(out/f'{name}.png'))
with tempfile.TemporaryDirectory() as temp:
    w=Window(Path(temp));w.resize(1190,790);w.show()
    try:
        a=w.project.import_image(Path('artifacts/fixtures/Fronalpstock_big.jpg'))
        r=w.project.placement(a,w.board);w.refresh_all([r['id']]);w.fit();app.processEvents()
        w.open_tool(tool_id='sample')
        for key in ('block_x','block_y','gap_x','gap_y'):w.panel.spins[key].setValue(280)
        capture('sampling');w.leave_editor()
        w.open_tool(tool_id='palette');capture('palette')
        w.panel.palette.style.setCurrentIndex(1);w.panel.palette.side.setCurrentIndex(3);capture('palette-ring')
        w.leave_editor();w.open_tool(tool_id='border');w.panel.border.apply_template(3);capture('border')
        frame_step=copy.deepcopy(w.panel.step());framed=w.project.execute(a['id'],frame_step)
        w.leave_editor();r2=w.project.placement(framed,w.board,x=500,y=0,width=440);w.refresh_all([r2['id']]);w.fit()
        w.tabs.setCurrentIndex(1);app.processEvents();w.grab().save(str(out/'overview.png'));w.tabs.setCurrentIndex(0)
        w.open_tool(tool_id='watermark')
        mark={**DEFAULT_MARK,'text':'PostStudio · 山间\n一次独立的创作','reference':'bottom','anchor':4,'x':0,'y':0,'size':22,'unit':'px','color':'#30465b','opacity':100,'width':90}
        # Percent size refers to the short dimension of the bottom margin.
        mark.update(size=16,unit='percent')
        w.panel.watermark.load(dict(layers=[mark]));w.schedule_preview();capture('watermark')
        watermark_step=copy.deepcopy(w.panel.step());w.leave_editor();w.fit();app.processEvents();w.grab().save(str(out/'workspace.png'))
        w.project.data['presets']=[dict(name='下方题注框',step=frame_step),dict(name='居中签名',step=watermark_step)]
        dialog=WorkflowEditor(w.project,frame_step,[frame_step,watermark_step,dict(action='name',params=dict(template='{原文件名}-{序号}')),dict(action='export',params=dict(directory='',options=dict(fmt='JPEG')))],w)
        dialog.show();app.processEvents();dialog.grab().save(str(out/'workflow.png'));dialog.close();dialog.deleteLater()
    finally:
        w.stop_preview()
        for worker in w.retiring_workers:worker.wait(30000)
        w.dirty=False;w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
print('Saved current interface screenshots in docs/images')
