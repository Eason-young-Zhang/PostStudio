"""Native Qt exercise with licensed landscape fixture; never reads private photos."""
import json
import resource
import tempfile
import time
from pathlib import Path
import numpy as np
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from blockstudio.app import Window,STYLE
from blockstudio.widgets import Preview
from blockstudio.imaging import read_image,export_image

app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
report={'platform':app.platformName(),'fixture':'Fronalpstock, Hannes Röst, CC BY-SA 3.0; 10109 × 4542 JPEG',
        'latency_definition':'Qt input dispatch to widget paint completion, not physical display presentation','measurements':{}}
output=Path('artifacts/v04');output.mkdir(exist_ok=True)

def wait_until(predicate,timeout=30):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>end:
            print('Preview diagnostic:',w.preview_status.text(),w.preview_generation,w.preview_displayed,flush=True)
            w.stop_preview()
            for worker in w.retiring_workers:worker.wait(10000)
            raise RuntimeError('UI validation timeout')
        app.processEvents();time.sleep(.005)

def measure(name,fn):
    start=time.perf_counter();value=fn();report['measurements'][name]=round(time.perf_counter()-start,3);return value

with tempfile.TemporaryDirectory(prefix='blockstudio-validation-') as temp:
    input_times={};geometry=[];images=[];seen=set();original_paint=Preview.paintEvent
    def paint(widget,event):
        original_paint(widget,event)
        if widget is not w.panel.preview:return
        now=time.perf_counter();g=w.preview_generation
        if ('geometry',g) not in seen and g in input_times:
            geometry.append((now-input_times[g])*1000);seen.add(('geometry',g))
        g=w.preview_displayed
        if ('image',g) not in seen and g in input_times:
            images.append((now-input_times[g])*1000);seen.add(('image',g))
    Preview.paintEvent=paint
    w=Window(Path(temp)/'sessions');w.show();w.raise_();w.activateWindow();app.processEvents()
    source=measure('import_45_9mp_seconds',lambda:w.project.import_image(Path('artifacts/fixtures/Fronalpstock_big.jpg')))
    record=w.project.placement(source,w.board);w.refresh_all([record['id']]);w.fit()
    measure('enter_sample_to_first_frame_seconds',lambda:(w.open_tool(tool_id='sample'),wait_until(lambda:not w.panel.preview.image.isNull())))
    wait_until(lambda:w.preview_exact)
    w.panel.shadow_controls.setChecked(True)
    w.panel.background_controls.kind.setCurrentIndex(1)
    wait_until(lambda:w.preview_exact and w.preview_displayed==w.preview_generation)
    index=[0]
    def tick():
        index[0]+=1;w.panel.spins['offset_x'].setValue(index[0]*3);input_times[w.preview_generation]=time.perf_counter()
    timer=QTimer();timer.setInterval(24);timer.timeout.connect(tick);timer.start()
    start=time.monotonic()
    while time.monotonic()-start<10:app.processEvents();time.sleep(.002)
    timer.stop();wait_until(lambda:w.preview_exact and w.preview_displayed==w.preview_generation)
    Preview.paintEvent=original_paint
    report['interaction']={'duration_seconds':10,'input_count':index[0],'painted_image_count':len(images),
                           'geometry_p95_ms':round(float(np.percentile(geometry,95)),2) if geometry else None,'image_p95_ms':round(float(np.percentile(images,95)),2) if images else None}
    w.grab().save(str(output/'sample-v03.png'));w.leave_editor();w.open_tool(tool_id='palette')
    measure('palette_first_preview_seconds',lambda:wait_until(lambda:bool(w.panel.palette.swatches)))
    wait_until(lambda:w.preview_displayed==w.preview_generation and w.preview_exact)
    w.grab().save(str(output/'palette-v03.png'))
    w.panel.palette.style.setCurrentIndex(1);w.panel.palette.side.setCurrentIndex(3)
    wait_until(lambda:w.preview_displayed==w.preview_generation and w.preview_exact)
    w.grab().save(str(output/'palette-ring-v03.png'))
    w.panel.palette.style.setCurrentIndex(0);w.panel.palette.side.setCurrentIndex(0)
    measure('palette_commit_seconds',lambda:(w.apply_current(),wait_until(lambda:w.job is None,60)))
    combined=w.project.data['assets'][-1]
    assert combined['kind']=='composition'
    measure('composition_materialize_seconds',lambda:read_image(w.project.file(combined)))
    measure('composition_export_seconds',lambda:export_image(output/'palette-example.jpg',read_image(w.project.file(combined))))
    measure('project_save_seconds',lambda:w.project.save(output/'palette-demo.blockproj'))
    w.grab().save(str(output/'workspace-v03.png'))
    # Many items exercise the same 42-photo count, using repeated licensed fixture.
    for _ in range(41):
        a=w.project.import_image(Path('artifacts/fixtures/Fronalpstock_big.jpg'));w.project.placement(a,w.board)
    measure('42_inputs_scene_refresh_seconds',lambda:(w.refresh_all(),w.fit(),app.processEvents()))
    report['counts']={'inputs':42,'assets':len(w.project.data['assets']),'placements':len(w.board['items'])}
    # Rapid session changes followed by close exercise asynchronous worker retirement.
    w.refresh_all([record['id']])
    for _ in range(4):w.open_tool(tool_id='sample');app.processEvents();w.leave_editor()
    wait_until(lambda:not w.retiring_workers,30)
    report['peak_resident_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,1)
    w.dirty=False;w.close();app.processEvents()
    w.deleteLater()
    from PySide6.QtCore import QCoreApplication,QEvent
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
Path('artifacts/v04/release-validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps(report,indent=2,ensure_ascii=False))
