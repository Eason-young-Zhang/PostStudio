import copy
import time
import numpy as np
import pytest
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from blockstudio.collage import defaults,template,geometry,render,create_asset,validate
from blockstudio.project import Project,validate_manifest
from blockstudio.imaging import write_tiff,read_image
from blockstudio import trash


def sources(tmp_path):
    p=Project(tmp_path/'project');ids=[]
    for i,color in enumerate(([12345,23456,34567],[50000,12000,3000],[333,22222,44444])):
        a=np.empty((60,80,4),np.uint16);a[...,:3]=color;a[...,3]=65535
        path=tmp_path/f'{i}.tiff';write_tiff(path,a);ids.append(p.import_image(path)['id'])
    return p,ids


def test_collage_gap_union_and_16bit(app,tmp_path):
    project,ids=sources(tmp_path);p=defaults(ids)
    p.update(width=400,height=300,margins=[0]*4,gap=20,background='#000000',line_color='#ffffff',line_opacity=50)
    for s in p['slots']:s['fit']='cover'
    a=render(project,p)
    assert a.dtype==np.uint16
    assert list(a[40,40,:3])==[12345,23456,34567]
    # The horizontal separator and its T-junction have identical alpha composition.
    assert abs(int(a[150,200,0])-32768)<3
    assert np.array_equal(a[150,200],a[150,30])
    cells,lines,_=geometry(p)
    total=sum(r.width()*r.height() for r in cells.values())+sum(r.width()*r.height() for r in lines)
    assert total==pytest.approx(400*300)
    for style in ('rows','columns','grid','hero'):
        p['tree']=template(3,style);validate(p)
        assert len(geometry(p)[0])==3


def test_collage_portable_dependencies_and_leaf_save(app,tmp_path):
    project,ids=sources(tmp_path);p=defaults(ids);p.update(width=400,height=300,margins=[10]*4,gap=8)
    a=create_asset(project,p);project.placement(a,project.data['boards'][0]);oldfile=a['file']
    p['line_color']='#112233';b=create_asset(project,p,a['id'])
    assert b['id']==a['id'] and b['file']!=oldfile and len(project.data['assets'])==4
    assert (project.root/oldfile).exists() # Undo still has its master.
    assert all(project.revision_blocker(id) for id in ids)
    trash.remove_assets(project,ids);assert not trash.purge_candidates(project)
    path=tmp_path/'portable.blockproj';project.save(path);restored=Project.open(path,tmp_path/'open')
    assert restored.asset(b['id'])['step']['params']==p
    assert np.array_equal(read_image(project.file(b)),read_image(restored.file(restored.asset(b['id']))))
    child=project.execute(b['id'],dict(tool='invert',version=1,params={}))
    with pytest.raises(ValueError,match='下游'):create_asset(project,p,b['id'])
    malformed=copy.deepcopy(project.data);malformed['assets'][-2]['sources'][0]='missing'
    with pytest.raises(ValueError):validate_manifest(malformed)
    malformed=copy.deepcopy(project.data);record=malformed['assets'][-2]
    record['sources'][0]=record['id'];record['step']['params']['slots'][0]['asset']=record['id']
    with pytest.raises(ValueError,match='循环'):validate_manifest(malformed)


def test_collage_editor_drag_sliders_and_history(app,tmp_path):
    from blockstudio.collage_widgets import CollageEditor
    from blockstudio.app import STYLE
    app.setStyleSheet(STYLE);project,ids=sources(tmp_path);w=CollageEditor(project,ids);w.resize(1100,780);w.show();app.processEvents()
    preview=w.preview
    def pos(i):return (preview.origin+preview.cells[i].center()*preview.scale).toPoint()
    start,end=pos(0),pos(1)
    QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(preview,end);QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=end)
    assert w.params['slots'][1]['asset']==ids[0]
    w.move_history(-1);assert w.params['slots'][0]['asset']==ids[0]
    path,axis,rect,offset=preview.handles[0]
    start=(preview.origin+rect.center()*preview.scale).toPoint()
    QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(preview,start+QPoint(0,30));QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=start+QPoint(0,30))
    assert w.params['tree']['ratio']>.5
    w.ratio.setCurrentIndex(3);assert w.params['height']==w.params['width']
    w.fit.setCurrentIndex(1);w.drag_mode.setCurrentIndex(1);app.processEvents()
    start=pos(w.index);before=w.params['slots'][w.index]['x']
    QTest.mousePress(preview,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(preview,start+QPoint(20,0));QTest.mouseRelease(preview,Qt.MouseButton.LeftButton,pos=start+QPoint(20,0))
    assert w.params['slots'][w.index]['x']<before
    w.tabs.setCurrentIndex(2);app.processEvents();control=w.controls['gap']
    assert control.slider.width()>control.spin.width()*1.8
    control.setValue(15.5);assert w.params['gap']==15.5
    w.link.setCurrentIndex(1);w.controls['margin0'].setValue(45);assert w.params['margins']==[45]*4
    w.controls['width'].setValue(1);assert not w.generate.isEnabled()


def test_collage_workbench_generate_reedit(app,tmp_path):
    from blockstudio.app import Window
    w=Window(tmp_path/'sessions');project,ids=sources(tmp_path);w.project=project;w.board_id=project.data['boards'][0]['id']
    records=[project.placement(project.asset(id),w.board)['id'] for id in ids];w.refresh_all(records)
    w.open_collage();app.processEvents();page=w.collage_page
    page.controls['width'].setValue(500);page.controls['height'].setValue(500);w.apply_collage()
    for _ in range(2000):
        app.processEvents();time.sleep(.002)
        if w.job is None:break
    assert w.job is None and w.pages.currentWidget()==w.workspace
    asset=project.data['assets'][-1];assert asset['step']['tool']=='collage'
    w.reload_step();assert w.collage_page.target==asset['id']
    w.collage_page.controls['gap'].setValue(10);w.apply_collage(save=True)
    for _ in range(2000):
        app.processEvents();time.sleep(.002)
        if w.job is None:break
    assert w.job is None and len(project.data['assets'])==4
    assert project.asset(asset['id'])['step']['params']['gap']==10
    w.undo_state(-1);assert w.project.asset(asset['id'])['step']['params']['gap']==24
    w.undo_state(1);assert w.project.asset(asset['id'])['step']['params']['gap']==10


def test_collage_contain_cover_pan_and_validation(app,tmp_path):
    project,ids=sources(tmp_path);p=defaults(ids[:1]);p.update(width=200,height=200,margins=[0]*4,gap=0,background='#ffffff')
    a=render(project,p)
    assert list(a[0,100,:3])==[65535]*3
    assert list(a[100,100,:3])==[12345,23456,34567]
    p['slots'][0]['fit']='cover';a=render(project,p)
    assert list(a[0,100,:3])==[12345,23456,34567]
    p['margins']=[150]*4;count=len(project.data['assets'])
    with pytest.raises(ValueError):create_asset(project,p)
    assert len(project.data['assets'])==count
    p=defaults(ids);p.update(width=10000,height=10000)
    with pytest.raises(ValueError,match='5000'):validate(p)
