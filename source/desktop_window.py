"""Approved HTML desktop shell with a native streaming export controller."""
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt,QCoreApplication,QUrl,QFile,QIODevice,QTimer,Signal,QEvent,Slot
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtGui import QIcon,QColor,QDesktopServices
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineUrlRequestInterceptor,QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel
from engine import resource_dir
from branding import VERSION,WHATSAPP_URL
from local_media import MediaServer
from desktop_controller import DesktopController
from native_movie import NativeMovie
from visuals import apply_window_theme,apply_palette


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def __init__(self,server,parent=None):
        super().__init__(parent);self.server=server;self.blocked=[]
    def interceptRequest(self,info):
        url=info.requestUrl();scheme=url.scheme()
        allowed=scheme in ('data','blob','about') or (scheme=='http' and url.host()=='127.0.0.1' and url.port()==self.server.http.server_port and url.path().startswith('/'+self.server.token+'/'))
        if not allowed:
            if len(self.blocked)<30:self.blocked.append(url.toString()[:180])
            info.block(True)


class LocalPage(QWebEnginePage):
    script_error=Signal(str)
    def __init__(self,profile,server,parent=None):
        super().__init__(profile,parent);self.server=server;self.errors=[]
    def acceptNavigationRequest(self,url,kind,is_main):
        local=url.toString().startswith(self.server.base) and (not is_main or url.path() in ('/'+self.server.token+'/', '/'+self.server.token+'/index.html'))
        if local or url.toString()=='about:blank':return True
        if kind==QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme()=='https':
            allowed={'wa.me','www.pexels.com','github.com','www.ffmpeg.org','pillow.readthedocs.io'}
            if url.host() in allowed:QDesktopServices.openUrl(url)
        return False
    def javaScriptConsoleMessage(self,level,message,line,source):
        if level==QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.errors.append(f'{line}: {message}');self.script_error.emit(message)


class DesktopView(QWebEngineView):
    def __init__(self,parent=None):super().__init__(parent);self.controller=None;self.setAcceptDrops(True);self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F5 or (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_R):event.accept();return
        super().keyPressEvent(event)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and not (self.controller.running or self.controller.importing):event.acceptProposedAction()
        else:event.ignore()
    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
        else:event.ignore()
    def dropEvent(self,event):
        paths=[Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.controller.add_paths(paths);event.acceptProposedAction()


class DesktopWindow(QMainWindow):
    loaded=Signal(bool)
    def __init__(self):
        super().__init__();self.setWindowTitle('MediaPress');self.setWindowIcon(QIcon(str(resource_dir()/'app.ico')))
        self.setMinimumSize(960,650);self.resize(1240,760);self.force_close=False;self.cleaned=False
        self.server=MediaServer(resource_dir()/'assets/ui')
        self.view=DesktopView(self);self.setCentralWidget(self.view)
        self.controller=DesktopController(self,self.server);self.view.controller=self.controller
        self.movie=NativeMovie(self,self.controller)
        self.controller.message.connect(self.push)
        self.profile=QWebEngineProfile(self.view);self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.profile.setHttpAcceptLanguage('ar,en-US;q=0.8,en;q=0.6')
        self.guard=LocalOnly(self.server,self.profile);self.profile.setUrlRequestInterceptor(self.guard)
        self.profile.downloadRequested.connect(lambda request:request.cancel())
        self.page=LocalPage(self.profile,self.server,self.view);self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor('#eff4f2'))
        settings=self.page.settings();settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled,False)
        self.channel=QWebChannel(self.page);self.channel.registerObject('desktop',self.controller);self.page.setWebChannel(self.channel)
        channel=QFile(':/qtwebchannel/qwebchannel.js')
        if not channel.open(QIODevice.OpenModeFlag.ReadOnly):raise RuntimeError('Qt WebChannel resource missing')
        self.server.channel=bytes(channel.readAll());channel.close()
        root=resource_dir()/'assets/ui'
        body=(root/'approved-body.html').read_text(encoding='utf-8')
        body=body.replace('<video id="previewVideo"','<video id="previewVideo"')
        body=body.replace('<div class="readouts">','<div class="readouts">')
        body=body.replace('</video>','</video><button class="btn mini" id="nativeOpenOriginal" hidden>فتح الأصل خارج البرنامج</button>',1)
        body=body.replace('</video>', '</video><div id="nativeVideoControls" hidden><button class="btn mini" id="nativePlay">تشغيل</button><div id="nativeSeekRail" class="range-area" style="--v:0%;--thumb:22px"><div class="range-geometry"><div class="range-track"><div class="range-fill"></div></div><div class="range-lens"></div></div><input type="range" id="nativeSeek" min="0" max="1" value="0" aria-label="موضع تشغيل الفيديو"></div><span id="nativeTime" dir="ltr">00:00 / 00:00</span><button class="btn mini" id="nativeMute" aria-label="كتم أو تشغيل الصوت"></button></div>',1)
        body=body.replace('<div class="profile-contact">','<p class="native-note" dir="ltr" style="text-align:center">+971543386217</p><div class="profile-contact">')
        dialogs=(root/'native-dialogs.html').read_text(encoding='utf-8')
        self.server.index=(f'<!doctype html><html lang="ar" dir="rtl" data-theme="{self.controller.theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MediaPress</title><link rel="icon" href="data:,"><link rel="stylesheet" href="approved.css"><link rel="stylesheet" href="native.css"></head><body>'+body+dialogs+'<script src="qwebchannel.js"></script><script src="desktop.js"></script><script src="approved-games.js"></script><script>initializeDesktop();</script></body></html>').encode('utf-8')
        self.controller.closeReady.connect(self.close_after_stop)
        self.page.loadFinished.connect(self.loaded.emit)
        self.server.start();self.view.load(QUrl(self.server.base));self.set_theme(self.controller.theme)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,watched,event):
        kinds=(QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop,QEvent.Type.DragLeave)
        if event.type() in kinds:
            parent=watched;inside=False
            while parent is not None:
                if parent is self.view:inside=True;break
                parent=parent.parent()
            if inside:
                if event.type()==QEvent.Type.DragLeave:
                    self.page.runJavaScript('document.querySelector(".queue")?.classList.remove("drag")');return False
                mime=event.mimeData()
                if mime.hasUrls():
                    paths=[Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
                    if paths and not (self.controller.running or self.controller.importing):
                        event.acceptProposedAction()
                        if event.type()==QEvent.Type.Drop:
                            self.page.runJavaScript('document.querySelector(".queue")?.classList.remove("drag")')
                            self.controller.add_paths(paths)
                        else:self.page.runJavaScript('document.querySelector(".queue")?.classList.add("drag")')
                    else:event.ignore()
                    return True
        return super().eventFilter(watched,event)

    @Slot(str)
    def push(self,raw):
        import json
        self.page.runJavaScript('if(typeof receive==="function")receive('+json.dumps(raw)+')')

    def set_theme(self,theme):
        self.dark_mode=theme=='dark';apply_palette(self.dark_mode);apply_window_theme(self,self.dark_mode)

    def close_after_stop(self):
        self.force_close=True;self.close()

    def closeEvent(self,event):
        if (self.controller.running or self.controller.importing) and not self.force_close:
            self.page.runJavaScript('openCloseDialog()');event.ignore();return
        if not self.cleaned:
            self.cleaned=True;QApplication.instance().removeEventFilter(self);self.page.triggerAction(QWebEnginePage.WebAction.Stop)
            self.movie.shutdown();self.controller.shutdown();self.server.close()
        event.accept()

    def changeEvent(self,event):
        if event.type()==QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.page.runJavaScript('if(typeof pauseGames==="function")pauseGames()')
            self.movie.player.pause()
        super().changeEvent(event)


def main():
    app=QApplication(sys.argv);app.setApplicationName('MediaPress');app.setApplicationVersion(VERSION);app.setStyle('Fusion')
    window=DesktopWindow();available=app.primaryScreen().availableGeometry()
    window.resize(min(1240,available.width()-28),min(760,available.height()-40));window.show()
    if len(sys.argv)>1:QTimer.singleShot(200,lambda:window.controller.add_paths([Path(p) for p in sys.argv[1:]]))
    sys.exit(app.exec())
