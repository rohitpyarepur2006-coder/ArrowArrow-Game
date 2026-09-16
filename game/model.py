"""核心游戏逻辑模块（不依赖 pygame，便于单元测试）。

包含：
- Arrow / Level 的数据表示
- find_blocker：路径检测——判断箭头前进方向（同一行/同一列）上
  在箭头与棋盘边界之间是否存在其他箭头
- solve：贪心求解器——求出一个可行的消除顺序，
  用于关卡可解性验证与游戏内"提示"功能
- Game：一局游戏的状态机（点击、失误、重置）
"""

from dataclasses import dataclass
from enum import Enum, auto

# 方向用 (行增量, 列增量) 表示：棋盘坐标系中行号向下增长、列号向右增长
UP = (-1, 0)     # 上：行号 -1
DOWN = (1, 0)    # 下：行号 +1
LEFT = (0, -1)   # 左：列号 -1
RIGHT = (0, 1)   # 右：列号 +1

DIRECTION_NAMES = {UP: "上", DOWN: "下", LEFT: "左", RIGHT: "右"}


@dataclass(frozen=True)
class Arrow:
    """棋盘上的一支箭。row/col 为所在单元格，direction 为 (dr, dc)。"""

    row: int
    col: int
    direction: tuple

    @property
    def name(self) -> str:
        return DIRECTION_NAMES[self.direction]


@dataclass
class Level:
    """一个关卡：网格大小 + 全部箭头。"""

    name: str
    grid_rows: int
    grid_cols: int
    arrows: list  # list[Arrow]

    def to_board(self) -> dict:
        """转为 {(row, col): Arrow} 字典，便于按坐标查询。"""
        return {(a.row, a.col): a for a in self.arrows}


class LaunchResult(Enum):
    """点击一个单元格后的结果。"""

    NO_ARROW = auto()   # 点击了空格
    FLY_OUT = auto()    # 前方无阻挡，箭头飞出
    BLOCKED = auto()    # 前方有阻挡，箭头碰撞


@dataclass
class ClickResult:
    result: LaunchResult
    arrow: Arrow | None = None
    blocker: Arrow | None = None  # 最近的阻挡箭头（BLOCKED 时有效）


def find_blocker(board: dict, arrow: Arrow, grid_rows: int, grid_cols: int):
    """沿箭头方向逐格探测，返回最近的阻挡箭头；无阻挡返回 None。

    规则（作业基础版）：只判断同一行/同一列。从箭头前方一格开始，
    一直检查到棋盘边界；路径上遇到的第一支箭头就是阻挡者。
    """
    dr, dc = arrow.direction
    r, c = arrow.row + dr, arrow.col + dc
    while 0 <= r < grid_rows and 0 <= c < grid_cols:
        blocker = board.get((r, c))
        if blocker is not None:
            return blocker
        r += dr
        c += dc
    return None


def solve(level: Level):
    """贪心求一个可行的消除顺序（list[Arrow]）。

    每一步取一支"当前前方无阻挡"的箭头消除；若某一步没有任何可选箭头，
    说明剩余箭头形成了互相阻挡的环（例如两支箭头互相指向对方），
    该关卡无法通关，返回 None。
    """
    board = level.to_board()
    order = []
    while board:
        free = [a for a in board.values()
                if find_blocker(board, a, level.grid_rows, level.grid_cols) is None]
        if not free:
            return None
        chosen = free[0]
        board.pop((chosen.row, chosen.col))
        order.append(chosen)
    return order


class Game:
    """一局游戏的逻辑状态。界面层（GameScene）负责调用 click/restart 并播放动画。"""

    def __init__(self, level: Level, max_mistakes: int = 3):
        self.level = level
        self.max_mistakes = max_mistakes
        self.restart()

    def restart(self):
        """恢复当前关卡到初始状态。"""
        self.board = self.level.to_board()
        self.mistakes_left = self.max_mistakes
        self.status = "playing"  # playing / cleared / failed

    @property
    def remaining(self) -> int:
        return len(self.board)

    def click(self, row: int, col: int) -> ClickResult:
        """点击单元格 (row, col)。"""
        arrow = self.board.get((row, col))
        if arrow is None:
            return ClickResult(LaunchResult.NO_ARROW)
        blocker = find_blocker(self.board, arrow,
                               self.level.grid_rows, self.level.grid_cols)
        if blocker is not None:
            # 被阻挡：不消除，消耗一次失误机会
            self.mistakes_left -= 1
            if self.mistakes_left <= 0:
                self.mistakes_left = 0
                self.status = "failed"
            return ClickResult(LaunchResult.BLOCKED, arrow=arrow, blocker=blocker)
        # 前方无阻挡：飞出并消除
        self.board.pop((row, col))
        if not self.board:
            self.status = "cleared"
        return ClickResult(LaunchResult.FLY_OUT, arrow=arrow)

    def next_hint(self):
        """提示：返回当前一步可以安全消除的箭头（无则返回 None）。"""
        free = [a for a in self.board.values()
                if find_blocker(self.board, a,
                                self.level.grid_rows, self.level.grid_cols) is None]
        return free[0] if free else None
