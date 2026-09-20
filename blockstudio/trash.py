"""Project-local recoverable deletion with dependency closure protection."""
import copy


def upgrade(project):
    project.data['schema']=max(3,project.data['schema'])
    return project.data.setdefault('trash',[])


def remove_board(project,board_id):
    from .project import blank_board,uid
    board=next(b for b in project.data['boards'] if b['id']==board_id)
    upgrade(project).append(dict(id=uid(),kind='board',name=board['name'],board=copy.deepcopy(board)))
    project.data['boards'].remove(board)
    if not project.data['boards']:project.data['boards'].append(blank_board())


def remove_assets(project,ids):
    from .project import uid
    ids=set(ids);entries=upgrade(project)
    for asset in project.data['assets']:
        if asset['id'] not in ids or asset.get('trashed'):continue
        placements=[]
        for board in project.data['boards']:
            for index,item in enumerate(board['items']):
                if item['asset']==asset['id']:placements.append(dict(board=board['id'],index=index,item=copy.deepcopy(item)))
            board['items'][:]=[i for i in board['items'] if i['asset']!=asset['id']]
        asset['trashed']=True
        entries.append(dict(id=uid(),kind='asset',name=asset['name'],asset=asset['id'],placements=placements))


def restore(project,entry_id):
    entries=project.data.get('trash',[]);entry=next(e for e in entries if e['id']==entry_id)
    if entry['kind']=='board':
        board=copy.deepcopy(entry['board'])
        board['items']=[i for i in board['items'] if not project.asset(i['asset']).get('trashed')]
        project.data['boards'].append(board)
    else:
        project.asset(entry['asset']).pop('trashed',None)
        for p in entry['placements']:
            board=next((b for b in project.data['boards'] if b['id']==p['board']),None)
            if board and not any(i['id']==p['item']['id'] for i in board['items']):board['items'].insert(p['index'],copy.deepcopy(p['item']))
    entries.remove(entry)


def dependencies(asset):
    refs={asset[k] for k in ('parent','root') if asset.get(k) and asset[k]!=asset['id']}
    refs.update(c['asset'] for c in asset.get('composition',{}).get('components',[]))
    return refs


def purge_candidates(project):
    assets={a['id']:a for a in project.data['assets']}
    protected={a['id'] for a in assets.values() if not a.get('trashed')}
    for board in project.data['boards']:protected.update(i['asset'] for i in board['items'])
    # A deleted board remains restorable until explicitly cleared as well.
    for entry in project.data.get('trash',[]):
        if entry['kind']=='board':protected.update(i['asset'] for i in entry['board']['items'])
    queue=list(protected)
    while queue:
        for dep in dependencies(assets[queue.pop()]):
            if dep not in protected:protected.add(dep);queue.append(dep)
    return set(assets)-protected


def purge_summary(project):
    candidates=purge_candidates(project)
    live={a[k] for a in project.data['assets'] if a['id'] not in candidates for k in ('file','thumb','original') if a.get(k)}
    live.update(r['file'] for r in project.data.get('resources',[]))
    files={a[k] for a in project.data['assets'] if a['id'] in candidates for k in ('file','thumb','original') if a.get(k)}-live
    size=sum((project.root/path).stat().st_size for path in files if (project.root/path).is_file())
    return dict(count=len(candidates),bytes=size,
                releasable=[a['name'] for a in project.data['assets'] if a['id'] in candidates],
                protected=[a['name'] for a in project.data['assets'] if a.get('trashed') and a['id'] not in candidates])


def purge(project):
    candidates=purge_candidates(project)
    removed=[a for a in project.data['assets'] if a['id'] in candidates]
    project.data['assets'][:]=[a for a in project.data['assets'] if a['id'] not in candidates]
    project.data['trash'][:]=[e for e in project.data.get('trash',[]) if not(e['kind']=='asset' and e['asset'] in candidates)]
    live={a[k] for a in project.data['assets'] for k in ('file','thumb','original') if a.get(k)}
    live.update(r['file'] for r in project.data.get('resources',[]))
    for asset in removed:
        for k in ('file','thumb','original'):
            if asset.get(k) and asset[k] not in live:(project.root/asset[k]).unlink(missing_ok=True)
    return len(removed)
