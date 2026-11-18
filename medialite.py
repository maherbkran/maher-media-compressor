"""MediaLite — an Arabic, portable, offline Windows media compressor."""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from engine import Compressor, ExportSettings, Result, SUPPORTED, IMAGE_EXTS, VIDEO_EXTS, resource_dir
from branding import APP_NAME, VERSION, ATTRIBUTION, WHATSAPP_NUMBER, WHATSAPP_URL
from settings_panel import MediaSettingsPanel

STATUS = {"compressed": "تم الضغط", "converted": "تم التحويل", "unchanged": "مضغوط مسبقاً", "skipped": "تم التجاوز",
          "error": "تعذّرت المعالجة", "cancelled": "متوقف"}


def size_text(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


class BatchWorker(QThread):
    started_file = Signal(int, str)
    progress_file = Signal(int, float)
    result_file = Signal(int, object)

    def __init__(self, paths: list[Path], output: Path | None, mode: str, settings: ExportSettings):
        super().__init__()
        self.paths, self.output, self.mode = paths, output, mode
        self.settings = settings
        self.cancel = threading.Event()

    def run(self):
        for index, path in enumerate(self.paths):
            if self.cancel.is_set():
                break
            self.started_file.emit(index, path.name)
            engine = Compressor(self.cancel, lambda value, i=index: self.progress_file.emit(i, value), settings=self.settings)
            result = engine.compress(path, self.output if self.output is not None else path.parent, self.mode)
            self.result_file.emit(index, result)


STYLES = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #202c3a; }
QMainWindow, QWidget#root { background: #f3f5f7; }
QFrame#hero { background: #172d37; border-radius: 16px; }
QLabel#brand { color: #ffffff; font-size: 24pt; font-weight: 700; }
QLabel#heroText { color: #b9cbd1; font-size: 11pt; }
QLabel#badge { background: #284944; color: #b1edcf; border-radius: 12px; padding: 6px 12px; font-size: 9pt; }
QFrame#panel { background: #ffffff; border: 1px solid #dce3e7; border-radius: 12px; }
QLabel#heading { font-size: 12pt; font-weight: 650; }
QLabel#muted { color: #617080; font-size: 9pt; }
QLabel#note { color: #455a64; background: #eaf3ef; padding: 10px 14px; border-radius: 9px; font-size: 9pt; }
QLabel#summary { font-size: 11pt; font-weight: 650; color: #16714e; }
QPushButton { background: #ffffff; border: 1px solid #cdd8df; border-radius: 8px; padding: 8px 14px; min-height: 21px; }
QPushButton:hover { background: #edf4f2; border-color: #7ea897; }
QPushButton:pressed { background: #dcece5; }
QPushButton:disabled { color: #a0a9b1; background: #f1f3f5; border-color: #e1e6e9; }
QPushButton#primary { background: #16835b; border: 1px solid #16835b; color: white; font-weight: 650; padding: 10px 25px; }
QPushButton#primary:hover { background: #106b49; }
QPushButton#primary:disabled { background: #b4c7bf; border-color: #b4c7bf; }
QPushButton#quiet { border: none; background: transparent; color: #526779; }
QPushButton#stop { color: #ae3c39; border-color: #e1bfbd; }
QRadioButton { spacing: 10px; font-size: 11pt; font-weight: 650; }
QRadioButton::indicator { width: 18px; height: 18px; border: 2px solid #9cadb4; border-radius: 10px; background: white; }
QRadioButton::indicator:checked { background: #16835b; border: 2px solid #16835b; }
QLineEdit { border: 1px solid #d6dfe4; border-radius: 7px; background: #f7f9fa; padding: 8px 10px; }
QComboBox { border: 1px solid #cdd8df; border-radius: 7px; background: white; padding: 6px 10px; min-width: 160px; }
QSpinBox, QDoubleSpinBox { border: 1px solid #cdd8df; border-radius: 7px; background: #f7f9fa; padding: 5px 8px; min-height: 24px; }
QTabWidget::pane { border: 1px solid #dce3e7; border-radius: 8px; background: #ffffff; }
QTabBar::tab { background: #eff3f5; padding: 8px 28px; border: 1px solid #dce3e7; }
QTabBar::tab:selected { color: #147450; background: #e2f1e9; font-weight: 650; }
QSlider::groove:horizontal { height: 7px; background: #dfe6e8; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #16835b; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; margin: -6px 0; background: #16835b; border: 1px solid #106d4b; border-radius: 9px; }
QTableWidget { border: 1px solid #e0e6eb; border-radius: 8px; background: white; alternate-background-color: #f8fafb; gridline-color: #edf0f3; selection-background-color: #e0f0e8; selection-color: #152e24; }
QHeaderView::section { background: #f2f6f7; color: #526575; border: none; border-bottom: 1px solid #dce4e8; padding: 10px; font-weight: 650; }
QTableWidget::item { padding: 7px; }
QProgressBar { border: none; background: #e1e8e8; border-radius: 5px; height: 9px; text-align: center; }
QProgressBar::chunk { background: #209a6d; border-radius: 5px; }
QToolTip { background: #172d37; color: #fff; border: none; padding: 7px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.paths: list[Path] = []
        self.results: dict[int, Result] = {}
        self.worker: BatchWorker | None = None
        self.output_dir: Path | None = None
        self.custom_output_dir: Path | None = None
        self.busy = False
        self.close_when_done = False
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(850, 650)
        self.resize(1120, 860)
        icon = resource_dir() / "app.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setAcceptDrops(True)
        self.build_ui()

    @staticmethod
    def label(text: str, name: str = "", wrap: bool = False):
        label = QLabel(text)
        if name:
            label.setObjectName(name)
        label.setWordWrap(wrap)
        return label

    @staticmethod
    def button(text: str, slot, name: str = ""):
        button = QPushButton(text)
        button.clicked.connect(slot)
        if name:
            button.setObjectName(name)
        return button

    def build_ui(self):
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(container)
        root = QWidget()
        root.setObjectName("root")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 18)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("hero")
        h = QHBoxLayout(hero)
        h.setContentsMargins(24, 18, 24, 18)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(self.label("MediaLite", "brand"))
        titles.addWidget(self.label("ضغط وتحويل محلي • MP4 للفيديو • JPEG للصور", "heroText"))
        h.addLayout(titles)
        h.addStretch()
        h.addWidget(self.label("محلي بالكامل  •  بدون إنترنت", "badge"))
        layout.addWidget(hero)

        settings = QFrame()
        settings.setObjectName("panel")
        s = QVBoxLayout(settings)
        s.setContentsMargins(18, 15, 18, 15)
        s.setSpacing(10)
        s.addWidget(self.label("١  إعدادات الضغط والتحويل", "heading"))
        s.addWidget(self.label("بدون حد لحجم الملفات أو مدة التحويل. اضبط الجودة، أو حدّد حجماً للناتج إذا احتجت.", "muted", True))
        self.settings_tabs = QTabWidget()
        self.image_settings = MediaSettingsPanel("image")
        self.video_settings = MediaSettingsPanel("video")
        self.settings_tabs.addTab(self.image_settings, "الصور")
        self.settings_tabs.addTab(self.video_settings, "الفيديوهات")
        self.settings_tabs.setCurrentIndex(1)
        s.addWidget(self.settings_tabs)
        self.mode_note = self.label("", "note", True)
        s.addWidget(self.mode_note)
        self.update_mode_note()
        layout.addWidget(settings)

        files_panel = QFrame()
        files_panel.setObjectName("panel")
        f = QVBoxLayout(files_panel)
        f.setContentsMargins(18, 14, 18, 16)
        f.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.label("٢  أضِف الصور والفيديوهات", "heading"))
        toolbar.addStretch()
        self.add_button = self.button("+ إضافة ملفات", self.pick_files)
        self.folder_button = self.button("إضافة مجلد", self.pick_folder)
        self.remove_button = self.button("إزالة المحدد", self.remove_selected, "quiet")
        self.clear_button = self.button("تفريغ القائمة", self.clear_files, "quiet")
        for button in (self.add_button, self.folder_button, self.remove_button, self.clear_button):
            toolbar.addWidget(button)
        f.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["الملف", "النوع", "الحجم الأصلي", "الحجم الجديد", "التوفير", "الحالة"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(180)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 65), (2, 118), (3, 118), (4, 85), (5, 155)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, width)
        self.table.cellDoubleClicked.connect(self.open_row)
        f.addWidget(self.table, 1)
        self.count = self.label("اسحب الملفات إلى النافذة، أو اضغط «إضافة ملفات» للبدء.", "muted")
        f.addWidget(self.count)
        layout.addWidget(files_panel, 1)

        output_row = QHBoxLayout()
        output_row.addWidget(self.label("٣  مكان حفظ النسخ", "heading"))
        self.auto_output = QCheckBox("نفس مجلد الملف الأصلي")
        self.auto_output.setChecked(True)
        self.auto_output.setToolTip("كل نتيجة تُحفظ بجانب أصلها، حتى لو أضفت ملفات من مجلدات مختلفة.")
        self.auto_output.toggled.connect(self.update_output_display)
        output_row.addWidget(self.auto_output)
        self.output_field = QLineEdit()
        self.output_field.setReadOnly(True)
        self.output_field.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.output_field.setPlaceholderText("يتحدد تلقائياً عند اختيار الملفات أو المجلد")
        output_row.addWidget(self.output_field, 1)
        self.browse_button = self.button("تغيير…", self.pick_output)
        output_row.addWidget(self.browse_button)
        layout.addLayout(output_row)

        # Keep Start/Stop and progress visible on smaller desktop screens.
        bottom = QWidget()
        outer.addWidget(bottom)
        layout = QVBoxLayout(bottom)
        layout.setContentsMargins(26, 10, 26, 12)
        layout.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(9)
        layout.addWidget(self.progress)

        actions = QHBoxLayout()
        self.start_button = self.button("ابدأ الضغط", self.start, "primary")
        self.start_button.setEnabled(False)
        self.stop_button = self.button("إيقاف", self.stop, "stop")
        self.stop_button.setEnabled(False)
        self.open_button = self.button("فتح مجلد النتائج", self.open_output)
        self.open_button.setToolTip("يفتح مجلد الصف المحدد، أو مجلد آخر نتيجة عند وجود أكثر من مجلد.")
        self.open_button.setEnabled(False)
        self.report_button = self.button("حفظ التقرير", self.save_report, "quiet")
        self.report_button.setEnabled(False)
        for button in (self.start_button, self.stop_button, self.open_button, self.report_button):
            actions.addWidget(button)
        actions.addStretch()
        self.summary = self.label("جاهز", "summary")
        actions.addWidget(self.summary)
        layout.addLayout(actions)
        self.detail = self.label("الأصول محفوظة. نحفظ نسخة MP4 أو JPEG باسم جديد، حتى لو كانت أكبر من الأصل.", "muted", True)
        self.detail.setMinimumHeight(26)
        layout.addWidget(self.detail)
        footer = QHBoxLayout()
        footer.addWidget(self.label(f"Windows 10/11  •  v{VERSION}", "muted"))
        footer.addStretch()
        footer.addWidget(self.label(ATTRIBUTION, "muted"))
        self.whatsapp_button = self.button(f"واتساب \u2066{WHATSAPP_NUMBER}\u2069", self.open_whatsapp, "quiet")
        footer.addWidget(self.whatsapp_button)
        footer.addWidget(self.button("عن التطبيق والمساعدة", self.about, "quiet"))
        layout.addLayout(footer)

    def update_mode_note(self):
        text = "كل الفيديوهات إلى MP4، وكل الصور إلى JPEG. الخلفية الشفافة تصبح بيضاء، والصور المتحركة أو متعددة الصفحات تصدّر أول إطار/صفحة."
        self.mode_note.setText(text)
        self.settings_tabs.setEnabled(not self.busy)

    def export_settings(self) -> ExportSettings:
        return ExportSettings(**self.image_settings.values(), **self.video_settings.values())

    def pick_files(self):
        extensions = " ".join("*" + ext for ext in sorted(SUPPORTED))
        paths, _ = QFileDialog.getOpenFileNames(self, "اختَر الصور أو الفيديوهات", "", f"ملفات الوسائط ({extensions});;كل الملفات (*)")
        self.add_paths([Path(path) for path in paths])

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "اختَر مجلداً لإضافة ملفاته والمجلدات الفرعية")
        if folder:
            self.add_paths([Path(folder)])

    def add_paths(self, incoming: list[Path]):
        if self.busy:
            return
        known = {str(path).casefold() for path in self.paths}
        added = 0
        ignored = 0
        for source in incoming:
            source = source.resolve()
            is_folder = source.is_dir()
            candidates = source.rglob("*") if is_folder else [source]
            try:
                for path in candidates:
                    if len(self.paths) >= 5000:
                        self.detail.setText("تم الوصول إلى حد 5000 ملف في الدفعة الواحدة.")
                        break
                    if not path.is_file() or (is_folder and path.suffix.lower() not in SUPPORTED):
                        if not source.is_dir():
                            ignored += 1
                        continue
                    path = path.resolve()
                    if is_folder:
                        try:
                            relative_parts = path.relative_to(source).parts
                        except ValueError:
                            continue
                        # Do not pick up our own completed/temporary outputs on the next folder scan.
                        if path.name.startswith(".medialite-") or re.search(r"_compressed(?:_\d+)?$", path.stem, re.IGNORECASE):
                            continue
                        if any(part.casefold() == "medialite-compressed" for part in relative_parts[:-1]):
                            continue
                    key = str(path).casefold()
                    if key in known:
                        continue
                    try:
                        byte_size = path.stat().st_size
                    except OSError:
                        ignored += 1
                        continue
                    known.add(key)
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    kind = "صورة" if path.suffix.lower() in IMAGE_EXTS else "فيديو" if path.suffix.lower() in VIDEO_EXTS else "تلقائي"
                    values = [path.name, kind, size_text(byte_size), "—", "—", "بانتظار البدء"]
                    for column, value in enumerate(values):
                        item = QTableWidgetItem(value)
                        item.setToolTip(str(path))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if column in {0, 2, 3, 4} else Qt.AlignmentFlag.AlignRight))
                        self.table.setItem(row, column, item)
                    self.paths.append(path)
                    added += 1
            except OSError:
                ignored += 1
        self.update_count()
        self.update_output_display()
        if ignored:
            self.detail.setText(f"تمت إضافة {added} ملف. تم تجاوز {ignored} ملف غير مدعوم أو غير متاح.")

    def update_count(self):
        self.count.setText(f"{len(self.paths)} ملف في القائمة  •  انقر مرتين على أي نتيجة لفتحها وعرض التفاصيل." if self.paths else "اسحب الملفات إلى النافذة، أو اضغط «إضافة ملفات» للبدء.")
        self.start_button.setEnabled(bool(self.paths) and not self.busy)

    def clear_files(self):
        if self.busy:
            return
        self.paths.clear()
        self.results.clear()
        self.table.setRowCount(0)
        self.report_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary.setText("جاهز")
        self.update_count()
        self.update_output_display()

    def remove_selected(self):
        if self.busy:
            return
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        old_results = {str(self.paths[row]): result for row, result in self.results.items()}
        for row in sorted(rows, reverse=True):
            self.paths.pop(row)
            self.table.removeRow(row)
        self.results = {i: old_results[str(path)] for i, path in enumerate(self.paths) if str(path) in old_results}
        self.report_button.setEnabled(bool(self.results))
        self.update_count()
        self.update_output_display()

    def update_output_display(self):
        if self.auto_output.isChecked():
            parents = {path.parent for path in self.paths}
            self.output_dir = self.paths[-1].parent if self.paths else None
            if len(parents) > 1:
                self.output_field.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                self.output_field.setText(f"تلقائي: كل نتيجة بجانب ملفها الأصلي ({len(parents)} مجلدات)")
                self.output_field.setToolTip("\n".join(sorted(str(parent) for parent in parents)))
            else:
                self.output_field.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                self.output_field.setText(str(self.output_dir) if self.output_dir else "")
                self.output_field.setToolTip(str(self.output_dir or ""))
        else:
            if self.custom_output_dir is None and self.paths:
                self.custom_output_dir = self.paths[-1].parent
            self.output_dir = self.custom_output_dir
            self.output_field.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.output_field.setText(str(self.output_dir) if self.output_dir else "")
            self.output_field.setToolTip(str(self.output_dir or ""))
        self.open_button.setEnabled(bool(self.output_dir and self.output_dir.is_dir()))

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "مكان حفظ النسخ المضغوطة", str(self.output_dir or ""))
        if folder:
            self.custom_output_dir = Path(folder).resolve()
            self.auto_output.setChecked(False)
            self.update_output_display()

    def set_busy(self, value: bool):
        self.busy = value
        for widget in (self.add_button, self.folder_button, self.remove_button, self.clear_button,
                       self.browse_button, self.auto_output):
            widget.setEnabled(not value)
        self.settings_tabs.setEnabled(not value)
        self.start_button.setEnabled(not value and bool(self.paths))
        self.stop_button.setEnabled(value)
        self.report_button.setEnabled(not value and bool(self.results))

    def start(self):
        if self.busy or not self.paths:
            return
        automatic = self.auto_output.isChecked()
        destination = None if automatic else self.output_dir
        if not automatic and destination is None:
            return
        # Confirm destination access before starting expensive encoding.
        try:
            import tempfile
            destinations = {path.parent for path in self.paths} if automatic else {destination}
            for folder in destinations:
                folder.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=folder):
                    pass
        except OSError as exc:
            QMessageBox.warning(self, "مجلد غير متاح", f"اختَر مجلداً يمكن الكتابة فيه.\n\n{exc}")
            return
        self.results.clear()
        self.progress.setValue(0)
        for row in range(len(self.paths)):
            for col in (3, 4):
                self.table.item(row, col).setText("—")
            self.table.item(row, 5).setText("بانتظار البدء")
            self.table.item(row, 5).setForeground(QColor("#526575"))
        self.set_busy(True)
        self.summary.setText("جارٍ الضغط…")
        self.worker = BatchWorker(self.paths.copy(), destination, "instagram", self.export_settings())
        self.worker.started_file.connect(self.on_started)
        self.worker.progress_file.connect(self.on_progress)
        self.worker.result_file.connect(self.on_result)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def stop(self):
        if self.worker and self.busy:
            self.worker.cancel.set()
            self.stop_button.setEnabled(False)
            self.detail.setText("جارٍ الإيقاف وتنظيف النسخة غير المكتملة…")

    def on_started(self, row: int, name: str):
        self.table.item(row, 5).setText("جارٍ الضغط…")
        self.table.scrollToItem(self.table.item(row, 0))
        self.detail.setText(f"{row + 1} / {len(self.paths)}  •  {name}")

    def on_progress(self, row: int, fraction: float):
        self.progress.setValue(int(1000 * (row + fraction) / len(self.paths)))
        self.table.item(row, 5).setText(f"جارٍ الضغط… {fraction:.0%}")

    def on_result(self, row: int, result: Result):
        self.results[row] = result
        self.table.item(row, 3).setText(size_text(result.after) if result.status in {"compressed", "converted", "unchanged"} else "—")
        saved = 1 - result.after / result.before if result.before else 0
        self.table.item(row, 4).setText(f"{saved:.1%}" if result.status == "compressed" else "—")
        item = self.table.item(row, 5)
        item.setText(STATUS[result.status])
        item.setToolTip(result.message + ("\n" + result.output if result.output else ""))
        color = "#16835b" if result.status == "compressed" else "#b14a39" if result.status == "error" else "#617080"
        item.setForeground(QColor(color))
        self.progress.setValue(int(1000 * (row + 1) / len(self.paths)))
        saving = sum(r.before - r.after for r in self.results.values() if r.status == "compressed")
        self.summary.setText(f"تم توفير {size_text(saving)}")

    def on_finished(self):
        stopped = self.worker.cancel.is_set() if self.worker else False
        self.set_busy(False)
        self.open_button.setEnabled(bool(self.output_dir and self.output_dir.exists()))
        if not stopped:
            self.progress.setValue(1000)
        compressed = sum(r.status == "compressed" for r in self.results.values())
        converted = sum(r.status == "converted" for r in self.results.values())
        unchanged = sum(r.status == "unchanged" for r in self.results.values())
        errors = sum(r.status == "error" for r in self.results.values())
        skipped = sum(r.status == "skipped" for r in self.results.values())
        self.detail.setText(f"{'تم الإيقاف' if stopped else 'اكتملت الدفعة'}  •  {compressed} نسخة أصغر  •  {converted} محوّل  •  {skipped} متجاوز  •  {errors} أخطاء. الأصول محفوظة.")
        if stopped:
            for row in range(len(self.paths)):
                if row not in self.results:
                    self.table.item(row, 5).setText("لم تتم معالجته")
        if self.close_when_done:
            self.close()

    def open_output(self):
        folder = self.output_dir
        if self.auto_output.isChecked():
            row = self.table.currentRow()
            if 0 <= row < len(self.paths):
                folder = self.paths[row].parent
            else:
                outputs = [Path(result.output).parent for result in self.results.values() if result.output]
                if outputs:
                    folder = outputs[-1]
        if folder and folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_row(self, row: int, column: int):
        result = self.results.get(row)
        if result:
            if result.output and Path(result.output).is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(result.output))
            else:
                QMessageBox.information(self, STATUS[result.status], result.message)

    def save_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "حفظ تقرير الضغط", str((self.output_dir or Path.cwd()) / "MediaLite-report.csv"), "CSV (*.csv)")
        if not path:
            return
        # Neutralize spreadsheet formulas in filenames and error messages.
        def safe(value):
            text = str(value)
            return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["Source", "Status", "Before bytes", "After bytes", "Saved bytes", "Output", "Details"])
                for row, result in sorted(self.results.items()):
                    writer.writerow([safe(result.source), STATUS[result.status], result.before, result.after,
                                     max(0, result.before - result.after), safe(result.output), safe(result.message)])
            self.detail.setText("تم حفظ التقرير: " + path)
        except OSError as exc:
            QMessageBox.warning(self, "تعذّر حفظ التقرير", str(exc))

    def open_whatsapp(self):
        QDesktopServices.openUrl(QUrl(WHATSAPP_URL))

    def about(self):
        QMessageBox.information(self, "عن MediaLite", (
            f"MediaLite {VERSION}\n{ATTRIBUTION}\nواتساب: {WHATSAPP_NUMBER}\n\n"
            "ضغط صور وفيديو محلي بالكامل. لا حساب، لا رفع ملفات، ولا اتصال بالشبكة.\n\n"
            "الافتراضي بدون حد حجم للناتج. لا يوجد حد برمجي لحجم الفيديو أو مدة قراءته وتحويله؛ يعتمد على المساحة وقدرة الجهاز.\n\n"
            "كل الفيديوهات تصدّر MP4 وكل الصور JPEG، مع تبويبين مستقلين للجودة (%) والحجم والعرض والارتفاع. "
            "التطبيق يضبط الضغط حسب المدة، ويحفظ الكادر كاملاً "
            "مع مسار الصوت الأساسي. الصور تُصغّر وتضغط للنشر. هذا الوضع ضياعي، ومناسب للمشاركة أكثر من الأرشفة.\n\n"
            "GIF والصور المتحركة ومتعددة الصفحات تصدّر أول إطار/صفحة. الشفافية تتحول لخلفية بيضاء. تصدير الفيديو يختار مسار الصورة والصوت الأساسيين. "
            "ألوان HDR المدعومة تحوّل إلى SDR للنشر؛ راجع الألوان في الناتج. "
            "تدعم HEIC/HEIF وAVIF والصيغ الشائعة المتاحة عبر Pillow وFFmpeg. الملفات التالفة أو المشفرة قد لا تُقرأ.\n\n"
            "يفتح النقر المزدوج النسخة الناتجة أو تفاصيل عدم المعالجة. الإيقاف يحافظ على النتائج المكتملة.\n\n"
            "الحفظ الافتراضي بجانب كل أصل. يتحدّث المسار تلقائياً عند اختيار الملفات أو المجلدات. يمكن اختيار مجلد مخصص من زر تغيير.\n\n"
            "المكتبات: Python، PySide6/Qt، Pillow، FFmpeg، libjpeg-turbo.\n"
            "التراخيص وإرشادات البناء ضمن مجلد التطبيق وملفات المصدر."
        ))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy:
            reply = QMessageBox.question(self, "إيقاف وإغلاق", "الضغط ما زال يعمل. هل تريد إيقافه وإغلاق التطبيق؟",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.close_when_done = True
                self.stop()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MediaLite")
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLES)
    window = MainWindow()
    available = app.primaryScreen().availableGeometry()
    window.resize(min(1120, available.width() - 32), min(860, available.height() - 40))
    window.show()
    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: window.add_paths([Path(path) for path in sys.argv[1:]]))
    sys.exit(app.exec())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from diagnostics import run_smoke_test
        sys.exit(run_smoke_test(Path(sys.argv[2])))
    main()
