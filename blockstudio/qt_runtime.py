"""Keep Qt plugin discovery reliable in macOS workspaces with hidden file flags.

Some workspace managers mark every file under .venv as UF_HIDDEN. Qt's plugin
scanner excludes those files. Stage only Qt plugins in an application cache;
never change user files or global Qt settings.
"""
from pathlib import Path
import os
import shutil
import stat
import sys


def prepare_qt():
    if sys.platform != 'darwin': return
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, qVersion
    source = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    hidden = getattr(stat, 'UF_HIDDEN', 32768)
    if not any(p.stat().st_flags & hidden for p in (source/'platforms').glob('*.dylib')):
        return
    cache = Path.home()/'Library'/'Caches'/'BlockStudio'/'qt-plugins'/qVersion()
    for folder in ('platforms','imageformats','styles'):
        if not (source/folder).exists(): continue
        dest=cache/folder;dest.mkdir(parents=True,exist_ok=True)
        for lib in (source/folder).glob('*.dylib'):
            target=dest/lib.name
            if not target.exists() or target.stat().st_size!=lib.stat().st_size:
                shutil.copyfile(lib,target)
            if target.stat().st_flags & hidden: os.chflags(target,target.stat().st_flags & ~hidden)
    QCoreApplication.addLibraryPath(str(cache))
