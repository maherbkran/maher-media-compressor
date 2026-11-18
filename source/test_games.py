"""Game behavior, independent progress, and theme contrast regression coverage."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from PySide6.QtCore import Qt,QPointF,QAbstractAnimation
from PySide6.QtGui import QPalette,QEnterEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from medialite import MainWindow
from dialogs import HelpDialog,ImportChoiceDialog
from games import MemoryPage,SnakeBoard


class GamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self): self.window=MainWindow(); self.window.show(); self.app.processEvents()
    def tearDown(self): self.window.close(); self.app.processEvents()

    def test_memory_has_ten_playable_levels_and_next_unlocks_only_after_matches(self):
        self.window.show_games(); self.window.games.choose('memory')
        game=self.window.games.memory
        counts=[]
        for level in range(1,11):
            counts.append(len(game.buttons)); self.assertEqual(game.level,level)
            game.next.click(); self.assertEqual(game.level,level)
            for value in range(game.PAIRS[level-1]):
                indices=[i for i,v in enumerate(game.deck) if v==value]
                for index in indices: game.buttons[index].click()
            self.assertEqual(len(game.matched),len(game.deck))
            self.assertTrue(game.next.isEnabled())
            if level<10: game.next.click()
        self.assertEqual(counts,[6,8,10,12,16,20,24,30,36,40])
        self.assertIn('العشرة',game.hint.text())
        game.next.click(); self.assertEqual(game.level,1)

    def test_memory_mismatch_and_close_reopen_preserves_game_and_progress(self):
        self.window.show_games(); popup=self.window.games; popup.choose('memory'); game=popup.memory
        first=0; second=next(i for i,v in enumerate(game.deck) if v!=game.deck[first])
        game.buttons[first].click(); game.buttons[second].click()
        self.assertTrue(game.locked)
        self.window.progress.setValue(375)
        popup.close(); self.assertFalse(popup.isVisible()); self.assertFalse(game.timer.isActive())
        self.window.show_games(); self.assertIs(self.window.games,popup)
        self.assertEqual(game.moves,1); self.assertEqual(game.open_cards,[first,second])
        self.assertEqual(popup.progress.value(),375); self.assertEqual(popup.percent.text(),'38%')
        self.assertTrue(game.timer.isActive())
        QTest.qWait(800); self.app.processEvents()
        self.assertEqual(game.open_cards,[]); self.assertFalse(game.locked)

    def test_snake_collision_restart_directions_and_level_progress(self):
        self.window.show_games(); popup=self.window.games; popup.choose('snake'); board=popup.snake.board
        board.pause(); board.snake=[(19,10),(18,10),(17,10)]
        board.tick(); self.assertTrue(board.over)
        popup.snake.play.click(); board.pause(); self.assertFalse(board.over); self.assertEqual(board.level,1)
        board.steer((-1,0)); self.assertEqual(board.next_direction,(1,0))
        for _ in range(3):
            head=board.snake[0]; board.food=(head[0]+1,head[1]); board.tick(); board.timer.stop()
        self.assertEqual(board.level,2); self.assertEqual(board.food_count,3)
        position=board.snake.copy(); popup.close(); self.assertFalse(board.timer.isActive())
        self.window.show_games(); self.assertEqual(board.snake,position)
        board.reset()
        route=([(x,10) for x in range(11,19)]+[(18,y) for y in range(11,19)]+
               [(x,18) for x in range(17,9,-1)]+[(10,y) for y in range(17,11,-1)])
        for food in route:
            head=board.snake[0]; board.steer((food[0]-head[0],food[1]-head[1])); board.food=food; board.tick()
        self.assertTrue(board.won); self.assertEqual(board.level,10)

    def test_both_themes_have_readable_standard_popups_and_clear_controls(self):
        for dark in (True,False):
            if self.window.dark_mode!=dark: self.window.theme_button.click()
            self.assertEqual(self.window.dark_mode,dark)
            palette=self.app.palette()
            text=palette.color(QPalette.ColorRole.Text); base=palette.color(QPalette.ColorRole.Base)
            self.assertGreater(abs(text.lightness()-base.lightness()),130)
            help_dialog=HelpDialog(self.window); help_dialog.show(); help_dialog.details.show(); self.app.processEvents()
            self.assertTrue(help_dialog.details.isVisible()); help_dialog.close()
            dialog=ImportChoiceDialog(self.window); dialog.file_button.click()
            self.assertEqual(dialog.choice,'files')
            self.assertEqual(self.window.byline.text().count('By Maher Bakran'),1)
            self.assertEqual(self.window.windowTitle(),'MediaPress')
            for control in (self.window.image_settings.quality,self.window.image_settings.max_size):
                self.assertGreater(control.lineEdit().width(),60)

    def test_glass_hover_loops_without_moving_target_and_reduced_effects_stop_it(self):
        self.window.reduced_effects=False
        button=self.window.add_button
        geometry=button.geometry()
        event=QEnterEvent(QPointF(10,10),QPointF(10,10),QPointF(10,10))
        self.app.sendEvent(button,event)
        self.assertEqual(button.sheen_animation.state(),QAbstractAnimation.State.Running)
        QTest.qWait(180)
        self.assertGreater(button.get_sheen(),0)
        self.assertEqual(button.geometry(),geometry)
        self.window.effects_button.setChecked(True); self.window.toggle_effects()
        self.assertEqual(button.sheen_animation.state(),QAbstractAnimation.State.Stopped)
        self.app.sendEvent(button,event)
        self.assertEqual(button.sheen_animation.state(),QAbstractAnimation.State.Stopped)


if __name__=='__main__': unittest.main()
