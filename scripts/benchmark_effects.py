"""Bounded synthetic benchmarks for PostStudio 0.4, excluding display latency."""
import json,time,resource,gc
from pathlib import Path
import numpy as np
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication
from blockstudio.editor import InteractiveSource
from blockstudio.tools import DEFAULT_SAMPLE,apply_tool
from blockstudio.effects import DEFAULT_BACKGROUND,DEFAULT_SHADOW
app=QApplication([])
report={'fixture':'Synthetic RGBA16; not photographic file-size or physical display latency evidence','cases':[]}
for width,height in [(1200,800),(6000,4000),(8000,6000)]:
    pixels=np.empty((height,width,4),np.uint16);pixels[...,0]=np.arange(width,dtype=np.uint32)[None,:]*53%65536;pixels[...,1]=np.arange(height,dtype=np.uint32)[:,None]*71%65536;pixels[...,2]=23456;pixels[...,3]=65535
    start=time.perf_counter();source=InteractiveSource(pixels,edge=560);setup=time.perf_counter()-start
    step=dict(tool='sample',version=3,params={**DEFAULT_SAMPLE,'transparent':False,'background_spec':{**DEFAULT_BACKGROUND,'kind':'linear'},'shadow':{**DEFAULT_SHADOW,'enabled':True}})
    times=[]
    for i in range(8):
        step['params']['offset_x']=i*7;start=time.perf_counter();source.render(step);times.append((time.perf_counter()-start)*1000)
    start=time.perf_counter();out=apply_tool(pixels,step);exact=time.perf_counter()-start
    assert out.shape==pixels.shape and out.dtype==np.uint16
    report['cases'].append(dict(width=width,height=height,setup_ms=round(setup*1000,2),interactive_median_ms=round(float(np.median(times)),2),interactive_p95_ms=round(float(np.percentile(times,95)),2),full_render_seconds=round(exact,3),peak_resident_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,1)))
    del pixels,source,out;gc.collect()
Path('artifacts/effects-v04.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
