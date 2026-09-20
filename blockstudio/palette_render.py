"""Palette layout and RGBA16 rendering. Analysis is deliberately separate."""
from __future__ import annotations
import numpy as np

DEFAULT_PALETTE=dict(count=5,mode='area',locked=[],colors=[],style='strip',proportional=False,
                     side='bottom',size=16,gap=2,margin=3,transparent=False,background='#f1ede5',
                     labels=False,output='composition')


def palette_params(params):
    p={**DEFAULT_PALETTE,**params}
    if p['style'] not in ('strip','ring') or p['side'] not in ('left','right','top','bottom'):
        raise ValueError('未知的色卡排版方式。')
    if p['output'] not in ('composition','palette'):raise ValueError('未知的色卡输出方式。')
    for k,lo,hi in [('size',4,60),('gap',0,20),('margin',0,20)]:
        p[k]=float(p[k])
        if not lo<=p[k]<=hi:raise ValueError('色卡排版参数超出范围。')
    return p


def layout(width,height,params):
    p=palette_params(params);unit=min(width,height)/100
    margin=round(unit*p['margin']);gap=round(unit*p['gap']);thick=max(1,round(unit*p['size']))
    vertical=p['side'] in ('left','right')
    if p['style']=='ring':cw=ch=max(2,thick*2)
    else:cw,ch=(thick,height) if vertical else (width,thick)
    o=p.get('layout_options',{})
    if o.get('enabled'):
        unit=1 if o.get('unit')=='px' else unit
        cw=max(1,round(o.get('card_width',0)*unit)) if o.get('card_width') else cw
        ch=max(1,round(o.get('card_height',0)*unit)) if o.get('card_height') else ch
        if p['style']=='ring' and o.get('ring_lock',True):cw=ch=max(cw,ch)
        gap=round(o.get('gap',p['gap'])*unit)
        top,right,bottom,left=[max(0,round(o.get(k,p['margin'])*unit)) for k in ('top','right','bottom','left')]
    else:top=right=bottom=left=margin
    align=o.get('align',1)/2 if o.get('enabled') else .5
    offset=round(o.get('offset',0)*unit) if o.get('enabled') else 0
    if p['output']=='palette':
        w,h=cw,ch;photo=None;card=[0,0,cw,ch]
    elif vertical:
        w=width+cw+gap;h=max(height,ch)
        photo=[cw+gap if p['side']=='left' else 0,round((h-height)*align),width,height]
        card=[0 if p['side']=='left' else width+gap,round((h-ch)*align)+offset,cw,ch]
    else:
        w=max(width,cw);h=height+ch+gap
        photo=[round((w-width)*align),ch+gap if p['side']=='top' else 0,width,height]
        card=[round((w-cw)*align)+offset,0 if p['side']=='top' else height+gap,cw,ch]
    rects=[r for r in (photo,card) if r is not None]
    minx=min(r[0] for r in rects);miny=min(r[1] for r in rects)
    w=max(r[0]+r[2] for r in rects)-minx;h=max(r[1]+r[3] for r in rects)-miny
    ow,oh=w+left+right,h+top+bottom
    if o.get('enabled'):
        mode=o.get('ratio_mode',0);ratio=width/height if mode==2 else o.get('ratio')
        if mode and ratio:
            ow=max(ow,round(oh*ratio));oh=max(oh,round(ow/ratio))
        scale=max(1,o.get('outer_scale',100)/100);ow=round(ow*scale);oh=round(oh*scale)
        # Explicit margins remain minima; extra space is distributed by content position.
        left+=round((ow-w-left-right)*o.get('position_x',50)/100)
        top+=round((oh-h-top-bottom)*o.get('position_y',50)/100)
    for rect in rects:rect[0]+=left-minx;rect[1]+=top-miny
    return dict(width=ow,height=oh,photo=photo,card=card)


def background(params):
    if params['transparent']:return [0,0,0,0]
    color=params['background']
    return [int(color[i:i+2],16)*257 for i in (1,3,5)]+[65535]


def draw_card(width,height,result,params):
    p=palette_params(params);swatches=result['swatches']
    if not swatches:raise ValueError('没有可绘制的颜色。')
    colors=np.array([s['rgb16']+[65535] for s in swatches],np.uint16)
    weights=np.array([s['weight'] for s in swatches]) if p['proportional'] else np.ones(len(colors))
    if weights.sum()<=0:weights=np.ones(len(colors))
    edges=np.cumsum(weights/weights.sum());edges[-1]=1
    out=np.zeros((height,width,4),np.uint16)
    if p['style']=='strip':
        vertical=p['side'] in ('left','right');length=height if vertical else width
        index=np.minimum(np.searchsorted(edges,(np.arange(length)+.5)/length,side='right'),len(colors)-1)
        out[:]=colors[index][:,None,:] if vertical else colors[index][None,:,:]
    else:
        # Banded antialiased boundaries retain 16-bit channel values in the interior.
        x=(np.arange(width)+.5-width/2)/(width/2)
        for y in range(0,height,128):
            yy=(np.arange(y,min(y+128,height))+.5-height/2)/(height/2)
            radius=np.sqrt(yy[:,None]**2+x[None,:]**2)
            angle=(np.arctan2(yy[:,None],x[None,:])+np.pi/2)%(2*np.pi)/(2*np.pi)
            indices=np.minimum(np.searchsorted(edges,angle,side='right'),len(colors)-1)
            out[y:y+len(yy)]=colors[indices]
            feather=2/min(width,height)
            alpha=np.clip((1-radius)/feather+.5,0,1)*np.clip((radius-.56)/feather+.5,0,1)
            out[y:y+len(yy),:,3]=np.rint(alpha*65535).astype(np.uint16)
    if p['labels']:
        from PySide6.QtCore import Qt,QRectF
        from PySide6.QtGui import QPainter,QColor,QFont
        from .imaging import to_qimage,from_qimage
        q=to_qimage(out);paint=QPainter(q)
        font=QFont('Helvetica Neue');font.setPixelSize(max(8,round(min(width,height)*(.18 if p['style']=='strip' else .035))));paint.setFont(font)
        start=0.
        for i,end in enumerate(edges):
            text=swatches[i]['hex']+'  '+f"{swatches[i]['weight']:.0%}"
            c=np.array(swatches[i]['rgb16'])/65535
            paint.setPen(QColor('#181818' if c@np.array([.2126,.7152,.0722])>.55 else '#ffffff'))
            if p['style']=='strip':
                r=QRectF(0,start*height,width,(end-start)*height) if vertical else QRectF(start*width,0,(end-start)*width,height)
            else:
                angle=(start+end)*np.pi-np.pi/2;cx=width/2+np.cos(angle)*width*.39;cy=height/2+np.sin(angle)*height*.39
                r=QRectF(cx-width*.16,cy-height*.04,width*.32,height*.08)
            if paint.fontMetrics().horizontalAdvance(text)<r.width()-4 and r.height()>paint.fontMetrics().height():
                paint.drawText(r,Qt.AlignmentFlag.AlignCenter,text)
            start=end
        paint.end();out=from_qimage(q)
    return out


def composite_at(out,source,x,y):
    """Straight alpha source-over, bounded temporary allocations."""
    h,w=source.shape[:2]
    for offset in range(0,h,128):
        src=source[offset:offset+128];dst=out[y+offset:y+offset+len(src),x:x+w]
        fg=src.astype(np.float32)/65535;bg=dst.astype(np.float32)/65535
        alpha=fg[...,3:4]+bg[...,3:4]*(1-fg[...,3:4])
        rgb=(fg[...,:3]*fg[...,3:4]+bg[...,:3]*bg[...,3:4]*(1-fg[...,3:4]))/np.maximum(alpha,1e-8)
        dst[...,:3]=np.clip(np.rint(rgb*65535),0,65535).astype(np.uint16)
        dst[...,3]=np.rint(alpha[...,0]*65535).astype(np.uint16)


def render_palette(pixels,result,params):
    p=palette_params(params);geometry=layout(pixels.shape[1],pixels.shape[0],p)
    if geometry['width']*geometry['height']>100_000_000:raise ValueError('组合超过 100MP，请减小留边或色卡尺寸。')
    out=np.empty((geometry['height'],geometry['width'],4),np.uint16);out[:]=background(p)
    if geometry['photo']:
        x,y,_,_=geometry['photo']
        from .effects import shadow
        shadow(out,pixels,x,y,p.get('photo_shadow',{}));composite_at(out,pixels,x,y)
    x,y,w,h=geometry['card'];card=draw_card(w,h,result,p)
    from .effects import shadow
    shadow(out,card,x,y,p.get('card_shadow',{}));composite_at(out,card,x,y)
    return out


def apply_palette(pixels,params,scale=1.0):
    from .palette import PaletteAnalysis
    p=palette_params(params)
    result=PaletteAnalysis(pixels).extract(p['count'],p['mode'],p['locked'],p['colors'])
    return render_palette(pixels,result,p)


def scaled_params(params,scale):
    import copy
    p=copy.deepcopy(params);o=p.get('layout_options',{})
    if o.get('unit')=='px':
        for key in ('top','right','bottom','left','gap','card_width','card_height','offset'):
            if key in o:o[key]*=scale
    for key in ('photo_shadow','card_shadow'):
        shadow=p.get(key,{})
        if shadow.get('unit','px')=='px':
            for k in ('x','y','blur'):
                if k in shadow:shadow[k]*=scale
    return p
