"""核心游戏逻辑模块（不依赖 pygame，便于单元测试）。

包含：
- Arrow / Level 的数据表示
- find_blocker：路径检测——判断箭头前进方向（同一行/同一列）上
  在箭头与棋盘边界之间是否存在其他箭头
- solve：贪心求解器——求出一个可行的消除顺序，
  用于关卡可解性验证与游戏内"提示"功能
- Game：一局游戏的状态机（点击、失误、重置）
"""

import random
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
    """一局游戏的逻辑状态。界面层（GameScene）负责调用 click/restart 并播放动画。

    每次有效的点击（飞出或碰撞）前都会在 history 中压入一份状态快照，
    供"撤销上一步"功能使用。
    """

    HISTORY_LIMIT = 200  # 撤销历史上限，防止内存无限增长

    def __init__(self, level: Level, max_mistakes: int = 3):
        self.level = level
        self.max_mistakes = max_mistakes
        self.restart()

    def restart(self):
        """恢复当前关卡到初始状态。"""
        self.board = self.level.to_board()
        self.mistakes_left = self.max_mistakes
        self.status = "playing"  # playing / cleared / failed
        self.history = []

    def restore(self, board: dict, mistakes_left: int, status: str = "playing"):
        """从存档恢复一局游戏（用于继续游戏）。"""
        self.board = board
        self.mistakes_left = mistakes_left
        self.status = status
        self.history = []

    @property
    def remaining(self) -> int:
        return len(self.board)

    def click(self, row: int, col: int) -> ClickResult:
        """点击单元格 (row, col)。"""
        arrow = self.board.get((row, col))
        if arrow is None:
            return ClickResult(LaunchResult.NO_ARROW)
        # 压入快照（深拷贝棋盘字典），供撤销使用
        self.history.append((dict(self.board), self.mistakes_left, self.status))
        if len(self.history) > self.HISTORY_LIMIT:
            self.history.pop(0)
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

    def undo(self) -> bool:
        """撤销上一步点击；无历史可撤销时返回 False。"""
        if not self.history:
            return False
        self.board, self.mistakes_left, self.status = self.history.pop()
        return True

    def next_hint(self):
        """提示：返回当前一步可以安全消除的箭头（无则返回 None）。"""
        free = [a for a in self.board.values()
                if find_blocker(self.board, a,
                                self.level.grid_rows, self.level.grid_cols) is None]
        return free[0] if free else None


def compute_score(elapsed_seconds: float, mistakes_used: int,
                  arrows_total: int, arrows_left: int,
                  max_mistakes: int = 3) -> int:
    """通关得分 = 消除数×50 + 时间奖励 + 剩余失误奖励（下限 0）。"""
    cleared = arrows_total - arrows_left
    time_bonus = max(0, 600 - int(elapsed_seconds) * 12)
    mistake_bonus = (max_mistakes - mistakes_used) * 80
    return max(0, cleared * 50 + time_bonus + mistake_bonus)


def stars_for(mistakes_used: int) -> int:
    """星级评价：0 失误 3 星，1 失误 2 星，2 失误 1 星（通关时最多失误 2 次）。"""
    return max(1, 3 - mistakes_used)


def generate_random_level(grid_rows: int = 6, grid_cols: int = 6,
                          count: int = 12, rng: random.Random = None) -> Level:
    """随机生成一个保证可通关的关卡。

    算法（逆序放置）：按"消除顺序的逆序"逐支放置箭头。已放置的箭头都会
    在本次放置的箭头之后才被消除，因此只要新箭头的正前方路径上没有已
    放置的箭头，它就一定能在自己的回合飞出。放置完成时，放置顺序的
    逆序就是一条可行的通关顺序。
    """
    rng = rng or random.Random()
    if count > grid_rows * grid_cols:
        raise ValueError("箭头数量超过网格容量")
    placed = {}
    occupied = set()
    arrows = []
    for _ in range(count):
        cells = [(r, c) for r in range(grid_rows) for c in range(grid_cols)
                 if (r, c) not in occupied]
        rng.shuffle(cells)
        chosen = None
        for r, c in cells:
            directions = [UP, DOWN, LEFT, RIGHT]
            rng.shuffle(directions)
            for d in directions:
                arrow = Arrow(r, c, d)
                if find_blocker(placed, arrow, grid_rows, grid_cols) is None:
                    chosen = arrow
                    break
            if chosen is not None:
                break
        if chosen is None:  # 极端情况下没有可放置的位置，提前结束
            break
        arrows.append(chosen)
        occupied.add((chosen.row, chosen.col))
        placed[(chosen.row, chosen.col)] = chosen
    return Level("无尽模式", grid_rows, grid_cols, arrows)
