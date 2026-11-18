"""MediaLite — an Arabic, portable, offline Windows media compressor."""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget, QSplitter, QSizePolicy,
)

from engine import Compressor, ExportSettings, Result, SUPPORTED, IMAGE_EXTS, VIDEO_EXTS, resource_dir
from branding import APP_NAME, VERSION, ATTRIBUTION, WHATSAPP_NUMBER, WHATSAPP_URL
from settings_panel import MediaSettingsPanel
from visuals import STYLES, Backdrop, GlassBar, SmoothButton, conservative_effects, icon, apply_palette, apply_window_theme
from media_preview import PreviewPanel
from dialogs import ImportChoiceDialog, HelpDialog, message
from games import GameDialog

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


class ImportWorker(QThread):
    collected = Signal(list, int)

    def __init__(self, incoming):
        super().__init__()
        self.incoming = incoming
        self.cancel = threading.Event()

    def run(self):
        paths, ignored = [], 0
        for source in self.incoming:
            try:
                source = source.resolve()
                folder = source.is_dir()
                for path in (source.rglob('*') if folder else [source]):
                    if self.cancel.is_set():
                        return
                    if len(paths) >= 5000:
                        break
                    if not path.is_file() or (folder and path.suffix.lower() not in SUPPORTED):
                        continue
                    if folder and (path.name.startswith('.medialite-') or
                                   re.search(r'_compressed(?:_\d+)?$', path.stem, re.IGNORECASE) or
                                   any(part.casefold() == 'medialite-compressed' for part in path.relative_to(source).parts[:-1])):
                        continue
                    paths.append(path)
            except OSError:
                ignored += 1
        self.collected.emit(paths, ignored)


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
        self.importing = False
        self.import_worker = None
        self.games = None
        self.setWindowTitle(APP_NAME)
        self.dark_mode = False
        apply_palette(False)
        self.reduced_effects = conservative_effects()
        self.setMinimumSize(960, 640)
        self.resize(1240, 760)
        icon = resource_dir() / "app.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setAcceptDrops(True)
        self.build_ui()
        self.apply_theme()

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

    def action(self, text, slot, icon_name=None, variant="secondary"):
        button = SmoothButton(text, variant=variant, icon_name=icon_name)
        button.clicked.connect(slot)
        return button

    def build_ui(self):
        self.canvas = Backdrop()
        self.setCentralWidget(self.canvas)
        layout = QVBoxLayout(self.canvas)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        self.header = GlassBar(radius=18)
        head = QHBoxLayout(self.header)
        head.setContentsMargins(16, 8, 12, 8)
        head.setSpacing(12)
        mark = QLabel()
        mark.setObjectName('logoPlate')
        mark.setFixedSize(64,64)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(QPixmap(str(resource_dir() / "assets" / "maher-mark.png")).scaled(
            60, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        head.addWidget(mark)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        self.wordmark=self.label('MediaPress','wordmark')
        self.wordmark.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        brand.addWidget(self.wordmark)
        self.byline=self.label('', 'byline')
        self.byline.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.byline.setOpenExternalLinks(True)
        self.byline.setCursor(Qt.CursorShape.PointingHandCursor)
        brand.addWidget(self.byline)
        head.addLayout(brand)
        head.addStretch()
        self.theme_button = self.action("داكن", self.toggle_theme, "moon", "ghost")
        head.addWidget(self.theme_button)
        self.effects_button = self.action("تقليل المؤثرات", self.toggle_effects, "sliders-horizontal", "ghost")
        self.effects_button.setCheckable(True)
        self.effects_button.setChecked(self.reduced_effects)
        self.effects_button.setToolTip("خلفية معتمة وحركات أقل")
        head.addWidget(self.effects_button)
        self.whatsapp_button = self.action("تواصل", self.open_whatsapp, "chat-circle-dots", "ghost")
        self.whatsapp_button.setToolTip(f"{ATTRIBUTION} · واتساب {WHATSAPP_NUMBER}")
        self.whatsapp_button.setAccessibleName(f"واتساب {WHATSAPP_NUMBER}")
        head.addWidget(self.whatsapp_button)
        head.addWidget(self.action("مساعدة", self.about, "info", "ghost"))
        layout.addWidget(self.header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        # Explicit direction keeps the file controls on the right in this Arabic workspace.
        self.splitter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        side = QFrame()
        side.setObjectName("content")
        side.setMinimumWidth(430)
        side.setMaximumWidth(500)
        panel = QVBoxLayout(side)
        panel.setContentsMargins(16, 14, 16, 14)
        panel.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(self.label("الملفات", "sectionTitle"))
        self.count = self.label("لا ملفات", "muted")
        row.addStretch()
        row.addWidget(self.count)
        panel.addLayout(row)
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.add_button = self.action("ملفات", self.pick_files, "file-plus")
        self.add_button.setToolTip("إضافة صور أو فيديوهات · Ctrl+O")
        self.folder_button = self.action("مجلد", self.pick_folder, "folder-open", "ghost")
        self.remove_button = self.action("إزالة", self.remove_selected, "x", "ghost")
        self.remove_button.setToolTip("إزالة المحدد من القائمة · Delete")
        self.remove_button.setAccessibleName("إزالة الملفات المحددة من القائمة")
        self.clear_button = self.action("تفريغ", self.clear_files, "trash", "ghost")
        self.clear_button.setToolTip("تفريغ القائمة")
        self.clear_button.setAccessibleName("تفريغ القائمة")
        actions.addWidget(self.add_button)
        actions.addWidget(self.folder_button)
        actions.addStretch()
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        panel.addLayout(actions)
        self.table = QTableWidget(0, 6)
        self.table.setAccessibleName("قائمة الصور والفيديوهات؛ اختر ملفاً لمعاينته")
        self.table.setHorizontalHeaderLabels(["الملف", "النوع", "قبل", "بعد", "التوفير", "الحالة"])
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 125)
        for column in (1, 2, 3, 4):
            self.table.hideColumn(column)
        self.table.setMinimumHeight(82)
        self.table.cellDoubleClicked.connect(self.open_row)
        self.table.currentCellChanged.connect(lambda *_: self.preview_selected())
        panel.addWidget(self.table, 1)
        divider = QFrame()
        divider.setObjectName("divider")
        panel.addWidget(divider)
        self.settings_tabs = QTabWidget()
        self.image_settings = MediaSettingsPanel("image")
        self.video_settings = MediaSettingsPanel("video")
        self.settings_tabs.addTab(self.image_settings, "الصور · JPEG")
        self.settings_tabs.addTab(self.video_settings, "الفيديو · MP4")
        panel.addWidget(self.settings_tabs)
        output = QHBoxLayout()
        self.auto_output = QCheckBox("الحفظ بجانب كل أصل")
        self.auto_output.setChecked(True)
        self.auto_output.toggled.connect(self.update_output_display)
        output.addWidget(self.auto_output)
        output.addStretch()
        self.browse_button = self.action("تغيير", self.pick_output, "folder-simple", "ghost")
        output.addWidget(self.browse_button)
        panel.addLayout(output)
        self.output_field = QLineEdit()
        self.output_field.setReadOnly(True)
        self.output_field.setAccessibleName("مسار حفظ النتائج")
        self.output_field.setPlaceholderText("يتحدد تلقائياً عند إضافة الملفات")
        self.output_field.setFixedHeight(30)
        panel.addWidget(self.output_field)
        self.mode_note = self.label("", "muted", True)
        self.mode_note.hide()
        self.preview = PreviewPanel()
        self.preview.request_import.connect(self.show_import_dialog)
        self.splitter.addWidget(side)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([455, 720])
        layout.addWidget(self.splitter, 1)
        self.dock = GlassBar(radius=18)
        dock = QVBoxLayout(self.dock)
        dock.setContentsMargins(14, 10, 14, 10)
        dock.setSpacing(6)
        commands = QHBoxLayout()
        commands.setSpacing(8)
        self.start_button = self.action("ابدأ الضغط", self.start, "play", "primary")
        self.start_button.setMinimumWidth(150)
        self.start_button.setToolTip("ابدأ ضغط الملفات · Ctrl+Enter")
        self.stop_button = self.action("إيقاف", self.stop, "x", "danger")
        self.stop_button.hide()
        self.stop_button.setEnabled(False)
        self.open_button = self.action("فتح مجلد النتائج", self.open_output, "folder-open", "ghost")
        self.open_button.hide()
        self.report_button = self.action("تقرير", self.save_report, "download-simple", "ghost")
        self.report_button.hide()
        self.report_button.setEnabled(False)
        self.games_button = self.action('الألعاب',self.show_games,'game-controller','ghost')
        self.games_button.hide()
        for button in (self.start_button, self.stop_button, self.games_button, self.open_button, self.report_button):
            commands.addWidget(button)
        commands.addStretch()
        self.summary = self.label("أضف ملفاتك للبدء", "summary")
        commands.addWidget(self.summary)
        dock.addLayout(commands)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        self.progress.setAccessibleName("تقدم ضغط الدفعة")
        self.progress.valueChanged.connect(lambda value: self.games.set_progress(value) if self.games else None)
        dock.addWidget(self.progress)
        self.detail = self.label("الأصول محفوظة · كل فيديو MP4 وكل صورة JPEG", "muted")
        self.detail.setMinimumWidth(0)
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        dock.addWidget(self.detail)
        layout.addWidget(self.dock)
        self.update_count()
        self.update_mode_note()
        self.shortcuts = []
        for key, slot in (("Ctrl+O", self.pick_files), ("Ctrl+Return", self.start)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(slot)
            self.shortcuts.append(shortcut)
        remove_shortcut = QShortcut(QKeySequence("Delete"), self.table)
        remove_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        remove_shortcut.activated.connect(self.remove_selected)
        self.shortcuts.append(remove_shortcut)

    def toggle_effects(self):
        self.reduced_effects = self.effects_button.isChecked()
        for button in self.findChildren(SmoothButton):
            button.animation.stop()
            button.sheen_animation.stop()
            button.update()
        for bar in (self.header, self.dock):
            bar._cache_key = None
            bar.update()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        apply_palette(self.dark_mode)
        self.theme_button.setText('فاتح' if self.dark_mode else 'داكن')
        self.theme_button.set_icon_name('sun' if self.dark_mode else 'moon')
        self.theme_button.setToolTip('الانتقال إلى الوضع الفاتح' if self.dark_mode else 'الانتقال إلى الوضع الداكن')
        color='#82E0BF' if self.dark_mode else '#107E73'
        self.byline.setText(f'<a href="{WHATSAPP_URL}" style="color:{color};text-decoration:none">By Maher Bakran</a>')
        self.canvas.rebuild()
        self.canvas.update()
        for bar in (self.header,self.dock):
            bar._cache_key=None; bar.update()
        for row,path in enumerate(self.paths):
            self.table.item(row,0).setIcon(icon('image' if path.suffix.lower() in IMAGE_EXTS else 'video'))
            status=self.results[row].status if row in self.results else 'waiting'
            self.table.item(row,5).setForeground(QColor(self.status_color(status)))
        for widget in QApplication.topLevelWidgets():
            apply_window_theme(widget,self.dark_mode)
        self.update()

    def status_color(self,status):
        if status=='error': return '#FFB8A9' if self.dark_mode else '#A33833'
        if status=='compressed': return '#82E0BF' if self.dark_mode else '#107E73'
        return '#B0C6BF' if self.dark_mode else '#526C73'

    def show_import_dialog(self):
        if self.busy: return
        dialog=ImportChoiceDialog(self)
        if dialog.exec():
            if dialog.choice=='files': self.pick_files()
            elif dialog.choice=='folder': self.pick_folder()

    def show_games(self):
        if self.games is None:
            self.games=GameDialog(self)
        self.games.set_progress(self.progress.value(),self.detail.text())
        self.games.results.setEnabled(any(result.output for result in self.results.values()))
        self.games.show()
        self.games.raise_()
        self.games.activateWindow()

    def preview_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.paths):
            self.preview.set_files(self.paths[row], self.results.get(row))
            self.settings_tabs.setCurrentIndex(0 if self.paths[row].suffix.lower() in IMAGE_EXTS else 1)
        else:
            self.preview.clear()

    def update_mode_note(self):
        text = "كل الفيديوهات إلى MP4، وكل الصور إلى JPEG. الخلفية الشفافة تصبح بيضاء، والصور المتحركة أو متعددة الصفحات تصدّر أول إطار/صفحة."
        self.mode_note.setText(text)
        self.settings_tabs.setEnabled(not self.busy)

    def export_settings(self) -> ExportSettings:
        return ExportSettings(**self.image_settings.values(), **self.video_settings.values())

    def pick_files(self):
        if self.busy or self.importing:
            return
        extensions = " ".join("*" + ext for ext in sorted(SUPPORTED))
        paths, _ = QFileDialog.getOpenFileNames(self, "اختَر الصور أو الفيديوهات", "", f"ملفات الوسائط ({extensions});;كل الملفات (*)")
        self.queue_import([Path(path) for path in paths])

    def pick_folder(self):
        if self.busy or self.importing:
            return
        folder = QFileDialog.getExistingDirectory(self, "اختَر مجلداً لإضافة ملفاته والمجلدات الفرعية")
        if folder:
            self.queue_import([Path(folder)])

    def queue_import(self, incoming):
        if not incoming or self.busy or self.importing:
            return
        self.importing = True
        self.set_busy(True)
        self.summary.setText('جارٍ إضافة الملفات…')
        self.detail.setText('يمكنك إيقاف الإضافة؛ الأصول محفوظة.')
        self.import_worker = ImportWorker(incoming)
        self.import_worker.collected.connect(self.import_collected)
        self.import_worker.finished.connect(self.import_scan_finished)
        self.import_worker.start()

    def import_collected(self, paths, ignored):
        self.pending_import = paths
        self.import_ignored = ignored
        self.import_chunk()

    def import_chunk(self):
        if not self.importing:
            return
        batch, self.pending_import = self.pending_import[:60], self.pending_import[60:]
        # Small GUI batches keep input responsive while rows are inserted.
        self.busy = False
        self.add_paths(batch)
        self.busy = True
        self.start_button.setEnabled(False)
        self.detail.setText(f'تمت إضافة {len(self.paths)} ملف…')
        if self.pending_import and not self.import_worker.cancel.is_set():
            QTimer.singleShot(0, self.import_chunk)
        else:
            self.finish_import()

    def import_scan_finished(self):
        if self.import_worker.cancel.is_set() and self.importing:
            self.finish_import()

    def finish_import(self):
        self.import_worker.wait()
        self.importing = False
        self.set_busy(False)
        self.update_count()
        self.summary.setText('جاهز للضغط' if self.paths else 'أضف ملفاتك للبدء')
        self.detail.setText('اختر ملفاً للمعاينة، أو ابدأ ضغط القائمة. الأصول محفوظة.')
        if self.close_when_done:
            self.close()

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
                        if column == 0:
                            item.setIcon(icon('image' if path.suffix.lower() in IMAGE_EXTS else 'video'))
                        item.setToolTip(str(path))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if column in {0, 2, 3, 4} else Qt.AlignmentFlag.AlignRight))
                        self.table.setItem(row, column, item)
                    self.paths.append(path)
                    added += 1
            except OSError:
                ignored += 1
        self.update_count()
        self.update_output_display()
        if self.paths and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 0)
        if ignored:
            self.detail.setText(f"تمت إضافة {added} ملف. تم تجاوز {ignored} ملف غير مدعوم أو غير متاح.")

    def update_count(self):
        self.count.setText(f"{len(self.paths)} ملف" if self.paths else "لا ملفات")
        self.start_button.setEnabled(bool(self.paths) and not self.busy)
        self.remove_button.setEnabled(bool(self.paths) and not self.busy)
        self.clear_button.setEnabled(bool(self.paths) and not self.busy)
        if not self.busy and not self.results:
            self.summary.setText('جاهز للضغط' if self.paths else 'أضف ملفاتك للبدء')

    def clear_files(self):
        if self.busy:
            return
        self.preview.clear()
        self.paths.clear()
        self.results.clear()
        self.table.setRowCount(0)
        self.report_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary.setText("أضف ملفاتك للبدء")
        self.open_button.hide()
        self.report_button.hide()
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
        self.preview_selected()

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
        self.output_field.setCursorPosition(len(self.output_field.text()))

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "مكان حفظ النسخ المضغوطة", str(self.output_dir or ""))
        if folder:
            self.custom_output_dir = Path(folder).resolve()
            self.auto_output.setChecked(False)
            self.update_output_display()

    def set_busy(self, value: bool):
        self.busy = value
        if value:
            self.preview.pause()
        self.stop_button.setVisible(value)
        self.start_button.setText("جارٍ الضغط…" if value else "ابدأ الضغط")
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
            message(self, "مجلد غير متاح", "اختَر مجلداً يمكن الكتابة فيه.", str(exc))
            return
        self.results.clear()
        self.preview_selected()
        self.report_button.hide()
        self.open_button.hide()
        self.progress.setValue(0)
        for row in range(len(self.paths)):
            for col in (3, 4):
                self.table.item(row, col).setText("—")
            self.table.item(row, 5).setText("بانتظار البدء")
            self.table.item(row, 5).setForeground(QColor(self.status_color("waiting")))
        self.set_busy(True)
        self.summary.setText("جارٍ الضغط…")
        self.worker = BatchWorker(self.paths.copy(), destination, "instagram", self.export_settings())
        self.worker.started_file.connect(self.on_started)
        self.worker.progress_file.connect(self.on_progress)
        self.worker.result_file.connect(self.on_result)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()
        self.games_button.show()
        self.show_games()

    def stop(self):
        if self.importing:
            self.import_worker.cancel.set()
            if not self.import_worker.isRunning():
                self.finish_import()
            return
        if self.worker and self.busy:
            self.worker.cancel.set()
            self.stop_button.setEnabled(False)
            self.detail.setText("جارٍ الإيقاف وتنظيف النسخة غير المكتملة…")

    def on_started(self, row: int, name: str):
        self.table.item(row, 5).setText("جارٍ الضغط…")
        self.table.scrollToItem(self.table.item(row, 0))
        self.detail.setText(f"{row + 1} / {len(self.paths)}  •  {name}")
        if self.games:
            self.games.set_progress(self.progress.value(),f'جارٍ الضغط · {row+1} / {len(self.paths)} · {name}')

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
        color = self.status_color(result.status)
        item.setForeground(QColor(color))
        self.progress.setValue(int(1000 * (row + 1) / len(self.paths)))
        saving = sum(r.before - r.after for r in self.results.values() if r.status == "compressed")
        self.summary.setText(f"تم توفير {size_text(saving)}")
        if self.table.currentRow() == row:
            self.preview_selected()

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
        if self.games:
            self.games.set_progress(self.progress.value(),'تم الإيقاف · النتائج المكتملة محفوظة' if stopped else 'انتهت الدفعة · يمكنك مراجعة النتائج أو متابعة اللعب')
            self.games.results.setEnabled(any(r.output for r in self.results.values()))
        if stopped:
            for row in range(len(self.paths)):
                if row not in self.results:
                    self.table.item(row, 5).setText("لم تتم معالجته")
        self.open_button.setVisible(any(r.output for r in self.results.values()))
        self.report_button.setVisible(bool(self.results))
        row = self.table.currentRow()
        if row in self.results and self.results[row].output:
            self.preview.show_result()
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
                self.table.setCurrentCell(row, 0)
                self.preview.show_result()
            else:
                message(self, STATUS[result.status],
                        'تعذّرت معالجة الملف. تأكد من أنه يفتح خارج البرنامج، ثم أعد إضافته.',result.message)

    def save_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "حفظ تقرير الضغط", str((self.output_dir or Path.cwd()) / "MediaPress-report.csv"), "CSV (*.csv)")
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
            message(self, "تعذّر حفظ التقرير", "اختَر مجلداً متاحاً للحفظ.", str(exc))

    def open_whatsapp(self):
        QDesktopServices.openUrl(QUrl(WHATSAPP_URL))

    def about(self):
        HelpDialog(self).exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.queue_import([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy:
            reply = message(self, 'إيقاف وإغلاق', 'العمل مستمر. هل تريد إيقافه وإغلاق البرنامج؟',confirm=True)
            if reply:
                self.close_when_done = True
                self.stop()
            event.ignore()
        else:
            if self.games:
                self.games.shutdown()
            if self.import_worker:
                self.import_worker.cancel.set()
                self.import_worker.wait()
            self.preview.dispose()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MediaPress")
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLES)
    window = MainWindow()
    available = app.primaryScreen().availableGeometry()
    window.resize(min(1240, available.width() - 32), min(760, available.height() - 40))
    window.show()
    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: window.add_paths([Path(path) for path in sys.argv[1:]]))
    sys.exit(app.exec())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from diagnostics import run_smoke_test
        sys.exit(run_smoke_test(Path(sys.argv[2])))
    main()
