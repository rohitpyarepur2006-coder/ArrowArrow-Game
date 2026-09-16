"""全局配置：窗口、棋盘、颜色与动画参数。"""

# ---------- 窗口 ----------
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 780
FPS = 60
TITLE = "一箭又一箭"

# ---------- 棋盘 ----------
GRID_ROWS = 6
GRID_COLS = 6
CELL = 84                 # 单元格边长（像素）
BOARD_PADDING = 18        # 棋盘内边距
BOARD_LEFT = (WINDOW_WIDTH - (GRID_COLS * CELL + BOARD_PADDING * 2)) // 2
BOARD_TOP = 140           # 棋盘顶部纵坐标（上方留给 HUD）

# ---------- 动画参数 ----------
FLY_SECONDS = 0.35        # 飞出动画时长（秒）
SHAKE_SECONDS = 0.45      # 碰撞晃动时长（秒）
HINT_SECONDS = 2.5        # 提示高亮时长（秒）
TRANSITION_DELAY = 0.6    # 通关/失败后进入结果界面的等待时间（秒）

# ---------- 颜色 ----------
BG = (243, 246, 250)          # 窗口背景
BOARD_BG = (255, 255, 255)    # 棋盘底色
CELL_BG = (236, 240, 245)     # 空格底色
CELL_HOVER = (221, 229, 239)  # 鼠标悬停
GRID_LINE = (204, 212, 222)
TEXT = (44, 54, 66)           # 正文
TEXT_LIGHT = (128, 138, 150)
WHITE = (255, 255, 255)
PRIMARY = (63, 130, 248)      # 主按钮
PRIMARY_DARK = (46, 102, 202)
DANGER = (231, 76, 60)        # 碰撞 / 失误
SUCCESS = (39, 174, 96)       # 通关
GOLD = (241, 196, 15)         # 提示 / 星星
ORANGE = (243, 156, 18)

# 四个方向的箭头颜色（键与 model 中的方向常量一致：上红 / 下蓝 / 左绿 / 右橙）
ARROW_COLORS = {
    (-1, 0): (231, 76, 60),
    (1, 0): (52, 152, 219),
    (0, -1): (39, 174, 96),
    (0, 1): (243, 156, 18),
}
