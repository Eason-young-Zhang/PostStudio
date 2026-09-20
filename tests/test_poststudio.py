import copy
import numpy as np
from blockstudio.project import Project,validate_manifest
from blockstudio.imaging import write_tiff,read_image
from blockstudio import trash
from blockstudio.history import History
from blockstudio.effects import background_image,shadow
from blockstudio.palette_render import layout,DEFAULT_PALETTE


def source(tmp_path):
    p=Project(tmp_path/'session');pixels=np.ones((32,48,4),np.uint16)*65535
    path=tmp_path/'photo.tiff';write_tiff(path,pixels);return p,p.import_image(path)


def test_trash_preserves_dependencies_and_restore(tmp_path):
    p,a=source(tmp_path);board=p.data['boards'][0];record=p.placement(a,board)
    result=p.execute(a['id'],dict(tool='invert',params={}))
    trash.remove_assets(p,[a['id']]);assert not board['items'];assert not trash.purge_candidates(p)
    p.save(tmp_path/'saved.blockproj');q=Project.open(tmp_path/'saved.blockproj',tmp_path/'reopen')
    assert q.asset(a['id'])['trashed'];assert read_image(q.file(q.asset(result['id']))).shape==(32,48,4)
    trash.restore(q,q.data['trash'][0]['id']);assert q.data['boards'][0]['items'][0]==record
    assert not q.asset(a['id']).get('trashed')


def test_purge_chain_and_shared_file(tmp_path):
    p,a=source(tmp_path);b=p.execute(a['id'],dict(tool='invert',params={}))
    trash.remove_assets(p,[a['id'],b['id']]);assert len(trash.purge_candidates(p))==2
    trash.purge(p);assert not p.data['assets'];validate_manifest(p.data)
    assert (tmp_path/'photo.tiff').exists()


def test_last_board_restore(tmp_path):
    p,a=source(tmp_path);b=p.data['boards'][0];p.placement(a,b);saved=copy.deepcopy(b)
    trash.remove_board(p,b['id']);assert len(p.data['boards'])==1
    trash.restore(p,p.data['trash'][0]['id']);assert saved in p.data['boards']


def test_history_branch():
    h=History({'x':0});h.record({'x':1});h.record({'x':2});assert h.move(-1)=={'x':1}
    h.record({'x':3});assert h.move(1) is None;assert h.move(-1)=={'x':1}


def test_layout_distinct_ratios_and_no_image_resize():
    p={**DEFAULT_PALETTE,'layout_options':dict(enabled=True,unit='px',top=30,right=10,bottom=90,left=70,card_width=140,card_height=20,ratio_mode=1,ratio=4/3)}
    a=layout(300,200,p);assert abs(a['width']/a['height']-4/3)<.01;assert a['photo'][2:]==[300,200];assert a['card'][2:]==[140,20]
    p['layout_options']['ratio_mode']=2;b=layout(300,200,p);assert abs(b['width']/b['height']-1.5)<.01


def test_gradient_and_shadow_clipping():
    out=background_image(100,50,dict(kind='linear',angle=0,stops=[dict(position=0,color='#ff0000',alpha=0),dict(position=100,color='#0000ff',alpha=100)]))
    assert out.dtype==np.uint16;assert out[0,0,3]<out[0,-1,3]
    fg=np.ones((10,10,4),np.uint16)*65535;canvas=np.zeros((20,20,4),np.uint16)
    shadow(canvas,fg,-4,-4,dict(enabled=True,blur=2,x=0,y=2,opacity=50))
    assert canvas[...,3].max()>0;assert canvas[...,3].max()<=32768


def test_border_geometry_pixels_and_inner_error():
    import pytest
    from blockstudio.border import border,geometry
    pixels=np.ones((20,30,4),np.uint16)*65535;pixels[...,:3]=[12345,23456,34567]
    p=dict(layers=[dict(mode='outer',unit='px',top=2,right=3,bottom=4,left=5)])
    out=border(pixels,p);assert out.shape==(26,38,4);assert np.array_equal(out[2:22,5:35],pixels)
    assert geometry(30,20,p)['photo']==[5,2,30,20]
    with pytest.raises(ValueError,match='有效开口'):border(pixels,dict(layers=[dict(mode='inner',unit='px',left=20,right=20)]))


def test_metadata_batch_override_is_project_only(tmp_path):
    from blockstudio.metadata import update,resolved
    p,a=source(tmp_path);b=p.import_image(tmp_path/'photo.tiff')
    update(p,[a['id'],b['id']],{'film':'Portra 400'})
    update(p,[a['id']],{'film':'HP5'})
    assert resolved(p,a['id'])['film']=='HP5';assert resolved(p,b['id'])['film']=='Portra 400'
    update(p,[a['id']],{},['film']);assert resolved(p,a['id'])['film']=='Portra 400'
    assert (tmp_path/'photo.tiff').exists()


def test_palette_decimal_controls_keep_fraction(app):
    from blockstudio.palette_widgets import PaletteControls
    c=PaletteControls();c.numbers['gap'].setValue(2.7);assert c.params()['gap']==2.7
    c.numbers['margin'].setValue(3.2);assert c.params()['margin']==3.2


def test_watermark_16bit_resource_project_and_metadata(tmp_path,app):
    from blockstudio.watermark import DEFAULT_MARK,expand
    from blockstudio.metadata import update
    p,a=source(tmp_path);update(p,[a['id']],{'author':'PostStudio','film':'HP5'})
    logo=np.zeros((8,8,4),np.uint16);logo[2:6,2:6]=[65000,1000,32000,40000]
    write_tiff(tmp_path/'logo.tiff',logo);resource=p.add_resource(tmp_path/'logo.tiff')
    mark={**DEFAULT_MARK,'kind':'image','resource':resource['id'],'width':20,'opacity':50}
    result=p.execute(a['id'],dict(tool='watermark',version=1,params=dict(layers=[mark])))
    out=read_image(p.file(result));assert out.dtype==np.uint16;assert out.shape==(32,48,4)
    assert np.array_equal(out[0,0],[65535]*4);assert result['metadata_snapshot']['film']=='HP5'
    p.data['presets'].append(dict(name='logo',step=dict(tool='watermark',params=dict(layers=[mark]))))
    p.save(tmp_path/'watermark.blockproj');(tmp_path/'logo.tiff').unlink()
    q=Project.open(tmp_path/'watermark.blockproj',tmp_path/'moved');again=q.execute(a['id'],result['step']);assert np.array_equal(read_image(q.file(again)),out)
    assert expand('{相机型号} · {胶卷型号}',dict(film='HP5'))[0]=='HP5'


def test_text_watermark_and_per_image_chain(tmp_path,app):
    from blockstudio.watermark import DEFAULT_MARK
    from blockstudio.workflow import execute_chain
    from blockstudio.metadata import update
    from PIL import Image
    p=Project(tmp_path/'project');ids=[]
    for i in range(10):
        image=np.full((120+i*3,160+i*7,4),65535,np.uint16);image[...,:3]=[4000+i*1000,12000,32000]
        path=tmp_path/f'{i}.tiff';write_tiff(path,image);a=p.import_image(path);ids.append(a['id']);update(p,[a['id']],{'author':f'Photo {i}','film':f'Film {i}'})
    step=dict(tool='watermark',version=1,params=dict(layers=[{**DEFAULT_MARK,'text':'{作者} · {胶卷型号}','size':12,'unit':'px','width':90}]))
    steps=[step,dict(action='name',params=dict(template='{原文件名}-{序号}')),dict(action='export',params=dict(directory=str(tmp_path),template='{name}',options=dict(fmt='PNG',half=True))),dict(tool='invert',params={})]
    report=execute_chain(p,ids,steps);assert report['completed']==10;assert not report['errors'];assert len(report['files'])==10;assert len(report['records'])==20
    for i,id in enumerate(ids):
        marked=report['records'][i*2][1];last=report['records'][i*2+1][1]
        assert marked['metadata_snapshot']['author']==f'Photo {i}';assert last['width']==160+i*7
        with Image.open(report['files'][i]) as exported:assert exported.width==(160+i*7+1)//2
    again=execute_chain(p,ids[:1],[steps[2]]);assert again['files'][0]!=report['files'][0]


def test_workflow_drag_data_and_parameter_edit(app,tmp_path):
    from blockstudio.workflow_widgets import WorkflowEditor
    from blockstudio.tools import DEFAULT_SAMPLE
    p,_=source(tmp_path);p.data['presets']=[dict(name='sample',step=dict(tool='sample',params=copy.deepcopy(DEFAULT_SAMPLE)))]
    dialog=WorkflowEditor(p,p.data['presets'][0]['step']);dialog.chain.add_step(dict(action='name',params=dict(template='A-{序号}')))
    dialog.template.setText('B-{序号}');assert dialog.steps[-1]['params']['template']=='B-{序号}'
    dialog.enabled.setChecked(False);assert dialog.steps[-1]['enabled'] is False
    dialog.move(-1);assert dialog.steps[0]['action']=='name';dialog.close();dialog.deleteLater();app.processEvents()


def test_missing_font_preserved_until_explicit_replacement(app):
    from blockstudio.watermark_widgets import WatermarkControls
    from blockstudio.watermark import DEFAULT_MARK
    from PySide6.QtGui import QFont
    c=WatermarkControls();c.load(dict(layers=[{**DEFAULT_MARK,'font':'Definitely Missing PostStudio Font'}]))
    c.values['opacity'].setValue(42)
    assert c.params()['layers'][0]['font']=='Definitely Missing PostStudio Font'
    assert '缺少字体' in c.font_note.text()
    c.font_changed(QFont('Helvetica'))
    assert c.params()['layers'][0]['font']=='Helvetica'


def test_bounded_shadow_box_matches_reference():
    from blockstudio.effects import _box
    rng=np.random.default_rng(12);a=rng.random((311,257),dtype=np.float32)
    for axis in (0,1):
        actual=_box(a,7,axis)
        expected=np.apply_along_axis(lambda row:np.convolve(row,np.ones(15)/15,mode='same'),axis,a)
        assert np.allclose(actual,expected,atol=1e-7)


def test_layout_linking_and_explicit_frame_ratio(app):
    from blockstudio.palette_widgets import PaletteControls
    c=PaletteControls();c.source_size=(300,200);o=c.layout_controls;o.setChecked(True);o.link.setCurrentIndex(1)
    o.values['top'].setValue(4.7);assert all(o.values[k].value()==4.7 for k in ('top','right','bottom','left'))
    o.ratio.setCurrentIndex(2);p=c.params();g=layout(300,200,p)
    assert abs(g['width']/g['height']-1.5)<.01
    assert '实际外框' in o.actual.text()


def test_border_ratio_scale_and_stroke():
    from blockstudio.border import geometry,border
    p=dict(layers=[dict(mode='outer',unit='px',top=2,right=2,bottom=20,left=2,ratio_mode=2,outer_scale=120)])
    g=geometry(90,60,p);assert abs(g['width']-g['height']*1.5)<=1;assert g['photo'][2:]==[90,60]
    pixels=np.full((60,90,4),65535,np.uint16);p['layers'][0].update(style='stroke',stroke=1)
    out=border(pixels,p);x,y,w,h=g['photo'];assert np.array_equal(out[y:y+h,x:x+w],pixels)
    assert out[3,3,3]==0


def test_chain_cancel_and_failure_reports(tmp_path,app):
    from blockstudio.workflow import execute_chain
    p,a=source(tmp_path);b=p.import_image(tmp_path/'photo.tiff')
    steps=[dict(tool='invert',params={}),dict(action='export',params=dict(directory=str(tmp_path/'missing'),options=dict(fmt='PNG'))),dict(tool='invert',params={})]
    report=execute_chain(p,[a['id'],b['id']],steps)
    assert len(report['errors'])==2;assert len(report['records'])==2;assert not report['files']
    from threading import Event
    cancel=Event()
    def progress(n,total,label):
        if n==1:cancel.set()
    report=execute_chain(p,[a['id'],b['id']],[steps[0],steps[0]],cancel=cancel,progress=progress)
    assert report['cancelled'];assert len(report['records'])<4


def test_discard_and_close_finishes_after_prompt(app,tmp_path,monkeypatch):
    from blockstudio.app import Window
    from PySide6.QtWidgets import QMessageBox
    w=Window(tmp_path/'close-session');w.show();w.dirty=True
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Discard)
    w.close();app.processEvents();app.processEvents()
    assert not w.isVisible();assert not w.project.root.exists()


def test_repeated_border_keeps_original_photo_region(tmp_path,app):
    p,a=source(tmp_path)
    step=dict(tool='border',params=dict(layers=[dict(mode='outer',unit='px',top=2,right=3,bottom=8,left=5)]))
    first=p.execute(a['id'],step);second=p.execute(first['id'],step)
    assert first['regions']['photo']==[5,2,48,32]
    assert second['regions']['photo']==[10,4,48,32]


def test_effect_sample_yields_to_new_preview_request(app):
    from blockstudio.editor import PreviewWorker
    from blockstudio.tools import DEFAULT_SAMPLE
    worker=PreviewWorker();worker.request(2,'unused',dict(tool='invert',params={}))
    pixels=np.full((100,140,4),65535,np.uint16)
    params={**DEFAULT_SAMPLE,'shadow':dict(enabled=True)}
    assert worker.exact_sample(pixels,dict(tool='sample',params=params)) is None


def test_project_workflow_actions_roundtrip_and_future_rejection(tmp_path):
    import pytest
    p,a=source(tmp_path)
    p.data['schema']=3
    p.data['workflows']=[dict(name='export',steps=[dict(action='name',params=dict(template='{序号}')),dict(action='export',params=dict(directory='/unavailable',options=dict(fmt='JPEG')))])]
    p.save(tmp_path/'actions.blockproj');q=Project.open(tmp_path/'actions.blockproj',tmp_path/'actions-reopen')
    assert q.data['workflows']==p.data['workflows']
    q.data['workflows'][0]['steps'].append(dict(tool='future-tool',params={}))
    with pytest.raises(ValueError,match='尚未安装'):validate_manifest(q.data)


def test_workflow_preflight_fields_and_missing_resources_without_outputs(tmp_path,app):
    from blockstudio.workflow import preflight
    p,a=source(tmp_path);before=len(p.data['assets'])
    steps=[dict(tool='watermark',params=dict(layers=[dict(kind='text',text='{胶卷型号}',missing='error'),dict(kind='image',resource='missing-logo')])),dict(action='export',params={})]
    result=preflight(p,[a['id']],steps)
    assert result['outputs']==1 and result['exports']==1
    assert 'missing-logo' in result['errors'][0]
    assert '胶卷型号' in result['warnings'][0] and '停止' in result['warnings'][0]
    assert len(p.data['assets'])==before


def test_workflow_external_drop_copies_step_and_internal_mime_moves(app):
    import json
    from PySide6.QtCore import QMimeData,QPoint,QPointF,Qt
    from PySide6.QtGui import QDragEnterEvent,QDropEvent
    from blockstudio.workflow_widgets import NodeChain,MIME
    chain=NodeChain();chain.resize(350,420);chain.show();app.processEvents()
    chain.add_step(dict(tool='invert',params={}))
    step=dict(action='name',params=dict(template='test'))
    mime=QMimeData();mime.setData(MIME,json.dumps(step).encode())
    point=QPoint(30,20)
    enter=QDragEnterEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(chain.viewport(),enter);assert enter.isAccepted()
    drop=QDropEvent(QPointF(point),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(chain.viewport(),drop);assert drop.isAccepted()
    assert chain.count()==2 and chain.item(0).data(Qt.ItemDataRole.UserRole)==step
    step['params']['template']='changed'
    assert chain.item(0).data(Qt.ItemDataRole.UserRole)['params']['template']=='test'
    # Qt's list model processes the same internal MIME generated by a native drag.
    model=chain.model();internal=model.mimeData([model.index(0,0)])
    assert model.dropMimeData(internal,Qt.DropAction.MoveAction,2,0,model.index(-1,-1))
    # QListWidget removes the source row after the accepted MoveAction returns.
    chain.takeItem(0)
    assert chain.item(0).data(Qt.ItemDataRole.UserRole)['tool']=='invert'
    assert chain.item(1).data(Qt.ItemDataRole.UserRole)['action']=='name'


def test_leaf_revision_preserves_id_layout_and_prior_pixels_for_undo(tmp_path):
    import pytest
    from blockstudio.tools import DEFAULT_SAMPLE
    p,a=source(tmp_path);step=dict(tool='sample',version=3,params={**DEFAULT_SAMPLE,'block_x':8,'block_y':8,'gap_x':8,'gap_y':8})
    leaf=p.execute(a['id'],step);record=p.placement(leaf,p.data['boards'][0]);before=copy.deepcopy(p.data);original=read_image(p.file(leaf)).copy()
    changed=copy.deepcopy(step);changed['params']['block_x']=4
    updated=p.revise_leaf(leaf['id'],changed)
    assert updated['id']==leaf['id'] and len(p.data['assets'])==2
    assert p.data['boards'][0]['items'][0]==record
    assert np.array_equal(read_image(p.root/leaf['file']),original)
    assert not np.array_equal(read_image(p.file(updated)),original)
    p.save(tmp_path/'revised.blockproj');q=Project.open(tmp_path/'revised.blockproj',tmp_path/'reopened')
    assert q.asset(leaf['id'])['step']['params']['block_x']==4
    child=p.execute(leaf['id'],dict(tool='invert',params={}))
    with pytest.raises(ValueError,match='下游'):p.revise_leaf(leaf['id'],step)
    trash.remove_assets(p,[child['id']])
    with pytest.raises(ValueError,match='下游'):p.revise_leaf(leaf['id'],step)
    p.data=before;assert np.array_equal(read_image(p.file(p.asset(leaf['id']))),original)


def test_revision_failure_rolls_back_and_composition_cache_tracks_content(tmp_path,app,monkeypatch):
    import pytest
    from blockstudio.palette_render import DEFAULT_PALETTE
    p,a=source(tmp_path)
    step=dict(tool='palette',version=2,params={**DEFAULT_PALETTE,'colors':[[65535,0,0],[0,0,65535]],'count':2})
    leaf=p.execute(a['id'],step);old_state=copy.deepcopy(p.data);old=read_image(p.file(leaf)).copy();count=len(p.data['assets'])
    changed=copy.deepcopy(step);changed['params']['margin']=20
    result=p.revise_leaf(leaf['id'],changed)
    assert len(p.data['assets'])==count and result['id']==leaf['id']
    assert read_image(p.file(result)).shape!=old.shape
    p.data=copy.deepcopy(old_state);assert np.array_equal(read_image(p.file(p.asset(leaf['id']))),old)
    def failure(*args,**kwargs):p.data['assets'].append({'id':'partial'});raise RuntimeError('render failed')
    monkeypatch.setattr(p,'execute',failure)
    with pytest.raises(RuntimeError):p.revise_leaf(leaf['id'],step)
    assert p.data==old_state


def test_overview_selection_and_explicit_leaf_save(app,tmp_path):
    from blockstudio.app import Window
    w=Window(tmp_path/'window');p=w.project
    path=tmp_path/'x.tiff';write_tiff(path,np.full((30,45,4),65535,np.uint16))
    a=p.import_image(path);leaf=p.execute(a['id'],dict(tool='invert',params={}))
    r=p.placement(a,w.board);w.refresh_all([r['id']]);layout=copy.deepcopy(w.board)
    w.tabs.setCurrentIndex(1);assert w.canvas_pages.currentWidget()==w.overview and w.overview.count()==2
    assert w.selected_ids()==[]  # Never fall back to the hidden canvas selection.
    w.overview.item(1).setSelected(True);assert w.selected_ids()==[leaf['id']]
    w.reload_step();assert w.reedit_target==leaf['id'] and w.save_revision_button.isEnabled()
    w.source_mode.setCurrentIndex(1);assert not w.save_revision_button.isEnabled()
    w.leave_editor();w.tabs.setCurrentIndex(0);assert w.board==layout
    w.stop_preview()
    for worker in w.retiring_workers:worker.wait(10000)
    w.dirty=False;w.close()


def test_border_selected_and_custom_ratios_persist_without_resampling(app):
    from blockstudio.border_widgets import BorderControls
    from blockstudio.border import border,geometry
    c=BorderControls();c.ratio.setCurrentIndex(3);c.choose_ratio(0)
    a=np.full((20,30,4),65535,np.uint16);a[...,:3]=[1000,2345,6543]
    p=c.params();g=geometry(30,20,p);assert g['width']==g['height']
    c.ratio_width.setValue(7);c.ratio_height.setValue(5);p=c.params();g=geometry(30,20,p)
    x,y,w,h=g['photo'];assert (w,h)==(30,20)
    assert abs(g['width']-g['height']*7/5)<=1
    assert np.array_equal(border(a,p)[y:y+h,x:x+w],a)
    restored=BorderControls();restored.load(p);assert restored.params()==p
    restored.mode.setCurrentIndex(1);assert not restored.ratio_options.isEnabled()


def test_save_revision_ui_returns_to_overview_and_undo_restores_pixels(app,tmp_path):
    import time
    from blockstudio.app import Window
    w=Window(tmp_path/'window');w.show();p=w.project
    src=tmp_path/'x.tiff';write_tiff(src,np.full((20,30,4),65535,np.uint16));a=p.import_image(src)
    leaf=p.execute(a['id'],dict(tool='border',params=dict(layers=[dict(mode='outer',unit='px',top=2,right=2,bottom=2,left=2)])))
    w.refresh_all();w.tabs.setCurrentIndex(1);w.overview.item(1).setSelected(True);w.reload_step()
    w.panel.border.values['bottom'].setValue(8);w.save_revision()
    until=time.monotonic()+5
    while w.job is not None and time.monotonic()<until:app.processEvents();time.sleep(.005)
    assert w.job is None and w.pages.currentWidget()==w.workspace and w.tabs.currentIndex()==1
    assert len(p.data['assets'])==2 and p.asset(leaf['id'])['height']==30
    w.overview.setFocus();w.undo_state(-1)
    assert p.asset(leaf['id'])['height']==24 and read_image(p.file(p.asset(leaf['id']))).shape[0]==24
    w.undo_state(1);assert p.asset(leaf['id'])['height']==30
    w.dirty=False;w.close()


def test_canvas_right_delete_targets_clicked_photo_and_all_placements(app,tmp_path,monkeypatch):
    from blockstudio.app import Window
    from blockstudio.project import blank_board
    from PySide6.QtWidgets import QMenu,QMessageBox
    from PySide6.QtCore import QPointF
    w=Window(tmp_path/'window');w.show();p=w.project
    src=tmp_path/'x.tiff';write_tiff(src,np.full((20,30,4),65535,np.uint16));a=p.import_image(src);b=p.import_image(src)
    p.placement(a,w.board);p.placement(b,w.board);other=blank_board();p.data['boards'].append(other);p.placement(b,other)
    w.refresh_all();w.fit();app.processEvents()
    target=next(i for i in w.view.scene().items() if getattr(i,'asset',{}).get('id')==b['id'])
    def choose_delete(menu,*_):
        next(action for action in menu.actions() if action.text().startswith('删除图像')).trigger()
    class TestMenu(QMenu):
        def exec(self,*args):return choose_delete(self,*args)
    monkeypatch.setattr('blockstudio.app.QMenu',TestMenu)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    point=w.view.mapFromScene(target.mapToScene(QPointF(20,20)));w.canvas_context(point)
    assert p.asset(b['id'])['trashed'] and not p.asset(a['id']).get('trashed')
    assert all(r['asset']!=b['id'] for board in p.data['boards'] for r in board['items'])
    assert src.exists();w.dirty=False;w.close()
