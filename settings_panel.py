"""Independent image/video controls; settings are copied into an immutable batch snapshot."""
from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSpinBox, QWidget,
)

from engine import ExportSettings


class MediaSettingsPanel(QWidget):
    changed = Signal()

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.size_step = 0.01 if kind == "image" else 0.1
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 12, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setSuffix(" %")
        self.quality.setMinimumWidth(120)
        self.quality_slider.setAccessibleName("نسبة جودة الصور" if kind == "image" else "نسبة جودة الفيديو")
        self.quality.setAccessibleName("جودة الصور بالنسبة المئوية" if kind == "image" else "جودة الفيديو بالنسبة المئوية")
        self.quality_slider.valueChanged.connect(self.quality.setValue)
        self.quality.valueChanged.connect(self.quality_slider.setValue)
        self.quality.valueChanged.connect(lambda value: self.changed.emit())
        grid.addWidget(QLabel("الجودة:"), 0, 0)
        grid.addWidget(self.quality_slider, 0, 1)
        grid.addWidget(self.quality, 0, 2)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.size_slider.setRange(0, 1000)
        self.max_size = QDoubleSpinBox()
        self.max_size.setRange(0, 1000)
        self.max_size.setDecimals(2)
        self.max_size.setSingleStep(0.1)
        self.max_size.setSuffix(" MB")
        self.max_size.setSpecialValueText("بدون حد")
        self.max_size.setAccessibleName("أقصى حجم لكل صورة" if kind == "image" else "أقصى حجم لكل فيديو")
        self.max_size.setToolTip("اكتب أي حجم حتى 1000 MB. صفر يعني بدون حد. الحجم لكل ملف على حدة.")
        self.size_slider.valueChanged.connect(lambda value: self.max_size.setValue(round(value * self.size_step, 2)))
        self.max_size.valueChanged.connect(self.update_size_slider)
        self.max_size.valueChanged.connect(lambda value: self.changed.emit())
        grid.addWidget(QLabel("أقصى حجم لكل ملف:"), 1, 0)
        grid.addWidget(self.size_slider, 1, 1)
        grid.addWidget(self.max_size, 1, 2)

        dimensions = QHBoxLayout()
        self.max_width = QSpinBox()
        self.max_height = QSpinBox()
        for control, label in ((self.max_width, "أقصى عرض"), (self.max_height, "أقصى ارتفاع")):
            control.setRange(16, 16384)
            control.setSingleStep(2 if kind == "video" else 1)
            control.setSuffix(" px")
            control.setAccessibleName(label + (" للصور" if kind == "image" else " للفيديو"))
            control.valueChanged.connect(lambda value: self.changed.emit())
            dimensions.addWidget(QLabel(label + ":"))
            dimensions.addWidget(control, 1)
        grid.addLayout(dimensions, 2, 0, 1, 3)

        note = QLabel("الناتج JPEG دائماً؛ الشفافية بخلفية بيضاء. صفر أو «بدون حد» يلغي سقف حجم الناتج."
                      if kind == "image" else "الجودة حدّ أعلى؛ قد تنخفض الجودة أو الأبعاد للوصول إلى الحجم. الكادر يبقى كاملاً.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        grid.addWidget(note, 3, 0, 1, 3)
        buttons = QHBoxLayout()
        reset = QPushButton("استعادة الافتراضي")
        reset.clicked.connect(self.reset_defaults)
        buttons.addWidget(reset)
        if kind == "video":
            for value in (5, 10):
                quick = QPushButton(f"{value} MB")
                quick.clicked.connect(lambda checked=False, amount=value: self.max_size.setValue(amount))
                buttons.addWidget(quick)
        unlimited = QPushButton("بدون حد حجم")
        unlimited.clicked.connect(lambda: self.max_size.setValue(0))
        buttons.addWidget(unlimited)
        buttons.addStretch()
        grid.addLayout(buttons, 4, 0, 1, 3)
        self.reset_defaults()

    def update_size_slider(self, value: float):
        position = round(value / self.size_step)
        with QSignalBlocker(self.size_slider):
            self.size_slider.setMaximum(max(1000, position))
            self.size_slider.setValue(position)

    def reset_defaults(self):
        defaults = ExportSettings()
        self.quality.setValue(getattr(defaults, self.kind + "_quality"))
        self.max_size.setValue(getattr(defaults, self.kind + "_max_mb"))
        self.max_width.setValue(getattr(defaults, self.kind + "_max_width"))
        self.max_height.setValue(getattr(defaults, self.kind + "_max_height"))

    def values(self) -> dict:
        return {self.kind + "_quality": self.quality.value(),
                self.kind + "_max_mb": self.max_size.value(),
                self.kind + "_max_width": self.max_width.value(),
                self.kind + "_max_height": self.max_height.value()}
