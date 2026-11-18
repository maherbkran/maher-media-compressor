"""Startup boundary; portable diagnostics never open a desktop error dialog."""
from pathlib import Path
import json,os,sys,traceback


def launch():
    self_test=len(sys.argv)==3 and sys.argv[1]=='--self-test'
    try:
        if self_test:
            os.environ['QT_QPA_PLATFORM']='offscreen'
            os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--disable-gpu'
        import desktop_window
        if self_test:
            from diagnostics import run_smoke_test
            from desktop_smoke import run_desktop_smoke
            app=desktop_window.QApplication([]);app.setStyle('Fusion')
            window=desktop_window.DesktopWindow()
            folder=Path(sys.argv[2]).resolve()
            status=run_smoke_test(folder)
            if status==0:run_desktop_smoke(window,app,folder)
            window.force_close=True;window.close();app.processEvents()
            return status
        desktop_window.main();return 0
    except Exception:
        error=traceback.format_exc()
        if self_test:
            folder=Path(sys.argv[2]);folder.mkdir(parents=True,exist_ok=True)
            (folder/'report.json').write_text(json.dumps({'ok':False,'error':error},indent=2),encoding='utf-8')
        else:
            import tempfile
            report=Path(tempfile.gettempdir())/'MediaPress-startup-error.txt';report.write_text(error,encoding='utf-8')
            if os.name=='nt':
                import ctypes
                ctypes.windll.user32.MessageBoxW(None,f'تعذّر تشغيل البرنامج.\nفك الحزمة بالكامل مع مجلد _internal.\n\nتفاصيل الخطأ:\n{report}','MediaPress',0x10)
        return 1

if __name__=='__main__':sys.exit(launch())
