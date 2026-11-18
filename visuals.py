"""Bounded native glass controls, shared tokens and official Phosphor icons."""
from functools import lru_cache
import os
import time

from PIL import Image, ImageFilter
from PySide6.QtCore import Qt, QSize, QRectF, QRect, QPoint, Property, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QImage, QIcon, QPixmap, QPen, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QFrame, QPushButton, QApplication

from engine import resource_dir

INK = "#163849"
ACCENT = "#107E73"
MUTED = "#526C73"


def is_dark(widget):
    parent = widget
    while parent is not None:
        if hasattr(parent, 'dark_mode'):
            return parent.dark_mode
        parent = parent.parentWidget()
    return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 100


def effects_reduced(widget):
    parent = widget
    while parent is not None:
        if hasattr(parent, 'reduced_effects'):
            return parent.reduced_effects
        parent = parent.parentWidget()
    return True


def icon(name, color=None):
    return rendered_icon(name, color or QApplication.palette().color(QPalette.ColorRole.Text).name())


@lru_cache(maxsize=128)
def rendered_icon(name, color):
    source = resource_dir() / "assets" / "icons" / (name + ".svg")
    if not source.exists():
        return QIcon()
    data = source.read_bytes().replace(b"currentColor", color.encode())
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def conservative_effects():
    if os.name != "nt":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            if winreg.QueryValueEx(key, "EnableTransparency")[0] == 0:
                return True
        import ctypes
        class HighContrast(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint), ("flags", ctypes.c_uint), ("scheme", ctypes.c_void_p)]
        state = HighContrast(ctypes.sizeof(HighContrast), 0, None)
        if ctypes.windll.user32.SystemParametersInfoW(0x0042, state.size, ctypes.byref(state), 0):
            if state.flags & 1:
                return True
        animations = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(animations), 0):
            if not animations.value:
                return True
    except (OSError, ValueError, ImportError):
        pass
    return False


class Backdrop(QWidget):
    """A static pearl/emerald application backdrop, cached at the actual window size."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.revision = 0

    def rebuild(self):
        if self.size().isEmpty():
            return
        self.image = QImage(self.size(), QImage.Format.Format_RGBA8888)
        painter = QPainter(self.image)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        dark = is_dark(self)
        gradient.setColorAt(0, QColor("#111E24" if dark else "#E4EFEE"))
        gradient.setColorAt(0.45, QColor("#1C3034" if dark else "#F5F8F8"))
        gradient.setColorAt(1, QColor("#12282B" if dark else "#DDEBEA"))
        painter.fillRect(self.rect(), gradient)
        # A restrained directional band supplies real optical variation under chrome.
        band = QPainterPath()
        band.moveTo(self.width() * .58, 0)
        band.cubicTo(self.width() * .8, self.height() * .12, self.width() * .4, self.height() * .82, self.width(), self.height())
        band.lineTo(self.width(), 0)
        band.closeSubpath()
        painter.fillPath(band, QColor(16, 126, 115, 12))
        painter.end()
        self.revision += 1

    def resizeEvent(self, event):
        self.rebuild()
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self.image.size() != self.size():
            self.rebuild()
        painter = QPainter(self)
        painter.drawImage(0, 0, self.image)


class GlassBar(QFrame):
    """Regular glass only. No content tables/forms use this material."""
    def __init__(self, parent=None, radius=18):
        super().__init__(parent)
        self.radius = radius
        self._cache_key = None
        self._blurred = QImage()
        self._sample = QImage()
        self.blur_build_ms = 0.0
        self.last_paint_ms = 0.0

    def paintEvent(self, event):
        started = time.perf_counter()
        canvas = getattr(self.window(), "canvas", None)
        reduced = getattr(self.window(), "reduced_effects", True)
        dark = is_dark(self)
        rect = QRectF(self.rect()).adjusted(.6, .6, -.6, -.6)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.setClipPath(path)
        if canvas is not None and not reduced and not canvas.image.isNull():
            point = self.mapTo(canvas, QPoint(0, 0))
            key = (canvas.revision, point.x(), point.y(), self.width(), self.height())
            if key != self._cache_key:
                before = time.perf_counter()
                crop = canvas.image.copy(QRect(point, self.size())).convertToFormat(QImage.Format.Format_RGBA8888)
                self._sample = crop
                pil = Image.frombytes("RGBA", (crop.width(), crop.height()), bytes(crop.constBits()))
                pil = pil.filter(ImageFilter.GaussianBlur(11))
                raw = pil.tobytes()
                self._blurred = QImage(raw, pil.width, pil.height, pil.width * 4, QImage.Format.Format_RGBA8888).copy()
                self._cache_key = key
                self.blur_build_ms = (time.perf_counter() - before) * 1000
            painter.drawImage(self.rect(), self._blurred)
            painter.fillPath(path, QColor(19, 37, 41, 160) if dark else QColor(255, 255, 255, 148))
            inner = QPainterPath()
            inner.addRoundedRect(rect.adjusted(2, 2, -2, -2), max(0, self.radius - 2), max(0, self.radius - 2))
            painter.save()
            painter.setClipPath(path.subtracted(inner))
            # Subtle magnified rim refracts the same actual backdrop; it never moves text.
            painter.drawImage(QRectF(-2, -1, self.width() + 4, self.height() + 2), self._sample)
            painter.restore()
        else:
            painter.fillPath(path, QColor("#203438" if dark else "#EFF5F4"))
        painter.setClipping(False)
        rim = QLinearGradient(0, 0, 0, self.height())
        rim.setColorAt(0, QColor(132, 184, 169, 155) if dark else QColor(255, 255, 255, 245))
        rim.setColorAt(.6, QColor(61, 96, 91, 150) if dark else QColor(192, 210, 208, 150))
        rim.setColorAt(1, QColor(82, 131, 119, 150) if dark else QColor(167, 193, 190, 170))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(rim, 1))
        painter.drawRoundedRect(rect, self.radius, self.radius)
        painter.end()
        self.last_paint_ms = (time.perf_counter() - started) * 1000


class SmoothButton(QPushButton):
    """Native button semantics with short paint-only hover/focus feedback."""
    def __init__(self, text="", parent=None, variant="secondary", icon_name=None):
        super().__init__(text, parent)
        self.variant = variant
        self._hover = 0.0
        self._sheen = 0.0
        self.icon_name = icon_name
        self.animation = QPropertyAnimation(self, b"hoverAmount", self)
        self.animation.setDuration(130)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.sheen_animation = QPropertyAnimation(self, b"sheenPhase", self)
        self.sheen_animation.setDuration(1600)
        self.sheen_animation.setStartValue(0.)
        self.sheen_animation.setEndValue(1.)
        self.sheen_animation.setLoopCount(-1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if icon_name:
            self.setIcon(icon(icon_name, "#FFFFFF" if variant == "primary" else INK))
        self.setIconSize(QSize(19, 19))
        if not text and icon_name:
            self.setFixedWidth(38)

    def get_hover(self):
        return self._hover

    def set_hover(self, value):
        self._hover = value
        self.update()

    hoverAmount = Property(float, get_hover, set_hover)

    def get_sheen(self):
        return self._sheen

    def set_sheen(self, value):
        self._sheen = value
        self.update()

    sheenPhase = Property(float, get_sheen, set_sheen)

    def set_icon_name(self, name):
        self.icon_name = name
        self.setIcon(icon(name))

    def animate(self, value):
        self.animation.stop()
        if effects_reduced(self):
            self.set_hover(value)
        else:
            self.animation.setStartValue(self._hover)
            self.animation.setEndValue(value)
            self.animation.start()

    def enterEvent(self, event):
        self.animate(1)
        if self.isEnabled() and not effects_reduced(self):
            self.sheen_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.sheen_animation.stop()
        self.animate(0)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.animation.stop(); self.sheen_animation.stop(); self._hover=0
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self.animation.stop(); self.sheen_animation.stop(); self._hover=0
        super().changeEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def sizeHint(self):
        return QSize(max(36, self.fontMetrics().horizontalAdvance(self.text()) + (30 if not self.icon().isNull() else 0) + 28), 38)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        hover = self._hover if self.isEnabled() else 0
        dark = is_dark(self)
        text_color = '#E4F0EC' if dark else INK
        def mix(first, second, amount):
            a, b = QColor(first), QColor(second)
            return QColor(*(round(x+(y-x)*amount) for x, y in zip(a.getRgb(), b.getRgb())))
        if self.variant == "primary":
            fill = mix("#107E73", "#0B6F66", hover) if not self.isDown() else QColor("#095E56")
            foreground = QColor("#FFFFFF")
            border = QColor("#0C7066")
        elif self.variant == "ghost":
            fill = mix('#203A3D', '#30564F', hover) if dark else mix('#F8FBFA', '#E5F3ED', hover)
            if self.isChecked():
                fill = QColor('#30584E' if dark else '#DDEFE6')
            foreground, border = QColor(text_color), QColor('#53766E' if dark else '#B8CEC5')
        else:
            fill = mix('#233B3F', '#34564F', hover) if dark else mix('#FFFFFF', '#EDF7F4', hover)
            if self.isDown():
                fill = QColor('#142D2F' if dark else '#DCECE8')
            foreground = QColor(('#FFB8A9' if dark else '#A33833') if self.variant == 'danger' else text_color)
            border = QColor('#53766E' if dark else '#B8CEC5')
        if not self.isEnabled():
            fill, foreground, border = (QColor('#24373B'), QColor('#89A19A'), QColor('#3C5550')) if dark else (QColor('#EAF0EE'), QColor('#738783'), QColor('#D0DDD7'))
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 10, 10)
        if hover and self.isEnabled():
            sheen = QLinearGradient(0, 0, self.width(), self.height())
            sheen.setColorAt(0, QColor(255, 255, 255, round(38*hover)))
            sheen.setColorAt(.55, QColor(255, 255, 255, 0))
            sheen.setColorAt(1, QColor(137, 209, 187, round(18*hover)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(sheen)
            painter.drawRoundedRect(rect, 10, 10)
            if self.sheen_animation.state() == QPropertyAnimation.State.Running:
                painter.save()
                clip = QPainterPath()
                clip.addRoundedRect(rect, 10, 10)
                painter.setClipPath(clip)
                if self.variant == 'primary':
                    painter.setClipRect(QRectF(0, 0, self.width(), 7), Qt.ClipOperation.IntersectClip)
                center = -self.width()*.5 + self._sheen*self.width()*2
                sweep = QLinearGradient(center-34, 0, center+34, self.height())
                sweep.setColorAt(0, QColor(255, 255, 255, 0))
                sweep.setColorAt(.5, QColor(255, 255, 255, 42 if dark else 110))
                sweep.setColorAt(1, QColor(255, 255, 255, 0))
                painter.fillRect(self.rect(), sweep)
                painter.restore()
        if self.hasFocus():
            painter.setPen(QPen(QColor("#82E0BF" if dark else "#107E73"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        text_rect = self.rect().adjusted(12, 0, -12, 0)
        if not self.icon().isNull():
            rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
            x = self.width() - 14 - 19 if rtl else 14
            drawing_icon = icon(self.icon_name, foreground.name()) if self.icon_name else self.icon()
            drawing_icon.paint(painter, QRect(x, (self.height() - 19) // 2, 19, 19), Qt.AlignmentFlag.AlignCenter,
                              QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
            text_rect.adjust(0 if rtl else 25, 0, -25 if rtl else 0, 0)
        painter.setPen(foreground)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()


STYLES = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #163849; }
QMainWindow { background: #EDF4F3; }
QFrame#content { background: #FFFFFF; border: 1px solid #D9E4E1; border-radius: 16px; }
QFrame#divider { background: #DFE9E5; max-height: 1px; }
QLabel#brandTitle { font-size: 19pt; font-weight: 650; }
QLabel#sectionTitle { font-size: 12pt; font-weight: 650; }
QLabel#muted { color: #526C73; font-size: 9pt; }
QLabel#summary { color: #0A6B5D; font-weight: 650; }
QLabel#previewTitle { font-size: 12pt; font-weight: 650; }
QLabel#previewStatus { color: #526C73; font-size: 9pt; }
QLineEdit { background: #F5F8F7; border: 1px solid #D8E3E0; border-radius: 7px; padding: 6px 8px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #107E73; }
QSpinBox, QDoubleSpinBox { background: #F6F9F8; border: 1px solid #D3E0DB; border-radius: 7px; padding: 5px 7px; min-height: 24px; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; color: #526C73; padding: 7px 18px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #0B7166; border-bottom: 2px solid #107E73; font-weight: 650; }
QTabBar::tab:hover { background: #EDF6F2; }
QTableWidget { background: white; border: none; selection-background-color: #E4F1EB; selection-color: #163849; gridline-color: white; }
QTableWidget::item { padding: 7px 9px; border-bottom: 1px solid #EFF3F1; }
QTableWidget::item:hover { background: #F0F7F3; }
QTableWidget:focus { outline: 2px solid #107E73; }
QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: #DEE7E3; }
QSlider::sub-page:horizontal { background: #107E73; border-radius: 2px; }
QSlider::handle:horizontal { background: #107E73; border: 2px solid #FFFFFF; width: 17px; margin: -7px 0; border-radius: 9px; }
QSlider::handle:horizontal:hover { background: #095E56; border: 2px solid #B5DCD0; }
QProgressBar { background: #DCE7E2; border: none; border-radius: 3px; min-height: 5px; max-height: 5px; }
QProgressBar::chunk { background: #107E73; border-radius: 3px; }
QCheckBox { spacing: 7px; color: #385A5C; font-size: 9pt; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #9FB8B0; border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #107E73; border: 1px solid #107E73; }
QToolTip { background: #163849; color: white; border: none; padding: 7px; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #C4D7CD; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: transparent; }
QDialog { background: #F7FAF8; }
"""

STYLES += '''
QLabel#imageCanvas { background: #EFF4F2; border-radius: 12px; }
QLabel#logoPlate { background: #F6FAF8; border: 1px solid #B8CEC5; border-radius: 12px; }
QPushButton { background: #F8FBFA; border: 1px solid #B8CEC5; border-radius: 8px; padding: 7px 12px; }
QPushButton:hover { background: #E5F3ED; border-color: #107E73; }
QPushButton:focus { border: 2px solid #107E73; }
QPushButton:disabled { color: #738783; background: #EAF0EE; border-color: #D0DDD7; }
QTextEdit, QPlainTextEdit { background: #F6F9F8; color: #163849; border: 1px solid #D3E0DB; border-radius: 9px; padding: 10px; }
QMenu { background: #FFFFFF; color: #163849; border: 1px solid #B8CEC5; padding: 6px; }
QMenu::item { padding: 7px 14px; }
QMenu::item:selected { background: #E4F1EB; }
QFrame#emptyAdd { background: #F6FAF8; border: 1px dashed #BDD2C8; border-radius: 12px; }
QFrame#emptyAdd:hover { background: #EDF7F2; border: 1px solid #107E73; }
QLabel#wordmark { color: #163849; font-size: 21pt; font-weight: 650; }
QLabel#byline { color: #107E73; font-size: 9pt; }
QLabel#byline:hover { color: #095E56; text-decoration: underline; }
QCheckBox::indicator:checked { image: url(assets/icons/check-circle.svg); }
'''


STYLES = STYLES.replace('url(assets/icons/check-circle.svg)', 'url("'+(resource_dir()/'assets/icons/check-circle.svg').as_posix()+'")')


def theme_styles(dark=False):
    if not dark:
        return STYLES
    replacements = {
        '#163849':'#E4F0EC', '#EDF4F3':'#14262B', '#FFFFFF':'#192C31',
        '#D9E4E1':'#3D5852', '#DFE9E5':'#3D5852', '#526C73':'#B0C6BF',
        '#0A6B5D':'#82E0BF', '#F5F8F7':'#20373A', '#D8E3E0':'#4B6961',
        '#107E73':'#73D7B5', '#F6F9F8':'#20373A', '#D3E0DB':'#4B6961',
        '#0B7166':'#86E3C3', '#EDF6F2':'#284C43', '#E4F1EB':'#2A5146',
        '#EFF3F1':'#263F40', '#F0F7F3':'#25483F', '#DEE7E3':'#3B5751',
        '#095E56':'#9FE9D0', '#B5DCD0':'#A0E5CD', '#DCE7E2':'#3B5751',
        '#385A5C':'#C4D6CE', '#9FB8B0':'#6E9285', '#C4D7CD':'#5B8072',
        '#F7FAF8':'#14262B', '#F8FBFA':'#243D3F', '#B8CEC5':'#53766E',
        '#E5F3ED':'#30564F', '#738783':'#92AAA0', '#EAF0EE':'#24373B',
        '#D0DDD7':'#3C5550', '#F6FAF8':'#1D3336', '#BDD2C8':'#4B7062',
        '#EDF7F2':'#24483C', '#EFF4F2':'#112126',
    }
    import re
    result = re.sub(r'#[0-9A-Fa-f]{6}', lambda match: replacements.get(match.group().upper(), match.group()), STYLES.replace(': white', ': #FFFFFF'))
    return result+'\nQToolTip { background: #E4F0EC; color: #14262B; }\nQLabel#logoPlate { background: #EDF5F1; border-color: #6A8C7E; }'


def apply_palette(dark=False):
    app = QApplication.instance()
    palette = QPalette()
    roles = QPalette.ColorRole
    colors = {
        roles.Window: '#14262B' if dark else '#F7FAF8',
        roles.WindowText: '#E4F0EC' if dark else INK,
        roles.Base: '#20373A' if dark else '#FFFFFF',
        roles.AlternateBase: '#243F3E' if dark else '#F3F8F5',
        roles.Text: '#E4F0EC' if dark else INK,
        roles.Button: '#243D3F' if dark else '#F8FBFA',
        roles.ButtonText: '#E4F0EC' if dark else INK,
        roles.Highlight: '#305F4F' if dark else '#CEE9DC',
        roles.HighlightedText: '#FFFFFF' if dark else INK,
        roles.ToolTipBase: '#163849', roles.ToolTipText: '#FFFFFF',
        roles.PlaceholderText: '#A1BFB1' if dark else '#526C73',
        roles.Link: '#82E0BF' if dark else '#107E73',
    }
    for role, value in colors.items():
        palette.setColor(role,QColor(value))
    palette.setColor(QPalette.ColorGroup.Disabled,roles.Text,QColor('#8DA69B' if dark else '#738783'))
    palette.setColor(QPalette.ColorGroup.Disabled,roles.ButtonText,QColor('#8DA69B' if dark else '#738783'))
    app.setPalette(palette)
    app.setStyleSheet(theme_styles(dark))


def apply_window_theme(widget, dark):
    if os.name != 'nt':
        return
    try:
        import ctypes
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(widget.winId()),20,ctypes.byref(value),ctypes.sizeof(value))
    except (OSError,AttributeError):
        pass
