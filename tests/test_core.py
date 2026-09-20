import copy
import json
import zipfile
import numpy as np
import pytest
import tifffile
from PySide6.QtGui import QImageReader
from blockstudio.imaging import read_image,write_tiff,downsample2,export_image
from blockstudio.tools import apply_tool,DEFAULT_SAMPLE
from blockstudio.project import Project,render_frame


def pixels(h=9,w=13):
    a=np.zeros((h,w,4),np.uint16)
    a[...,0]=np.arange(w)[None,:]*2001;a[...,1]=np.arange(h)[:,None]*3007;a[...,2]=12345;a[...,3]=65535
    return a


def test_16bit_roundtrip_and_png(tmp_path):
    a=pixels();a[1,2]=[501,32769,65001,40001]
    for fmt,suffix in [('TIFF','tiff'),('PNG','png')]:
        path=tmp_path/('test.'+suffix);export_image(path,a,fmt)
        assert np.array_equal(read_image(path),a)
    with tifffile.TiffFile(tmp_path/'test.tiff') as t:
        assert t.pages[0].bitspersample==16
        assert int(t.pages[0].compression)==32946 or int(t.pages[0].compression)==8
        assert t.pages[0].tags[34675].value


def test_sample_coordinates_offset_and_transparency():
    a=pixels(7,11);p={**DEFAULT_SAMPLE,'block_x':2,'block_y':3,'gap_x':1,'gap_y':2,'offset_x':-1,'offset_y':1}
    result=apply_tool(a,dict(tool='sample',params=p))
    for y in range(7):
        for x in range(11):
            if (x+1)%3<2 and (y-1)%5<3:assert np.array_equal(result[y,x],a[y,x])
            else:assert np.array_equal(result[y,x],[0,0,0,0])
    assert np.array_equal(a,pixels(7,11))
    p.update(transparent=False,color='#102030')
    result=apply_tool(a,dict(tool='sample',params=p));assert np.array_equal(result[0,0],[16*257,32*257,48*257,65535])


def test_alpha_weighted_downsample_odd_edges():
    a=np.array([[[65535,0,0,65535],[0,0,65535,0],[123,456,789,65535]],[[65535,0,0,65535],[0,0,65535,0],[123,456,789,65535]],[[42,84,126,65535],[42,84,126,65535],[11,22,33,65535]]],np.uint16)
    r=downsample2(a)
    assert r.shape==(2,2,4)
    assert np.array_equal(r[0,0],[65535,0,0,32768])
    assert np.array_equal(r[1,1],a[2,2])


def test_project_independent_branches_archive_and_recovery(tmp_path):
    source=tmp_path/'source.tiff';a=pixels();write_tiff(source,a)
    p=Project(tmp_path/'work');src=p.import_image(source)
    step=dict(tool='sample',params={**DEFAULT_SAMPLE,'block_x':2,'gap_x':2,'block_y':2,'gap_y':2})
    a1=p.execute(src['id'],step);b1=p.execute(a1['id'],dict(tool='invert',params={}))
    before=p.file(b1).read_bytes()
    step['params']['gap_x']=3;a2=p.execute(src['id'],step)
    assert len(p.data['assets'])==4 and p.file(b1).read_bytes()==before
    assert a1['step']['params']['gap_x']==2
    b2=p.execute(a2['id'],dict(tool='invert',params={}))
    assert b2['parent']==a2['id'] and b1['parent']==a1['id']
    p.placement(b1,p.data['boards'][0],-30,70)
    p.data['workflows']=[dict(name='two',steps=[step,dict(tool='invert',params={})])]
    saved=tmp_path/'test.blockproj';p.save(saved)
    q=Project.open(saved,tmp_path/'reopen')
    assert q.data==p.data and q.file(q.asset(b1['id'])).read_bytes()==before
    recovered=Project.recover(tmp_path/'reopen');assert recovered.data==q.data


def test_half_import_default_no_original(tmp_path):
    source=tmp_path/'source.tiff';write_tiff(source,pixels(8,12))
    p=Project(tmp_path/'work');a=p.import_image(source,True,False)
    assert a['original'] is None and (a['width'],a['height'])==(6,4)
    assert np.array_equal(read_image(p.file(a)),downsample2(pixels(8,12)))
    b=p.import_image(source,True,True)
    assert (p.root/b['original']).read_bytes()==source.read_bytes()


def test_reject_unsafe_archive(tmp_path):
    p=Project(tmp_path/'work');source=tmp_path/'src.tiff';write_tiff(source,pixels());p.import_image(source)
    manifest=copy.deepcopy(p.data);manifest['assets'][0]['file']='../outside.tiff'
    bad=tmp_path/'bad.blockproj'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json',json.dumps(manifest))
    with pytest.raises(ValueError,match='非法'):Project.open(bad,tmp_path/'extract')


def test_frame_composition_geometry_and_transparency(tmp_path):
    a=np.full((4,4,4),65535,np.uint16);a[...,:3]=[65535,0,0]
    source=tmp_path/'red.tiff';write_tiff(source,a)
    p=Project(tmp_path/'work');asset=p.import_image(source);board=p.data['boards'][0]
    item=p.placement(asset,board,2,2);item['width']=4
    result=render_frame(p,board,dict(x=0,y=0,width=8,height=8),8)
    assert result.shape==(8,8,4)
    assert np.all(result[2:6,2:6,0]==65535) and np.all(result[2:6,2:6,3]==65535)
    assert result[0,0,3]==0


def test_jpeg_flattens_selected_background(tmp_path):
    a=np.zeros((8,8,4),np.uint16);p=tmp_path/'x.jpg';export_image(p,a,'JPEG',100,background='#ffffff')
    decoded=read_image(p);assert decoded.shape==(8,8,4);assert np.all(decoded>=65000)


def test_failed_save_keeps_previous_project(tmp_path,monkeypatch):
    src=tmp_path/'x.tiff';write_tiff(src,pixels())
    p=Project(tmp_path/'work');p.import_image(src);dest=tmp_path/'saved.blockproj';p.save(dest);before=dest.read_bytes()
    def fail(*args,**kwargs):raise OSError('disk full simulation')
    monkeypatch.setattr(zipfile.ZipFile,'write',fail)
    with pytest.raises(OSError):p.save(dest)
    assert dest.read_bytes()==before


def test_tiff_orientation_and_grayscale(tmp_path):
    gray=np.arange(24,dtype=np.uint16).reshape(4,6)*1001
    path=tmp_path/'gray.tiff';tifffile.imwrite(path,gray,photometric='minisblack',extratags=[(274,'H',1,6,False)])
    a=read_image(path)
    assert a.shape==(6,4,4)
    assert np.array_equal(a[...,0],np.rot90(gray,-1))
    assert np.array_equal(a[...,0],a[...,2])


def test_self_contained_after_source_deleted(tmp_path):
    src=tmp_path/'input.tiff';write_tiff(src,pixels())
    p=Project(tmp_path/'session');a=p.import_image(src);p.save(tmp_path/'copy.blockproj');src.unlink()
    q=Project.open(tmp_path/'copy.blockproj',tmp_path/'other-computer')
    assert np.array_equal(read_image(q.file(q.asset(a['id']))),pixels())


def test_single_block_move_preserves_others_and_uses_new_source_pixels():
    from blockstudio.tools import block_at
    a=pixels(12,16)
    p={**DEFAULT_SAMPLE,'block_x':2,'block_y':2,'gap_x':2,'gap_y':2,'moved_blocks':{'0,0':[1,2]}}
    result=apply_tool(a,dict(tool='sample',params=p))
    assert np.all(result[0:2,0:2,3]==0)
    assert np.array_equal(result[2:4,1:3],a[2:4,1:3])
    assert np.array_equal(result[0:2,4:6],a[0:2,4:6])
    assert block_at(p,1.5,2.5)=='0,0'
    assert block_at(p,.5,.5) is None


def test_resolve_old_accidental_masks_and_explicit_append(tmp_path):
    from blockstudio.tools import resolve_input
    p=Project(tmp_path/'work');src=tmp_path/'source.tiff';write_tiff(src,pixels(96,160));original=p.import_image(src)
    a1=p.execute(original['id'],dict(tool='sample',params=DEFAULT_SAMPLE))
    a2=p.execute(a1['id'],dict(tool='sample',params={**DEFAULT_SAMPLE,'block_x':80,'gap_x':80}))
    source,step=resolve_input(p,a2['id'],'sample')
    assert source==original['id']
    fixed=p.execute(source,step)
    expected=apply_tool(read_image(src),step)
    assert np.array_equal(read_image(p.file(fixed)),expected)
    assert not np.array_equal(read_image(p.file(a2)),expected)
    assert resolve_input(p,a1['id'],'sample',append=True)[0]==a1['id']
    intentional=p.execute(a1['id'],dict(tool='sample',params=DEFAULT_SAMPLE,intent='append'))
    assert resolve_input(p,intentional['id'],'sample')[0]==a1['id']
    assert resolve_input(p,a1['id'],'invert')[0]==a1['id']
