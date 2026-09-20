import numpy as np
from blockstudio.editor import coverage_mask
from blockstudio.tools import DEFAULT_SAMPLE,apply_tool


def test_coverage_equals_exact_pixel_area_including_moved_union():
    # Integral scale allows a direct box-average reference independent of Qt.
    a=np.ones((144,240,4),np.uint16)*65535
    cases=[dict(block_x=1,block_y=1,gap_x=1,gap_y=2,offset_x=-3,offset_y=2),
           dict(block_x=13,block_y=11,gap_x=8,gap_y=7,offset_x=-4,offset_y=-5,
                moved_blocks={'0,0':[9,8],'1,0':[-12,9],'2,1':[-31,-9],'-1,0':[22,5]})]
    for params in cases:
        p={**DEFAULT_SAMPLE,**params}
        native=apply_tool(a,dict(tool='sample',params=p))[...,3]/65535
        reference=native.reshape(24,6,40,6).mean(axis=(1,3))
        assert np.allclose(coverage_mask(240,144,p,40,24),reference,atol=2e-6)


def test_preview_allows_progress_without_stale_session(app,tmp_path):
    from blockstudio.app import Window
    from blockstudio.imaging import write_tiff,preview
    w=Window(tmp_path/'sessions');w.show();app.processEvents()
    src=tmp_path/'x.tiff';write_tiff(src,np.ones((60,90,4),np.uint16)*65535)
    asset=w.project.import_image(src);r=w.project.placement(asset,w.board)
    w.refresh_all([r['id']]);w.open_tool(tool_id='sample')
    floor=w.preview_floor
    w.preview_generation=floor+10
    image=preview(np.ones((60,90,4),np.uint16)*32768)
    w.preview_ready(floor+1,dict(image=image,exact=False))
    assert w.preview_displayed==floor+1
    w.preview_ready(floor+2,dict(image=image,exact=True))
    w.preview_ready(floor+1,dict(image=preview(np.zeros((60,90,4),np.uint16)),exact=True))
    assert w.panel.preview.image==image and w.preview_displayed==floor+2
    w.preview_ready(floor-1,dict(image=preview(np.zeros((60,90,4),np.uint16)),exact=True))
    assert w.panel.preview.image==image
    w.leave_editor();w.dirty=False;w.close();app.processEvents()


def test_exact_bands_match_full_source(app):
    from blockstudio.editor import PreviewWorker
    from blockstudio.imaging import preview
    a=np.ones((530,730,4),np.uint16)*65535;a[...,:3]=[12345,23456,34567]
    p={**DEFAULT_SAMPLE,'offset_x':-13,'offset_y':47,'block_y':23,'gap_y':19,'moved_blocks':{'2,3':[11,139],'0,0':[-20,-30]}}
    step=dict(tool='sample',params=p)
    worker=PreviewWorker()
    assert worker.exact_sample(a,step)==preview(apply_tool(a,step),1600)
    worker.request(2,'irrelevant',step)
    assert worker.exact_sample(a,step) is None


def test_incremental_moved_window_mask_matches_full_rebuild():
    from blockstudio.editor import InteractiveSource
    import copy
    source=InteractiveSource(np.ones((1200,1800,4),np.uint16)*65535)
    p=copy.deepcopy(DEFAULT_SAMPLE)
    p['moved_blocks']={'0,0':[120,30],'1,0':[-40,80],'3,4':[400,-60]}
    source.sampling_mask(p)
    for value in [[90,40],[-200,600],[1700,1100],[0,0]]:
        p['moved_blocks']['0,0']=value
        actual=source.sampling_mask(p).copy()
        assert np.allclose(actual,coverage_mask(1800,1200,p,source.image.width(),source.image.height()),atol=2e-6)
    del p['moved_blocks']['0,0']
    assert np.allclose(source.sampling_mask(p),coverage_mask(1800,1200,p,source.image.width(),source.image.height()),atol=2e-6)


def test_effect_preview_cache_uses_requested_resolution_and_source_coordinates(app):
    from blockstudio.editor import InteractiveSource
    a=np.ones((600,900,4),np.uint16)*65535
    source=InteractiveSource(a,edge=560)
    assert source.pixels.shape[1]==560
    p={**DEFAULT_SAMPLE,'block_x':47,'block_y':39,'offset_x':19,'gap_x':31,
       'background_spec':{'kind':'linear'},'shadow':{'enabled':True}}
    result=source.render(dict(tool='sample',params=p))
    assert result.width()==560
    assert np.allclose(source.mask,coverage_mask(900,600,p,560,source.image.height()))
    assert np.all(a==65535)
