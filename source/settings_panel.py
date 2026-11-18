"""Compact controls with dimensions in an optional dialog."""
from PySide6.QtCore import Qt, QSignalBlocker, Signal, QLocale
from PySide6.QtWidgets import (QDoubleSpinBox, QGridLayout, QHBoxLayout, QVBoxLayout, QAbstractSpinBox,
                               QLabel, QSlider, QSpinBox, QWidget, QDialog)
from engine import ExportSettings
from visuals import SmoothButton
from dialogs import ThemeDialog


class MediaSettingsPanel(QWidget):
    changed = Signal()

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.size_step = .01 if kind == 'image' else .1
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 10, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.quality_slider.setAccessibleName('نسبة الجودة')
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setSuffix(' %')
        self.quality.setFixedWidth(95)
        self.quality.setAccessibleName('الجودة بالنسبة المئوية')
        self.quality_slider.valueChanged.connect(self.quality.setValue)
        self.quality.valueChanged.connect(self.quality_slider.setValue)
        self.quality.valueChanged.connect(lambda _: self.changed.emit())
        grid.addWidget(QLabel('الجودة'), 0, 0)
        grid.addWidget(self.quality_slider, 0, 1)
        grid.addWidget(self.quality, 0, 2)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.size_slider.setRange(0, 1000)
        self.size_slider.setAccessibleName('أقصى حجم لكل ملف')
        self.max_size = QDoubleSpinBox()
        self.max_size.setRange(0, 1000)
        self.max_size.setDecimals(2)
        self.max_size.setSingleStep(.1)
        self.max_size.setSuffix(' MB')
        self.max_size.setSpecialValueText('بدون حد')
        self.max_size.setFixedWidth(115)
        self.max_size.setAccessibleName('أقصى حجم لكل ملف بالميغابايت')
        self.max_size.setToolTip('صفر يعني بدون حد لحجم الناتج. الحجم المحدد لكل ملف على حدة.')
        self.size_slider.valueChanged.connect(lambda value: self.max_size.setValue(round(value*self.size_step, 2)))
        self.max_size.valueChanged.connect(self.update_size_slider)
        self.max_size.valueChanged.connect(lambda _: self.changed.emit())
        grid.addWidget(QLabel('الحجم الأقصى'), 1, 0)
        grid.addWidget(self.size_slider, 1, 1)
        grid.addWidget(self.max_size, 1, 2)
        bottom = QHBoxLayout()
        format_note = QLabel('JPEG · خلفية بيضاء' if kind == 'image' else 'MP4 · الكادر كاملاً')
        format_note.setObjectName('muted')
        bottom.addWidget(format_note)
        bottom.addStretch()
        if kind == 'video':
            for size in (5, 10):
                button = SmoothButton(f'{size} MB', variant='ghost')
                button.setToolTip(f'حجم مستهدف {size} ميغابايت لكل فيديو')
                button.clicked.connect(lambda checked=False, amount=size: self.max_size.setValue(amount))
                bottom.addWidget(button)
        self.more_button = SmoothButton('المزيد', icon_name='sliders-horizontal', variant='ghost')
        self.more_button.clicked.connect(self.show_more)
        bottom.addWidget(self.more_button)
        grid.addLayout(bottom, 2, 0, 1, 3)
        self.dialog = ThemeDialog(self, 'إعدادات الصور' if kind == 'image' else 'إعدادات الفيديو')
        self.dialog.setFixedWidth(460)
        box = self.dialog.body
        title=QLabel('أبعاد الصور' if kind == 'image' else 'أبعاد الفيديو')
        title.setObjectName('sectionTitle'); box.addWidget(title)
        note=QLabel('نحافظ على النسبة والكادر؛ لا نكبّر الملفات الصغيرة.')
        note.setWordWrap(True); note.setObjectName('muted'); box.addWidget(note)
        dimensions=QHBoxLayout()
        self.max_width=QSpinBox(); self.max_height=QSpinBox()
        for control,text in ((self.max_width,'أقصى عرض'),(self.max_height,'أقصى ارتفاع')):
            control.setRange(16,16384); control.setSingleStep(2 if kind=='video' else 1)
            control.setSuffix(' px'); control.setAccessibleName(text)
            control.valueChanged.connect(lambda _:self.changed.emit())
            column=QVBoxLayout(); column.setSpacing(6)
            column.addWidget(QLabel(text)); column.addWidget(control)
            dimensions.addLayout(column,1)
        box.addLayout(dimensions)
        hint=QLabel('الصور المتحركة: أول إطار أو صفحة فقط.' if kind=='image' else 'الحجم المحدد قد يستلزم أبعاداً أو جودة أقل.')
        hint.setWordWrap(True); hint.setObjectName('muted'); box.addWidget(hint)
        actions=QHBoxLayout()
        reset=SmoothButton('الافتراضي',icon_name='arrow-counter-clockwise',variant='ghost')
        reset.clicked.connect(self.reset_defaults); actions.addWidget(reset)
        actions.addStretch()
        cancel=SmoothButton('إلغاء'); cancel.clicked.connect(self.dialog.reject); actions.addWidget(cancel)
        apply=SmoothButton('حفظ',variant='primary',icon_name='check-circle')
        apply.clicked.connect(self.dialog.accept); actions.addWidget(apply)
        box.addLayout(actions)
        self.reset_defaults()
        for control in (self.quality, self.max_size, self.max_width, self.max_height):
            control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            control.setLocale(QLocale(QLocale.Language.English))
            control.lineEdit().setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def show_more(self):
        before = self.values()
        if self.dialog.exec() != QDialog.DialogCode.Accepted:
            self.quality.setValue(before[self.kind+'_quality'])
            self.max_size.setValue(before[self.kind+'_max_mb'])
            self.max_width.setValue(before[self.kind+'_max_width'])
            self.max_height.setValue(before[self.kind+'_max_height'])

    def update_size_slider(self, value):
        position = round(value/self.size_step)
        with QSignalBlocker(self.size_slider):
            self.size_slider.setMaximum(max(1000, position))
            self.size_slider.setValue(position)

    def reset_defaults(self):
        defaults = ExportSettings()
        for control, suffix in ((self.quality, '_quality'), (self.max_size, '_max_mb'),
                                (self.max_width, '_max_width'), (self.max_height, '_max_height')):
            control.setValue(getattr(defaults, self.kind+suffix))

    def values(self):
        return {self.kind+'_quality': self.quality.value(), self.kind+'_max_mb': self.max_size.value(),
                self.kind+'_max_width': self.max_width.value(), self.kind+'_max_height': self.max_height.value()}
