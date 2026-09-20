"""Single-chain batch executor: export and naming are actions, not pixel filters."""
import copy
import os
from pathlib import Path
from .imaging import read_image,export_image
from .watermark import expand


def node_label(node):
    if node.get('action')=='name':return '命名'
    if node.get('action')=='export':return '导出'
    from .tools import TOOLS
    return TOOLS[node['tool']].label


def safe_name(text):
    name=''.join(c for c in text if c not in '/\\:*?"<>|' and ord(c)>=32).strip('. ')[:150]
    return name or '未命名'


def preflight(project,ids,steps):
    """Inspect shared resources and per-input fields without creating any outputs."""
    from .resources import referenced_resources,safe_path
    from .tools import TOOLS
    active=[s for s in steps if s.get('enabled',True)]
    issues=[];errors=[]
    resources={r['id']:r for r in project.data.get('resources',[])}
    for resource_id in referenced_resources(active):
        r=resources.get(resource_id)
        if r is None or not (project.root/safe_path(r['file'])).is_file():errors.append('图片水印资源缺失：'+resource_id)
    for step in active:
        if step.get('action') not in (None,'name','export') or ('action' not in step and step.get('tool') not in TOOLS):errors.append('无法识别的流程节点。')
    for index,id in enumerate(ids):
        a=project.asset(id);fields={**project.ensure_metadata(id),'filename':project.asset(a['root'])['name'],'sequence':f'{index+1:03}','name':a['name']}
        for step in active:
            params=step.get('params',{});templates=[]
            if step.get('action') in ('name','export'):templates=[(params.get('template',''),params.get('missing','hide'))]
            elif step.get('tool')=='watermark':templates=[(l.get('text',''),l.get('missing','hide')) for l in params.get('layers',[]) if l.get('enabled',True) and l.get('kind','text')=='text']
            for template,policy in templates:
                _,missing=expand(template,fields,'placeholder')
                if missing:issues.append(a['name']+'：缺少 '+', '.join(dict.fromkeys(missing))+('（该张将在此节点停止）' if policy=='error' else '（按缺失字段规则处理）'))
    return dict(errors=list(dict.fromkeys(errors)),warnings=list(dict.fromkeys(issues)),inputs=len(ids),
                nodes=len(active),outputs=len(ids)*sum('action' not in s for s in active),exports=len(ids)*sum(s.get('action')=='export' for s in active))


def execute_chain(project,ids,steps,cancel=None,progress=None):
    from .project import uid
    steps=copy.deepcopy([s for s in steps if s.get('enabled',True)])
    if len(ids)>10:raise ValueError('一次最多选择 10 张输入。')
    report=dict(records=[],files=[],errors=[],warnings=[],cancelled=False,inputs=len(ids),completed=0)
    # Freeze all metadata before processing any input; templates remain unresolved in presets.
    fields=[{**project.ensure_metadata(id),'filename':project.asset(project.asset(id)['root'])['name'],'sequence':f'{i+1:03}'} for i,id in enumerate(ids)]
    total=len(ids)*len(steps);n=0
    for index,id in enumerate(ids):
        parent=id;name=project.asset(id)['name'];named=False
        for step in steps:
            if cancel is not None and cancel.is_set():report['cancelled']=True;return report
            if progress:progress(n,total,f'{index+1}/{len(ids)} · {node_label(step)}')
            try:
                action=step.get('action','tool');params=step.get('params',{})
                if action=='name':
                    text,missing=expand(params.get('template','{原文件名}-{序号}'),fields[index],params.get('missing','hide'))
                    name=safe_name(text);named=True
                    # Only this run's created assets can be named in-place; old source identity is immutable.
                    if parent!=id:project.asset(parent)['name']=name
                    else:project.data.setdefault('naming_records',[]).append(dict(source=id,name=name));project.data['schema']=3
                elif action=='export':
                    options={**dict(fmt='JPEG',quality=95,half=False,background='#ffffff',compress=True),**params.get('options',{})}
                    directory=Path(params.get('directory',''))
                    if not params.get('directory') or not directory.is_dir():raise ValueError('导出目录不存在。')
                    text,missing=expand(params.get('template') or name,dict(fields[index],name=name),params.get('missing','hide'))
                    stem=safe_name(text);ext={'JPEG':'jpg','PNG':'png','TIFF':'tiff'}[options['fmt']];path=directory/f'{stem}.{ext}';count=1
                    while path.exists():path=directory/f'{stem}-{count}.{ext}';count+=1
                    temp=directory/f'.{uid()}.{ext}'
                    try:export_image(temp,read_image(project.file(project.asset(parent))),**options);os.replace(temp,path)
                    finally:temp.unlink(missing_ok=True)
                    report['files'].append(str(path))
                else:
                    a=project.execute(parent,step,fields=fields[index]);parent=a['id']
                    if named:a['name']=name
                    report['records'].append((id,a));missing=[]
                    if step.get('tool')=='watermark':
                        for layer in params.get('layers',[]):
                            if layer.get('enabled',True) and layer.get('kind','text')=='text':
                                _,absent=expand(layer.get('text',''),fields[index],layer.get('missing','hide'));missing+=absent
                if missing:report['warnings'].append(project.asset(id)['name']+'：缺少 '+', '.join(dict.fromkeys(missing)))
            except Exception as error:
                report['errors'].append(project.asset(id)['name']+' · '+node_label(step)+'：'+str(error));break
            n+=1
        else:report['completed']+=1
    if cancel is not None and cancel.is_set():report['cancelled']=True
    return report
