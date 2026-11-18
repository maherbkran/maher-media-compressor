"""User-visible native flow, recovery, keyboard, layout, and preview checks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
import time
import unittest
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from medialite import MainWindow, STYLES
from visuals import SmoothButton


class ExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'arial.ttf'):
            QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
        cls.app.setStyle('Fusion')
        cls.app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        cls.app.setStyleSheet(STYLES)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def until(self, predicate, seconds=15):
        deadline = time.monotonic()+seconds
        while not predicate() and time.monotonic()<deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertTrue(predicate())

    def test_primary_controls_fit_small_window_without_page_scroll(self):
        for width,height in ((1366,768),(1100,720),(960,640)):
            self.window.resize(width,height)
            self.app.processEvents()
            self.assertLessEqual(self.window.dock.geometry().bottom(), self.window.canvas.height())
            for control in (self.window.add_button,self.window.start_button,self.window.auto_output,
                            self.window.image_settings.quality,self.window.image_settings.max_size):
                self.assertTrue(control.isVisible())
                self.assertTrue(self.window.canvas.rect().contains(control.mapTo(self.window.canvas, control.rect().center())))
            self.assertGreater(self.window.table.height(),75)

    def test_real_happy_path_and_broken_file_does_not_block_next_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            photo=root/'صورة Product 01.bmp'
            Image.new('RGB',(420,280),'#297E72').save(photo)
            broken=root/'broken.mov'; broken.write_bytes(b'broken input')
            self.window.queue_import([broken,photo])
            self.until(lambda:not self.window.busy)
            self.assertEqual(len(self.window.paths),2)
            self.window.table.setCurrentCell(1,0)
            self.until(lambda:self.window.preview.image_ready)
            self.assertEqual(self.window.preview.active_path,photo)
            self.window.start_button.click()
            self.assertTrue(self.window.games.isVisible())
            self.window.games.choose('memory')
            self.window.games.memory.buttons[0].click()
            self.window.games.close()
            self.assertFalse(self.window.worker.cancel.is_set())
            self.window.show_games()
            self.assertEqual(self.window.games.memory.open_cards,[0])
            self.until(lambda:not self.window.busy,30)
            self.assertEqual(self.window.games.progress.value(),1000)
            self.assertEqual(self.window.results[0].status,'error')
            self.assertEqual(self.window.results[1].status,'compressed')
            self.assertTrue(self.window.open_button.isVisible())
            self.assertTrue(self.window.preview.result_button.isEnabled())
            self.assertEqual(self.window.preview.active_path,Path(self.window.results[1].output))
            self.until(lambda:self.window.preview.image_ready)
            self.window.preview.original_button.click()
            self.assertEqual(self.window.preview.active_path,photo)
            self.window.preview.clear(); self.window.preview.pool.waitForDone()

    def test_reduced_effects_uses_opaque_bar_and_keeps_geometry(self):
        self.window.reduced_effects=False
        self.window.effects_button.setChecked(False)
        self.window.header._cache_key=None
        self.window.grab()
        key=self.window.header._cache_key
        self.assertIsNotNone(key)
        geometry=self.window.start_button.geometry()
        self.window.start_button.setEnabled(True)
        self.window.start_button.set_hover(1)
        self.window.grab()
        self.assertEqual(self.window.start_button.geometry(),geometry)
        self.assertEqual(self.window.header._cache_key,key)
        self.window.effects_button.click()
        self.assertTrue(self.window.reduced_effects)
        self.assertEqual(self.window.start_button.geometry(),geometry)
        self.window.grab()

    def test_extra_settings_cancel_restores_values(self):
        panel=self.window.video_settings
        before=panel.values()
        def reject():
            panel.max_width.setValue(720)
            panel.max_size.setValue(5)
            panel.dialog.reject()
        QTimer.singleShot(0,reject)
        panel.show_more()
        self.assertEqual(panel.values(),before)

    def test_keyboard_focus_and_delete_only_changes_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'صورة Test.bmp'
            Image.new('RGB',(20,20),'red').save(source)
            self.window.add_paths([source])
            self.window.table.setFocus()
            QTest.keyClick(self.window.table,Qt.Key.Key_Delete)
            self.app.processEvents()
            self.assertEqual(len(self.window.paths),0)
            self.assertTrue(source.is_file())
            self.window.add_button.setFocus()
            QTest.keyClick(self.window.add_button,Qt.Key.Key_Tab)
            self.assertTrue(self.window.folder_button.hasFocus())
            self.window.preview.clear(); self.window.preview.pool.waitForDone()


if __name__=='__main__': unittest.main()
