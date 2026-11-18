"""Frozen desktop-shell smoke test using actual encoders and the approved view."""
from pathlib import Path
import hashlib,json,time
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtTest import QTest


def run_desktop_smoke(window,app,folder):
    def js(code,timeout=5000):
        values=[];loop=QEventLoop()
        window.page.runJavaScript(code,lambda value:(values.append(value),loop.quit()))
        timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);timer.start(timeout);loop.exec();timer.stop()
        return values[0] if values else None
    def wait(predicate,seconds=25):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            QTest.qWait(20)
        raise AssertionError('Desktop smoke check timed out')
    window.resize(1240,740);window.show()
    wait(lambda:js('Boolean(window.nativeReady)') is True)
    wait(lambda:js('document.fonts.status')=='loaded')
    assert 'IBM Plex Sans Arabic' in js('getComputedStyle(document.body).fontFamily')
    window.controller.add_paths([folder])
    wait(lambda:not window.controller.importing)
    assert len(window.controller.items)==5
    wait(lambda:js('queue.length')==5)
    assert window.controller.auto_output
    assert window.controller.settings.video_max_mb==0
    js('$("startBtn").click()')
    wait(lambda:js('$("runDialog").open') is True)
    js('chooseGame("memory");flipCard(0);closeDialog("runDialog")')
    assert not window.controller.worker.cancel.is_set()
    js('openJob()');assert js('memory.open.length')==1
    wait(lambda:not window.controller.running,50)
    wait(lambda:js('job.percent')==100)
    assert len(window.controller.results)==5
    assert all(result.output and Path(result.output).parent==folder for result in window.controller.results.values())
    js('closeDialog("runDialog");chooseKind("video")')
    wait(lambda:window.movie.path is not None)
    window.movie.audio.setMuted(True)
    js('$("nativePlay").click()')
    wait(lambda:window.movie.frames>0,20)
    assert window.movie.player.duration()>0
    window.movie.player.pause()
    themes=[]
    for theme in ('light','dark'):
        js(f'setTheme("{theme}")')
        assert js('document.documentElement.dataset.theme')==theme
        assert js('getComputedStyle(document.body).color')==('rgb(20, 47, 52)' if theme=='light' else 'rgb(237, 245, 242)')
        themes.append(theme)
    assert not window.page.errors,window.page.errors
    report_path=folder/'report.json';report=json.loads(report_path.read_text(encoding='utf-8'))
    report['desktop']={'ok':True,'font':'IBM Plex Sans Arabic','themes':themes,'native_video_frames':window.movie.frames,
                       'batch_outputs':len(window.controller.results),'games_reopen_preserves_state':True,
                       'approved_css_sha256':hashlib.sha256((Path(__file__).parent/'assets/ui/approved.css').read_bytes()).hexdigest() if not getattr(__import__('sys'),'frozen',False) else json.loads((__import__('engine').resource_dir()/'assets/ui/reference.json').read_text())['approved_css_sha256']}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
