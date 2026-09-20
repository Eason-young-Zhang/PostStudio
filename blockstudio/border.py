"""Layered border geometry. Originals are never resampled."""
import copy
import math
import numpy as np
from .effects import background_image,composite,shadow

DEFAULT_LAYER=dict(mode='outer',unit='percent',top=3.,right=3.,bottom=3.,left=3.,radius=0.,
                   background=dict(kind='solid',color='#f1ede5'),opacity=100.,shadow={},enabled=True,
                   ratio_mode=0,ratio=None,outer_scale=100.,position_x=50.,position_y=50.,style='fill',stroke=1.)
DEFAULT_BORDER=dict(layers=[copy.deepcopy(DEFAULT_LAYER)])


def layer_geometry(width,height,p,scale=1.):
    unit=min(width,height)/100 if p['unit']=='percent' else scale
    t,r,b,l=[max(0,round(p[k]*unit)) for k in ('top','right','bottom','left')]
    if p['mode']=='outer':
        ow,oh=width+l+r,height+t+b;ratio=width/height if p['ratio_mode']==2 else p.get('ratio')
        if p['ratio_mode']==3 and (not isinstance(ratio,(int,float)) or not math.isfinite(ratio) or ratio<=0):raise ValueError('外框比例必须是正数。')
        if p['ratio_mode'] and ratio:
            ow=max(ow,round(oh*ratio));oh=max(oh,round(ow/ratio))
        factor=max(1,p['outer_scale']/100);ow=round(ow*factor);oh=round(oh*factor)
        l+=round((ow-width-l-r)*p['position_x']/100);t+=round((oh-height-t-b)*p['position_y']/100)
        opening=[l,t,width,height]
    else:
        ow,oh=width,height
        if l+r>=width or t+b>=height:raise ValueError('内遮边框必须保留有效开口。')
        opening=[l,t,width-l-r,height-t-b]
    if ow*oh>100_000_000:raise ValueError('边框输出超过 100MP，请减小尺寸。')
    return dict(size=[ow,oh],opening=opening,mode=p['mode'],unit=unit)


def geometry(width,height,params,scale=1.,source_regions=None):
    import copy
    photo=copy.deepcopy(source_regions.get('photo')) if source_regions is not None else [0,0,width,height]
    frames=[]
    for raw in params.get('layers',[]):
        p={**DEFAULT_LAYER,**raw}
        if not p['enabled']:continue
        g=layer_geometry(width,height,p,scale);width,height=g['size']
        if p['mode']=='outer':
            dx,dy=g['opening'][:2]
            if photo is not None:photo[0]+=dx;photo[1]+=dy
            for frame in frames:
                frame['opening'][0]+=dx;frame['opening'][1]+=dy
        elif photo is not None:
            # Only the still-visible photo is a reliable caption reference.
            x,y,w,h=g['opening'];px,py,pw,ph=photo
            left,top=max(x,px),max(y,py);right,bottom=min(x+w,px+pw),min(y+h,py+ph)
            photo=[left,top,right-left,bottom-top] if right>left and bottom>top else None
        frames.append(g)
    return dict(width=width,height=height,photo=photo,frames=frames)


def rounded_mask(width,height,radius):
    radius=min(max(0,radius),width/2,height/2)
    if not radius:return np.ones((height,width),np.float32)
    xs=np.abs(np.arange(width)+.5-width/2)-(width/2-radius)
    out=np.empty((height,width),np.float32)
    for y in range(0,height,128):
        ys=np.abs(np.arange(y,min(y+128,height))+.5-height/2)-(height/2-radius)
        distance=np.sqrt(np.maximum(xs[None,:],0)**2+np.maximum(ys[:,None],0)**2)-radius
        out[y:y+len(ys)]=np.clip(.5-distance,0,1)
    return out


def border(pixels,params,scale=1.):
    geometry(pixels.shape[1],pixels.shape[0],params,scale)
    out=pixels.copy()
    for raw in params.get('layers',[]):
        p={**DEFAULT_LAYER,**raw}
        if not p['enabled']:continue
        h,w=out.shape[:2];g=layer_geometry(w,h,p,scale);ow,oh=g['size'];l,t,iw,ih=g['opening'];unit=g['unit']
        frame=background_image(ow,oh,p['background']);coverage=rounded_mask(ow,oh,p['radius']*unit)
        if p['style']=='stroke':
            stroke=max(1,round(p['stroke']*unit))
            if stroke*2<min(ow,oh):coverage[stroke:oh-stroke,stroke:ow-stroke]*=1-rounded_mask(ow-stroke*2,oh-stroke*2,max(0,p['radius']*unit-stroke))
        if p['mode']=='inner':
            coverage[t:t+ih,l:l+iw]*=1-rounded_mask(iw,ih,p['radius']*unit)
        frame[...,3]=np.rint(frame[...,3]*coverage*np.clip(p['opacity']/100,0,1)).astype(np.uint16)
        if p['mode']=='outer':shadow(frame,out,l,t,p['shadow'],scale);composite(frame,out,l,t);out=frame
        else:shadow(out,frame,0,0,p['shadow'],scale);composite(out,frame)
    return out
