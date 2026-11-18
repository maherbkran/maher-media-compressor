"""Offscreen UI and mixed-batch integration tests; never sends desktop input."""
import os
import hashlib
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from PIL import Image

from engine import Compressor, ExportSettings
from medialite import MainWindow, BatchWorker
from diagnostics import run_smoke_test


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_sliders_numeric_fields_are_synced_and_independent(self):
        self.window.image_settings.quality_slider.setValue(60)
        self.assertEqual(self.window.image_settings.quality.value(), 60)
        self.window.video_settings.quality.setValue(45)
        self.assertEqual(self.window.video_settings.quality_slider.value(), 45)
        self.window.image_settings.size_slider.setValue(150)
        self.assertEqual(self.window.image_settings.max_size.value(), 1.5)
        self.window.video_settings.max_size.setValue(7.55)
        self.assertEqual(self.window.video_settings.max_size.value(), 7.55)
        snapshot = self.window.export_settings()
        self.assertEqual(snapshot.image_quality, 60)
        self.assertEqual(snapshot.video_quality, 45)
        self.assertEqual(snapshot.video_max_mb, 7.55)
        self.window.image_settings.quality.setValue(99)
        self.assertEqual(snapshot.image_quality, 60)

    def test_reset_unlimited_and_lossless_controls(self):
        self.window.image_settings.max_size.setValue(0)
        self.window.video_settings.max_width.setValue(4096)
        self.window.image_settings.reset_defaults()
        self.window.video_settings.reset_defaults()
        self.assertEqual(self.window.export_settings(), ExportSettings())
        self.assertTrue(self.window.settings_tabs.isEnabled())
        self.window.set_busy(True)
        self.assertFalse(self.window.settings_tabs.isEnabled())
        self.window.set_busy(False)
        self.assertTrue(self.window.settings_tabs.isEnabled())

    def test_mixed_batch_uses_the_image_and_video_controls(self):
        with tempfile.TemporaryDirectory(prefix="medialite-ui-") as directory:
            root = Path(directory)
            self.assertEqual(run_smoke_test(root / "fixtures"), 0)
            photo = root / "photo.bmp"
            Image.effect_noise((600, 400), 70).convert("RGB").save(photo)
            video = root / "fixtures" / "فيديو تجريبي.mp4"
            self.window.image_settings.max_width.setValue(180)
            self.window.image_settings.max_height.setValue(120)
            self.window.image_settings.max_size.setValue(0.03)
            self.window.video_settings.max_width.setValue(160)
            self.window.video_settings.max_height.setValue(120)
            self.window.video_settings.max_size.setValue(0.1)
            snapshot = self.window.export_settings()
            worker = BatchWorker([photo, video], root / "out", "instagram", snapshot)
            results = []
            worker.result_file.connect(lambda index, result: results.append(result))
            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(worker.cancel.set)
            timer.start(30000)
            worker.start()
            loop.exec()
            worker.wait()
            timer.stop()
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r.status == "compressed" for r in results), str(results))
            with Image.open(results[0].output) as image:
                self.assertEqual(image.size, (180, 120))
            self.assertLessEqual(results[0].after, 30_000)
            exported = Compressor().probe(Path(results[1].output))["streams"][0]
            self.assertEqual((exported["width"], exported["height"]), (160, 120))
            self.assertLessEqual(results[1].after, 100_000)

    def test_output_path_tracks_selected_folders_and_manual_override_is_optional(self):
        with tempfile.TemporaryDirectory(prefix="medialite-routing-") as directory:
            root = Path(directory)
            first, second, custom = root / "المجلد الأول", root / "المجلد الثاني", root / "اختياري"
            for folder in (first, second, custom):
                folder.mkdir()
            Image.new("RGB", (64, 64), "red").save(first / "a.bmp")
            Image.new("RGB", (64, 64), "blue").save(second / "b.bmp")
            self.assertTrue(self.window.auto_output.isChecked())
            self.window.add_paths([first])
            self.assertEqual(self.window.output_dir, first.resolve())
            self.assertEqual(self.window.output_field.text(), str(first.resolve()))
            self.window.clear_files()
            self.window.add_paths([second])
            self.assertEqual(self.window.output_dir, second.resolve())
            self.assertEqual(self.window.output_field.text(), str(second.resolve()))
            self.window.custom_output_dir = custom.resolve()
            self.window.auto_output.setChecked(False)
            self.assertEqual(self.window.output_dir, custom.resolve())
            self.window.auto_output.setChecked(True)
            self.assertEqual(self.window.output_dir, second.resolve())
            self.window.clear_files()
            self.window.custom_output_dir = root.resolve()
            self.window.auto_output.setChecked(False)
            self.window.add_paths([first])
            self.assertEqual(len(self.window.paths), 1)
            self.assertEqual(self.window.output_dir, root.resolve())
            self.window.preview.clear()
            self.window.preview.pool.waitForDone()

    def test_mixed_folders_save_next_to_each_original_without_readding_outputs(self):
        with tempfile.TemporaryDirectory(prefix="medialite-inplace-") as directory:
            root = Path(directory)
            originals = []
            for name in ("A", "B"):
                folder = root / name
                folder.mkdir()
                source = folder / "same-name.bmp"
                Image.new("RGB", (64, 64), "green").save(source)
                originals.append(source)
            hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
            self.window.add_paths([root / "A", root / "B"])
            self.assertEqual(len(self.window.paths), 2)
            self.assertIn("2", self.window.output_field.text())
            worker = BatchWorker(self.window.paths.copy(), None, "instagram", self.window.export_settings())
            results = []
            worker.result_file.connect(lambda index, result: results.append(result))
            worker.run()
            self.assertEqual(len(results), 2)
            for source, result in zip(originals, results):
                self.assertEqual(result.status, "compressed", result.message)
                self.assertEqual(Path(result.output).parent, source.parent)
                self.assertIn("_compressed", Path(result.output).stem)
                self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), hashes[source])
                self.assertFalse((source.parent / "MediaLite-Compressed").exists())
            self.window.clear_files()
            self.window.add_paths([root])
            self.assertEqual(set(self.window.paths), set(originals))
            # The generated copy can still be added explicitly when the user chooses it.
            self.window.add_paths([Path(results[0].output)])
            self.assertEqual(len(self.window.paths), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
