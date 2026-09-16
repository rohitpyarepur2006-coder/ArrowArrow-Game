"""关卡数据：8 个 6x6 关卡。

第 1~5 关为手工设计，第 6~8 关使用随机关卡生成器（逆序放置算法，
见 model.generate_random_level）以固定种子生成并人工挑选、试玩。
每个关卡都经过 solve() 验证（见 tests/test_model.py 的 T07/T08），
保证存在合理的通关顺序。
"""

import random

from game.model import Arrow, Level, generate_random_level, UP, DOWN, LEFT, RIGHT


def _arrows(raw):
    """把 [(row, col, 方向字符), ...] 转为 Arrow 列表，方向字符取 U/D/L/R。"""
    ch = {"U": UP, "D": DOWN, "L": LEFT, "R": RIGHT}
    return [Arrow(r, c, ch[d]) for (r, c, d) in raw]


# 每个关卡 6x6 网格，R=朝右 L=朝左 U=朝上 D=朝下。
LEVELS = [
    Level("第一关 · 初试身手", 6, 6, _arrows([
        (0, 0, "R"), (0, 3, "D"),
        (1, 1, "L"), (1, 4, "U"),
        (2, 2, "U"), (2, 5, "L"),
        (3, 0, "R"), (3, 3, "R"),
    ])),
    Level("第二关 · 渐入佳境", 6, 6, _arrows([
        (0, 2, "D"), (0, 5, "L"),
        (1, 0, "R"), (1, 3, "U"),
        (2, 1, "U"), (2, 4, "L"),
        (3, 2, "R"), (4, 0, "D"),
        (4, 5, "U"), (5, 3, "L"),
    ])),
    Level("第三关 · 小试牛刀", 6, 6, _arrows([
        (0, 1, "R"), (0, 4, "D"),
        (1, 0, "D"), (1, 2, "U"), (1, 5, "L"),
        (2, 3, "U"), (2, 4, "L"),
        (3, 1, "R"), (3, 5, "D"),
        (4, 0, "R"), (4, 3, "U"),
        (5, 2, "U"), (5, 4, "L"),
    ])),
    Level("第四关 · 纵横交错", 6, 6, _arrows([
        (0, 0, "D"), (0, 2, "R"), (0, 4, "D"),
        (1, 1, "L"), (1, 3, "U"), (1, 5, "L"),
        (2, 2, "D"), (2, 4, "L"),
        (3, 0, "R"), (3, 2, "D"), (3, 4, "R"), (3, 5, "D"),
        (4, 1, "U"), (4, 3, "U"),
        (5, 0, "R"), (5, 4, "R"),
    ])),
    Level("第五关 · 高手对决", 6, 6, _arrows([
        (0, 0, "D"), (0, 2, "U"), (0, 3, "D"), (0, 5, "L"),
        (1, 1, "L"), (1, 4, "U"), (1, 5, "L"),
        (2, 0, "D"), (2, 2, "U"), (2, 4, "L"), (2, 5, "U"),
        (3, 1, "R"), (3, 3, "D"), (3, 5, "U"),
        (4, 0, "D"), (4, 2, "R"), (4, 4, "U"),
        (5, 2, "L"), (5, 4, "L"), (5, 5, "U"),
    ])),
    # 第 6~8 关由随机生成器 + 固定种子生成（逆序放置算法保证可解），
    # 已人工挑选布局并通过试玩验证：
    Level("第六关 · 步步为营", 6, 6,
          generate_random_level(count=14, rng=random.Random(7)).arrows),
    Level("第七关 · 势如破竹", 6, 6,
          generate_random_level(count=16, rng=random.Random(8)).arrows),
    Level("第八关 · 万箭齐发", 6, 6,
          generate_random_level(count=18, rng=random.Random(7)).arrows),
]

MAX_MISTAKES = 3  # 每关失误机会
