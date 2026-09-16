"""游戏主程序：场景管理与界面渲染。

场景划分：
- StartScene       开始界面（标题、规则说明、开始/继续按钮、装饰飞箭）
- LevelSelectScene 关卡选择界面（8 个关卡 + 无尽模式，星级与解锁进度）
- GameScene        游戏界面（HUD、棋盘、飞出/碰撞动画、提示/撤销/演示/重开）
- WinScene         通关界面（得分、用时、星级，下一关/继续挑战）
- FailScene        失败界面（重新开始、返回主菜单）

动画实现说明：箭头被点击后立即从逻辑棋盘（Game.board）移除，
画面上的"飞出"由 FlyingArrow 特效独立渲染（拖尾 + 旋转 + 粒子爆发），
二者互不干扰；碰撞反馈由 Collision 特效驱动：箭头原地晃动 + 摇摆 +
红色闪烁（闪烁画在箭头下层，保证箭头始终可见）+ 浮动文字。
"""

import math
import random

import pygame

from game import config
from game import save as save_module
from game.assets import draw_arrow, draw_star, draw_text, draw_text_center, get_font, make_sounds
from game.levels import LEVELS, MAX_MISTAKES
from game.model import (Arrow, Game, LaunchResult, Level,
                        compute_score, generate_random_level, solve, stars_for)
from game.ui import Button


# ---------------------------------------------------------------------------
# 动画特效
# ---------------------------------------------------------------------------

class FlyingArrow:
    """飞出动画：记录被消除的箭头与动画进度，带拖尾与旋转。"""

    def __init__(self, arrow, start_center):
        self.arrow = arrow
        self.start = pygame.Vector2(start_center)
        dr, dc = arrow.direction
        # 屏幕坐标换算：行号变化 -> y 轴，列号变化 -> x 轴
        self.screen_dir = pygame.Vector2(dc, dr)
        self.t = 0.0
        self.duration = config.FLY_SECONDS
        self.spin = random.choice((-1, 1)) * 180  # 飞行中的旋转角度（总 180°）

    @property
    def eased(self):
        # 缓动：先快后慢
        k = min(1.0, self.t / self.duration)
        return 1 - (1 - k) ** 2

    @property
    def pos(self):
        distance = max(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        return self.start + self.screen_dir * (self.eased * distance)

    @property
    def done(self):
        return self.t >= self.duration

    def update(self, dt):
        self.t += dt

    def draw(self, surface):
        color = config.ARROW_COLORS[self.arrow.direction]
        # 飞出后 40% 路程逐渐淡出
        alpha = 255 if self.t < self.duration * 0.6 else \
            max(0, 255 * (1 - (self.t / self.duration - 0.6) / 0.4))
        # 拖尾：两个逐渐变小的残影
        for j, (back, ghost_alpha) in enumerate(((18, 90), (38, 45))):
            ghost = self.pos - self.screen_dir * back
            size = int(config.CELL * 0.66 * (1 - j * 0.18))
            draw_arrow(surface, ghost, self.arrow.direction, size, color,
                       int(ghost_alpha * alpha / 255))
        # 本体：飞行中旋转
        draw_arrow(surface, self.pos, self.arrow.direction,
                   int(config.CELL * 0.66), color, int(alpha),
                   angle_offset=self.spin * self.eased)


class Collision:
    """碰撞特效：箭头原地晃动 + 摇摆 + 红色闪烁（闪烁在箭头下层）。"""

    def __init__(self, arrow, cell_rect):
        self.arrow = arrow
        self.rect = cell_rect
        self.t = 0.0
        self.duration = config.SHAKE_SECONDS

    @property
    def done(self):
        return self.t >= self.duration

    def update(self, dt):
        self.t += dt

    @property
    def offset(self):
        # 正弦晃动，振幅随时间衰减
        k = self.t / self.duration
        return math.sin(self.t * 55) * 7 * (1 - k)

    @property
    def angle(self):
        # 小幅摇摆，增强"撞上东西"的感觉
        k = self.t / self.duration
        return math.sin(self.t * 40) * 10 * (1 - k)

    def draw(self, surface):
        # 前 0.22 秒红色闪烁，画在箭头下层：箭头始终保持清晰可见，
        # 不会因为被红色盖住而看起来像"消失"
        flash = max(0.0, 1 - self.t / 0.22)
        if flash > 0:
            overlay = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            overlay.fill((231, 76, 60, int(150 * flash)))
            surface.blit(overlay, self.rect)
        color = config.ARROW_COLORS[self.arrow.direction]
        center = (self.rect.centerx + self.offset, self.rect.centery)
        draw_arrow(surface, center, self.arrow.direction,
                   int(config.CELL * 0.66), color, angle_offset=self.angle)


class FloatText:
    """向上漂浮并淡出的提示文字（如"被阻挡！"）。"""

    def __init__(self, text, start_center, color, seconds=1.0, font_size=22):
        self.text = text
        self.pos = pygame.Vector2(start_center)
        self.color = color
        self.t = 0.0
        self.seconds = seconds
        self.font_size = font_size

    @property
    def done(self):
        return self.t >= self.seconds

    def update(self, dt):
        self.t += dt
        self.pos.y -= 30 * dt

    def draw(self, surface):
        k = self.t / self.seconds
        img = get_font(self.font_size, True).render(self.text, True, self.color)
        img.set_alpha(int(255 * (1 - k)))
        surface.blit(img, img.get_rect(center=self.pos))


class Particle:
    """带重力的彩色粒子（发射爆发与通关庆祝共用）。"""

    def __init__(self, center, speed_range=(90, 280)):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(*speed_range)
        self.pos = pygame.Vector2(center)
        self.vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        self.t = 0.0
        self.life = random.uniform(0.6, 1.4)
        self.size = random.randint(3, 6)
        self.color = random.choice(
            [config.GOLD, config.SUCCESS, config.PRIMARY, (255, 200, 60)])

    @property
    def done(self):
        return self.t >= self.life

    def update(self, dt):
        self.t += dt
        self.pos += self.vel * dt
        self.vel.y += 260 * dt  # 重力

    def draw(self, surface):
        k = self.t / self.life
        radius = max(1, int(self.size * (1 - k)))
        pygame.draw.circle(surface, self.color,
                           (int(self.pos.x), int(self.pos.y)), radius)


# ---------------------------------------------------------------------------
# 开始界面
# ---------------------------------------------------------------------------

class StartScene:
    """开始界面：标题 + 规则说明 + 开始/继续按钮 + 装饰飞箭。"""

    RULES = [
        "点击箭头：前进方向没有阻挡时，它会飞出棋盘",
        "清除全部箭头即可通关；点错会消耗失误机会，用完即失败",
        "提示 / 撤销 / 演示按钮助你闯关，通关后记录得分与星级",
    ]

    def __init__(self, app):
        self.app = app
        self.mouse_pos = (-1, -1)
        self.buttons = [Button((config.WINDOW_WIDTH // 2, 495), "开始游戏",
                               self.start, size=(190, 56), font_size=26)]
        if app.save_data.get("mid_level"):
            self.buttons.append(Button((config.WINDOW_WIDTH // 2, 575),
                                       "继续游戏", self.resume,
                                       size=(190, 50), font_size=24,
                                       color=config.SUCCESS))
        self.decor = []       # [(FlyingArrow, alpha), ...]
        self.decor_timer = 0.0

    def start(self):
        self.app.play("click")
        self.app.show_level_select()

    def resume(self):
        self.app.play("click")
        self.app.resume_game()

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        for button in self.buttons:
            button.handle_event(event)

    def update(self, dt):
        # 每隔 0.7 秒从窗口边缘放出一支半透明的装饰飞箭
        self.decor_timer -= dt
        if self.decor_timer <= 0:
            self.decor_timer = 0.7
            edge = random.randrange(4)
            if edge == 0:
                pos, direction = (-40, random.uniform(60, 700)), (0, 1)
            elif edge == 1:
                pos, direction = (config.WINDOW_WIDTH + 40, random.uniform(60, 700)), (0, -1)
            elif edge == 2:
                pos, direction = (random.uniform(60, 840), -40), (1, 0)
            else:
                pos, direction = (random.uniform(60, 840), config.WINDOW_HEIGHT + 40), (-1, 0)
            fake = type("Arrow", (), {"direction": direction})()
            self.decor.append((FlyingArrow(fake, pos), 70))
        for item in self.decor:
            item[0].update(dt)
        self.decor = [(f, a) for f, a in self.decor if not f.done]

    def draw(self, surface):
        surface.fill(config.BG)
        for f, alpha in self.decor:
            draw_arrow(surface, f.pos, f.arrow.direction, 40,
                       config.ARROW_COLORS[f.arrow.direction], alpha)
        draw_text_center(surface, "一箭又一箭",
                         (config.WINDOW_WIDTH // 2, 175), 64, config.TEXT, bold=True)
        draw_text_center(surface, "箭 头 解 谜 小 游 戏",
                         (config.WINDOW_WIDTH // 2, 240), 26, config.TEXT_LIGHT)
        for i, line in enumerate(self.RULES):
            draw_text_center(surface, line,
                             (config.WINDOW_WIDTH // 2, 315 + i * 36),
                             21, config.TEXT_LIGHT)
        for button in self.buttons:
            button.draw(surface)
        draw_text_center(surface, "Python + Pygame · 软件工程课程作业",
                         (config.WINDOW_WIDTH // 2, 735), 17, config.TEXT_LIGHT)


# ---------------------------------------------------------------------------
# 关卡选择界面
# ---------------------------------------------------------------------------

class LevelSelectScene:
    """关卡选择：8 个关卡（星级与解锁状态）+ 无尽模式。"""

    CARD = (160, 100)

    def __init__(self, app):
        self.app = app
        self.mouse_pos = (-1, -1)
        self.cards = []  # [(rect, level_index)]
        for i in range(len(LEVELS)):
            col, row = i % 4, i // 4
            rect = pygame.Rect(0, 0, *self.CARD)
            rect.center = (94 + col * 184 + self.CARD[0] // 2,
                           175 + row * 128 + self.CARD[1] // 2)
            self.cards.append((rect, i))
        self.endless_button = Button((config.WINDOW_WIDTH // 2, 505),
                                     "无尽模式 · 随机关卡", self.start_endless,
                                     size=(320, 64), font_size=24,
                                     color=config.SUCCESS)
        self.back_button = Button((config.WINDOW_WIDTH // 2, 640), "返回",
                                  self.back, size=(140, 46),
                                  color=(140, 152, 166))

    def back(self):
        self.app.play("click")
        self.app.to_menu()

    def start_endless(self):
        self.app.play("click")
        self.app.start_endless()

    def _start(self, i):
        self.app.play("click")
        self.app.start_game(i)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        self.back_button.handle_event(event)
        self.endless_button.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, i in self.cards:
                if rect.collidepoint(event.pos) and i < self.app.save_data["unlocked"]:
                    self._start(i)
                    return

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(config.BG)
        draw_text_center(surface, "选择关卡", (config.WINDOW_WIDTH // 2, 70),
                         40, config.TEXT, bold=True)
        draw_text_center(surface, "通关即可解锁下一关，通关成绩会记录在卡片上",
                         (config.WINDOW_WIDTH // 2, 115), 20, config.TEXT_LIGHT)
        for rect, i in self.cards:
            unlocked = i < self.app.save_data["unlocked"]
            best_stars = self.app.save_data["stars"].get(str(i), 0)
            hovered = unlocked and rect.collidepoint(self.mouse_pos)
            pygame.draw.rect(surface, config.CELL_HOVER if hovered else config.CELL_BG,
                             rect, border_radius=12)
            border = config.PRIMARY if unlocked else config.GRID_LINE
            pygame.draw.rect(surface, border, rect, 2, border_radius=12)
            if unlocked:
                draw_text_center(surface, f"第 {i + 1} 关", rect.center, 24,
                                 config.TEXT, bold=True)
                # 底部三颗小星星展示历史最佳
                for s in range(3):
                    center = (rect.centerx + (s - 1) * 30, rect.bottom - 26)
                    color = config.GOLD if s < best_stars else (214, 220, 228)
                    draw_star(surface, center, 12, color)
            else:
                draw_text_center(surface, f"第 {i + 1} 关", rect.center, 24,
                                 config.TEXT_LIGHT)
                draw_text_center(surface, "未解锁", (rect.centerx, rect.bottom - 26),
                                 18, config.TEXT_LIGHT)
        self.endless_button.draw(surface)
        best = self.app.save_data.get("endless_best", 0)
        if best:
            draw_text_center(surface, f"无尽模式最高分：{best}",
                             (config.WINDOW_WIDTH // 2, 555), 20, config.TEXT_LIGHT)
        self.back_button.draw(surface)


# ---------------------------------------------------------------------------
# 游戏界面
# ---------------------------------------------------------------------------

class GameScene:
    """游戏场景：渲染 HUD 与棋盘，处理点击、动画与辅助功能。"""

    def __init__(self, app, level_index, level=None):
        self.app = app
        self.level_index = level_index
        self.endless = level_index == -1
        self.level = level if level is not None else LEVELS[level_index]
        self.total_arrows = len(self.level.arrows)
        self.game = Game(self.level, MAX_MISTAKES)
        self.elapsed = 0.0        # 本关用时（秒）
        self.mouse_pos = (-1, -1)
        self.flying = []          # 飞出动画
        self.collisions = {}      # {(row, col): Collision}
        self.float_texts = []
        self.particles = []       # 发射粒子
        self.blocker_ring = None  # (rect, t) 碰撞瞬间圈出阻挡箭头
        self.hint = None          # (arrow, t) 提示高亮
        self.mistake_flash_t = 99 # 距上次失误的时间（用于失误数闪红）
        self.pending = None       # "cleared" / "failed"，等待进入结果界面
        self.pending_t = 0.0
        self.demo_order = []      # AI 自动演示的剩余消除序列
        self.demo_timer = 0.0
        self._build_buttons()

    def apply_resume(self, board, mistakes_left, elapsed):
        """从存档恢复进行到一半的对局。"""
        self.game.restore(board, mistakes_left, "playing")
        self.elapsed = elapsed

    def serialize_state(self):
        """序列化当前对局（用于继续游戏存档）。"""
        dir_key = {(0, 1): "R", (0, -1): "L", (1, 0): "D", (-1, 0): "U"}
        return {
            "level": self.level_index,
            "arrows": [[a.row, a.col, dir_key[a.direction]]
                       for a in self.game.board.values()],
            "mistakes": self.game.mistakes_left,
            "elapsed": self.elapsed,
        }

    def _build_buttons(self):
        y = config.WINDOW_HEIGHT - 58
        centers = [226, 338, 450, 562, 674]
        self.buttons = [
            Button((centers[0], y), "提示", self.do_hint,
                   size=(100, 40), font_size=20, color=config.GOLD),
            Button((centers[1], y), "撤销", self.do_undo,
                   size=(100, 40), font_size=20, color=(102, 126, 234)),
            Button((centers[2], y), "演示", self.do_demo,
                   size=(100, 40), font_size=20, color=config.SUCCESS),
            Button((centers[3], y), "重新开始", self.do_restart,
                   size=(100, 40), font_size=20),
            Button((centers[4], y), "主菜单", self.do_menu,
                   size=(100, 40), font_size=20, color=(140, 152, 166)),
        ]

    # ---- 按钮回调 ----

    def do_hint(self):
        if self.pending:
            return
        arrow = self.game.next_hint()
        if arrow is not None:
            self.hint = (arrow, 0.0)
            self.app.play("click")

    def do_undo(self):
        if not self.game.undo():
            return
        self.app.play("click")
        # 撤销会恢复上一步的状态：取消过渡、清空特效与演示
        self.pending = None
        self.demo_order = []
        self.flying.clear()
        self.collisions.clear()
        self.float_texts.clear()
        self.blocker_ring = None
        self.hint = None
        self.app.save_mid_level()

    def do_demo(self):
        """AI 自动求解：按求解器顺序自动点击；再次点击停止。"""
        if self.pending:
            return
        if self.demo_order:
            self.demo_order = []
            return
        level = Level("demo", self.level.grid_rows, self.level.grid_cols,
                      list(self.game.board.values()))
        order = solve(level)
        if order:
            self.demo_order = order
            self.demo_timer = 0.0
            self.hint = None
            self.app.play("click")

    def do_restart(self):
        self.app.play("click")
        self.game.restart()
        self.elapsed = 0.0
        self.flying.clear()
        self.collisions.clear()
        self.float_texts.clear()
        self.particles.clear()
        self.blocker_ring = None
        self.hint = None
        self.pending = None
        self.demo_order = []
        self.app.save_mid_level()

    def do_menu(self):
        self.app.play("click")
        self.app.to_menu()

    # ---- 坐标换算 ----

    def cell_rect(self, row, col):
        x = config.BOARD_LEFT + config.BOARD_PADDING + col * config.CELL
        y = config.BOARD_TOP + config.BOARD_PADDING + row * config.CELL
        return pygame.Rect(x + 4, y + 4, config.CELL - 8, config.CELL - 8)

    def cell_at(self, pos):
        x, y = pos
        in_board = (config.BOARD_LEFT <= x < config.BOARD_LEFT +
                    config.GRID_COLS * config.CELL + config.BOARD_PADDING * 2 and
                    config.BOARD_TOP <= y < config.BOARD_TOP +
                    config.GRID_ROWS * config.CELL + config.BOARD_PADDING * 2)
        if not in_board:
            return None
        col = (x - config.BOARD_LEFT - config.BOARD_PADDING) // config.CELL
        row = (y - config.BOARD_TOP - config.BOARD_PADDING) // config.CELL
        if 0 <= row < config.GRID_ROWS and 0 <= col < config.GRID_COLS:
            return row, col
        return None

    # ---- 事件 ----

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        for button in self.buttons:
            if button.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click_board(event.pos)

    def _click_board(self, pos):
        if self.pending:
            return
        cell = self.cell_at(pos)
        if cell is None:
            return
        self.demo_order = []  # 手动操作会停止演示
        self._launch(*cell)

    def _launch(self, row, col):
        """执行一次点击逻辑并播放对应特效（玩家点击与演示共用）。"""
        result = self.game.click(row, col)
        if result.result is LaunchResult.NO_ARROW:
            return
        if result.result is LaunchResult.BLOCKED:
            self.app.play("blocked")
            self.mistake_flash_t = 0.0
            rect = self.cell_rect(row, col)
            self.collisions[(row, col)] = Collision(result.arrow, rect)
            self.blocker_ring = (self.cell_rect(result.blocker.row, result.blocker.col), 0.0)
            self.float_texts.append(FloatText("被阻挡！", rect.center, config.DANGER,
                                              font_size=28))
            if self.game.status == "failed":
                self._schedule("failed")
        else:  # FLY_OUT
            self.app.play("launch")
            start = self.cell_rect(row, col).center
            self.flying.append(FlyingArrow(result.arrow, start))
            self._burst(start)
            self.hint = None
            if self.game.status == "cleared":
                self._schedule("cleared")
        self.app.save_mid_level()

    def _burst(self, center):
        """箭头飞出时的粒子爆发。"""
        self.particles.extend(Particle(center, speed_range=(60, 200))
                              for _ in range(8))

    def _schedule(self, status):
        self.pending = status
        self.pending_t = config.TRANSITION_DELAY

    # ---- 更新与绘制 ----

    def update(self, dt):
        if not self.pending and self.game.status == "playing":
            self.elapsed += dt
        self.mistake_flash_t += dt
        for f in self.flying:
            f.update(dt)
        self.flying = [f for f in self.flying if not f.done]
        for key in list(self.collisions):
            effect = self.collisions[key]
            effect.update(dt)
            if effect.done:
                del self.collisions[key]
        for ft in self.float_texts:
            ft.update(dt)
        self.float_texts = [ft for ft in self.float_texts if not ft.done]
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if not p.done]
        if self.blocker_ring:
            self.blocker_ring = (self.blocker_ring[0], self.blocker_ring[1] + dt)
        if self.hint:
            arrow, t = self.hint
            if t >= config.HINT_SECONDS:
                self.hint = None
            else:
                self.hint = (arrow, t + dt)
        # AI 自动演示：每隔 0.55 秒自动消除一步
        if self.demo_order and not self.pending:
            self.demo_timer -= dt
            while self.demo_order and self.demo_timer <= 0:
                arrow = self.demo_order[0]
                if (arrow.row, arrow.col) not in self.game.board:
                    # 状态与预期不符（理论上不会发生），重新计算剩余解
                    level = Level("demo", self.level.grid_rows,
                                  self.level.grid_cols,
                                  list(self.game.board.values()))
                    self.demo_order = solve(level) or []
                    if not self.demo_order:
                        break
                    arrow = self.demo_order[0]
                self.demo_order.pop(0)
                self._launch(arrow.row, arrow.col)
                self.demo_timer += 0.55
        if self.pending:
            self.pending_t -= dt
            if self.pending_t <= 0:
                if self.pending == "cleared":
                    score = compute_score(
                        self.elapsed,
                        self.game.max_mistakes - self.game.mistakes_left,
                        self.total_arrows, self.game.remaining,
                        self.game.max_mistakes)
                    self.app.on_level_cleared(self.level_index,
                                              self.game.mistakes_left,
                                              score, self.elapsed, self.endless)
                else:
                    self.app.on_level_failed(self.level_index)

    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_hud(surface)
        self._draw_board(surface)
        for f in self.flying:
            f.draw(surface)
        for effect in self.collisions.values():
            effect.draw(surface)
        for p in self.particles:
            p.draw(surface)
        self._draw_rings(surface)
        for ft in self.float_texts:
            ft.draw(surface)

    def _draw_hud(self, surface):
        title = "无尽模式" if self.endless else f"第 {self.level_index + 1} 关"
        draw_text(surface, title, (28, 16), 26, config.TEXT, bold=True)
        name = self.level.name if not self.endless else \
            f"随机关卡 · {self.total_arrows} 支箭"
        draw_text(surface, name, (28, 52), 20, config.TEXT_LIGHT)
        draw_text(surface, f"用时：{self.elapsed:.1f} 秒", (28, 88), 20,
                  config.TEXT_LIGHT)
        right = config.WINDOW_WIDTH - 210
        draw_text(surface, f"剩余箭头：{self.game.remaining}", (right, 16), 24)
        # 刚发生失误时失误数字闪红提醒
        flash = max(0.0, 1 - self.mistake_flash_t / 0.6)
        mistake_color = config.DANGER if flash > 0 else config.TEXT
        draw_text(surface, f"剩余失误：{self.game.mistakes_left}",
                  (right, 52), 24, mistake_color)
        score = compute_score(self.elapsed,
                              self.game.max_mistakes - self.game.mistakes_left,
                              self.total_arrows, self.game.remaining,
                              self.game.max_mistakes)
        draw_text(surface, f"得分：{score}", (right, 88), 24)
        for button in self.buttons:
            button.draw(surface)

    def _draw_board(self, surface):
        outer = pygame.Rect(
            config.BOARD_LEFT - 8, config.BOARD_TOP - 8,
            config.GRID_COLS * config.CELL + config.BOARD_PADDING * 2 + 16,
            config.GRID_ROWS * config.CELL + config.BOARD_PADDING * 2 + 16)
        pygame.draw.rect(surface, config.BOARD_BG, outer, border_radius=14)
        pygame.draw.rect(surface, config.GRID_LINE, outer, 2, border_radius=14)

        hover_cell = self.cell_at(self.mouse_pos)
        for row in range(config.GRID_ROWS):
            for col in range(config.GRID_COLS):
                rect = self.cell_rect(row, col)
                arrow = self.game.board.get((row, col))
                hovered = arrow is not None and (row, col) == hover_cell
                pygame.draw.rect(surface,
                                 config.CELL_HOVER if hovered else config.CELL_BG,
                                 rect, border_radius=10)
                if (row, col) in self.collisions:
                    continue  # 碰撞中的箭头由特效绘制（带晃动）
                if arrow is not None:
                    draw_arrow(surface, rect.center, arrow.direction,
                               int(config.CELL * 0.66),
                               config.ARROW_COLORS[arrow.direction])

    def _draw_rings(self, surface):
        # 碰撞瞬间圈出阻挡箭头（橙色脉动圆环，0.6 秒）
        if self.blocker_ring and self.blocker_ring[1] < 0.6:
            rect, t = self.blocker_ring
            grow = 8 + 3 * math.sin(t * 22)
            pygame.draw.rect(surface, config.ORANGE, rect.inflate(grow, grow), 3,
                             border_radius=12)
        # 提示高亮：金色呼吸圆环
        if self.hint:
            arrow, t = self.hint
            rect = self.cell_rect(arrow.row, arrow.col)
            grow = 6 + 4 * math.sin(t * 8)
            pygame.draw.rect(surface, config.GOLD, rect.inflate(grow, grow), 3,
                             border_radius=12)


# ---------------------------------------------------------------------------
# 通关 / 失败界面
# ---------------------------------------------------------------------------

class WinScene:
    """通关界面：得分、用时、星级评价 + 下一关/继续挑战。"""

    def __init__(self, app, level_index, mistakes_left, score, elapsed,
                 endless=False):
        self.app = app
        self.level_index = level_index
        self.mistakes_left = mistakes_left
        self.score = score
        self.elapsed = elapsed
        self.endless = endless
        self.mouse_pos = (-1, -1)
        self.stars = stars_for(MAX_MISTAKES - mistakes_left)
        self.particles = [Particle((config.WINDOW_WIDTH // 2, 170))
                          for _ in range(50)]
        cx = config.WINDOW_WIDTH // 2
        if endless:
            self.buttons = [
                Button((cx - 120, 480), "继续挑战", self.next,
                       size=(200, 54), color=config.SUCCESS),
                Button((cx + 130, 480), "主菜单", self.to_menu,
                       size=(160, 54), color=(140, 152, 166)),
            ]
        elif level_index == len(LEVELS) - 1:
            self.buttons = [
                Button((cx, 480), "返回主菜单", self.to_menu, size=(180, 54)),
            ]
        else:
            self.buttons = [
                Button((cx - 120, 480), "下一关", self.next_level,
                       size=(180, 54), color=config.SUCCESS),
                Button((cx + 130, 480), "主菜单", self.to_menu,
                       size=(160, 54), color=(140, 152, 166)),
            ]

    def next_level(self):
        self.app.play("click")
        self.app.start_game(self.level_index + 1)

    def next(self):
        self.app.play("click")
        self.app.start_endless()

    def to_menu(self):
        self.app.play("click")
        self.app.to_menu()

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        for button in self.buttons:
            button.handle_event(event)

    def update(self, dt):
        for p in self.particles:
            p.update(dt)

    def draw(self, surface):
        surface.fill(config.BG)
        for p in self.particles:
            p.draw(surface)
        cx = config.WINDOW_WIDTH // 2
        if self.endless:
            title = "无尽模式 通关！"
        elif self.level_index == len(LEVELS) - 1:
            title = "恭喜通关全部关卡！"
        else:
            title = f"第 {self.level_index + 1} 关 通关！"
        draw_text_center(surface, title, (cx, 155), 52, config.SUCCESS, bold=True)
        # 三颗星：未获得的画成灰色
        for i in range(3):
            center = (cx + (i - 1) * 110, 250)
            color = config.GOLD if i < self.stars else (214, 220, 228)
            draw_star(surface, center, 40, color)
        draw_text_center(surface, f"得分：{self.score}",
                         (cx, 335), 28, config.TEXT, bold=True)
        draw_text_center(surface, f"用时：{self.elapsed:.1f} 秒 · 剩余失误机会：{self.mistakes_left}",
                         (cx, 380), 22, config.TEXT_LIGHT)
        for button in self.buttons:
            button.draw(surface)


class FailScene:
    """失败界面：重新开始 / 返回主菜单。"""

    def __init__(self, app, level_index):
        self.app = app
        self.level_index = level_index
        self.mouse_pos = (-1, -1)
        self.buttons = [
            Button((330, 450), "重新开始", self.restart, size=(180, 54)),
            Button((560, 450), "主菜单", self.to_menu, size=(160, 54),
                   color=(140, 152, 166)),
        ]

    def restart(self):
        self.app.play("click")
        self.app.start_game(self.level_index)

    def to_menu(self):
        self.app.play("click")
        self.app.to_menu()

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        for button in self.buttons:
            button.handle_event(event)

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(config.BG)
        cx = config.WINDOW_WIDTH // 2
        draw_text_center(surface, f"第 {self.level_index + 1} 关 失败",
                         (cx, 230), 52, config.DANGER, bold=True)
        draw_text_center(surface, "失误机会已用完，再试一次吧！",
                         (cx, 320), 26, config.TEXT_LIGHT)
        for button in self.buttons:
            button.draw(surface)


# ---------------------------------------------------------------------------
# 应用外壳
# ---------------------------------------------------------------------------

class App:
    """初始化 pygame，管理场景切换、进度存档与主循环。"""

    def __init__(self, sound_enabled=True):
        pygame.init()
        pygame.display.set_caption(config.TITLE)
        self.screen = pygame.display.set_mode(
            (config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.sounds = make_sounds() if sound_enabled else {}
        self.save_data = save_module.load()
        self.scene = StartScene(self)

    def play(self, name):
        sound = self.sounds.get(name)
        if sound:
            sound.play()

    # ---- 场景切换 ----

    def show_level_select(self):
        self.scene = LevelSelectScene(self)

    def start_game(self, level_index):
        self.scene = GameScene(self, level_index)

    def start_endless(self):
        """无尽模式：随机生成一个保证可通关的关卡。"""
        level = generate_random_level(config.GRID_ROWS, config.GRID_COLS,
                                      random.randint(12, 18))
        self.scene = GameScene(self, -1, level=level)

    def resume_game(self):
        """继续上次进行到一半的对局。"""
        mid = self.save_data.get("mid_level")
        if not mid:
            self.show_level_select()
            return
        ch = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
        try:
            arrows = [Arrow(r, c, ch[d]) for r, c, d in mid["arrows"]]
        except (KeyError, TypeError, ValueError):
            self.show_level_select()
            return
        level = Level("无尽模式" if mid.get("level") == -1 else "继续挑战",
                      config.GRID_ROWS, config.GRID_COLS, arrows)
        board = {(a.row, a.col): a for a in arrows}
        scene = GameScene(self, mid.get("level", 0), level=level)
        scene.apply_resume(board, mid.get("mistakes", MAX_MISTAKES),
                           mid.get("elapsed", 0.0))
        self.scene = scene

    def on_level_cleared(self, level_index, mistakes_left, score, elapsed,
                         endless=False):
        self.play("win")
        used = MAX_MISTAKES - mistakes_left
        stars = stars_for(used)
        if endless:
            self.save_data["endless_best"] = max(
                self.save_data.get("endless_best", 0), score)
        else:
            self.save_data["unlocked"] = max(self.save_data["unlocked"],
                                             level_index + 2)
            key = str(level_index)
            self.save_data["stars"][key] = max(
                self.save_data["stars"].get(key, 0), stars)
            self.save_data["scores"][key] = max(
                self.save_data["scores"].get(key, 0), score)
        self.save_data["mid_level"] = None
        save_module.save(self.save_data)
        self.scene = WinScene(self, level_index, mistakes_left, score,
                              elapsed, endless)

    def on_level_failed(self, level_index):
        self.play("fail")
        self.save_data["mid_level"] = None
        save_module.save(self.save_data)
        self.scene = FailScene(self, level_index)

    def save_mid_level(self):
        """保存当前对局的进度（每次有效点击后调用）。"""
        scene = self.scene
        if not isinstance(scene, GameScene):
            return
        self.save_data["mid_level"] = scene.serialize_state()
        save_module.save(self.save_data)

    def to_menu(self):
        self.scene = StartScene(self)

    # ---- 主循环 ----

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(config.FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.scene.handle_event(event)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()
