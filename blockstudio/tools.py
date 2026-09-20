"""Tool registry: each operation receives an image and JSON-compatible parameters."""
from dataclasses import dataclass
from typing import Callable
import numpy as np
from .watermark import watermark,DEFAULT_WATERMARK
from .border import border,DEFAULT_BORDER
from .palette_render import DEFAULT_PALETTE,apply_palette

DEFAULT_SAMPLE = dict(block_x=64, block_y=64, gap_x=64, gap_y=64, offset_x=0, offset_y=0, transparent=True, color='#f1ede5', moved_blocks={})


def sample(a, p, scale=1.0):
    h, w = a.shape[:2]
    bx, by = max(1, int(p['block_x'])), max(1, int(p['block_y']))
    gx, gy = max(0, int(p['gap_x'])), max(0, int(p['gap_y']))
    # Preview samples use coordinates in the original working image, not preview pixels.
    x = (np.arange(w) + .5) / scale
    y = (np.arange(h) + .5) / scale
    keep_x = ((x - int(p['offset_x'])) % (bx + gx)) < bx
    keep_y = ((y - int(p['offset_y'])) % (by + gy)) < by
    moves=p.get('moved_blocks',{})
    mask=None
    if moves:
        mask=keep_y[:,None] & keep_x[None,:]
        rects=[]
        for key,delta in moves.items():
            col,row=map(int,key.split(','));dx,dy=map(int,delta)
            left=int(p['offset_x'])+col*(bx+gx);top=int(p['offset_y'])+row*(by+gy)
            original=(x>=left)&(x<left+bx)
            rows=(y>=top)&(y<top+by)
            mask[np.ix_(rows,original)]=False
            rects.append((left+dx,top+dy))
        for left,top in rects:
            columns=(x>=left)&(x<left+bx);rows=(y>=top)&(y<top+by)
            mask[np.ix_(rows,columns)]=True
    cancel=p.get('_cancel')
    enhanced=p.get('background_spec',{}).get('kind','solid')!='solid' or p.get('shadow',{}).get('enabled')
    if enhanced:
        from .effects import background_image,shadow,composite
        foreground=a.copy()
        for row in range(0,h,128):
            if cancel and cancel():raise InterruptedError()
            band=mask[row:row+128] if mask is not None else keep_y[row:row+128,None]&keep_x[None,:]
            foreground[row:row+128, :,3][~band]=0
        spec={**p.get('background_spec',{}),'color':p['color']}
        if p['transparent']:spec['kind']='transparent'
        out=background_image(w,h,spec,cancel);shadow(out,foreground,0,0,p.get('shadow',{}),scale,cancel);composite(out,foreground,cancel=cancel)
    else:
        out=a.copy();color=[int(p['color'][i:i+2],16)*257 for i in (1,3,5)]
        bg=np.array([0,0,0,0] if p['transparent'] else color+[65535],np.uint16)
        for row in range(0,h,128):
            if cancel and cancel():raise InterruptedError()
            band=mask[row:row+128] if mask is not None else keep_y[row:row+128,None]&keep_x[None,:]
            out[row:row+128][~band]=bg
    return out


def invert(a, p, scale=1.0):
    out = a.copy()
    out[..., :3] = 65535 - out[..., :3]
    return out


@dataclass(frozen=True)
class Tool:
    id: str
    label: str
    apply: Callable
    defaults: dict
    version: int = 1


TOOLS = {
    'sample': Tool('sample', '分块取样', sample, DEFAULT_SAMPLE, version=3),
    'watermark': Tool('watermark','水印',watermark,DEFAULT_WATERMARK),
    'border': Tool('border','边框',border,DEFAULT_BORDER,version=2),
    'invert': Tool('invert', '反转色', invert, {}),
    'palette': Tool('palette', '配色提取', apply_palette, DEFAULT_PALETTE, version=2),
}


def apply_tool(a, step, scale=1.0):
    if step['tool'] not in TOOLS: raise ValueError('此项目需要尚未安装的工具：'+step['tool'])
    tool = TOOLS[step['tool']]
    if step.get('version', 1) not in range(1,tool.version+1): raise ValueError('工具参数版本不兼容。')
    return tool.apply(a, {**tool.defaults, **step.get('params', {})}, scale)


def resolve_input(project, selected_id, tool_id, append=False):
    """Resolve an editor session once; canvas result selection cannot change its input.

    Older 0.1 results did not distinguish editing from appending. Consecutive
    unmarked copies of the same tool are treated as the old accidental reapply
    chain. Explicit append steps in new projects remain intentional boundaries.
    """
    selected = project.asset(selected_id)
    step = selected.get('step')
    if append or not step or step['tool'] != tool_id:
        return selected_id, None
    source = project.asset(selected['parent'])
    if 'intent' not in step:
        seen = {selected_id}
        while source.get('step') and source['step']['tool'] == tool_id and 'intent' not in source['step']:
            if source['id'] in seen: raise ValueError('项目包含循环的输入关系。')
            seen.add(source['id'])
            source = project.asset(source['parent'])
    return source['id'], step


def block_at(p, x, y):
    """Hit a moved sampling window first, then a regular grid window."""
    bx,by=p['block_x'],p['block_y'];px,py=bx+p['gap_x'],by+p['gap_y']
    ox,oy=p['offset_x'],p['offset_y'];moves=p.get('moved_blocks',{})
    for key,(dx,dy) in reversed(list(moves.items())):
        col,row=map(int,key.split(','));left=ox+col*px+dx;top=oy+row*py+dy
        if left<=x<left+bx and top<=y<top+by:return key
    col=int((x-ox)//px);row=int((y-oy)//py);key=f'{col},{row}'
    if key not in moves and ox+col*px<=x<ox+col*px+bx and oy+row*py<=y<oy+row*py+by:return key
    return None


def block_rect(p,key):
    col,row=map(int,key.split(','));dx,dy=p.get('moved_blocks',{}).get(key,(0,0))
    return (p['offset_x']+col*(p['block_x']+p['gap_x'])+dx,
            p['offset_y']+row*(p['block_y']+p['gap_y'])+dy,p['block_x'],p['block_y'])
