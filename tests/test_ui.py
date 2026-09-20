import numpy as np
from PySide6.QtCore import Qt,QPoint,QRectF
from PySide6.QtTest import QTest
from blockstudio.app import Window,STYLE
from blockstudio.imaging import write_tiff
from blockstudio.canvas import PhotoItem,FrameItem


def test_window_workflow_selection_and_versions(app,tmp_path):
    app.setStyleSheet(STYLE)
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    a=np.zeros((96,160,4),np.uint16);a[...,:3]=[12345,23456,34567];a[...,3]=65535
    src=tmp_path/'source.tiff';write_tiff(src,a)
    asset=w.project.import_image(src);r=w.project.placement(asset,w.board)
    w.refresh_all([r['id']]);w.fit();app.processEvents();w.open_tool(tool_id='sample');w.update_preview()
    for _ in range(200):
        app.processEvents();QTest.qWait(5)
        if not w.panel.preview.image.isNull():break
    assert not w.panel.preview.image.isNull()
    w.apply_current()
    for _ in range(200):
        app.processEvents();QTest.qWait(10)
        if w.job is None:break
    assert w.job is None
    assert len(w.project.data['assets'])==2
    result=w.project.data['assets'][-1]
    w.reload_step();assert w.edit_source==asset['id']
    w.panel.spins['gap_x'].setValue(17);w.apply_current()
    for _ in range(200):
        app.processEvents();QTest.qWait(10)
        if w.job is None:break
    assert len(w.project.data['assets'])==3
    assert result['step']['params']['gap_x']==64
    w.create_frame(QRectF(-20,-20,1000,400));assert len(w.board['frames'])==1
    w.dirty=False;w.close();app.processEvents()


def wait_job(app,w):
    for _ in range(500):
        app.processEvents();QTest.qWait(5)
        if w.job is None:return
    raise AssertionError('background task did not complete')


def test_batch_10_steps_stack_and_cancel(app,tmp_path):
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    a=np.ones((40,60,4),np.uint16)*65535
    src=tmp_path/'source.tiff';write_tiff(src,a)
    records=[]
    for _ in range(10):
        asset=w.project.import_image(src);records.append(w.project.placement(asset,w.board)['id'])
    w.refresh_all(records);w.panel.mode.setCurrentIndex(2)
    steps=[w.panel.step(),dict(tool='invert',version=1,params={})]
    w.run_steps(steps);wait_job(app,w)
    assert len(w.project.data['assets'])==30
    assert len(w.board['items'])==10
    assert all(r['view']=='stack' for r in w.board['items'])
    assert all(w.project.asset(r['asset'])['step']['tool']=='invert' for r in w.board['items'])
    before=len(w.project.data['assets']);w.run_steps(steps);w.job.cancel.set();wait_job(app,w)
    assert len(w.project.data['assets'])<=before+1
    w.project.save(tmp_path/'batch.blockproj')
    from blockstudio.project import Project
    q=Project.open(tmp_path/'batch.blockproj',tmp_path/'reopened')
    assert len(q.data['assets'])==len(w.project.data['assets'])
    w.dirty=False;w.close()


def test_canvas_drag_frame_and_resize(app,tmp_path):
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    src=tmp_path/'source.tiff';write_tiff(src,np.ones((50,100,4),np.uint16)*65535)
    a=w.project.import_image(src);r=w.project.placement(a,w.board);w.refresh_all([r['id']]);w.fit();app.processEvents()
    item=next(i for i in w.view.scene().items() if isinstance(i,PhotoItem))
    from PySide6.QtCore import QPointF
    start=w.view.mapFromScene(item.mapToScene(QPointF(100,100)));end=start+QPoint(35,20)
    QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(w.view.viewport(),end);QTest.mouseRelease(w.view.viewport(),Qt.MouseButton.LeftButton,pos=end);app.processEvents()
    assert r['x']!=0 and r['y']!=0
    corner=w.view.mapFromScene(item.mapToScene(QPointF(item.w,item.h)))
    QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=corner);QTest.mouseMove(w.view.viewport(),corner+QPoint(40,30));QTest.mouseRelease(w.view.viewport(),Qt.MouseButton.LeftButton,pos=corner+QPoint(40,30));app.processEvents()
    assert r['width']>440
    w.view.start_frame();QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(30,30));QTest.mouseMove(w.view.viewport(),QPoint(400,300));QTest.mouseRelease(w.view.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(400,300));app.processEvents()
    assert len(w.board['frames'])==1
    w.dirty=False;w.close()


def test_editor_separate_page_revises_same_source_after_commit(app,tmp_path):
    from blockstudio.imaging import read_image
    from blockstudio.tools import apply_tool
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    a=np.zeros((180,240,4),np.uint16);a[...,:3]=[11000,33000,44000];a[...,3]=65535
    src=tmp_path/'original.tiff';write_tiff(src,a);source=w.project.import_image(src);r=w.project.placement(source,w.board)
    w.refresh_all([r['id']]);assert w.pages.currentWidget()==w.workspace
    w.open_tool(tool_id='sample');assert w.pages.currentWidget()==w.editor_page and not w.toolbar.isVisible()
    w.apply_current();wait_job(app,w);a1=w.project.data['assets'][-1];old=w.project.file(a1).read_bytes()
    assert w.pages.currentWidget()==w.workspace
    w.open_tool(tool_id='sample');assert w.editor_inputs==[source['id']]
    w.panel.spins['block_x'].setValue(80);w.panel.spins['block_y'].setValue(80);w.panel.spins['gap_x'].setValue(80);w.panel.spins['gap_y'].setValue(80)
    step=w.panel.step();w.apply_current();wait_job(app,w);a2=w.project.data['assets'][-1]
    assert a2['parent']==source['id'] and w.project.file(a1).read_bytes()==old
    assert np.array_equal(read_image(w.project.file(a2)),apply_tool(a,step))
    # Explicit append remains possible but cannot silently replace revise mode.
    w.open_tool(tool_id='sample',append=True);assert w.editor_inputs==[a2['id']]
    count=len(w.project.data['assets']);w.leave_editor();assert len(w.project.data['assets'])==count
    w.dirty=False;w.close()


def test_sliders_keyboard_grid_and_single_block_drag(app,tmp_path):
    w=Window(tmp_path/'sessions');w.resize(1320,820);w.show();app.processEvents()
    a=np.ones((400,600,4),np.uint16)*65535;src=tmp_path/'x.tiff';write_tiff(src,a)
    asset=w.project.import_image(src);r=w.project.placement(asset,w.board);w.refresh_all([r['id']]);w.open_tool(tool_id='sample')
    w.panel.preview.image=w.panel.preview.pick_image;app.processEvents()
    slider=w.panel.sliders['block_x'];slider.setValue(73);assert w.panel.spins['block_x'].value()==73
    slider.setFocus();QTest.keyClick(slider,Qt.Key.Key_Right);assert w.panel.spins['block_x'].value()==74
    w.panel.spins['block_x'].setValue(64);assert slider.value()==64
    preview=w.panel.preview;rect=preview.image_rect();start=rect.center().toPoint()
    QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(preview,start+QPoint(25,20));QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=start+QPoint(25,20))
    assert w.panel.spins['offset_x'].value()!=0 and w.panel.spins['offset_y'].value()!=0
    w.move_grid(0,0);w.move_mode.setCurrentIndex(1);app.processEvents();rect=preview.image_rect()
    start=QPoint(round(rect.x()+20/600*rect.width()),round(rect.y()+20/400*rect.height()))
    QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(preview,start+QPoint(30,15));QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=start+QPoint(30,15))
    assert '0,0' in w.panel.moved_blocks
    before=list(w.panel.moved_blocks['0,0']);QTest.keyClick(preview,Qt.Key.Key_Right,Qt.KeyboardModifier.ShiftModifier)
    assert w.panel.moved_blocks['0,0']==[before[0]+10,before[1]]
    assert w.panel.spins['offset_x'].value()==0
    w.leave_editor();w.dirty=False;w.close()


def test_preview_matches_native_render_and_ignores_stale_frames(app,tmp_path):
    from blockstudio.imaging import preview,from_qimage
    from blockstudio.tools import apply_tool
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    a=np.ones((96,160,4),np.uint16)*65535;a[...,:3]=[7654,23456,45678]
    src=tmp_path/'x.tiff';write_tiff(src,a);asset=w.project.import_image(src);r=w.project.placement(asset,w.board);w.refresh_all([r['id']]);w.open_tool(tool_id='sample')
    w.panel.spins['block_x'].setValue(3);w.panel.spins['gap_x'].setValue(2);w.move_block('1,0',2,5);w.update_preview()
    for _ in range(200):
        app.processEvents();QTest.qWait(5)
        if not w.panel.preview.image.isNull():break
    expected=preview(apply_tool(a,w.panel.step()),1600)
    assert np.array_equal(from_qimage(w.panel.preview.image),from_qimage(expected))
    before=w.panel.preview.image.copy()
    w.preview_ready(w.preview_generation-1,preview(np.zeros_like(a)))
    assert w.panel.preview.image==before
    w.leave_editor();w.dirty=False;w.close()


def test_palette_editor_generation_reedit_and_split(app,tmp_path):
    from blockstudio.project import Project
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    a=np.ones((120,180,4),np.uint16)*65535;a[:60,:,:3]=[12345,23456,34567];a[60:,:,:3]=[50000,32000,16000]
    src=tmp_path/'x.tiff';write_tiff(src,a);asset=w.project.import_image(src);r=w.project.placement(asset,w.board)
    w.refresh_all([r['id']]);w.open_tool(tool_id='palette')
    for _ in range(200):
        app.processEvents();QTest.qWait(10)
        if w.panel.palette.swatches:break
    assert w.panel.palette.swatches and w.panel.palette.isVisible()
    assert not w.panel.sample_box.isVisible()
    controls=w.panel.palette
    controls.list.setCurrentRow(0);controls.list.item(0).setCheckState(Qt.CheckState.Checked)
    assert len(controls.locked)==1
    controls.pick_target='swatch';w.pick_palette_color(.1,.1)
    assert controls.swatches[0]['rgb16']==[12345,23456,34567]
    controls.style.setCurrentIndex(1);controls.side.setCurrentIndex(3)
    w.apply_current();wait_job(app,w)
    combined=w.project.data['assets'][-1];assert combined['kind']=='composition'
    assert w.pages.currentWidget()==w.workspace
    w.open_tool(tool_id='palette');assert w.editor_inputs==[asset['id']]
    assert w.panel.palette.style.currentData()=='ring'
    w.leave_editor();w.split_selected();assert len(w.board['items'])==3
    w.project.save(tmp_path/'palette.blockproj');q=Project.open(tmp_path/'palette.blockproj',tmp_path/'reopen')
    assert len(q.data['assets'])==3
    w.dirty=False;w.close();app.processEvents()
