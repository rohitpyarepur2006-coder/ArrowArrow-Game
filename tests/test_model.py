"""核心逻辑单元测试（对应测试记录 T01~T06，另含关卡可解性验证 T07/T08）。

运行方式（项目根目录）：
    python -m unittest discover -s tests -v
"""

import random
import unittest

from game.levels import LEVELS, MAX_MISTAKES
from game.model import (Arrow, Game, LaunchResult, Level,
                        compute_score, find_blocker, generate_random_level,
                        solve, stars_for,
                        DOWN, LEFT, RIGHT, UP)


def make_game(raw, rows=6, cols=6, max_mistakes=None):
    """用 [(row, col, 'U/D/L/R'), ...] 快速构造一局游戏。"""
    ch = {"U": UP, "D": DOWN, "L": LEFT, "R": RIGHT}
    level = Level("test", rows, cols, [Arrow(r, c, ch[d]) for r, c, d in raw])
    return Game(level, max_mistakes or MAX_MISTAKES)


class PathDetectionTest(unittest.TestCase):
    """路径检测：同行/同列的阻挡判断（T01/T02 + 边界情况）。"""

    def test_t01_click_free_arrow_files_out(self):
        game = make_game([(0, 0, "R")])
        result = game.click(0, 0)
        self.assertEqual(result.result, LaunchResult.FLY_OUT)
        self.assertNotIn((0, 0), game.board)          # 箭头消失
        self.assertEqual(game.remaining, 0)
        self.assertEqual(game.status, "cleared")

    def test_t02_blocked_arrow_consumes_mistake(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        result = game.click(0, 0)
        self.assertEqual(result.result, LaunchResult.BLOCKED)
        self.assertEqual(result.blocker, Arrow(0, 3, DOWN))
        self.assertIn((0, 0), game.board)             # 箭头不消失
        self.assertEqual(game.mistakes_left, MAX_MISTAKES - 1)

    def test_blocking_ignores_arrows_behind(self):
        # 只判断箭头"前方"：身后的箭头不影响
        game = make_game([(0, 2, "R"), (0, 0, "L")])
        self.assertEqual(game.click(0, 2).result, LaunchResult.FLY_OUT)

    def test_all_four_directions(self):
        # 上、下、左、右四个方向各测一次阻挡判定
        cases = [
            ([(2, 2, "U"), (0, 2, "D")], (2, 2)),
            ([(2, 2, "D"), (4, 2, "U")], (2, 2)),
            ([(2, 2, "L"), (2, 0, "R")], (2, 2)),
            ([(2, 2, "R"), (2, 5, "L")], (2, 2)),
        ]
        for raw, cell in cases:
            with self.subTest(raw=raw):
                game = make_game(raw)
                self.assertEqual(game.click(*cell).result, LaunchResult.BLOCKED)

    def test_blocker_is_nearest_arrow(self):
        # 多个阻挡箭头时，返回最近的那一支
        game = make_game([(0, 0, "R"), (0, 2, "D"), (0, 5, "D")])
        result = game.click(0, 0)
        self.assertEqual(result.blocker, Arrow(0, 2, DOWN))


class EdgeAndFlowTest(unittest.TestCase):
    """边界处理、通关/失败流程与重置（T03~T06）。"""

    def test_t03_edge_arrow_facing_outward(self):
        # 位于边缘且朝向棋盘外的箭头：正常飞出，不发生越界错误
        cases = [
            ([(0, 0, "L")], (0, 0)),   # 左上角朝左
            ([(0, 0, "U")], (0, 0)),   # 左上角朝上
            ([(5, 5, "R")], (5, 5)),   # 右下角朝右
            ([(5, 5, "D")], (5, 5)),   # 右下角朝下
            ([(0, 5, "R")], (0, 5)),   # 右上角朝右
            ([(5, 0, "L")], (5, 0)),   # 左下角朝左
        ]
        for raw, cell in cases:
            with self.subTest(raw=raw):
                game = make_game(raw)
                self.assertEqual(game.click(*cell).result, LaunchResult.FLY_OUT)

    def test_t04_clear_all_arrows_marks_cleared(self):
        # (0,0) 被 (0,3) 阻挡，需按 (1,1) -> (0,3) -> (0,0) 的顺序点击
        game = make_game([(0, 0, "R"), (0, 3, "D"), (1, 1, "L")])
        game.click(1, 1)
        self.assertEqual(game.status, "playing")
        game.click(0, 3)
        game.click(0, 0)
        self.assertEqual(game.status, "cleared")
        self.assertEqual(game.remaining, 0)

    def test_t05_mistakes_exhausted_marks_failed(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")], max_mistakes=1)
        game.click(0, 0)   # 被阻挡，消耗唯一一次失误机会
        self.assertEqual(game.mistakes_left, 0)
        self.assertEqual(game.status, "failed")

    def test_click_empty_cell_no_penalty(self):
        game = make_game([(0, 0, "R")])
        result = game.click(3, 3)
        self.assertEqual(result.result, LaunchResult.NO_ARROW)
        self.assertEqual(game.mistakes_left, MAX_MISTAKES)

    def test_t06_restart_resets_board_and_mistakes(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        game.click(0, 0)   # 失误 -1
        game.click(0, 3)   # 飞出 1 支
        self.assertLess(game.mistakes_left, MAX_MISTAKES)
        self.assertEqual(game.remaining, 1)
        game.restart()
        self.assertEqual(game.mistakes_left, MAX_MISTAKES)
        self.assertEqual(game.remaining, 2)
        self.assertEqual(game.status, "playing")


class SolvabilityTest(unittest.TestCase):
    """关卡可解性验证（T07/T08）。"""

    def test_t07_every_level_is_solvable(self):
        for i, level in enumerate(LEVELS):
            with self.subTest(level=level.name):
                order = solve(level)
                self.assertIsNotNone(order,
                                     f"关卡 {i + 1}({level.name}) 无法通关！")
                self.assertEqual(len(order), len(level.arrows))

    def test_t08_solution_order_is_valid(self):
        """模拟求解序列的每一步：被点击的箭头当时必须前方无阻挡。"""
        for level in LEVELS:
            with self.subTest(level=level.name):
                board = level.to_board()
                for arrow in solve(level):
                    blocker = find_blocker(board, arrow,
                                           level.grid_rows, level.grid_cols)
                    self.assertIsNone(
                        blocker,
                        f"{level.name} 中 ({arrow.row},{arrow.col}) 仍被阻挡")
                    board.pop((arrow.row, arrow.col))
                self.assertEqual(len(board), 0)

    def test_mutual_blocking_is_unsolvable(self):
        # 两支箭头互相指向对方：形成环，无法全部消除
        level = Level("deadlock", 6, 6, [Arrow(0, 0, RIGHT), Arrow(0, 1, LEFT)])
        self.assertIsNone(solve(level))

    def test_hint_returns_valid_move(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        hint = game.next_hint()
        self.assertIsNotNone(hint)
        self.assertEqual(hint, Arrow(0, 3, DOWN))


class UndoTest(unittest.TestCase):
    """撤销上一步功能（扩展）。"""

    def test_undo_restores_mistake_after_blocked_click(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        game.click(0, 0)   # 被阻挡，失误 -1
        self.assertEqual(game.mistakes_left, MAX_MISTAKES - 1)
        self.assertTrue(game.undo())
        self.assertEqual(game.mistakes_left, MAX_MISTAKES)

    def test_undo_restores_flown_arrow(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        game.click(0, 3)   # 飞出
        self.assertNotIn((0, 3), game.board)
        self.assertTrue(game.undo())
        self.assertIn((0, 3), game.board)
        self.assertEqual(game.remaining, 2)

    def test_undo_on_empty_history_returns_false(self):
        game = make_game([(0, 0, "R")])
        self.assertFalse(game.undo())

    def test_undo_restores_failed_status(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")], max_mistakes=1)
        game.click(0, 0)   # 唯一一次失误耗尽 -> 失败
        self.assertEqual(game.status, "failed")
        game.undo()
        self.assertEqual(game.status, "playing")
        self.assertEqual(game.mistakes_left, 1)

    def test_click_empty_cell_not_undoable(self):
        game = make_game([(0, 0, "R")])
        game.click(3, 3)
        self.assertFalse(game.undo())   # 空格点击不产生历史

    def test_restart_clears_history(self):
        game = make_game([(0, 0, "R"), (0, 3, "D")])
        game.click(0, 3)
        game.restart()
        self.assertFalse(game.undo())


class GeneratorTest(unittest.TestCase):
    """随机生成可通关关卡（扩展）。"""

    def test_generated_levels_are_solvable(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                level = generate_random_level(count=14, rng=random.Random(seed))
                self.assertEqual(len(level.arrows), 14)
                order = solve(level)
                self.assertIsNotNone(order, f"seed={seed} 生成的关卡不可解")
                self.assertEqual(len(order), 14)

    def test_generated_arrows_in_bounds_and_unique(self):
        level = generate_random_level(count=18, rng=random.Random(42))
        cells = [(a.row, a.col) for a in level.arrows]
        self.assertEqual(len(cells), len(set(cells)))          # 不重叠
        for r, c in cells:
            self.assertTrue(0 <= r < 6 and 0 <= c < 6)         # 在网格内

    def test_generator_rejects_too_many_arrows(self):
        with self.assertRaises(ValueError):
            generate_random_level(6, 6, count=37)

    def test_generator_is_deterministic_with_seed(self):
        a = generate_random_level(count=12, rng=random.Random(7))
        b = generate_random_level(count=12, rng=random.Random(7))
        self.assertEqual(a.arrows, b.arrows)


class ScoreTest(unittest.TestCase):
    """得分与星级（扩展）。"""

    def test_score_rewards_faster_clear(self):
        fast = compute_score(20, 0, 10, 0)
        slow = compute_score(60, 0, 10, 0)
        self.assertGreater(fast, slow)

    def test_score_rewards_fewer_mistakes(self):
        careful = compute_score(20, 0, 10, 0)
        sloppy = compute_score(20, 2, 10, 0)
        self.assertGreater(careful, sloppy)

    def test_score_never_negative(self):
        self.assertGreaterEqual(compute_score(9999, 2, 10, 10), 0)

    def test_stars_for(self):
        self.assertEqual(stars_for(0), 3)
        self.assertEqual(stars_for(1), 2)
        self.assertEqual(stars_for(2), 1)
        self.assertEqual(stars_for(3), 1)   # 失败时也会给最低 1 星的下限

    def test_score_keeps_mistake_bonus_floor(self):
        # 时间奖励归零后，剩余失误奖励仍然保留（下限为失误奖励）
        self.assertEqual(compute_score(9999, 2, 10, 10), 80)


if __name__ == "__main__":
    unittest.main()
