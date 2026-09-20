"""Paths carried by a self-contained project, never arbitrary project-supplied paths."""
from pathlib import PurePosixPath


def safe_path(value):
    p=PurePosixPath(value)
    if p.is_absolute() or len(p.parts)!=2 or p.parts[0]!='assets' or '..' in p.parts or '\\' in value:raise ValueError('项目包含非法素材路径。')
    return value


def file_refs(data):
    refs={a[k] for a in data['assets'] for k in ('file','thumb','original') if a.get(k)}
    refs.update(r['file'] for r in data.get('resources',[]))
    return {safe_path(r) for r in refs}


def referenced_resources(value):
    refs=set()
    if isinstance(value,dict):
        if value.get('kind')=='image' and value.get('resource'):refs.add(value['resource'])
        for child in value.values():refs.update(referenced_resources(child))
    elif isinstance(value,list):
        for child in value:refs.update(referenced_resources(child))
    return refs
