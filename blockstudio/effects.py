"""Shared RGBA16 backgrounds and shadows, independent of editor state."""
import numpy as np
from .palette import srgb_to_oklab,oklab_to_srgb

DEFAULT_SHADOW=dict(enabled=False,color='#101923',opacity=25.,blur=12.,x=0.,y=6.,unit='px')
DEFAULT_BACKGROUND=dict(kind='solid',color='#f1ede5',angle=90.,cx=50.,cy=50.,radius=70.,
                        stops=[dict(position=0.,color='#edf2f6',alpha=100.),dict(position=100.,color='#6f8ba1',alpha=100.)])


def rgba(color,alpha=65535):return [int(color[i:i+2],16)*257 for i in (1,3,5)]+[int(alpha)]


def background_image(width,height,spec,cancel=None):
    if width*height>100_000_000:raise ValueError('输出超过 100MP，请减小尺寸。')
    p={**DEFAULT_BACKGROUND,**spec};out=np.empty((height,width,4),np.uint16)
    if p['kind']=='transparent':out[:]=0;return out
    if p['kind']=='solid':out[:]=rgba(p['color']);return out
    stops=sorted(p['stops'],key=lambda s:s['position'])
    if len(stops)<2:raise ValueError('渐变至少需要两个色标。')
    positions=np.array([s['position']/100 for s in stops]);colors=srgb_to_oklab(np.array([rgba(s['color'])[:3] for s in stops])/65535)
    alphas=np.array([s.get('alpha',100)/100 for s in stops]);angle=np.deg2rad(p['angle'])
    xs=(np.arange(width)+.5)/width
    for top in range(0,height,128):
        if cancel and cancel():raise InterruptedError()
        ys=(np.arange(top,min(height,top+128))+.5)/height
        if p['kind']=='radial':
            t=np.sqrt((xs[None,:]-p['cx']/100)**2+(ys[:,None]-p['cy']/100)**2)/max(.001,p['radius']/100)
        else:
            denom=max(abs(np.cos(angle))+abs(np.sin(angle)),1e-6)
            t=.5+((xs[None,:]-.5)*np.cos(angle)+(ys[:,None]-.5)*np.sin(angle))/denom
        t=np.clip(t,0,1);alpha=np.interp(t,positions,alphas)
        lab=np.stack([np.interp(t,positions,colors[:,i]*alphas)/np.maximum(alpha,1e-12) for i in range(3)],axis=-1)
        out[top:top+len(ys),:,:3]=np.rint(np.clip(oklab_to_srgb(lab),0,1)*65535).astype(np.uint16)
        out[top:top+len(ys),:,3]=np.rint(alpha*65535).astype(np.uint16)
    return out


def composite(out,source,x=0,y=0,mode='normal',opacity=1.,cancel=None):
    x,y=int(x),int(y);h,w=source.shape[:2];oh,ow=out.shape[:2]
    x0,y0=max(0,x),max(0,y);x1,y1=min(ow,x+w),min(oh,y+h)
    if x1<=x0 or y1<=y0:return
    for top in range(y0,y1,128):
        if cancel and cancel():raise InterruptedError()
        end=min(top+128,y1);dst=out[top:end,x0:x1]
        fg=source[top-y:end-y,x0-x:x1-x].astype(np.float32)/65535;bg=dst.astype(np.float32)/65535
        f,b=fg[...,:3],bg[...,:3];fa=fg[...,3:4]*opacity;ba=bg[...,3:4]
        blend=f
        if mode=='multiply':blend=f*b
        elif mode=='screen':blend=1-(1-f)*(1-b)
        elif mode=='overlay':blend=np.where(b<=.5,2*f*b,1-2*(1-f)*(1-b))
        elif mode=='difference':blend=np.abs(b-f)
        elif mode=='softlight':
            d=np.where(b<=.25,((16*b-12)*b+4)*b,np.sqrt(b))
            blend=np.where(f<=.5,b-(1-2*f)*b*(1-b),b+(2*f-1)*(d-b))
        alpha=fa+ba*(1-fa)
        rgb=(fa*((1-ba)*f+ba*blend)+ba*(1-fa)*b)/np.maximum(alpha,1e-10)
        dst[...,:3]=np.rint(np.clip(rgb,0,1)*65535).astype(np.uint16);dst[...,3]=np.rint(alpha[...,0]*65535).astype(np.uint16)


def _box(a,radius,axis,cancel=None):
    if radius<1:return a
    result=np.empty_like(a)
    # Bound float64 prefix sums to a stripe; never allocate a full-image sum.
    other=1-axis
    for start in range(0,a.shape[other],128):
        if cancel and cancel():raise InterruptedError()
        region=[slice(None),slice(None)];region[other]=slice(start,start+128)
        part=a[tuple(region)];pad=[(0,0)]*2;pad[axis]=(radius,radius)
        padded=np.pad(part,pad);prefix=np.cumsum(padded,axis=axis,dtype=np.float64)
        shape=list(prefix.shape);shape[axis]=1;prefix=np.concatenate([np.zeros(shape),prefix],axis=axis)
        first=[slice(None)]*2;last=first.copy();first[axis]=slice(0,part.shape[axis]);last[axis]=slice(2*radius+1,2*radius+1+part.shape[axis])
        result[tuple(region)]=(prefix[tuple(last)]-prefix[tuple(first)])/(2*radius+1)
    return result


def shadow(out,source,x,y,spec,scale=1.,cancel=None):
    p={**DEFAULT_SHADOW,**(spec or {})}
    if not p['enabled']:return
    unit=min(out.shape[:2])/100 if p['unit']=='percent' else scale
    blur=max(0,float(p['blur'])*unit);radius=int(round(blur/2));pad=radius*3+2
    if (source.shape[0]+2*pad)*(source.shape[1]+2*pad)>110_000_000:
        raise ValueError('阴影中间尺寸过大，请减小模糊或输出尺寸。')
    alpha=np.pad(source[...,3].astype(np.float32)/65535,pad)
    for _ in range(3):alpha=_box(_box(alpha,radius,0,cancel),radius,1,cancel)
    # Only an alpha field and small row bands are needed, not a full shadow RGBA master.
    color=rgba(p['color']);sx=int(round(x+p['x']*unit))-pad;sy=int(round(y+p['y']*unit))-pad
    for top in range(0,len(alpha),128):
        if cancel and cancel():raise InterruptedError()
        band=alpha[top:top+128];rgba_band=np.empty((*band.shape,4),np.uint16);rgba_band[:]=color
        rgba_band[...,3]=np.rint(np.clip(band*p['opacity']/100,0,1)*65535).astype(np.uint16)
        composite(out,rgba_band,sx,sy+top)
