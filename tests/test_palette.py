import numpy as np
import pytest
from blockstudio.palette import PaletteAnalysis,srgb_to_oklab,oklab_to_srgb,stratified_samples


def test_oklab_reference_and_roundtrip():
    rgb=np.array([[1,0,0],[0,1,0],[0,0,1],[1,1,1],[0,0,0],[.5,.5,.5]])
    lab=srgb_to_oklab(rgb)
    assert np.allclose(lab[0],[.627955,.224863,.125846],atol=1e-6)
    assert np.allclose(lab[3],[1,0,0],atol=1e-7)
    assert abs(lab[-1,0]-.598181)<1e-6
    assert np.allclose(oklab_to_srgb(lab),rgb,atol=1e-6)


def test_palette_real_pixels_and_area_alpha():
    a=np.zeros((10,10,4),np.uint16)
    a[:5,:,:]=[65535,0,0,65535];a[5:8,:,:]=[0,0,65535,65535]
    a[8:,:,:]=[0,65535,0,0]
    result=PaletteAnalysis(a).extract(5)
    assert len(result['swatches'])==2
    assert [s['rgb16'] for s in result['swatches']]==[[65535,0,0],[0,0,65535]]
    assert np.allclose([s['weight'] for s in result['swatches']],[.625,.375])
    a[8:,:,:]=[0,0,65535,32768]
    result=PaletteAnalysis(a).extract(2)
    assert abs(result['swatches'][0]['weight']-50/90)<1e-5


def test_palette_locks_manual_order_and_transparency():
    a=np.ones((20,30,4),np.uint16)*65535;a[:10,:,:3]=12345
    analysis=PaletteAnalysis(a)
    assert analysis.extract(5)==analysis.extract(5)
    result=analysis.extract(3,locked=[[0,65535,0]])
    assert any(s['locked'] and s['rgb16']==[0,65535,0] for s in result['swatches'])
    order=[[0,65535,0],[65535,65535,65535]]
    result=analysis.extract(2,locked=[order[0]],colors=order)
    assert [s['rgb16'] for s in result['swatches']]==order
    with pytest.raises(ValueError):analysis.extract(2,locked=[[0,0,0],[1,1,1],[2,2,2]])
    a[...,3]=0
    with pytest.raises(ValueError,match='透明'):PaletteAnalysis(a)


def test_sampling_deterministic_bounded_and_gray_levels():
    a=np.ones((300,500,4),np.uint16)*65535
    for i,value in enumerate([0,12345,34567,65535]):a[:,i*125:(i+1)*125,:3]=value
    rgb,weights=stratified_samples(a)
    assert len(rgb)<=32768 and weights.sum()==150000
    assert np.array_equal(rgb,stratified_samples(a)[0])
    result=PaletteAnalysis(a).extract(4)
    assert {tuple(s['rgb16']) for s in result['swatches']}=={(v,v,v) for v in [0,12345,34567,65535]}


def test_distinctive_mode_retains_small_red_accent():
    # Snow/sky/trees occupy almost all the frame; the red mark is only 0.25%.
    a=np.ones((200,400,4),np.uint16)*65535
    a[:80,:,:3]=[56000,59000,63000];a[80:150,:,:3]=[24000,33000,40000];a[150:,:,:3]=[16000,24000,22000]
    a[190:200,390:400,:3]=[60000,5000,4000]
    analysis=PaletteAnalysis(a)
    area=analysis.extract(3,'area');distinctive=analysis.extract(3,'distinctive')
    red=lambda result:any(s['rgb16'][0]>50000 and s['rgb16'][1]<10000 for s in result['swatches'])
    assert red(distinctive) and not red(area)


def test_composition_roundtrip_split_and_downstream(app,tmp_path):
    from blockstudio.project import Project,validate_manifest
    from blockstudio.imaging import write_tiff,read_image
    from blockstudio.tools import apply_tool
    from blockstudio.palette_render import DEFAULT_PALETTE,layout
    a=np.ones((80,120,4),np.uint16)*65535;a[:40,:,:3]=[12345,23456,34567];a[40:,:,:3]=[52345,43456,24567]
    src=tmp_path/'x.tiff';write_tiff(src,a)
    p=Project(tmp_path/'work');source=p.import_image(src);source_bytes=p.file(source).read_bytes()
    step=dict(tool='palette',version=1,intent='revise',params={**DEFAULT_PALETTE,'count':3,'side':'left','transparent':True})
    asset=p.execute(source['id'],step);assert asset['kind']=='composition' and asset['file'] is None
    geometry=layout(120,80,step['params'])
    rendered=read_image(p.file(asset));x,y,w,h=geometry['photo']
    assert np.array_equal(rendered[y:y+h,x:x+w],a)
    board=p.data['boards'][0];record=p.placement(asset,board)
    children=p.split_composition(record,board)
    assert len(children)==2 and len(p.data['assets'])==3
    follow=p.execute(asset['id'],dict(tool='invert',version=1,params={}))
    assert np.array_equal(read_image(p.file(follow)),apply_tool(rendered,dict(tool='invert',params={})))
    p.save(tmp_path/'share.blockproj');q=Project.open(tmp_path/'share.blockproj',tmp_path/'other-machine')
    assert not (q.root/'cache').exists()
    assert np.array_equal(read_image(q.file(q.asset(asset['id']))),rendered)
    assert p.file(source).read_bytes()==source_bytes
    assert q.asset(asset['id'])['palette']==asset['palette']
    validate_manifest(q.data)
    # Unsupported readers must reject v2 rather than silently discard composition data.
    assert q.data['schema']==2


def test_ring_and_standalone_render_preserves_swatch_depth(app):
    from blockstudio.palette_render import DEFAULT_PALETTE,render_palette,layout
    a=np.ones((100,200,4),np.uint16)*65535;a[...,:3]=[12345,23456,34567]
    result=PaletteAnalysis(a).extract(5)
    p={**DEFAULT_PALETTE,'style':'ring','output':'palette','size':60,'transparent':True,'margin':0}
    image=render_palette(a,result,p)
    assert image.dtype==np.uint16 and image.shape[:2]==(120,120)
    assert image[60,60,3]==0 and image[60,108,3]==65535
    assert image[60,108,:3].tolist()==[12345,23456,34567]
    for side in ['left','right','top','bottom']:
        p={**DEFAULT_PALETTE,'side':side,'style':'ring'};g=layout(200,100,p)
        assert render_palette(a,result,p).shape==(g['height'],g['width'],4)


def test_palette_workflow_batch_ten_and_schema_rejection(app,tmp_path):
    import copy
    from blockstudio.project import Project,validate_manifest
    from blockstudio.imaging import write_tiff,read_image
    from blockstudio.palette_render import DEFAULT_PALETTE
    p=Project(tmp_path/'work')
    for i in range(10):
        a=np.ones((24+i,40+i*2,4),np.uint16)*65535;a[...,:3]=[1000+i*5300,23456,34567]
        src=tmp_path/f'{i}.tiff';write_tiff(src,a);source=p.import_image(src)
        a1=p.execute(source['id'],dict(tool='palette',version=1,params={**DEFAULT_PALETTE,'output':'palette'}))
        b1=p.execute(a1['id'],dict(tool='sample',version=2,params=dict(block_x=4,block_y=4,gap_x=2,gap_y=2,offset_x=0,offset_y=0)))
        assert a1['palette']['swatches'][0]['rgb16']==a[0,0,:3].tolist()
        assert read_image(p.file(b1)).dtype==np.uint16
    assert len(p.data['assets'])==30
    p.save(tmp_path/'batch.blockproj');q=Project.open(tmp_path/'batch.blockproj',tmp_path/'loaded')
    assert len(q.data['assets'])==30
    bad=copy.deepcopy(q.data);bad['schema']=99
    with pytest.raises(ValueError,match='版本'):validate_manifest(bad)
