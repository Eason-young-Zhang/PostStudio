"""Self-contained, immutable assets; JSON scene state; atomic ZIP publication."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import threading
import uuid
import zipfile
import numpy as np
from PySide6.QtCore import Qt
from .imaging import read_image, write_tiff, thumbnail_file, downsample2, to_qimage, from_qimage
from .tools import apply_tool, TOOLS
from .metadata import read_metadata,resolved
from .resources import file_refs,safe_path,referenced_resources


def uid(): return uuid.uuid4().hex


def atomic_json(path, data):
    temp = Path(str(path) + '.tmp')
    with temp.open('w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def blank_board(name='画布 01'):
    return dict(id=uid(), name=name, items=[], frames=[])


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/'assets').mkdir(exist_ok=True)
        self.data = dict(schema=1, name='未命名项目', assets=[], boards=[blank_board()], presets=[], workflows=[])
        self.path = None
        self.lock = threading.RLock()

    def checkpoint(self):
        with self.lock: atomic_json(self.root/'manifest.json', self.data)

    def asset(self, id):
        return next(a for a in self.data['assets'] if a['id'] == id)

    def file(self, asset):
        if asset.get('file'):return self.root/asset['file']
        if asset.get('kind')!='composition':raise ValueError('图像缺少内容。')
        # Derived masters are disposable; the project stores source + card + layout.
        import hashlib
        key=hashlib.sha256((asset['id']+':'+asset.get('content_revision','initial')).encode()).hexdigest()
        cache=self.root/'cache';cache.mkdir(exist_ok=True);path=cache/(key+'.tiff')
        with self.lock:
            if not path.exists():
                from .palette_render import composite_at
                spec=asset['composition'];out=np.empty((asset['height'],asset['width'],4),np.uint16);out[:]=spec['background']
                for component in spec['components']:
                    pixels=read_image(self.file(self.asset(component['asset'])))
                    from .effects import shadow
                    shadow(out,pixels,component['x'],component['y'],component.get('shadow',{}))
                    composite_at(out,pixels,component['x'],component['y'])
                write_tiff(path,out)
        return path

    def import_image(self, path, half=False, retain=False):
        path = Path(path)
        if path.suffix.lower() not in ('.tif','.tiff','.jpg','.jpeg','.png'):
            raise ValueError('只支持 TIFF、JPEG 和 PNG。')
        a = read_image(path)
        id = uid()
        if half:
            working = downsample2(a)
            rel = f'assets/{id}.tiff'
            write_tiff(self.root/rel, working)
        else:
            working = a
            rel = f'assets/{id}{path.suffix.lower()}'
            shutil.copyfile(path, self.root/rel)
        original = None
        if half and retain:
            original = f'assets/{id}-original{path.suffix.lower()}'
            shutil.copyfile(path, self.root/original)
        thumb = f'assets/{id}-preview.png'
        thumbnail_file(self.root/thumb, working)
        asset = dict(id=id, name=path.stem + (' · ½' if half else ''), file=rel, thumb=thumb,
                     width=working.shape[1], height=working.shape[0], parent=None, root=id,
                     step=None, original=original, imported_half=half, metadata=read_metadata(path))
        with self.lock: self.data['assets'].append(asset)
        return asset

    def add_resource(self,path):
        pixels=read_image(Path(path));id=uid();rel=f'assets/{id}-resource.tiff';write_tiff(self.root/rel,pixels)
        record=dict(id=id,file=rel,name=Path(path).stem,width=pixels.shape[1],height=pixels.shape[0])
        with self.lock:self.data.setdefault('resources',[]).append(record);self.data['schema']=3
        return record

    def ensure_metadata(self,asset_id):
        root=self.asset(self.asset(asset_id)['root'])
        if 'metadata' not in root:
            source=root.get('original') or root.get('file')
            root['metadata']=read_metadata(self.root/source) if source else dict(original={},batch={},overrides={},raw={})
        return resolved(self,asset_id)

    def prepare_step(self,asset_id,step,fields=None):
        runtime=copy.deepcopy(step)
        if step['tool']=='watermark':
            asset=self.asset(asset_id);metadata=dict(fields if fields is not None else self.ensure_metadata(asset_id))
            metadata.setdefault('filename',self.asset(asset['root'])['name']);metadata.update(width=asset['width'],height=asset['height'])
            runtime['params'].update(_fields=metadata,_regions=copy.deepcopy(asset.get('regions')),
                _resources={r['id']:str(self.root/safe_path(r['file'])) for r in self.data.get('resources',[])})
        return runtime

    def execute(self, asset_id, step, fields=None):
        if step['tool'] not in TOOLS:raise ValueError('此项目需要尚未安装的工具：'+step['tool'])
        if step.get('version',1) not in range(1,TOOLS[step['tool']].version+1):raise ValueError('工具参数版本不兼容。')
        source = self.asset(asset_id)
        pixels = read_image(self.file(source))
        if step.get('version',1)>1 and step['tool']=='palette' or step.get('version',1)>2 and step['tool']=='sample':self.data['schema']=3
        if step['tool']=='palette':return self.execute_palette(source,pixels,step)
        runtime=self.prepare_step(asset_id,step,fields)
        result = apply_tool(pixels, runtime)
        region=copy.deepcopy(source.get("regions"))
        if step['tool']=='border':
            from .border import geometry
            region=geometry(source['width'],source['height'],step['params'],source_regions=source.get('regions'));self.data['schema']=3
        del pixels
        id = uid(); rel = f'assets/{id}.tiff'; thumb = f'assets/{id}-preview.png'
        write_tiff(self.root/rel, result)
        thumbnail_file(self.root/thumb, result)
        asset = dict(id=id, name=f"{source['name']} · {TOOLS[step['tool']].label}", file=rel, thumb=thumb,
                     width=result.shape[1], height=result.shape[0], parent=source['id'], root=source['root'],
                     step=copy.deepcopy(step), original=None, imported_half=False, regions=region)
        if step['tool']=='watermark':asset['metadata_snapshot']=runtime['params']['_fields'];self.data['schema']=3
        with self.lock: self.data['assets'].append(asset)
        return asset

    def revision_blocker(self,asset_id):
        from .trash import dependencies
        a=self.asset(asset_id)
        if a.get('trashed') or not a.get('step') or not a.get('parent'):return '仅已生成的工具产物可以保存修改。'
        if any(asset_id in dependencies(other) for other in self.data['assets'] if other['id']!=asset_id):
            return '该产物已有下游处理或组合引用，请生成新版本。'
        return None

    def revise_leaf(self,asset_id,step):
        """Replace a leaf's record only after rendering succeeds; old files serve undo."""
        with self.lock:
            reason=self.revision_blocker(asset_id)
            if reason:raise ValueError(reason)
            old=copy.deepcopy(self.asset(asset_id))
            if step['tool']!=old['step']['tool']:raise ValueError('只能保存最后一个工具步骤的修改。')
            before=copy.deepcopy(self.data)
            try:
                fresh=self.execute(old['parent'],step)
                replacement=copy.deepcopy(fresh)
                # A palette's private card is implementation data, not another version.
                old_parts=old.get('composition',{}).get('components',[])
                new_parts=replacement.get('composition',{}).get('components',[])
                from .trash import dependencies
                for previous,current in zip(old_parts,new_parts):
                    cid=previous['asset'];nid=current['asset']
                    if cid==old['parent'] or nid==old['parent']:continue
                    placed=any(i['asset']==cid for b in self.data['boards'] for i in b['items'])
                    placed|=any(i['asset']==cid for e in self.data.get('trash',[]) if e['kind']=='board' for i in e['board']['items'])
                    used=any(cid in dependencies(a) for a in self.data['assets'] if a['id']!=asset_id)
                    card=self.asset(cid)
                    if not placed and not used and not card.get('trashed'):
                        updated=copy.deepcopy(self.asset(nid));updated.update(id=cid,name=card['name'],content_revision=uid())
                        self.data['assets']=[updated if a['id']==cid else a for a in self.data['assets'] if a['id']!=nid]
                        current['asset']=cid
                replacement.update(id=asset_id,name=old['name'],content_revision=uid())
                self.data['assets']=[replacement if a['id']==asset_id else a for a in self.data['assets'] if a['id']!=fresh['id']]
                return replacement
            except Exception:
                self.data=before
                raise

    def execute_palette(self,source,pixels,step):
        from .palette import PaletteAnalysis
        from .palette_render import palette_params,layout,draw_card,render_palette,background,scaled_params
        p=palette_params(step.get('params',{}))
        result=PaletteAnalysis(pixels).extract(p['count'],p['mode'],p['locked'],p['colors'])
        geometry=layout(source['width'],source['height'],p)
        if geometry['width']*geometry['height']>100_000_000:raise ValueError('组合超过 100MP，请减小留边或色卡尺寸。')
        result['source']=source['id']
        stored=copy.deepcopy(step);stored['params']=p
        def make_asset(content,name,kind):
            id=uid();rel=f'assets/{id}.tiff';thumb=f'assets/{id}-preview.png'
            write_tiff(self.root/rel,content);thumbnail_file(self.root/thumb,content)
            return dict(id=id,name=name,file=rel,thumb=thumb,width=content.shape[1],height=content.shape[0],
                        parent=source['id'],root=source['root'],step=copy.deepcopy(stored),original=None,
                        imported_half=False,kind=kind,palette=copy.deepcopy(result))
        if p['output']=='palette':
            asset=make_asset(render_palette(pixels,result,p),source['name']+' · 色卡','palette')
            with self.lock:self.data['schema']=max(2,self.data['schema']);self.data['assets'].append(asset)
            return asset
        x,y,w,h=geometry['card']
        card=make_asset(draw_card(w,h,result,p),source['name']+' · 色卡组件','palette')
        # Re-editing a card creates a new standalone card, not a second composition.
        card['step']['params']['output']='palette'
        id=uid();thumb=f'assets/{id}-preview.png'
        # Only a display-size composition is needed while creating an editable group.
        from .imaging import preview
        small=from_qimage(preview(pixels,1400))
        thumbnail_file(self.root/thumb,render_palette(small,result,scaled_params(p,small.shape[1]/pixels.shape[1])))
        px,py,_,_=geometry['photo']
        asset=dict(id=id,name=source['name']+' · 配色组合',file=None,thumb=thumb,
                   width=geometry['width'],height=geometry['height'],parent=source['id'],root=source['root'],
                   step=stored,original=None,imported_half=False,kind='composition',palette=result,regions=dict(photo=([px+source['regions']['photo'][0],py+source['regions']['photo'][1],*source['regions']['photo'][2:]] if (source.get('regions') or {}).get('photo') else geometry['photo'])),
                   composition=dict(background=background(p),components=[dict(asset=source['id'],x=px,y=py,shadow=p.get('photo_shadow',{})),dict(asset=card['id'],x=x,y=y,shadow=p.get('card_shadow',{}))]))
        with self.lock:self.data['schema']=max(2,self.data['schema']);self.data['assets'].extend([card,asset])
        return asset

    def split_composition(self,record,board):
        asset=self.asset(record['asset'])
        if asset.get('kind')!='composition':raise ValueError('请选择照片与色卡组合。')
        scale=record['width']/asset['width'];items=[]
        for component in asset['composition']['components']:
            child=self.asset(component['asset'])
            item=dict(id=uid(),asset=child['id'],x=record['x']+component['x']*scale,
                      y=record['y']+component['y']*scale,width=child['width']*scale,view='single')
            items.append(item)
        board['items'].remove(record);board['items'].extend(items)
        return items

    def placement(self, asset, board, x=None, y=None, width=440.0):
        n = len(board['items'])
        x = float(x if x is not None else (n%4)*500)
        y = float(y if y is not None else (n//4)*400)
        height = width*asset['height']/asset['width']
        for _ in range(len(board['items'])+1):
            collision = None
            for existing in board['items']:
                other = self.asset(existing['asset'])
                oh = existing['width']*other['height']/other['width']
                if x < existing['x']+existing['width']+24 and x+width+24 > existing['x'] and y < existing['y']+oh+24 and y+height+24 > existing['y']:
                    collision = existing; break
            if collision is None: break
            x = collision['x']+collision['width']+40
        item = dict(id=uid(), asset=asset['id'], x=x, y=y, width=width, view='single')
        board['items'].append(item)
        return item

    def save(self, path):
        path = Path(path)
        self.checkpoint()
        with self.lock: data = copy.deepcopy(self.data)
        validate_manifest(data)
        refs = file_refs(data)
        handle, tmpname = tempfile.mkstemp(prefix='.'+path.name, suffix='.tmp', dir=path.parent)
        os.close(handle)
        temp = Path(tmpname)
        try:
            with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
                z.writestr('manifest.json', json.dumps(data, ensure_ascii=False))
                for rel in sorted(refs): z.write(self.root/rel, rel)
            with temp.open('rb') as f: os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        self.path = path

    @classmethod
    def open(cls, path, root):
        # Extract only explicit asset references; never use archive-supplied filesystem paths.
        p = cls(root)
        with zipfile.ZipFile(path) as z:
            info = z.getinfo('manifest.json')
            if info.file_size > 32*1024*1024: raise ValueError('项目清单过大。')
            data = json.loads(z.read('manifest.json'))
            validate_manifest(data)
            refs = file_refs(data)
            for rel in refs:
                dest = p.root / rel
                with z.open(rel) as src, dest.open('wb') as out: shutil.copyfileobj(src, out, 1024*1024)
        p.data = data; p.path = Path(path); p.checkpoint()
        return p

    @classmethod
    def recover(cls, root):
        p = cls(root)
        data = json.loads((p.root/'manifest.json').read_text())
        validate_manifest(data)
        for a in data['assets']:
            for key in ('file','thumb','original'):
                if a.get(key) and not (p.root/a[key]).is_file(): raise ValueError('恢复项目缺少素材文件。')
        for rel in file_refs(data):
            if not (p.root/rel).is_file():raise ValueError('恢复项目缺少资源。')
        p.data = data
        return p


def validate_manifest(data):
    if data.get('schema') not in (1,2,3): raise ValueError('项目格式版本不受支持。')
    file_refs(data)
    def validate_step(step,allow_action=False):
        if step.get('tool')=='collage':
            from .collage import validate
            if allow_action or step.get('version')!=1:raise ValueError('拼图仅支持多图编辑页。')
            validate(step['params']);return
        if 'action' in step:
            if not allow_action or step['action'] not in ('name','export'):raise ValueError('项目包含未知流程动作。')
            if step.get('version',1)!=1:raise ValueError('流程动作版本不兼容。')
        else:
            tool=TOOLS.get(step.get('tool'))
            if tool is None:raise ValueError('此项目需要尚未安装的工具：'+str(step.get('tool')))
            version=step.get('version',1)
            if not isinstance(version,int) or not 1<=version<=tool.version:raise ValueError('工具参数版本不兼容。')
        if not isinstance(step.get('params',{}),dict):raise ValueError('工具参数无效。')
    for asset in data['assets']:
        if asset.get('step'):validate_step(asset['step'])
    for preset in data.get('presets',[]):validate_step(preset['step'])
    for flow in data.get('workflows',[]):
        for step in flow['steps']:validate_step(step,True)
    resource_ids=[r['id'] for r in data.get('resources',[])]
    if len(resource_ids)!=len(set(resource_ids)):raise ValueError('资源标识重复。')
    if not referenced_resources(data).issubset(resource_ids):raise ValueError('项目缺少水印资源。')
    ids = set()
    for a in data['assets']:
        if a['id'] in ids: raise ValueError('项目存在重复图像标识。')
        ids.add(a['id'])
        for key in ('file','thumb','original'):
            if not a.get(key): continue
            path = PurePosixPath(a[key])
            if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != 'assets' or '..' in path.parts or '\\' in a[key]:
                raise ValueError('项目包含非法素材路径。')
        if not 0 < a['width'] <= 100000 or not 0 < a['height'] <= 100000: raise ValueError('图像尺寸无效。')
    for a in data['assets']:
        if a.get('parent') and a['parent'] not in ids: raise ValueError('项目缺少输入图像。')
        if a.get('root') and a['root'] not in ids:raise ValueError('项目缺少原始图像。')
    for a in data['assets']:
        if any(id not in ids for id in a.get('sources',[])):raise ValueError('拼图缺少输入图像。')
        if (a.get('step') or {}).get('tool')=='collage':
            if a.get('sources')!=[s['asset'] for s in a['step']['params']['slots']]:raise ValueError('拼图来源不一致。')
    lookup={a['id']:a for a in data['assets']}
    for a in data['assets']:
        if a.get('kind')=='composition':
            if data['schema']<2:raise ValueError('组合需要新版项目格式。')
            if a['width']*a['height']>100_000_000:raise ValueError('组合图像过大。')
            spec=a.get('composition',{})
            bg=spec.get('background',[])
            if len(bg)!=4 or not all(isinstance(v,int) and 0<=v<=65535 for v in bg):raise ValueError('组合背景无效。')
            if not spec.get('components'):raise ValueError('组合缺少组件。')
            for component in spec['components']:
                child=lookup.get(component['asset'])
                if child is None:raise ValueError('组合缺少图像。')
                x,y=component['x'],component['y']
                if not all(isinstance(v,int) and v>=0 for v in (x,y)) or x+child['width']>a['width'] or y+child['height']>a['height']:
                    raise ValueError('组合位置无效。')
        elif not a.get('file'):raise ValueError('图像缺少文件。')
    visited=set();active=set()
    def visit(id):
        if id in active:raise ValueError('项目包含循环的输入关系。')
        if id in visited:return
        active.add(id);asset=lookup[id]
        deps=[asset['parent']] if asset.get('parent') else []
        deps.extend(asset.get('sources',[]))
        deps.extend(c['asset'] for c in asset.get('composition',{}).get('components',[]))
        for dep in deps:visit(dep)
        active.remove(id);visited.add(id)
    for id in lookup:visit(id)
    if not data['boards']: raise ValueError('项目没有画布。')
    trash=data.get('trash',[])
    if trash and data['schema']<3:raise ValueError('回收站需要新版项目格式。')
    entry_ids=set()
    for entry in trash:
        if entry.get('id') in entry_ids:raise ValueError('回收记录重复。')
        entry_ids.add(entry.get('id'))
        if entry.get('kind')=='asset' and entry.get('asset') not in ids:raise ValueError('回收站引用不存在的图像。')
        if entry.get('kind') not in ('asset','board'):raise ValueError('回收记录无效。')
    for b in data['boards']+[e['board'] for e in trash if e['kind']=='board']:
        for item in b['items']:
            if item['asset'] not in ids: raise ValueError('画布引用不存在的图像。')
            if not all(np.isfinite(item[k]) for k in ('x','y','width')) or item['width'] <= 0: raise ValueError('画布位置无效。')
        for frame in b['frames']:
            if not all(np.isfinite(frame[k]) for k in ('x','y','width','height')) or min(frame['width'],frame['height']) <= 0: raise ValueError('作品框无效。')


def render_frame(project, board, frame, output_width, background=None, cancel=None):
    """Composite masters one at a time, preserving 16-bit output and layout aspect ratio."""
    width = int(output_width)
    height = max(1, round(width * frame['height']/frame['width']))
    if width*height > 100_000_000: raise ValueError('首版单次作品导出限制为 100MP，请降低输出宽度。')
    canvas = np.zeros((height,width,4), np.uint16)
    if background:
        canvas[...,:3] = [int(background[i:i+2],16)*257 for i in (1,3,5)]
        canvas[...,3] = 65535
    scale = width/frame['width']
    for item in board['items']:
        if cancel and cancel.is_set(): raise InterruptedError('已取消导出')
        asset = project.asset(item['asset'])
        iw = item['width']; ih = iw*asset['height']/asset['width']
        left = max(item['x'],frame['x']); top = max(item['y'],frame['y'])
        right = min(item['x']+iw,frame['x']+frame['width']); bottom = min(item['y']+ih,frame['y']+frame['height'])
        if right <= left or bottom <= top: continue
        x0,y0 = round((left-frame['x'])*scale),round((top-frame['y'])*scale)
        x1,y1 = min(width,round((right-frame['x'])*scale)),min(height,round((bottom-frame['y'])*scale))
        if x1<=x0 or y1<=y0: continue
        a = read_image(project.file(asset))
        sx0,sy0 = int((left-item['x'])/iw*asset['width']),int((top-item['y'])/ih*asset['height'])
        sx1,sy1 = min(asset['width'],int(np.ceil((right-item['x'])/iw*asset['width']))),min(asset['height'],int(np.ceil((bottom-item['y'])/ih*asset['height'])))
        q = to_qimage(a[sy0:sy1,sx0:sx1]); del a
        q = q.scaled(x1-x0,y1-y0,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        src = from_qimage(q); del q
        for y in range(0,y1-y0,128):
            fg=src[y:y+128].astype(np.float64)/65535
            dst=canvas[y0+y:min(y0+y+128,y1),x0:x1]
            bg=dst.astype(np.float64)/65535
            alpha=fg[...,3:4]+bg[...,3:4]*(1-fg[...,3:4])
            rgb=(fg[...,:3]*fg[...,3:4]+bg[...,:3]*bg[...,3:4]*(1-fg[...,3:4]))/np.maximum(alpha,1e-12)
            dst[...,:3]=np.clip(np.rint(rgb*65535),0,65535).astype(np.uint16)
            dst[...,3]=np.rint(alpha[...,0]*65535).astype(np.uint16)
    return canvas
