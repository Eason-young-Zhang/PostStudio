"""Independent collage geometry and 16-bit rendering; all dimensions are output pixels."""
import copy
import math
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from .imaging import SRGB, to_qimage, from_qimage, read_image


def partition(slots, axis):
    if len(slots)==1:return {'slot':slots[0]}
    return dict(axis=axis,ratio=1/len(slots),a={'slot':slots[0]},b=partition(slots[1:],axis))


def template(count, name):
    slots=list(range(count))
    if name=='rows':return partition(slots,'y')
    if name=='columns':return partition(slots,'x')
    if name=='hero' and count>1:return dict(axis='x',ratio=.62,a={'slot':0},b=partition(slots[1:],'y'))
    if count<=2:return partition(slots,'x')
    cut=math.ceil(count/2)
    return dict(axis='y',ratio=.5,a=partition(slots[:cut],'x'),b=partition(slots[cut:],'x'))


def defaults(ids):
    return dict(width=2400,height=3000,background='#f1ede5',line_color='#f1ede5',line_opacity=100,
                gap=24,margins=[60,60,60,60],tree=template(len(ids),'grid'),
                slots=[dict(asset=i,fit='contain',x=50,y=50) for i in ids])


def validate(p):
    w,h=p['width'],p['height']
    if not all(isinstance(v,int) and 1<=v<=20000 for v in (w,h)) or w*h>50_000_000:
        raise ValueError('拼图输出最多 5000 万像素，单边最多 20000px。')
    if not 1<=len(p['slots'])<=10:raise ValueError('请选择 1–10 张图片。')
    if len(p['margins'])!=4 or any(not math.isfinite(v) or v<0 for v in p['margins']):raise ValueError('外框参数无效。')
    if not math.isfinite(p['gap']) or not 0<=p['gap']<=2000:raise ValueError('内框宽度无效。')
    if not 0<=p['line_opacity']<=100:raise ValueError('内框透明度无效。')
    for k in ('background','line_color'):
        if not QColor(p[k]).isValid():raise ValueError('拼图颜色无效。')
    seen=[]
    def walk(node,depth=0):
        if depth>12:raise ValueError('拼图布局过深。')
        if 'slot' in node:seen.append(node['slot']);return
        if node['axis'] not in ('x','y') or not .02<=node['ratio']<=.98:raise ValueError('分隔位置无效。')
        walk(node['a'],depth+1);walk(node['b'],depth+1)
    walk(p['tree'])
    if sorted(seen)!=list(range(len(p['slots']))):raise ValueError('拼图布局与图片数量不一致。')
    for slot in p['slots']:
        if slot['fit'] not in ('contain','cover') or not all(math.isfinite(slot[k]) and 0<=slot[k]<=100 for k in ('x','y')):
            raise ValueError('图片显示参数无效。')
    geometry(p)


def geometry(p):
    top,right,bottom,left=p['margins'];w,h=p['width'],p['height'];g=p['gap']
    cells={};lines=[];handles=[]
    def walk(node,rect,path):
        x,y,w,h=rect
        if w<1 or h<1:raise ValueError('外框或内框过宽，图片区域不足；请减小框宽或调整分隔位置。')
        if 'slot' in node:cells[node['slot']]=QRectF(x,y,w,h);return
        r=node['ratio'];axis=node['axis'];length=w if axis=='x' else h;pos=length*r
        if axis=='x':
            a=(x,y,pos-g/2,h);b=(x+pos+g/2,y,w-pos-g/2,h);line=QRectF(x+pos-g/2,y,g,h)
        else:
            a=(x,y,w,pos-g/2);b=(x,y+pos+g/2,w,h-pos-g/2);line=QRectF(x,y+pos-g/2,w,g)
        lines.append(line);handles.append((path,axis,QRectF(*rect),pos))
        walk(node['a'],a,path+('a',));walk(node['b'],b,path+('b',))
    walk(p['tree'],(left,top,w-left-right,h-top-bottom),())
    return cells,lines,handles


def image_rect(image,cell,slot):
    sw,sh=image.width(),image.height();factor=(min if slot['fit']=='contain' else max)(cell.width()/sw,cell.height()/sh)
    w,h=sw*factor,sh*factor
    return QRectF(cell.x()+(cell.width()-w)*slot['x']/100,cell.y()+(cell.height()-h)*slot['y']/100,w,h)


def paint(painter,p,load):
    cells,lines,_=geometry(p)
    painter.fillRect(QRectF(0,0,p['width'],p['height']),QColor(p['background']))
    color=QColor(p['line_color']);color.setAlphaF(p['line_opacity']/100)
    # Recursive gaps do not overlap, so T-junctions retain the same opacity.
    for line in lines:painter.fillRect(line,color)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for index,cell in cells.items():
        im=load(p['slots'][index]['asset'])
        painter.save();painter.setClipRect(cell);painter.drawImage(image_rect(im,cell,p['slots'][index]),im);painter.restore()


def render(project,p):
    validate(p)
    q=QImage(p['width'],p['height'],QImage.Format.Format_RGBA64);q.setColorSpace(SRGB)
    if q.isNull():raise ValueError('无法分配拼图图像内存。')
    painter=QPainter(q)
    try:paint(painter,p,lambda id:to_qimage(read_image(project.file(project.asset(id)))))
    finally:painter.end()
    return from_qimage(q)


def create_asset(project,p,target=None):
    from .project import uid
    from .imaging import write_tiff,thumbnail_file
    with project.lock:
        if target:
            reason=project.revision_blocker(target)
            if reason:raise ValueError(reason)
            old=project.asset(target)
            if old['step']['tool']!='collage' or sorted(old['sources'])!=sorted(s['asset'] for s in p['slots']):
                raise ValueError('保存修改仅支持原拼图的来源图像。')
        pixels=render(project,p);id=uid();rel=f'assets/{id}.tiff';thumb=f'assets/{id}.jpg'
        write_tiff(project.root/rel,pixels);thumbnail_file(project.root/thumb,pixels)
        ids=[s['asset'] for s in p['slots']]
        asset=dict(id=id,name='拼图',file=rel,thumb=thumb,width=p['width'],height=p['height'],
                   parent=ids[0],root=project.asset(ids[0]).get('root',ids[0]),sources=ids,
                   step=dict(tool='collage',version=1,params=copy.deepcopy(p)),original=None,imported_half=False)
        if target:
            old=project.asset(target);asset.update(id=target,name=old['name'],content_revision=uid())
            project.data['assets']=[asset if a['id']==target else a for a in project.data['assets']]
        else:project.data['assets'].append(asset)
        return asset
