"""Optional local games; their timers never own or control compression work."""
import random
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,
                               QStackedWidget,QProgressBar,QSizePolicy)
from dialogs import ThemeDialog
from visuals import SmoothButton,is_dark


class SnakeBoard(QWidget):
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(280,260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('لعبة الدودة؛ الأسهم أو W A S D للحركة، ومسافة للإيقاف المؤقت')
        self.timer=QTimer(self); self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.reset()

    def reset(self):
        self.timer.stop(); self.snake=[(10,10),(9,10),(8,10)]
        self.direction=(1,0); self.next_direction=(1,0)
        self.food_count=0; self.level=1; self.over=False; self.won=False
        self.place_food(); self.changed.emit(); self.update()

    def place_food(self):
        free=[(x,y) for x in range(20) for y in range(20) if (x,y) not in self.snake]
        self.food=random.choice(free) if free else None

    def steer(self,direction):
        if direction != (-self.direction[0],-self.direction[1]):
            self.next_direction=direction
        self.setFocus()

    def resume(self):
        if not self.over and not self.won:
            self.timer.start(max(65,155-(self.level-1)*9)); self.setFocus(); self.changed.emit(); self.update()

    def pause(self):
        self.timer.stop(); self.changed.emit(); self.update()

    def toggle(self):
        if self.over or self.won: self.reset(); self.resume()
        elif self.timer.isActive(): self.pause()
        else: self.resume()

    def tick(self):
        self.direction=self.next_direction
        head=(self.snake[0][0]+self.direction[0],self.snake[0][1]+self.direction[1])
        eating=head==self.food
        if not (0<=head[0]<20 and 0<=head[1]<20) or head in (self.snake if eating else self.snake[:-1]):
            self.over=True; self.pause(); return
        self.snake.insert(0,head)
        if eating:
            self.food_count+=1
            if self.food_count>=30:
                self.won=True; self.pause(); return
            self.level=min(10,self.food_count//3+1)
            self.place_food()
            self.timer.setInterval(max(65,155-(self.level-1)*9))
        else: self.snake.pop()
        self.changed.emit(); self.update()

    def keyPressEvent(self,event):
        directions={Qt.Key.Key_Up:(0,-1),Qt.Key.Key_W:(0,-1),Qt.Key.Key_Down:(0,1),Qt.Key.Key_S:(0,1),
                    Qt.Key.Key_Left:(-1,0),Qt.Key.Key_A:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_D:(1,0)}
        if event.key() in directions: self.steer(directions[event.key()]); event.accept()
        elif event.key()==Qt.Key.Key_Space: self.toggle(); event.accept()
        else: super().keyPressEvent(event)

    def paintEvent(self,event):
        dark=is_dark(self); painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side=min(self.width()-8,self.height()-8); x=(self.width()-side)/2; y=(self.height()-side)/2; cell=side/20
        background=QColor('#102428' if dark else '#EDF6F1')
        painter.setBrush(background); painter.setPen(QPen(QColor('#42675B' if dark else '#BCD6C7'),1))
        painter.drawRoundedRect(QRectF(x,y,side,side),12,12)
        painter.setPen(QPen(QColor('#1C3839' if dark else '#DFEDE4'),.6))
        for n in range(1,20):
            painter.drawLine(int(x+n*cell),int(y),int(x+n*cell),int(y+side))
            painter.drawLine(int(x),int(y+n*cell),int(x+side),int(y+n*cell))
        painter.setPen(Qt.PenStyle.NoPen)
        for index,(sx,sy) in enumerate(reversed(self.snake)):
            painter.setBrush(QColor('#70D9AC' if dark else '#168573'))
            painter.drawRoundedRect(QRectF(x+sx*cell+1,y+sy*cell+1,cell-2,cell-2),cell*.28,cell*.28)
        hx,hy=self.snake[0]
        painter.setBrush(QColor('#123A35' if dark else '#FFFFFF'))
        for offset in (.32,.65):
            painter.drawEllipse(QRectF(x+hx*cell+offset*cell,y+hy*cell+.27*cell,cell*.12,cell*.12))
        if self.food:
            fx,fy=self.food; painter.setBrush(QColor('#F0AE77' if dark else '#CE7348'))
            painter.drawEllipse(QRectF(x+fx*cell+3,y+fy*cell+3,cell-6,cell-6))
        if not self.timer.isActive():
            painter.setBrush(QColor(10,28,30,205) if dark else QColor(247,252,249,220))
            painter.drawRoundedRect(QRectF(x+12,y+side*.36,side-24,side*.28),12,12)
            painter.setPen(QColor('#E4F0EC' if dark else '#163849'))
            text='أنهيت المستويات العشرة' if self.won else 'انتهت الجولة · جرّب مجدداً' if self.over else 'اضغط ابدأ أو مسافة للعب'
            painter.drawText(QRectF(x+14,y+side*.36,side-28,side*.28),Qt.AlignmentFlag.AlignCenter,text)
        painter.end()


class SnakePage(QWidget):
    back=Signal()

    def __init__(self):
        super().__init__(); box=QVBoxLayout(self); box.setContentsMargins(0,0,0,0)
        row=QHBoxLayout(); self.stats=QLabel(); self.stats.setObjectName('summary'); row.addWidget(self.stats,1)
        back=SmoothButton('الألعاب',icon_name='arrow-right',variant='ghost'); back.clicked.connect(self.back.emit); row.addWidget(back); box.addLayout(row)
        self.board=SnakeBoard(); box.addWidget(self.board,1)
        row=QHBoxLayout()
        self.play=SmoothButton('ابدأ',icon_name='play',variant='primary'); self.play.clicked.connect(self.board.toggle); row.addWidget(self.play)
        reset=SmoothButton('جولة جديدة',icon_name='arrow-clockwise'); reset.clicked.connect(self.restart); row.addWidget(reset)
        row.addStretch()
        for name,direction in (('arrow-left',(-1,0)),('arrow-up',(0,-1)),('arrow-down',(0,1)),('arrow-right',(1,0))):
            control=SmoothButton('',icon_name=name); control.setAccessibleName('اتجاه '+name)
            control.clicked.connect(lambda checked=False,d=direction:self.board.steer(d)); row.addWidget(control)
        box.addLayout(row)
        hint=QLabel('الأسهم أو W A S D للحركة · مسافة للإيقاف المؤقت'); hint.setObjectName('muted'); box.addWidget(hint)
        self.board.changed.connect(self.refresh); self.refresh()

    def restart(self): self.board.reset(); self.board.resume()

    def refresh(self):
        b=self.board; self.stats.setText(f'المستوى {b.level} / 10  ·  النقاط {b.food_count}')
        self.play.setText('إعادة اللعب' if b.over or b.won else 'إيقاف مؤقت' if b.timer.isActive() else 'ابدأ')
        self.play.set_icon_name('pause' if b.timer.isActive() else 'play')


class MemoryPage(QWidget):
    back=Signal()
    PAIRS=(3,4,5,6,8,10,12,15,18,20)
    ICONS=('image','video','play','folder-open','file-plus','trash','sliders-horizontal','check-circle','warning-circle','hourglass',
           'folder-simple','chat-circle-dots','info','arrow-clockwise','download-simple','sun','moon','files','game-controller','arrow-up')

    def __init__(self):
        super().__init__(); self.level=1; self.moves=0; self.open_cards=[]; self.matched=set(); self.locked=False
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.hide_mismatch)
        box=QVBoxLayout(self); box.setContentsMargins(0,0,0,0)
        row=QHBoxLayout(); self.stats=QLabel(); self.stats.setObjectName('summary'); row.addWidget(self.stats,1)
        back=SmoothButton('الألعاب',icon_name='arrow-right',variant='ghost'); back.clicked.connect(self.back.emit); row.addWidget(back); box.addLayout(row)
        self.board=QWidget(); self.grid=QGridLayout(self.board); self.grid.setSpacing(8); self.grid.setContentsMargins(0,6,0,6); box.addWidget(self.board,1)
        row=QHBoxLayout()
        self.next=SmoothButton('المستوى التالي',variant='primary',icon_name='arrow-left'); self.next.clicked.connect(self.next_level); row.addWidget(self.next)
        reset=SmoothButton('من البداية',icon_name='arrow-clockwise'); reset.clicked.connect(self.restart); row.addWidget(reset)
        row.addStretch(); self.hint=QLabel('اكشف بطاقتين متطابقتين.'); self.hint.setObjectName('muted'); row.addWidget(self.hint)
        box.addLayout(row); self.setup_level()

    def restart(self): self.level=1; self.setup_level()

    def setup_level(self):
        self.timer.stop(); self.open_cards=[]; self.matched=set(); self.moves=0; self.locked=False
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():
                item.widget().hide(); item.widget().deleteLater()
        pairs=self.PAIRS[self.level-1]; self.deck=list(range(pairs))*2; random.shuffle(self.deck)
        self.buttons=[]
        columns=3 if pairs<=3 else 4 if pairs<=8 else 5 if pairs<=10 else 6 if pairs<=18 else 8
        for index in range(len(self.deck)):
            button=SmoothButton('',icon_name='squares-four')
            button.setMinimumWidth(0); button.setMaximumWidth(16777215)
            button.setMinimumHeight(42); button.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
            button.setCheckable(True); button.setAccessibleName(f'بطاقة مغطاة {index+1}')
            button.clicked.connect(lambda checked=False,i=index:self.flip(i))
            self.grid.addWidget(button,index//columns,index%columns); self.buttons.append(button)
        self.next.setEnabled(False); self.next.setText('المستوى التالي'); self.hint.setText('اكشف بطاقتين متطابقتين.'); self.refresh()

    def flip(self,index):
        if self.locked or index in self.matched or index in self.open_cards:
            self.buttons[index].setChecked(index in self.matched or index in self.open_cards); return
        button=self.buttons[index]; button.setChecked(True); button.set_icon_name(self.ICONS[self.deck[index]])
        button.setAccessibleName(f'بطاقة مكشوفة · رمز {self.deck[index]+1}')
        self.open_cards.append(index)
        if len(self.open_cards)==2:
            self.moves+=1
            a,b=self.open_cards
            if self.deck[a]==self.deck[b]:
                self.matched.update(self.open_cards)
                for i in self.open_cards:
                    self.buttons[i].setEnabled(False); self.buttons[i].setAccessibleName('زوج مكتمل')
                self.open_cards=[]
                if len(self.matched)==len(self.deck):
                    self.next.setEnabled(True)
                    self.hint.setText('اكتمل المستوى' if self.level<10 else 'أنهيت المستويات العشرة')
                    if self.level==10: self.next.setText('العب من جديد')
            else:
                self.locked=True; self.timer.start(750)
        self.refresh()

    def hide_mismatch(self):
        for index in self.open_cards:
            self.buttons[index].setChecked(False); self.buttons[index].set_icon_name('squares-four')
            self.buttons[index].setAccessibleName(f'بطاقة مغطاة {index+1}')
        self.open_cards=[]; self.locked=False

    def next_level(self):
        if len(self.matched)==len(self.deck):
            self.level=self.level+1 if self.level<10 else 1; self.setup_level()

    def refresh(self): self.stats.setText(f'المستوى {self.level} / 10  ·  المحاولات {self.moves}  ·  الأزواج {len(self.matched)//2} / {len(self.deck)//2}')
    def pause(self): self.timer.stop()
    def resume(self):
        if self.locked: self.timer.start(750)


class GameDialog(ThemeDialog):
    def __init__(self,parent):
        super().__init__(parent,'MediaPress · وقت اللعب')
        self.setModal(False); self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(650,340); self.resize(720,390)
        self.body.setContentsMargins(20,16,20,16); self.body.setSpacing(10)
        row=QHBoxLayout(); title=QLabel('وقت اللعب'); title.setObjectName('sectionTitle'); row.addWidget(title,1)
        self.percent=QLabel('0%'); self.percent.setObjectName('summary'); self.percent.setLayoutDirection(Qt.LayoutDirection.LeftToRight); row.addWidget(self.percent); self.body.addLayout(row)
        self.progress=QProgressBar(); self.progress.setRange(0,1000); self.progress.setTextVisible(False); self.progress.setAccessibleName('تقدم الضغط أثناء اللعب'); self.body.addWidget(self.progress)
        self.status=QLabel('الضغط يعمل في الخلفية'); self.status.setObjectName('muted'); self.body.addWidget(self.status)
        self.stack=QStackedWidget(); self.body.addWidget(self.stack,1)
        chooser=QWidget(); choose=QVBoxLayout(chooser); choose.setContentsMargins(0,16,0,16); choose.addStretch()
        label=QLabel('شو بتحب تلعب؟'); label.setObjectName('sectionTitle'); label.setAlignment(Qt.AlignmentFlag.AlignCenter); choose.addWidget(label)
        note=QLabel('لعبتان على جهازك · حالة اللعب محفوظة خلال الجلسة'); note.setObjectName('muted'); note.setAlignment(Qt.AlignmentFlag.AlignCenter); choose.addWidget(note)
        row=QHBoxLayout()
        snake=SmoothButton('الدودة · 10 مستويات',icon_name='game-controller'); snake.setMinimumHeight(80); snake.clicked.connect(lambda:self.choose('snake')); row.addWidget(snake)
        memory=SmoothButton('الذاكرة · 10 مستويات',icon_name='squares-four'); memory.setMinimumHeight(80); memory.clicked.connect(lambda:self.choose('memory')); row.addWidget(memory)
        choose.addLayout(row); choose.addStretch()
        self.snake=SnakePage(); self.memory=MemoryPage()
        self.stack.addWidget(chooser); self.stack.addWidget(self.snake); self.stack.addWidget(self.memory); self.chooser=chooser
        self.snake.back.connect(self.show_chooser); self.memory.back.connect(self.show_chooser)
        row=QHBoxLayout()
        self.results=SmoothButton('مجلد النتائج',icon_name='folder-open',variant='ghost'); self.results.clicked.connect(parent.open_output); self.results.setEnabled(False); row.addWidget(self.results)
        row.addStretch(); hide=SmoothButton('العودة للضغط',icon_name='arrow-right'); hide.clicked.connect(self.close); row.addWidget(hide); self.body.addLayout(row)

    def choose(self,kind):
        self.setMinimumHeight(570); self.resize(self.width(),650)
        self.snake.board.pause(); self.memory.pause()
        self.stack.setCurrentWidget(self.snake if kind=='snake' else self.memory)
        if kind=='memory': self.memory.resume()
        else: self.snake.board.setFocus()

    def show_chooser(self):
        self.snake.board.pause(); self.memory.pause(); self.stack.setCurrentWidget(self.chooser)
        self.setMinimumHeight(340); self.resize(self.width(),390)

    def set_progress(self,value,status=None):
        self.progress.setValue(value); self.percent.setText(f'{value/10:.0f}%')
        if status: self.status.setText(self.status.fontMetrics().elidedText(status,Qt.TextElideMode.ElideMiddle,max(300,self.width()-45)))

    def showEvent(self,event):
        super().showEvent(event)
        if self.stack.currentWidget()==self.memory: self.memory.resume()
        elif self.stack.currentWidget()==self.snake: self.snake.board.setFocus()

    def reject(self):
        self.close()

    def closeEvent(self,event):
        self.snake.board.pause(); self.memory.pause(); self.hide(); event.ignore()

    def changeEvent(self,event):
        if event.type()==QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.snake.board.pause()
        super().changeEvent(event)

    def shutdown(self):
        self.snake.board.pause(); self.memory.pause(); self.hide()
