import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from blockstudio.qt_runtime import prepare_qt
prepare_qt()
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope='session',autouse=True)
def app():
    instance=QApplication.instance() or QApplication([])
    yield instance

@pytest.fixture(autouse=True)
def dispose_test_widgets(app):
    """Destroy complete widget trees while QApplication is still alive.

    PySide shutdown otherwise visits signal-cycle children in arbitrary order.
    Windows must stop their workers before they can safely be disposed.
    """
    yield
    from PySide6.QtCore import QCoreApplication,QEvent
    from shiboken6 import isValid
    for widget in list(app.topLevelWidgets()):
        if not isValid(widget):continue
        if hasattr(widget,'stop_preview'):
            widget.stop_preview()
            for worker in list(widget.retiring_workers):worker.wait(10000)
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
