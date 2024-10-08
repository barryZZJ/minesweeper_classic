from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPushButton

from game.gui_w_solver import MinesweeperGameWSolver
from solver.classic.search import ClassicMinesweeperSolver


class SolverWorker(QThread):
    move_made = pyqtSignal(int, int, bool)

    def __init__(self, solver: ClassicMinesweeperSolver):
        super().__init__()
        self.solver = solver

    def run(self):
        while True:
            self.solver.update_knowledge_base()
            moved = False
            for row, col, flag in self.solver.make_safe_moves():
                print(f"Solver safe move: {row}, {col}{', flag' if flag else ''}")
                self.move_made.emit(row, col, flag)
                self.msleep(10)
                moved = True
            if moved:
                continue

            for row, col, flag in self.solver.make_advanced1_moves():
                print(f"Solver advanced 1 move: {row}, {col}{', flag' if flag else ''}")
                self.move_made.emit(row, col, flag)
                self.msleep(10)
                moved = True
            if moved:
                continue
            #
            for row, col, flag in self.solver.make_advanced2_moves():
                print(f"Solver advanced 2 move: {row}, {col}{', flag' if flag else ''}")
                self.move_made.emit(row, col, flag)
                self.msleep(10)
                moved = True
            if moved:
                continue
            #
            # row, col, flag = self.solver.make_random_move()
            # print(f"Solver random move: {row}, {col}")
            # self.move_made.emit(row, col, flag)

            print("Solver no move")
            if not moved:
                break


class MinesweeperGameWSearcher(MinesweeperGameWSolver):
    def __init__(self, rows=16, cols=16, mines=40, *, logical_dpi):
        super().__init__(rows, cols, mines, logical_dpi=logical_dpi)
        self.solver_worker = SolverWorker(self.solver)
        self.solver_worker.move_made.connect(self.handle_solver_move)

    def initUI(self):
        super().initUI()
        self.replayButton = QPushButton('🔄')
        self.replayButton.setFont(self.restartButton.font())
        self.replayButton.setFixedSize(self.restartButton.size())
        self.replayButton.clicked.connect(self.replayGame)
        self.topLayout.addWidget(self.replayButton, 0, 3)

    def initSolver(self, rows, cols, mines):
        self.solver = ClassicMinesweeperSolver(self.env)

    def solverMove(self):
        self.solver_worker.start()

    def handle_solver_move(self, row, col, flag):
        self.makeMoveHndlr(row, col, flag=flag, show_last_action=True, allow_click_revealed_num=False, allow_recursive=True)()

    def makeMoveHndlr(self, row, col, flag: bool, show_last_action=True, allow_click_revealed_num=True, allow_recursive=True):
        handler_super = super().makeMoveHndlr(row, col, flag, show_last_action, allow_click_revealed_num, allow_recursive)

        def handler():
            self.solver.first_click = False
            handler_super()
        return handler

    def newGame(self, rows, cols, mines):
        self.solver.reset()
        super().newGame(rows, cols, mines)

    def replayGame(self):
        self.solver.replay()
        super().replayGame()

    def resetGame(self):
        self.solver.reset()
        super().resetGame()
