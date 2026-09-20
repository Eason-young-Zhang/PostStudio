"""Original photographic fields and user overrides; never writes source EXIF."""
from PIL import Image,ExifTags

FIELDS={'camera':'相机型号','lens':'镜头','focal':'焦距','aperture':'光圈','shutter':'快门','iso':'感光度','date':'拍摄日期','location':'拍摄地点','film':'胶卷型号','development':'冲洗信息','scanner':'扫描设备','scan':'扫描信息','author':'作者','note':'备注'}
TAGS={'Model':'camera','LensModel':'lens','FocalLength':'focal','FNumber':'aperture','ExposureTime':'shutter','PhotographicSensitivity':'iso','ISOSpeedRatings':'iso','DateTimeOriginal':'date','Artist':'author'}


def read_metadata(path):
    fields={};raw={}
    try:
        with Image.open(path) as image:
            exif=image.getexif();tags=dict(exif)
            try:tags.update(exif.get_ifd(34665))
            except (KeyError,TypeError,ValueError):pass
            for key,value in tags.items():
                name=ExifTags.TAGS.get(key,str(key))
                if isinstance(value,(bytes,dict,tuple,list)) or len(str(value))>1000:continue
                raw[name]=str(value)
                if name not in TAGS:continue
                field=TAGS[name]
                try:
                    if field=='focal':value=f'{float(value):g} mm'
                    elif field=='aperture':value=f'f/{float(value):g}'
                    elif field=='shutter':
                        v=float(value);value=f'1/{round(1/v)} s' if 0<v<1 else f'{v:g} s'
                except (TypeError,ValueError,ZeroDivisionError):pass
                fields[field]=str(value).strip('\x00 ')
    except (OSError,ValueError,TypeError):pass
    return dict(original=fields,raw=raw,overrides={},batch={})


def resolved(project,asset_id):
    a=project.asset(asset_id);root=project.asset(a['root']);data=root.get('metadata',{})
    return {**data.get('original',{}),**data.get('batch',{}),**data.get('overrides',{}),**a.get('metadata_overrides',{})}


def update(project,ids,changes,clear=()):
    roots=list(dict.fromkeys(project.asset(i)['root'] for i in ids));key='batch' if len(roots)>1 else 'overrides'
    for root in roots:
        data=project.asset(root).setdefault('metadata',dict(original={},raw={},batch={},overrides={}))
        target=data.setdefault(key,{})
        for field in clear:target.pop(field,None)
        target.update(changes)
    project.data['schema']=3
