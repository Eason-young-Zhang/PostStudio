"""Bounded interactive previews and exact, idle-only refinement.

Interactive geometry is integrated in source coordinates. Display pixels are
approximate (source/mask correlation is recovered by the exact idle render).
"""
from __future__ import annotations
import copy
import threading
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from .imaging import read_image, preview, from_qimage
from .tools import apply_tool, block_rect


def _axis(edges, lo=None, hi=None, period=None, size=None, offset=0):
    left=edges[:-1];right=edges[1:]
    if lo is not None:left=np.maximum(left,lo)
    if hi is not None:right=np.minimum(right,hi)
    right=np.maximum(left,right)
    if period is None:area=right-left
    else:
        def integral(x):
            t=x-offset
            return np.floor(t/period)*size+np.minimum(np.mod(t,period),size)
        area=integral(right)-integral(left)
    return np.asarray(area/np.diff(edges),np.float32)


def _union_rectangles(rectangles):
    """Disjoint horizontal slabs, so moved windows never double-count overlap."""
    if not rectangles:return
    ys=sorted({v for x,y,w,h in rectangles for v in (y,y+h)})
    for top,bottom in zip(ys,ys[1:]):
        intervals=sorted((x,x+w) for x,y,w,h in rectangles if y<bottom and y+h>top)
        merged=[]
        for left,right in intervals:
            if merged and left<=merged[-1][1]:merged[-1][1]=max(right,merged[-1][1])
            else:merged.append([left,right])
        for left,right in merged:yield left,top,right,bottom


def coverage_mask(width,height,p,out_width,out_height,bounds=None):
    """Exact area coverage of the union of integer source sampling windows."""
    ex=np.linspace(0,width,out_width+1);ey=np.linspace(0,height,out_height+1)
    if bounds:
        x0,y0,x1,y1=bounds;ex=ex[x0:x1+1];ey=ey[y0:y1+1]
    left_bound,right_bound=ex[0],ex[-1];top_bound,bottom_bound=ey[0],ey[-1]
    def visible(x,y,w,h):return x<right_bound and x+w>left_bound and y<bottom_bound and y+h>top_bound
    bx,by=p['block_x'],p['block_y'];px,py=bx+p['gap_x'],by+p['gap_y']
    ox,oy=p['offset_x'],p['offset_y']
    def regular_x(lo=None,hi=None):return _axis(ex,lo,hi,px,bx,ox)
    def regular_y(lo=None,hi=None):return _axis(ey,lo,hi,py,by,oy)
    mask=regular_y()[:,None]*regular_x()[None,:]
    originals=[];moved=[]
    for key in p.get('moved_blocks',{}):
        col,row=map(int,key.split(','));x=ox+col*px;y=oy+row*py
        if visible(x,y,bx,by):
            originals.append((x,y,x+bx,y+by))
            mask-=_axis(ey,y,y+by)[:,None]*_axis(ex,x,x+bx)[None,:]
        rect=block_rect(p,key)
        if visible(*rect):moved.append(rect)
    for left,top,right,bottom in _union_rectangles(moved):
        mask+=_axis(ey,top,bottom)[:,None]*_axis(ex,left,right)[None,:]
        mask-=regular_y(top,bottom)[:,None]*regular_x(left,right)[None,:]
        for x0,y0,x1,y1 in originals:
            l,r=max(left,x0),min(right,x1);t,b=max(top,y0),min(bottom,y1)
            if r>l and b>t:mask+=_axis(ey,t,b)[:,None]*_axis(ex,l,r)[None,:]
    return np.clip(mask,0,1)


class InteractiveSource:
    def __init__(self,pixels,edge=960):
        self.height,self.width=pixels.shape[:2];self.edge=edge
        self.image=preview(pixels,edge)
        self.pixels=pixels if max(self.width,self.height)<=self.edge else from_qimage(self.image)
        self.normal=self.pixels.astype(np.float32)/65535
        self.mask=None;self.mask_params=None;self.background_spec=None;self.background=None

    def sampling_mask(self,p):
        keys=('block_x','block_y','gap_x','gap_y','offset_x','offset_y')
        old=self.mask_params;w,h=self.image.width(),self.image.height()
        if old is None or any(old[k]!=p[k] for k in keys):
            self.mask=coverage_mask(self.width,self.height,p,w,h)
        else:
            before=old.get('moved_blocks',{});after=p.get('moved_blocks',{})
            changed=[k for k in before.keys()|after.keys() if before.get(k)!=after.get(k)]
            if len(changed)>3:self.mask=coverage_mask(self.width,self.height,p,w,h)
            else:
                for key in changed:
                    for params in (old,p):
                        x,y,rw,rh=block_rect(params,key)
                        x0=max(0,int(np.floor(x/self.width*w)));y0=max(0,int(np.floor(y/self.height*h)))
                        x1=min(w,int(np.ceil((x+rw)/self.width*w)));y1=min(h,int(np.ceil((y+rh)/self.height*h)))
                        if x1>x0 and y1>y0:
                            self.mask[y0:y1,x0:x1]=coverage_mask(self.width,self.height,p,w,h,(x0,y0,x1,y1))
        self.mask_params=copy.deepcopy(p)
        return self.mask

    def render(self,step):
        if max(self.width,self.height)<=self.edge:
            return preview(apply_tool(self.pixels,step),960)
        if step['tool']!='sample':return preview(apply_tool(self.pixels,step,self.pixels.shape[1]/self.width),960)
        from .tools import DEFAULT_SAMPLE
        p={**DEFAULT_SAMPLE,**step['params']}
        mask=self.sampling_mask(p)
        if p.get('background_spec',{}).get('kind','solid')!='solid' or p.get('shadow',{}).get('enabled'):
            from .effects import background_image,shadow,composite
            fg=self.pixels.copy();fg[...,3]=np.rint(fg[...,3]*mask).astype(np.uint16)
            spec={**p.get('background_spec',{}),'color':p['color']}
            if p['transparent']:spec['kind']='transparent'
            if self.background_spec!=spec:
                self.background=background_image(fg.shape[1],fg.shape[0],spec);self.background_spec=copy.deepcopy(spec)
            out=self.background.copy();shadow(out,fg,0,0,p.get('shadow',{}),fg.shape[1]/self.width);composite(out,fg)
            return preview(out,960)
        # Premultiplied arithmetic avoids transparent-edge darkening.
        alpha=self.normal[...,3]*mask
        rgb=self.normal[...,:3]*alpha[...,None]
        if not p['transparent']:
            bg=np.array([int(p['color'][i:i+2],16)/255 for i in (1,3,5)],np.float32)
            rgb+=(1-mask)[...,None]*bg
            alpha+=1-mask
        rgba=np.empty(self.normal.shape,np.uint8)
        rgba[...,:3]=np.clip(np.rint(rgb/np.maximum(alpha[...,None],1e-8)*255),0,255).astype(np.uint8)
        rgba[...,3]=np.rint(alpha*255).astype(np.uint8)
        return QImage(rgba.data,rgba.shape[1],rgba.shape[0],rgba.strides[0],QImage.Format.Format_RGBA8888).copy()


class PreviewWorker(QThread):
    ready=Signal(int,object)
    failed=Signal(int,str)

    def __init__(self):
        super().__init__();self.condition=threading.Condition();self.pending=None;self.stopping=False;self.source_pixels=None;self.source_path=None

    def request(self,generation,path,step,exact=False):
        with self.condition:
            self.pending=(generation,path,copy.deepcopy(step),exact)
            self.condition.notify()

    def stop(self):
        with self.condition:
            self.stopping=True;self.pending=None;self.condition.notify()

    def pick(self,x,y):
        pixels=self.source_pixels
        if pixels is None:return None
        h,w=pixels.shape[:2]
        return pixels[min(h-1,max(0,int(y*h))),min(w-1,max(0,int(x*w))),:3].tolist()

    def exact_sample(self,pixels,step):
        p=step['params']
        if p.get('background_spec',{}).get('kind','solid')!='solid' or p.get('shadow',{}).get('enabled'):
            def cancelled():
                with self.condition:return self.stopping or self.pending is not None
            runtime=copy.deepcopy(step);runtime['params']['_cancel']=cancelled
            try:return preview(apply_tool(pixels,runtime),1600)
            except InterruptedError:return None
        result=np.empty_like(pixels)
        for y in range(0,len(pixels),128):
            with self.condition:
                if self.stopping or self.pending is not None:return None
            band_step=copy.deepcopy(step);band_step['params']['offset_y']=step['params'].get('offset_y',0)-y
            result[y:y+128]=apply_tool(pixels[y:y+128],band_step)
        return preview(result,1600)

    def run(self):
        cached_path=None;pixels=None;interactive=None;effects_interactive=None;analysis=None
        while True:
            with self.condition:
                while self.pending is None and not self.stopping:self.condition.wait()
                if self.stopping:return
                generation,path,step,exact=self.pending;self.pending=None
            try:
                if path!=cached_path:
                    pixels=None;interactive=None;effects_interactive=None;analysis=None;self.source_pixels=None;self.source_path=None
                    resolved=path[0].file(path[0].asset(path[1])) if isinstance(path,tuple) else path
                    pixels=read_image(resolved);interactive=InteractiveSource(pixels);cached_path=path
                    self.source_pixels=pixels;self.source_path=path
                with self.condition:
                    if self.stopping:return
                payload={}
                if isinstance(path,tuple):step=path[0].prepare_step(path[1],step)
                if step['tool']=='palette':
                    from .palette import PaletteAnalysis
                    from .palette_render import palette_params,render_palette,layout,scaled_params
                    if analysis is None:analysis=PaletteAnalysis(pixels)
                    p=palette_params(step['params']);result=analysis.extract(p['count'],p['mode'],p['locked'],p['colors'])
                    image=preview(render_palette(interactive.pixels,result,scaled_params(p,interactive.pixels.shape[1]/pixels.shape[1])),1400)
                    payload={'palette':result,'layout':layout(pixels.shape[1],pixels.shape[0],p)}
                elif step['tool']=='watermark':
                    from .watermark import watermark
                    src=pixels if exact else interactive.pixels;factor=src.shape[1]/pixels.shape[1]
                    rendered,boxes=watermark(src,step['params'],factor,with_boxes=True);image=preview(rendered,1600)
                    from .watermark import expand
                    texts=[]
                    for layer in step['params'].get('layers',[]):
                        if layer.get('enabled',True) and layer.get('kind','text')=='text':
                            text,missing=expand(layer.get('text',''),step['params'].get('_fields',{}),layer.get('missing','hide'))
                            texts.append(text+('（缺少：'+', '.join(missing)+'）' if missing else ''))
                    payload={'watermark_boxes':[dict(index=b['index'],rect=[v/factor for v in b['rect']]) for b in boxes],
                             'watermark_text':'\n'.join(texts),'watermark_clipped':any(b['clipped'] for b in boxes)}
                elif exact and step['tool']=='sample':image=self.exact_sample(pixels,step)
                elif exact:image=preview(apply_tool(pixels,step),1600)
                else:
                    p=step['params']
                    enhanced=step['tool']=='sample' and (p.get('background_spec',{}).get('kind','solid')!='solid' or p.get('shadow',{}).get('enabled'))
                    if enhanced:
                        # Effects are costlier than coverage feedback. A separate bounded
                        # cache keeps input coordinates exact while dragging; idle rendering
                        # still uses the full source and is never derived from this preview.
                        if effects_interactive is None:effects_interactive=InteractiveSource(pixels,edge=560)
                        image=effects_interactive.render(step)
                    else:image=interactive.render(step)
                if image is None:continue
                with self.condition:
                    if self.stopping:return
                # The UI checks session + monotonically increasing displayed request.
                self.ready.emit(generation,{'image':image,'exact':exact,**payload})
            except Exception as error:
                cached_path=None;pixels=None;interactive=None;effects_interactive=None;analysis=None;self.source_pixels=None;self.source_path=None
                self.failed.emit(generation,str(error))
