"""Metadata-aware, layered RGBA16 watermarks. Runtime context is not serialized."""
import copy
import re
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QFont,QFontMetricsF,QTransform,QPainterPath,QPen,QColor
from .imaging import from_qimage,to_qimage,read_image
from .effects import composite,shadow
from .metadata import FIELDS

DEFAULT_MARK=dict(name='签名',kind='text',enabled=True,text='{作者}',resource=None,font='Helvetica Neue',bold=False,
 size=2.5,unit='percent',width=35.,anchor=8,x=-2.,y=-2.,reference='image',color='#ffffff',opacity=85.,
 blend='normal',rotation=0.,align='left',spacing=0.,line_height=120.,missing='hide',stroke=0.,stroke_color='#18212b',shadow={})
DEFAULT_WATERMARK=dict(layers=[copy.deepcopy(DEFAULT_MARK)])
ALIASES={label:key for key,label in FIELDS.items()};ALIASES.update({'ISO':'iso','原文件名':'filename','序号':'sequence'})


def expand(text,fields,missing='hide'):
    absent=[]
    def replace(match):
        name=match[1];key=ALIASES.get(name,name);value=fields.get(key)
        if value is None or value=='':
            absent.append(name);return '—' if missing=='placeholder' else '\x00'
        return str(value)
    result=re.sub(r'\{([^{}]+)\}',replace,text)
    if absent and missing=='error':raise ValueError('缺少字段：'+', '.join(dict.fromkeys(absent)))
    if missing=='hide':
        lines=[]
        for line in result.splitlines():
            # Remove only delimited fragments carrying a missing field; free text survives.
            fragments=re.split(r'\s*[·|｜]\s*',line)
            fragments=[re.sub(r'\s*\x00\s*','',v).strip() for v in fragments if '\x00' not in v or len(fragments)==1]
            joined=' · '.join(v for v in fragments if v)
            if joined:lines.append(joined)
        result='\n'.join(lines)
    return result,absent


def reference_rect(width,height,p,scale=1.):
    region=p.get('_regions') or {};ref=p.get('reference','image')
    if ref=='image':return [0,0,width,height]
    photo=region.get('photo')
    if not photo:raise ValueError('此输入没有可用的照片／边框区域，请选择整张图像定位。')
    x,y,w,h=[round(v*scale) for v in photo]
    if ref=='photo':return [x,y,w,h]
    if ref=='bottom':
        if y+h>=height:raise ValueError('此输入没有下边框区域。')
        return [0,y+h,width,height-y-h]
    return [0,0,width,height]


def text_image(text,p,size,max_width):
    font=QFont(p['font']);font.setBold(p['bold']);font.setPixelSize(max(1,round(size)));font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,p['spacing']*size/100)
    metrics=QFontMetricsF(font);lines=[]
    for paragraph in text.split('\n'):
        line=''
        for char in paragraph:
            if line and metrics.horizontalAdvance(line+char)>max_width:lines.append(line);line=char
            else:line+=char
        lines.append(line)
    lineheight=metrics.height()*p['line_height']/100
    stroke=max(0,p['stroke']*size/100);pad=max(2,int(stroke+2))
    width=max(1,int(max((metrics.horizontalAdvance(l) for l in lines),default=0)+pad*2+1));height=max(1,int(lineheight*len(lines)+pad*2+1))
    if width*height>16_000_000:raise ValueError('水印文字区域过大，请减小字号或文字长度。')
    q=QImage(width,height,QImage.Format.Format_RGBA64);q.fill(Qt.GlobalColor.transparent);paint=QPainter(q);paint.setRenderHint(QPainter.RenderHint.Antialiasing);paint.setFont(font)
    for i,line in enumerate(lines):
        length=metrics.horizontalAdvance(line);x=pad if p['align']=='left' else width-pad-length if p['align']=='right' else (width-length)/2
        path=QPainterPath();path.addText(QPointF(x,pad+metrics.ascent()+i*lineheight),font,line)
        if stroke:paint.setPen(QPen(QColor(p['stroke_color']),stroke*2));paint.setBrush(QColor(p['color']));paint.drawPath(path)
        else:paint.fillPath(path,QColor(p['color']))
    paint.end();return from_qimage(q)


def watermark(pixels,params,scale=1.,with_boxes=False):
    out=pixels.copy();h,w=out.shape[:2];boxes=[]
    fields=params.get('_fields',{});resources=params.get('_resources',{})
    for index,raw in enumerate(params.get('layers',[])):
        p={**DEFAULT_MARK,**raw,'_regions':params.get('_regions')}
        if not p['enabled']:continue
        rx,ry,rw,rh=reference_rect(w,h,p,scale);unit=min(rw,rh)/100 if p['unit']=='percent' else scale
        max_width=max(1,round(rw*p['width']/100))
        if p['kind']=='text':
            text,_=expand(p['text'],fields,p['missing'])
            if not text.strip():continue
            fg=text_image(text,p,max(1,p['size']*unit),max_width)
        else:
            resource=resources.get(p['resource'])
            if not resource:raise ValueError('图片水印资源缺失，请重新导入。')
            fg=read_image(resource)
            if max_width*max_width*fg.shape[0]/max(1,fg.shape[1])>16_000_000:raise ValueError('图片水印过大，请减小水印宽度。')
            q=to_qimage(fg);q=q.scaledToWidth(max_width,Qt.TransformationMode.SmoothTransformation);fg=from_qimage(q)
        if p['rotation']:
            fg=from_qimage(to_qimage(fg).transformed(QTransform().rotate(p['rotation']),Qt.TransformationMode.SmoothTransformation))
        fh,fw=fg.shape[:2];anchor=int(p['anchor']);x=round(rx+(rw-fw)*(anchor%3)/2+p['x']*unit);y=round(ry+(rh-fh)*(anchor//3)/2+p['y']*unit)
        fg[...,3]=np.rint(fg[...,3]*np.clip(p['opacity']/100,0,1)).astype(np.uint16)
        shadow(out,fg,x,y,p['shadow'],scale);composite(out,fg,x,y,p['blend']);boxes.append(dict(index=index,rect=[x,y,fw,fh],clipped=x<0 or y<0 or x+fw>w or y+fh>h))
    return (out,boxes) if with_boxes else out
