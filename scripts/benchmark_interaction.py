"""Reproducible CPU preview benchmark; not mouse-to-display latency evidence."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from blockstudio.imaging import preview
from blockstudio.tools import apply_tool, DEFAULT_SAMPLE


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='artifacts/interaction-baseline.json');parser.add_argument('--fast',action='store_true');args=parser.parse_args()
    report={'fixture':'Deterministic synthetic RGBA16; timings exclude decode and display latency','mode':'interactive' if args.fast else '0.2 full-resolution','sizes':[]}
    for w,h in [(1200,800),(6000,4000),(8000,6000)]:
        a=np.empty((h,w,4),np.uint16)
        a[...,0]=(np.arange(w,dtype=np.uint32)*53%65536)[None,:]
        a[...,1]=(np.arange(h,dtype=np.uint32)*71%65536)[:,None]
        a[...,2]=23456;a[...,3]=65535
        step=dict(tool='sample',version=2,params=dict(DEFAULT_SAMPLE))
        if args.fast:
            from blockstudio.editor import InteractiveSource
            start=time.perf_counter();source=InteractiveSource(a);setup=time.perf_counter()-start
        else:setup=0
        times=[]
        for offset in range(12):
            step['params']['offset_x']=offset*7
            start=time.perf_counter()
            if args.fast:q=source.render(step)
            else:q=preview(apply_tool(a,step),1600)
            times.append((time.perf_counter()-start)*1000)
        report['sizes'].append({'width':w,'height':h,'setup_ms':round(setup*1000,2),'median_ms':round(float(np.median(times)),2),'p95_ms':round(float(np.percentile(times,95)),2)})
        del a
    Path(args.output).parent.mkdir(exist_ok=True)
    Path(args.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':run()
