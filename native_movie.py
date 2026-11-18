"""Native local playback aligned to the approved HTML video stage."""
from pathlib import Path
import time
from PySide6.QtCore import QObject,QUrl,Qt,QRect
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QRegion,QPainterPath

class NativeMovie(QObject):
    def __init__(self,window,controller):
        super().__init__(window);self.window=window;self.controller=controller
        self.surface=QVideoWidget(window.view);self.surface.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.surface.hide()
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.surface)
        self.path=None;self.visible=False;self.first_frame=False;self.rect=QRect();self.last_emit=0;self.frames=0
        self.player.positionChanged.connect(self.emit_state);self.player.durationChanged.connect(lambda _:self.emit_state(force=True))
        self.player.playbackStateChanged.connect(lambda _:self.emit_state(force=True));self.player.errorOccurred.connect(self.on_error)
        self.surface.videoSink().videoFrameChanged.connect(self.on_frame)

    def handle(self,request):
        command=request.get('command')
        if command=='geometry':
            self.visible=bool(request.get('visible'))
            if not self.visible:self.player.pause();self.surface.hide();return
            item=self.controller.find_item(request.get('id'))
            if not item:return
            path=Path(item['result']['path']) if request.get('output') and item.get('result') else item['source']
            if path!=self.path:
                self.player.stop();self.first_frame=False;self.path=path;self.surface.hide();self.player.setSource(QUrl.fromLocalFile(str(path)))
            values=request.get('rect',{})
            x=max(-5000,min(5000,int(values.get('x',0))));y=max(-5000,min(5000,int(values.get('y',0))))
            width=max(1,min(self.window.view.width(),int(values.get('width',1))));height=max(1,min(self.window.view.height(),int(values.get('height',1))))
            self.rect=QRect(x,y,width,height);self.surface.setGeometry(self.rect)
            path_mask=QPainterPath();path_mask.addRoundedRect(0,0,width,height,10,10)
            self.surface.setMask(QRegion(path_mask.toFillPolygon().toPolygon()))
            self.surface.setVisible(self.first_frame and self.visible);self.surface.raise_();return
        if command=='play':
            if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
            else:
                if self.player.duration()>0 and self.player.position()>=self.player.duration()-100:self.player.setPosition(0)
                self.player.play()
        elif command=='seek':self.player.setPosition(max(0,min(self.player.duration(),int(request.get('position',0)))))
        elif command=='mute':self.audio.setMuted(not self.audio.isMuted());self.emit_state(force=True)
        elif command=='pause':self.player.pause()

    def on_frame(self,frame):
        if frame.isValid():
            self.frames+=1
            if not self.first_frame:
                self.first_frame=True;self.surface.setVisible(self.visible);self.surface.raise_();self.emit_state(force=True)

    def emit_state(self,*args,force=False):
        now=time.monotonic()
        if not force and now-self.last_emit<.12:return
        self.last_emit=now
        self.controller.emit_event('media',position=self.player.position(),duration=self.player.duration(),playing=self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState,muted=self.audio.isMuted(),error='')

    def on_error(self,*args):
        self.surface.hide();self.first_frame=False
        self.controller.emit_event('media',position=0,duration=0,playing=False,muted=self.audio.isMuted(),error='معاينة هذه الصيغة غير متاحة. يمكنك ضغطها أو فتح الأصل خارج البرنامج.')

    def shutdown(self):self.player.stop();self.player.setSource(QUrl());self.surface.hide()
