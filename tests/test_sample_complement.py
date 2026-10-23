import copy
import numpy as np
import pytest
from blockstudio.tools import DEFAULT_SAMPLE,apply_tool
from blockstudio.project import Project
from blockstudio.imaging import write_tiff,read_image
from blockstudio.workflow import execute_chain,preflight


def step(**params):return dict(tool='sample',version=4,intent='revise',params={**DEFAULT_SAMPLE,**params})


@pytest.mark.parametrize('moves',[{}, {'0,0':[6,4],'1,0':[-4,0]}])
def test_complement_partition(moves):
    rng=np.random.default_rng(4);pixels=rng.integers(0,65536,(21,31,4),dtype=np.uint16)
    p=step(block_x=5,block_y=4,gap_x=3,gap_y=2,offset_x=-2,offset_y=1,moved_blocks=moves)
    kept=apply_tool(pixels,p);p['params']['output_part']='removed';removed=apply_tool(pixels,p)
    assert not np.any((kept[...,3]>0)&(removed[...,3]>0))
    assert np.array_equal(kept.astype(np.uint32)+removed,pixels)


def fixture(tmp_path):
    p=Project(tmp_path/'project');pixels=np.full((24,32,4),40000,np.uint16)
    path=tmp_path/'source.tiff';write_tiff(path,pixels);a=p.import_image(path)
    return p,a


def test_outputs_reedit_portable_and_workflow(app,tmp_path):
    p,a=fixture(tmp_path);s=step(block_x=4,block_y=4,gap_x=4,gap_y=4,emit_complement=True)
    outputs=p.execute_outputs(a['id'],s);main,extra=outputs
    assert main['parent']==extra['parent']==a['id']
    assert extra['step']['params']['output_part']=='removed'
    assert not extra['step']['params']['emit_complement']
    assert p.revision_blocker(main['id']) is None
    old=read_image(p.file(extra));changed=copy.deepcopy(s);changed['params']['gap_x']=7
    p.execute_outputs(a['id'],changed,revision=main['id'])
    assert np.array_equal(read_image(p.file(extra)),old)
    path=tmp_path/'both.blockproj';p.save(path);reopened=Project.open(path,tmp_path/'reopen')
    assert reopened.asset(extra['id'])['step']==extra['step']
    flow=[s,dict(tool='invert',version=1,params={})]
    assert preflight(p,[a['id']],flow)['outputs']==3
    report=execute_chain(p,[a['id']],flow)
    assert not report['errors'] and len(report['records'])==3 and len(report['side_outputs'])==1
    side,primary,final=[r[1] for r in report['records']]
    assert final['parent']==primary['id'] and side['parent']==a['id']


def test_companion_failure_rolls_back(app,tmp_path,monkeypatch):
    p,a=fixture(tmp_path);before=copy.deepcopy(p.data);execute=p.execute
    def fail(id,s,fields=None):
        if s['params'].get('output_part')=='removed':raise OSError('disk full')
        return execute(id,s,fields)
    monkeypatch.setattr(p,'execute',fail)
    with pytest.raises(OSError):p.execute_outputs(a['id'],step(emit_complement=True))
    assert p.data==before


def test_panel_roundtrip_and_legacy(app):
    from blockstudio.widgets import ToolPanel
    panel=ToolPanel();panel.load_step(step(output_part='removed',emit_complement=True))
    assert panel.output_part.currentIndex()==1 and panel.emit_complement.isChecked()
    assert panel.step()['params']['output_part']=='removed'
    legacy=step();legacy['params'].pop('output_part');legacy['params'].pop('emit_complement');legacy['version']=3
    panel.load_step(legacy)
    assert panel.output_part.currentIndex()==0 and not panel.emit_complement.isChecked()


@pytest.mark.parametrize('mode',[0,1,2])
def test_workbench_pair_placement_and_revision(app,tmp_path,mode):
    import time
    from blockstudio.app import Window
    w=Window(tmp_path/'sessions');p,a=fixture(tmp_path);w.project=p;w.board_id=p.data['boards'][0]['id']
    placement=p.placement(a,w.board);w.refresh_all([placement['id']]);w.open_tool(tool_id='sample')
    w.panel.load_step(step(block_x=4,block_y=4,gap_x=4,gap_y=4,emit_complement=True));w.panel.mode.setCurrentIndex(mode)
    def wait():
        for _ in range(2000):
            app.processEvents();time.sleep(.002)
            if w.job is None:return
        raise AssertionError('job timeout')
    w.apply_current();wait()
    assert len(p.data['assets'])==3
    extra,main=[r[1] for r in w.last_run_report['records']]
    assert {main['id'],extra['id']} <= {r['asset'] for r in w.board['items']}
    record=next(r for r in w.board['items'] if r['asset']==main['id'])
    w.refresh_all([record['id']]);w.reload_step();w.panel.spins['gap_x'].setValue(7)
    old=copy.deepcopy(extra);w.save_revision();wait()
    assert len(p.data['assets'])==4 and p.asset(extra['id'])==old
    assert p.asset(main['id'])['step']['params']['gap_x']==7
    assert any(r['asset']==p.data['assets'][-1]['id'] for r in w.board['items'])
