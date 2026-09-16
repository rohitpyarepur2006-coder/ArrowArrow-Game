"""游戏主程序：场景管理与界面渲染。

场景划分：
- StartScene   开始界面（标题、规则说明、开始按钮、装饰飞箭）
- GameScene    游戏界面（HUD、棋盘、飞出/碰撞动画、提示、重新开始）
- WinScene     通关界面（星级、下一关）
- FailScene    失败界面（重新开始、返回主菜单）

动画实现说明：箭头被点击后立即从逻辑棋盘（Game.board）移除，
画面上的"飞出"由 FlyingArrow 特效独立渲染，二者互不干扰；
碰撞反馈由 Collision 特效驱动：箭头原地晃动 + 红色闪烁 + 浮动文字。
"""

import math
import random

import pygame

from game import config
from game.assets import draw_arrow, draw_star, draw_text, draw_text_center, get_font, make_sounds
from game.levels import LEVELS, MAX_MISTAKES
from game.model import Game, LaunchResult, solve
from game.ui import Button


# ---------------------------------------------------------------------------
# 动画特效
# ---------------------------------------------------------------------------

class FlyingArrow:
    """飞出动画：记录被消除的箭头与动画进度。"""

    def __init__(self, arrow, start_center):
        self.arrow = arrow
        self.start = pygame.Vector2(start_center)
        dr, dc = arrow.direction
        # 屏幕坐标换算：行号变化 -> y 轴，列号变化 -> x 轴
        self.screen_dir = pygame.Vector2(dc, dr)
        self.t = 0.0
        self.duration = config.FLY_SECONDS

    @property
    def pos(self):
        # 缓动：先快后慢
        k = min(1.0, self.t / self.duration)
        k = 1 - (1 - k) ** 2
        distance = max(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        return self.start + self.screen_dir * (k * distance)

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
        draw_arrow(surface, self.pos, self.arrow.direction,
                   int(config.CELL * 0.66), color, int(alpha))


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
    """通关庆祝粒子：带重力的彩色圆点。"""

    def __init__(self, center):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(90, 280)
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
    """开始界面：标题 + 规则说明 + 开始按钮 + 装饰飞箭。"""

    RULES = [
        "点击箭头：前进方向没有其他箭头阻挡时，它会飞出棋盘",
        "清除棋盘上全部箭头即可通关",
        "点错被阻挡的箭头会消耗一次失误机会，机会用完则本关失败",
    ]

    def __init__(self, app):
        self.app = app
        self.mouse_pos = (-1, -1)
        self.button = Button((config.WINDOW_WIDTH // 2, 512), "开始游戏",
                             self.start, size=(180, 56), font_size=26)
        self.decor = []       # [(FlyingArrow, alpha), ...]
        self.decor_timer = 0.0

    def start(self):
        self.app.play("click")
        self.app.start_game(0)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        self.button.handle_event(event)

    def update(self, dt):
        # 每隔 0.7 秒从窗口边缘放出一支半透明的装饰飞箭
        self.decor_timer -= dt
        if self.decor_timer <= 0:
            self.decor_timer = 0.7
            edge = random.randrange(4)
            if edge == 0:
                pos, direction = (-40, random.uniform(60, 640)), (0, 1)
            elif edge == 1:
                pos, direction = (config.WINDOW_WIDTH + 40, random.uniform(60, 640)), (0, -1)
            elif edge == 2:
                pos, direction = (random.uniform(60, 700), -40), (1, 0)
            else:
                pos, direction = (random.uniform(60, 700), config.WINDOW_HEIGHT + 40), (-1, 0)
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
                         (config.WINDOW_WIDTH // 2, 190), 64, config.TEXT, bold=True)
        draw_text_center(surface, "箭 头 解 谜 小 游 戏",
                         (config.WINDOW_WIDTH // 2, 255), 26, config.TEXT_LIGHT)
        for i, line in enumerate(self.RULES):
            draw_text_center(surface, line,
                             (config.WINDOW_WIDTH // 2, 330 + i * 36),
                             21, config.TEXT_LIGHT)
        self.button.draw(surface)
        draw_text_center(surface, "Python + Pygame · 软件工程课程作业",
                         (config.WINDOW_WIDTH // 2, 660), 17, config.TEXT_LIGHT)


# ---------------------------------------------------------------------------
# 游戏界面
# ---------------------------------------------------------------------------

class GameScene:
    """游戏场景：渲染 HUD 与棋盘，处理点击与动画。"""

    def __init__(self, app, level_index):
        self.app = app
        self.level_index = level_index
        self.game = Game(LEVELS[level_index], MAX_MISTAKES)
        self.mouse_pos = (-1, -1)
        self.flying = []            # 飞出动画
        self.collisions = {}        # {(row, col): Collision}
        self.float_texts = []
        self.blocker_ring = None    # (rect, t) 碰撞瞬间圈出阻挡箭头
        self.hint = None            # (arrow, t) 提示高亮
        self.mistake_flash_t = 99   # 距上次失误的时间（用于失误数闪红）
        self.pending = None         # "cleared" / "failed"，等待进入结果界面
        self.pending_t = 0.0
        self._build_buttons()

    def _build_buttons(self):
        y = 96
        self.buttons = [
            Button((270, y), "提 示", self.do_hint, color=config.GOLD),
            Button((380, y), "重新开始", self.do_restart),
            Button((490, y), "主菜单", self.do_menu, color=(140, 152, 166)),
        ]

    # ---- 回调 ----

    def do_hint(self):
        if self.pending:
            return
        arrow = self.game.next_hint()
        if arrow is not None:
            self.hint = (arrow, 0.0)
            self.app.play("click")

    def do_restart(self):
        self.app.play("click")
        self.game.restart()
        self.flying.clear()
        self.collisions.clear()
        self.float_texts.clear()
        self.blocker_ring = None
        self.hint = None
        self.pending = None

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
        result = self.game.click(*cell)
        if result.result is LaunchResult.NO_ARROW:
            return
        if result.result is LaunchResult.BLOCKED:
            self.app.play("blocked")
            self.mistake_flash_t = 0.0
            rect = self.cell_rect(*cell)
            self.collisions[cell] = Collision(result.arrow, rect)
            self.blocker_ring = (self.cell_rect(result.blocker.row, result.blocker.col), 0.0)
            self.float_texts.append(FloatText("被阻挡！", rect.center, config.DANGER,
                                              font_size=28))
            if self.game.status == "failed":
                self._schedule("failed")
        else:  # FLY_OUT
            self.app.play("launch")
            start = self.cell_rect(*cell).center
            self.flying.append(FlyingArrow(result.arrow, start))
            self.hint = None
            if self.game.status == "cleared":
                self._schedule("cleared")

    def _schedule(self, status):
        self.pending = status
        self.pending_t = config.TRANSITION_DELAY

    # ---- 更新与绘制 ----

    def update(self, dt):
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
        if self.blocker_ring:
            self.blocker_ring = (self.blocker_ring[0], self.blocker_ring[1] + dt)
        if self.hint:
            arrow, t = self.hint
            if t >= config.HINT_SECONDS:
                self.hint = None
            else:
                self.hint = (arrow, t + dt)
        if self.pending:
            self.pending_t -= dt
            if self.pending_t <= 0:
                if self.pending == "cleared":
                    self.app.on_level_cleared(self.level_index, self.game.mistakes_left)
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
        self._draw_rings(surface)
        for ft in self.float_texts:
            ft.draw(surface)

    def _draw_hud(self, surface):
        draw_text(surface, f"第 {self.level_index + 1} 关",
                  (28, 16), 26, config.TEXT, bold=True)
        draw_text(surface, self.game.level.name, (28, 52), 20, config.TEXT_LIGHT)
        right = config.WINDOW_WIDTH - 330
        draw_text(surface, f"剩余箭头：{self.game.remaining}", (right, 16), 24)
        # 刚发生失误时失误数字闪红提醒
        flash = max(0.0, 1 - self.mistake_flash_t / 0.6)
        mistake_color = config.DANGER if flash > 0 else config.TEXT
        draw_text(surface, f"剩余失误：{self.game.mistakes_left}",
                  (right, 52), 24, mistake_color)
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
    """通关界面：星级评价 + 下一关/返回主菜单。"""

    def __init__(self, app, level_index, mistakes_left):
        self.app = app
        self.level_index = level_index
        self.mistakes_left = mistakes_left
        self.mouse_pos = (-1, -1)
        # 星级：3 次失误一次没用 -> 3 星，用 1 次 -> 2 星，用 2 次 -> 1 星
        self.stars = MAX_MISTAKES - (MAX_MISTAKES - mistakes_left)
        self.particles = [Particle((config.WINDOW_WIDTH // 2, 210)) for _ in range(50)]
        last = level_index == len(LEVELS) - 1
        if last:
            self.buttons = [Button((config.WINDOW_WIDTH // 2, 470),
                                   "返回主菜单", self.to_menu, size=(180, 54))]
        else:
            self.buttons = [
                Button((288, 470), "下一关", self.next_level, size=(180, 54),
                       color=config.SUCCESS),
                Button((492, 470), "主菜单", self.to_menu, size=(160, 54),
                       color=(140, 152, 166)),
            ]

    def next_level(self):
        self.app.play("click")
        self.app.start_game(self.level_index + 1)

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
        last = self.level_index == len(LEVELS) - 1
        title = "恭喜通关全部关卡！" if last else f"第 {self.level_index + 1} 关 通关！"
        draw_text_center(surface, title, (config.WINDOW_WIDTH // 2, 190),
                         52, config.SUCCESS, bold=True)
        # 三颗星：未获得的画成灰色
        cx = config.WINDOW_WIDTH // 2
        for i in range(3):
            center = (cx + (i - 1) * 110, 290)
            color = config.GOLD if i < self.stars else (214, 220, 228)
            draw_star(surface, center, 40, color)
        draw_text_center(surface, f"剩余失误机会：{self.mistakes_left}",
                         (config.WINDOW_WIDTH // 2, 380), 24, config.TEXT_LIGHT)
        for button in self.buttons:
            button.draw(surface)


class FailScene:
    """失败界面：重新开始 / 返回主菜单。"""

    def __init__(self, app, level_index):
        self.app = app
        self.level_index = level_index
        self.mouse_pos = (-1, -1)
        self.buttons = [
            Button((290, 440), "重新开始", self.restart, size=(180, 54)),
            Button((490, 440), "主菜单", self.to_menu, size=(160, 54),
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
        draw_text_center(surface, f"第 {self.level_index + 1} 关 失败",
                         (config.WINDOW_WIDTH // 2, 220), 52, config.DANGER, bold=True)
        draw_text_center(surface, "失误机会已用完，再试一次吧！",
                         (config.WINDOW_WIDTH // 2, 310), 26, config.TEXT_LIGHT)
        for button in self.buttons:
            button.draw(surface)


# ---------------------------------------------------------------------------
# 应用外壳
# ---------------------------------------------------------------------------

class App:
    """初始化 pygame，管理场景切换与主循环。"""

    def __init__(self, sound_enabled=True):
        pygame.init()
        pygame.display.set_caption(config.TITLE)
        self.screen = pygame.display.set_mode(
            (config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.sounds = make_sounds() if sound_enabled else {}
        self.scene = StartScene(self)

    def play(self, name):
        sound = self.sounds.get(name)
        if sound:
            sound.play()

    # ---- 场景切换 ----

    def start_game(self, level_index):
        self.scene = GameScene(self, level_index)

    def on_level_cleared(self, level_index, mistakes_left):
        self.play("win")
        self.scene = WinScene(self, level_index, mistakes_left)

    def on_level_failed(self, level_index):
        self.play("fail")
        self.scene = FailScene(self, level_index)

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


def demo_solution(level_index):
    """返回指定关卡的一条可行通关顺序（供自动化测试/演示使用）。"""
    return solve(LEVELS[level_index])
