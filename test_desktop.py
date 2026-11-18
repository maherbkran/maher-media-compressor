"""Approved desktop view integration tests with real native exports and playback."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--disable-gpu'
import json,tempfile,time,unittest,hashlib
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QEventLoop,QTimer,Qt,QMimeData,QUrl,QPointF
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from desktop_window import DesktopWindow,QApplication
from engine import resource_dir

class ApprovedDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.window=DesktopWindow();self.window.resize(1366,768);self.window.movie.audio.setMuted(True);self.window.show()
        self.wait(lambda:self.js('Boolean(window.nativeReady)') is True)
    def tearDown(self):
        self.window.force_close=True;self.window.close();self.app.processEvents()
    def js(self,code,timeout=5000):
        values=[];loop=QEventLoop()
        self.window.page.runJavaScript(code,lambda value:(values.append(value),loop.quit()))
        timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);timer.start(timeout);loop.exec();timer.stop()
        return values[0] if values else None
    def wait(self,predicate,timeout=20):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.app.processEvents()
            if predicate():return
            QTest.qWait(20)
        self.fail('Timed out waiting for desktop state')

    def test_reference_css_and_fonts_are_retained_and_both_themes_render(self):
        root=resource_dir()/'assets/ui'
        receipt=json.loads((root/'reference.json').read_text())
        self.assertEqual(hashlib.sha256((root/'approved.css').read_bytes()).hexdigest(),receipt['approved_css_sha256'])
        self.wait(lambda:self.js('document.fonts.status')=='loaded')
        self.assertIn('IBM Plex Sans Arabic',self.js('getComputedStyle(document.body).fontFamily'))
        for theme in ('light','dark'):
            self.js(f'setTheme("{theme}")')
            self.wait(lambda:self.js('document.documentElement.dataset.theme')==theme)
            self.assertEqual(self.js('document.documentElement.dataset.theme'),theme)
            self.assertEqual(self.js('getComputedStyle(document.body).color'),'rgb(20, 47, 52)' if theme=='light' else 'rgb(237, 245, 242)')
            for dialog in ('pickDialog','nativeSettingsDialog','destinationDialog','aboutDialog','helpDialog'):
                self.js(f'showDialog("{dialog}")')
                self.assertTrue(self.js(f'$("{dialog}").open'))
                self.js(f'closeDialog("{dialog}")')
        self.assertEqual(self.window.page.errors,[])

    def test_native_batch_preserves_originals_and_games_reopen_with_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=root/'A';second=root/'B';first.mkdir();second.mkdir()
            photo=first/'صورة Product.bmp';Image.new('RGB',(240,160),'#407B64').save(photo)
            broken=second/'broken.mov';broken.write_bytes(b'not media')
            before=hashlib.sha256(photo.read_bytes()).hexdigest()
            self.window.controller.add_paths([broken,photo])
            self.wait(lambda:not self.window.controller.importing)
            self.wait(lambda:self.js('queue.length')==2)
            self.js('selectItem(queue[1])')
            self.wait(lambda:bool(self.window.controller.items[1]['url']))
            self.js('$("startBtn").click()')
            self.wait(lambda:self.js('$("runDialog").open') is True)
            self.js('chooseGame("memory");flipCard(0);closeDialog("runDialog")')
            self.assertFalse(self.window.controller.worker.cancel.is_set())
            self.js('openJob()')
            self.assertEqual(self.js('memory.open.length'),1)
            self.wait(lambda:not self.window.controller.running,30)
            self.wait(lambda:self.js('job.percent')==100)
            self.assertEqual(self.window.controller.items[0]['status'],'error')
            result=self.window.controller.items[1]['result'];self.assertIsNotNone(result)
            self.assertEqual(Path(result['path']).parent,first)
            self.assertEqual(Path(result['path']).suffix,'.jpg')
            self.assertEqual(hashlib.sha256(photo.read_bytes()).hexdigest(),before)
            self.js('closeDialog("runDialog")')
            self.wait(lambda:bool(self.window.controller.items[1].get('resultThumb')))
            self.wait(lambda:self.js('$("resultBytes").textContent')!='—')
            self.assertEqual(self.window.page.errors,[])


    def test_advanced_cancel_discards_presets_and_apply_commits_them(self):
        original=self.js('JSON.stringify(opts.image)')
        self.js('$("advancedBtn").click();advancedDraft.cap=5;$("nativeWidth").value=720;closeDialog("nativeSettingsDialog")')
        self.assertEqual(self.js('JSON.stringify(opts.image)'),original)
        self.js('$("advancedBtn").click();advancedDraft.cap=5;$("nativeWidth").value=720;$("nativeApply").click()')
        self.assertEqual(self.js('opts.image.cap'),5)
        self.assertEqual(self.js('opts.image.width'),720)
        self.wait(lambda:self.window.controller.settings.image_max_mb==5)

    def test_native_video_playback_seek_and_modal_hiding(self):
        self.js('chooseKind("video")')
        self.wait(lambda:self.window.movie.path is not None)
        self.js('$("nativePlay").click()')
        self.wait(lambda:self.window.movie.frames>0,15)
        self.assertGreater(self.window.movie.player.duration(),0)
        self.js('showDialog("pickDialog")')
        self.wait(lambda:not self.window.movie.surface.isVisible())
        self.js('closeDialog("pickDialog")')
        self.wait(lambda:self.window.movie.visible)
        self.js('send("media",{command:"seek",position:700})')
        self.wait(lambda:self.window.movie.player.position()>=650)
        self.assertEqual(self.window.page.errors,[])

    def test_native_drop_imports_local_files_from_renderer_child(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'dragged.jpg';Image.new('RGB',(80,60),'#507A64').save(source)
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(source))])
            target=self.window.view.focusProxy() or self.window.view
            drag=QDragEnterEvent(target.rect().center(),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(target,drag)
            event=QDropEvent(QPointF(target.rect().center()),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(target,event)
            self.wait(lambda:len(self.window.controller.items)==1 and not self.window.controller.importing)
            self.assertEqual(self.window.controller.items[0]['source'],source)
            self.assertTrue(event.isAccepted())
            self.window.force_close=True;self.window.close()

    def test_approved_memory_game_ten_levels_and_reduced_effects(self):
        self.window.controller.job={'running':False,'percent':100,'finished':1,'total':1,'name':'test','errors':[],'outputs':1,'stopped':False}
        self.window.controller.emit_event('state',state=self.window.controller.snapshot())
        self.js('openJob();chooseGame("memory")')
        for level in range(1,11):
            self.js(f'{{initMemory({level});const groups=new Map();memory.deck.forEach((value,index)=>{{if(!groups.has(value))groups.set(value,[]);groups.get(value).push(index)}});for(const pair of groups.values()){{flipCard(pair[0]);flipCard(pair[1])}}}}')
            self.assertTrue(self.js('memory.won'))
        self.assertEqual(self.js('memory.level'),10)
        self.js('$("fxCheck").checked=true;$("fxCheck").dispatchEvent(new Event("change"))')
        self.assertEqual(self.js('document.documentElement.dataset.effects'),'off')
        self.assertEqual(self.window.page.errors,[])

    def test_dense_queue_is_bounded_and_settings_are_independent(self):
        originals=[{'id':str(i),'name':f'ملف {i}.mp4','size':2000000,'kind':'video','status':'idle','error':'','url':''} for i in range(1000)]
        snapshot=self.window.controller.snapshot();snapshot['items']=originals;snapshot['selected']='0'
        self.js('applyState('+json.dumps(snapshot)+')')
        self.assertLessEqual(self.js('$("fileList").querySelectorAll(".file-row").length'),18)
        self.js('opts.video.quality=66;showSettings();chosenKind="image";opts.image.quality=88;showSettings()')
        self.assertEqual(self.js('settings().video_quality'),66)
        self.assertEqual(self.js('settings().image_quality'),88)
        self.assertFalse(self.js('document.querySelector("#nativeWidth").valueAsNumber>16384'))

if __name__=='__main__':unittest.main()
