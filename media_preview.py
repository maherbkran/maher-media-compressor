"""Asynchronous still previews and native, local video playback."""
from pathlib import Path
import subprocess
import io
import threading
import time
import os

# The native player, like the export engine, accepts local media only.
os.environ['QT_FFMPEG_PROTOCOL_WHITELIST'] = 'file,pipe'
os.environ.setdefault('QT_MEDIA_BACKEND', 'ffmpeg')

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QUrl
from PySide6.QtGui import QImage, QPixmap, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QFrame, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QStackedWidget, QSlider, QSizePolicy)

from engine import IMAGE_EXTS, resource_dir
from visuals import SmoothButton, icon


def human_size(value):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}'
        value /= 1024


class Loaded(QObject):
    done = Signal(int, object, str)


class LoadPreview(QRunnable):
    def __init__(self, token, path):
        super().__init__()
        self.token, self.path = token, path
        self.signals = Loaded()
        self.cancelled = threading.Event()

    def poster(self):
        command = [str(resource_dir() / 'tools' / 'ffmpeg.exe'), '-v', 'error', '-nostdin',
                   '-protocol_whitelist', 'file,pipe', '-i', str(self.path), '-frames:v', '1',
                   '-vf', 'scale=1280:1280:force_original_aspect_ratio=decrease',
                   '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
            deadline = time.monotonic()+15
            while True:
                if self.cancelled.is_set() or time.monotonic() > deadline:
                    process.kill()
                    process.communicate()
                    raise ValueError('preview cancelled')
                try:
                    data, _ = process.communicate(timeout=.1)
                    return QImage.fromData(data)
                except subprocess.TimeoutExpired:
                    continue

    def run(self):
        try:
            if self.path.suffix.lower() in IMAGE_EXTS:
                with Image.open(self.path) as source:
                    if source.width*source.height > 36_000_000:
                        raise ValueError('use bounded decoder')
                    width, height = source.size
                    if source.getexif().get(274) in (5, 6, 7, 8):
                        width, height = height, width
                    dimensions = f'{width} × {height}'
                    source.draft('RGB', (1500, 1500))
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail((1500, 1500))
                    image = image.convert('RGBA')
                    rgba = image.tobytes()
                    result = QImage(rgba, image.width, image.height, QImage.Format.Format_RGBA8888).copy()
            else:
                result = self.poster()
                dimensions = 'اضغط تشغيل لمعاينة الفيديو'
                if result.isNull():
                    raise ValueError('preview unavailable')
            self.signals.done.emit(self.token, result, dimensions)
        except Exception:
            try:
                if self.cancelled.is_set():
                    return
                result = self.poster()
                if result.isNull():
                    raise ValueError('unavailable')
                self.signals.done.emit(self.token, result, 'المعاينة')
            except Exception:
                self.signals.done.emit(self.token, None, 'المعاينة غير متاحة لهذا الملف. يمكنك تجربة ضغطه أو فتحه خارج التطبيق.')


class AddArea(QFrame):
    activated = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName('emptyAdd')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('إضافة ملفات أو مجلد')

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.activated.emit()
        else:
            super().keyPressEvent(event)


class ImageCanvas(QLabel):
    def __init__(self):
        super().__init__()
        self.original = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setObjectName('imageCanvas')

    def set_image(self, image):
        self.original = QPixmap.fromImage(image) if image else QPixmap()
        self.refresh()

    def refresh(self):
        if self.original.isNull():
            self.clear()
        else:
            self.setPixmap(self.original.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        self.refresh()
        super().resizeEvent(event)


class PreviewPanel(QFrame):
    request_import = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('content')
        self.source = None
        self.result = None
        self.active_path = None
        self.token = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.tasks = {}
        self.disposed = False
        self.is_video = False
        self.image_ready = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        self.title = QLabel('المعاينة')
        self.title.setObjectName('previewTitle')
        heading.addWidget(self.title, 1)
        self.original_button = SmoothButton('الأصل', variant='ghost')
        self.result_button = SmoothButton('النتيجة', variant='ghost')
        for button in (self.original_button, self.result_button):
            button.setCheckable(True)
            heading.addWidget(button)
        self.original_button.clicked.connect(lambda: self.choose(False))
        self.result_button.clicked.connect(lambda: self.choose(True))
        layout.addLayout(heading)
        self.name = QLabel('')
        self.name.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.name.setObjectName('muted')
        self.name.setMinimumWidth(0)
        layout.addWidget(self.name)
        self.stack = QStackedWidget()
        self.empty = AddArea()
        self.empty.activated.connect(lambda: self.request_import.emit() if self.source is None else None)
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch()
        mark = QLabel()
        mark.setPixmap(QPixmap(str(resource_dir() / 'assets' / 'maher-mark.png')).scaled(
            112, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(mark)
        empty_title = QLabel('أضف ملفاتك')
        empty_title.setObjectName('sectionTitle')
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        self.empty_note = QLabel('أضف صوراً أو فيديوهات، أو اسحبها إلى هنا.')
        self.empty_note.setObjectName('muted')
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setWordWrap(True)
        empty_layout.addWidget(self.empty_note)
        empty_layout.addStretch()
        for label in self.empty.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.stack.addWidget(self.empty)
        self.image = ImageCanvas()
        self.stack.addWidget(self.image)
        self.video = QVideoWidget()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.stack.addWidget(self.video)
        layout.addWidget(self.stack, 1)
        self.status = QLabel('المعاينة والضغط على جهازك')
        self.status.setObjectName('previewStatus')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.controls = QWidget()
        controls = QHBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.play_button = SmoothButton('تشغيل', icon_name='play', variant='ghost')
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.seek.setAccessibleName('موضع تشغيل الفيديو')
        self.seek.sliderMoved.connect(lambda position: self.player.setPosition(position))
        controls.addWidget(self.seek, 1)
        self.time = QLabel('00:00 / 00:00')
        self.time.setObjectName('muted')
        self.time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        controls.addWidget(self.time)
        self.external_button = SmoothButton('', icon_name='arrow-square-out', variant='ghost')
        self.external_button.setToolTip('فتح الملف خارج التطبيق')
        self.external_button.setAccessibleName('فتح الملف خارج التطبيق')
        self.external_button.clicked.connect(self.open_external)
        heading.addWidget(self.external_button)
        layout.addWidget(self.controls)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda duration: self.seek.setRange(0, int(min(duration, 2147483647))))
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(self.playback_error)
        self.clear()

    def set_files(self, source, result=None):
        self.source, self.result = Path(source), result
        self.result_button.setEnabled(bool(result and result.output and Path(result.output).is_file()))
        self.original_button.setEnabled(True)
        self.choose(False)

    def choose(self, output=False):
        if self.source is None:
            return
        path = Path(self.result.output) if output and self.result and self.result.output else self.source
        self.original_button.setChecked(not output)
        self.result_button.setChecked(output)
        if path == self.active_path:
            return
        self.pause()
        self.player.setSource(QUrl())
        self.active_path = path
        self.original_button.setChecked(not output)
        self.result_button.setChecked(output)
        self.name.setText(self.name.fontMetrics().elidedText(path.name, Qt.TextElideMode.ElideMiddle, max(160, self.width()-45)))
        self.name.setToolTip(str(path))
        self.is_video = path.suffix.lower() not in IMAGE_EXTS
        self.controls.setVisible(self.is_video)
        self.play_button.setVisible(self.is_video)
        self.seek.setVisible(self.is_video)
        self.time.setVisible(self.is_video)
        self.external_button.setEnabled(True)
        self.stack.setCurrentWidget(self.empty)
        self.empty_note.setText('جارٍ تجهيز المعاينة…')
        self.status.setText('جارٍ قراءة الملف…')
        self.token += 1
        task = LoadPreview(self.token, path)
        self.tasks[self.token] = task
        task.signals.done.connect(self.loaded)
        self.pool.clear()
        for old in self.tasks.values():
            if old is not task:
                old.cancelled.set()
        self.pool.start(task)
        self.image_ready = False

    def loaded(self, token, image, details):
        self.tasks.pop(token, None)
        if self.disposed or token != self.token:
            return
        self.image_ready = image is not None
        if image is not None:
            self.image.set_image(image)
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.stack.setCurrentWidget(self.image)
        else:
            self.empty_note.setText('تعذّرت المعاينة')
        sizes = ''
        try:
            sizes = human_size(self.active_path.stat().st_size)
            if self.result and self.result.output:
                sizes = f'قبل \u2066{human_size(self.result.before)}\u2069  ·  بعد \u2066{human_size(self.result.after)}\u2069'
                if self.result.status == 'compressed' and self.result.before:
                    sizes += f'  ·  توفير \u2066{1-self.result.after/self.result.before:.0%}\u2069'
        except OSError:
            pass
        self.status.setText(f'\u2066{details}\u2069  ·  {sizes}' if not self.is_video else sizes)

    def show_result(self):
        if self.result_button.isEnabled():
            self.choose(True)

    def toggle_play(self):
        if not self.active_path or not self.is_video:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            url = QUrl.fromLocalFile(str(self.active_path))
            if self.player.source() != url:
                self.player.setSource(url)
            self.stack.setCurrentWidget(self.video)
            self.player.play()

    def pause(self):
        self.player.pause()

    def playback_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText('إيقاف مؤقت' if playing else 'تشغيل')
        self.play_button.set_icon_name('pause' if playing else 'play')

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(min(position, 2147483647)))
        def stamp(ms):
            seconds = ms // 1000
            return f'{seconds//60:02}:{seconds%60:02}'
        self.time.setText(f'{stamp(position)} / {stamp(self.player.duration())}')

    def playback_error(self, *args):
        if self.active_path and not self.player.source().isEmpty():
            self.status.setText('تعذّر تشغيل المعاينة. افتح الملف خارج التطبيق، أو جرّب ضغطه إلى MP4.')
            if self.image_ready:
                self.stack.setCurrentWidget(self.image)

    def open_external(self):
        if self.active_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.active_path)))

    def clear(self):
        self.pause()
        self.player.setSource(QUrl())
        self.token += 1
        self.source = self.result = self.active_path = None
        self.pool.clear()
        for task in self.tasks.values():
            task.cancelled.set()
        self.image.set_image(None)
        self.stack.setCurrentWidget(self.empty)
        self.empty_note.setText('أضف صوراً أو فيديوهات، أو اسحبها إلى هنا.')
        self.name.clear()
        self.status.setText('المعاينة والضغط على جهازك')
        for widget in (self.play_button, self.seek, self.time):
            widget.hide()
        self.controls.hide()
        for button in (self.original_button, self.result_button, self.external_button):
            button.setEnabled(False)
            button.setChecked(False)

    def dispose(self):
        self.disposed = True
        self.clear()
        self.pool.waitForDone()
