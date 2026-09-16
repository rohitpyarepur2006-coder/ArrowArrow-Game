"""可复用 UI 控件。"""

import pygame

from game import config
from game.assets import get_font


class Button:
    """圆角矩形按钮：支持悬停高亮与点击回调。"""

    def __init__(self, center, text, callback, size=(132, 46),
                 color=config.PRIMARY, font_size=22):
        self.rect = pygame.Rect(0, 0, *size)
        self.rect.center = center
        self.text = text
        self.callback = callback
        self.color = color
        self.font = get_font(font_size, bold=True)
        self.hovered = False

    def handle_event(self, event):
        """鼠标事件处理；被点击时执行回调并返回 True。"""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()
                return True
        return False

    def draw(self, surface):
        # 悬停时略微变亮 + 外描边，按下效果由回调即时触发
        base = tuple(min(255, c + 22) for c in self.color) if self.hovered else self.color
        shadow = pygame.Rect(self.rect.move(0, 3))
        pygame.draw.rect(surface, (30, 40, 55, 60), shadow, border_radius=12)
        pygame.draw.rect(surface, base, self.rect, border_radius=12)
        pygame.draw.rect(surface, tuple(max(0, c - 45) for c in base),
                         self.rect, 2, border_radius=12)
        text = self.font.render(self.text, True, config.WHITE)
        surface.blit(text, text.get_rect(center=self.rect.center))
