from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QCheckBox,QDialogButtonBox,QScrollArea,QWidget,QHBoxLayout
from .metadata import FIELDS,resolved,update


class MetadataDialog(QDialog):
    def __init__(self,project,ids,parent=None):
        super().__init__(parent);self.setWindowTitle('照片与胶片资料');self.resize(590,690);self.project=project;self.ids=ids
        outer=QVBoxLayout(self);note=QLabel(f'已选 {len(ids)} 张 · 只更新勾选字段。手动资料保存在项目，不改写原文件。\n多选写入批量值，单张覆盖优先；相机字段来自文件，扫描照片请核对实际拍摄设备。');note.setWordWrap(True);outer.addWidget(note)
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();f=QFormLayout(content);scroll.setWidget(content);outer.addWidget(scroll)
        values=[resolved(project,i) for i in ids];self.controls={}
        for key,label in FIELDS.items():
            row=QHBoxLayout();check=QCheckBox();edit=QLineEdit();clear=QCheckBox('清除此级覆盖')
            texts={v.get(key,'') for v in values};edit.setText(next(iter(texts)) if len(texts)==1 else '');edit.setPlaceholderText('混合值' if len(texts)>1 else '未填写')
            edit.textEdited.connect(lambda _,c=check:c.setChecked(True));clear.toggled.connect(lambda v,c=check:c.setChecked(True) if v else None)
            row.addWidget(check);row.addWidget(edit);row.addWidget(clear);f.addRow(label,row);self.controls[key]=(check,edit,clear)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);bb.accepted.connect(self.save);bb.rejected.connect(self.reject);outer.addWidget(bb)
    def save(self):
        changes={k:e.text() for k,(c,e,r) in self.controls.items() if c.isChecked() and not r.isChecked()}
        clear=[k for k,(c,e,r) in self.controls.items() if c.isChecked() and r.isChecked()]
        update(self.project,self.ids,changes,clear);self.accept()
