"""Small startup boundary: headless diagnostics never open an error dialog."""
from pathlib import Path
import json
import os
import sys
import traceback


def launch():
    self_test = len(sys.argv) == 3 and sys.argv[1] == "--self-test"
    try:
        if self_test:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        import medialite
        if self_test:
            from diagnostics import run_smoke_test
            app = medialite.QApplication([])
            window = medialite.MainWindow()
            assert window.auto_output.isChecked(), "Outputs must follow each source folder by default"
            assert window.export_settings().video_max_mb == 0
            assert window.export_settings().image_max_mb == 0
            assert "ماهر بكران" in medialite.ATTRIBUTION
            assert "+971543386217" in window.whatsapp_button.text()
            window.image_settings.quality_slider.setValue(60)
            window.image_settings.max_size.setValue(0.25)
            window.video_settings.quality.setValue(75)
            window.video_settings.max_size.setValue(7.5)
            controls = window.export_settings()
            assert controls.image_quality == 60 and controls.image_max_mb == 0.25
            assert controls.video_quality == 75 and controls.video_max_mb == 7.5
            window.image_settings.reset_defaults()
            window.video_settings.reset_defaults()
            app.processEvents()
            folder = Path(sys.argv[2]).resolve()
            status = run_smoke_test(folder)
            if status == 0:
                window.add_paths([folder])
                assert len(window.paths) == 5, "Generated outputs must be excluded from folder scans"
                assert window.output_dir == folder, "Automatic output must use the selected source folder"
                window.custom_output_dir = folder.parent
                window.auto_output.setChecked(False)
                window.clear_files()
                window.add_paths([folder])
                assert len(window.paths) == 5, "A custom destination ancestor must not hide source files"
                window.auto_output.setChecked(True)
                assert window.output_dir == folder
            return status
        medialite.main()
        return 0
    except Exception:
        error = traceback.format_exc()
        if self_test:
            folder = Path(sys.argv[2])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "report.json").write_text(json.dumps({"ok": False, "error": error}, indent=2), encoding="utf-8")
        else:
            import tempfile
            report = Path(tempfile.gettempdir()) / "MediaLite-startup-error.txt"
            report.write_text(error, encoding="utf-8")
            if os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, f"تعذّر تشغيل التطبيق.\nفك ضغط المجلد بالكامل، بما فيه _internal.\n\nتفاصيل الخطأ:\n{report}", "MediaLite", 0x10)
        return 1


if __name__ == "__main__":
    sys.exit(launch())
