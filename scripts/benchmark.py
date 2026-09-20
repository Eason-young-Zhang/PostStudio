"""Synthetic validation fixture, not an artwork or a photographic benchmark."""
import json
import resource
import time
import tempfile
from pathlib import Path
import numpy as np
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from blockstudio.imaging import write_tiff,read_image,downsample2
from blockstudio.tools import DEFAULT_SAMPLE
from blockstudio.project import Project

report={'fixture':'Synthetic 8000 × 6000, RGBA16 sRGB; compressible patterns, not photographic file-size evidence','measurements':{}}
def timed(name,fn):
    t=time.perf_counter();value=fn();report['measurements'][name]=round(time.perf_counter()-t,3);return value
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);a=np.empty((6000,8000,4),np.uint16)
    a[...,0]=np.arange(8000,dtype=np.uint16)[None,:]*8
    a[...,1]=np.arange(6000,dtype=np.uint16)[:,None]*10
    a[...,2]=23456;a[...,3]=65535
    src=root/'48mp.tiff';timed('write_48mp_seconds',lambda:write_tiff(src,a));del a
    p=Project(root/'work')
    source=timed('import_48mp_seconds',lambda:p.import_image(src))
    result=timed('sample_48mp_seconds',lambda:p.execute(source['id'],dict(tool='sample',params=DEFAULT_SAMPLE)))
    pixels=timed('read_result_seconds',lambda:read_image(p.file(result)))
    assert pixels.dtype==np.uint16 and pixels.shape==(6000,8000,4);del pixels
    timed('project_save_seconds',lambda:p.save(root/'sample.blockproj'))
    timed('project_open_seconds',lambda:Project.open(root/'sample.blockproj',root/'reopen'))
    report['project_bytes']= (root/'sample.blockproj').stat().st_size
    report['peak_resident_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,1)
Path('artifacts/benchmark.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
