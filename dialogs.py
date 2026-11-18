"""Consistent, compact popups in both application themes."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
from visuals import SmoothButton, is_dark, apply_window_theme
from branding import APP_NAME, VERSION, WHATSAPP_NUMBER, WHATSAPP_URL
from engine import resource_dir


class ThemeDialog(QDialog):
    def __init__(self, parent=None, title=''):
        super().__init__(parent)
        self.setWindowTitle(title or APP_NAME)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24,20,24,20)
        self.body.setSpacing(14)

    def showEvent(self,event):
        apply_window_theme(self,is_dark(self))
        super().showEvent(event)


class ImportChoiceDialog(ThemeDialog):
    def __init__(self,parent):
        super().__init__(parent,'إضافة ملفات')
        self.choice = None
        title=QLabel('ماذا تريد أن تضيف؟'); title.setObjectName('sectionTitle')
        self.body.addWidget(title)
        note=QLabel('اختر ملفات محددة أو أضف محتوى مجلد.'); note.setObjectName('muted')
        self.body.addWidget(note)
        self.file_button=SmoothButton('صور وفيديوهات',icon_name='files')
        self.folder_button=SmoothButton('مجلد كامل',icon_name='folder-open')
        for button in (self.file_button,self.folder_button): button.setMinimumHeight(52)
        self.file_button.clicked.connect(lambda:self.choose('files'))
        self.folder_button.clicked.connect(lambda:self.choose('folder'))
        self.body.addWidget(self.file_button)
        self.body.addWidget(self.folder_button)
        row=QHBoxLayout(); row.addStretch()
        close=SmoothButton('إلغاء',variant='ghost'); close.clicked.connect(self.reject)
        row.addWidget(close); self.body.addLayout(row)

    def choose(self,choice):
        self.choice=choice
        self.accept()


class MessageDialog(ThemeDialog):
    def __init__(self,parent,title,text,details='',confirm=False):
        super().__init__(parent,title)
        self.resize(460,220)
        heading=QLabel(title); heading.setObjectName('sectionTitle'); self.body.addWidget(heading)
        message=QLabel(text); message.setWordWrap(True); self.body.addWidget(message)
        if details:
            self.details = QTextEdit()
            self.details.setReadOnly(True)
            self.details.setPlainText(details)
            self.details.setMinimumHeight(120)
            self.details.setMaximumHeight(210)
            self.details.hide()
            more=SmoothButton('عرض التفاصيل',variant='ghost',icon_name='info')
            more.setCheckable(True)
            more.toggled.connect(self.details.setVisible)
            self.body.addWidget(more)
            self.body.addWidget(self.details)
        actions=QHBoxLayout(); actions.addStretch()
        if confirm:
            cancel=SmoothButton('متابعة العمل'); cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        accept=SmoothButton('إيقاف وإغلاق' if confirm else 'تم',variant='danger' if confirm else 'primary')
        accept.clicked.connect(self.accept); actions.addWidget(accept)
        self.body.addLayout(actions)


def message(parent,title,text,details='',confirm=False):
    return MessageDialog(parent,title,text,details,confirm).exec() == QDialog.DialogCode.Accepted


class HelpDialog(ThemeDialog):
    def __init__(self,parent):
        super().__init__(parent,'عن MediaPress')
        self.setFixedWidth(480)
        row=QHBoxLayout()
        mark=QLabel(); mark.setPixmap(QPixmap(str(resource_dir()/'assets'/'maher-mark.png')).scaled(54,54,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        row.addWidget(mark)
        title=QLabel(f'{APP_NAME}  {VERSION}'); title.setObjectName('sectionTitle'); title.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row.addWidget(title,1); self.body.addLayout(row)
        byline=QLabel(f'<a href="{WHATSAPP_URL}" style="color:{"#82E0BF" if is_dark(self) else "#107E73"}">By Maher Bakran</a>')
        byline.setOpenExternalLinks(True); byline.setLayoutDirection(Qt.LayoutDirection.LeftToRight); self.body.addWidget(byline)
        note=QLabel('أضف ملفاتك، اضبط الجودة أو الحجم، ثم ابدأ الضغط.\nعاين النتيجة وافتح مجلدها عند الانتهاء.')
        note.setWordWrap(True); self.body.addWidget(note)
        format_note=QLabel('MP4 للفيديو · JPEG للصور\nالحفظ بجانب كل أصل تلقائياً · المعالجة على جهازك')
        format_note.setObjectName('muted'); format_note.setWordWrap(True); self.body.addWidget(format_note)
        self.details=QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText('من تطوير ماهر بكران\nواتساب: \u2066'+WHATSAPP_NUMBER+'\u2069\n\n'
            'لا حد برمجي لحجم الفيديو أو مدة تحويله. الوقت والمساحة حسب جهازك.\n'
            'الحجم المطلوب لكل ملف هدف اختياري، وقد يستلزم جودة أو أبعاداً أقل.\n'
            'الضغط ضياعي للنشر. الجودة 100% لا تعني تطابقاً مع الأصل.\n'
            'الشفافية تصبح بيضاء. الصور المتحركة ومتعددة الصفحات: أول إطار/صفحة.\n'
            'الفيديو: مسار الصورة والصوت الأساسيان، وHDR المدعوم إلى SDR.\n'
            'الملفات التالفة أو المشفرة قد لا تقرأ. تعذّر المعاينة لا يمنع تجربة التحويل.\n'
            'الأصول محفوظة. الإيقاف يحتفظ بالنتائج المكتملة.\n'
            'كل المعالجة محلية. زر التواصل يفتح واتساب عند الضغط عليه.\n'
            'Python · Qt/PySide6 · Pillow · FFmpeg · libjpeg-turbo · Phosphor Icons.\n'
            'التراخيص والمصدر وإرشادات البناء مرفقة مع الحزمة.')
        self.details.setFixedHeight(200); self.details.hide()
        more=SmoothButton('تفاصيل التصدير والتراخيص',icon_name='info',variant='ghost')
        more.setCheckable(True); more.toggled.connect(self.details.setVisible)
        self.body.addWidget(more); self.body.addWidget(self.details)
        close=SmoothButton('تم',variant='primary',icon_name='check-circle'); close.clicked.connect(self.accept)
        row=QHBoxLayout(); row.addStretch(); row.addWidget(close); self.body.addLayout(row)
