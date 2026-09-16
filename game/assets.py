"""绘图工具与运行时资源：中文字体、箭头绘制、程序合成音效。

所有视觉元素均由代码绘制，音效由程序实时合成，
不依赖任何外部图片/音频素材文件。
"""

import io
import math
import os
import struct
import wave

import pygame

from game import config

_FONT_CACHE = {}
# 其他平台使用 SysFont 依次尝试常见中文字体
FONT_CANDIDATES = "microsoftyahei,msyh,simhei,dengxian,simsun"

# Windows 上 pygame 2.6 的 SysFont 字体枚举存在 bug：读取注册表字体信息时
# 遇到非字符串值会抛 TypeError（见 pygame/sysfont.py 的 initsysfonts_win32），
# 导致中文字体加载失败、文字渲染成豆腐块。因此 Windows 下直接按路径加载
# 字体文件，绕过注册表枚举：
_WINDOWS_FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"   # 微软雅黑 Bold
_WINDOWS_FONT_NORMAL = r"C:\Windows\Fonts\msyh.ttc"   # 微软雅黑
_WINDOWS_FONT_FALLBACK = r"C:\Windows\Fonts\simhei.ttf"  # 黑体（备选）


def _load_windows_font(size: int, bold: bool):
    """按路径加载 Windows 中文字体；加载失败返回 None。"""
    # 粗体优先使用微软雅黑 Bold 字体文件，否则加载普通字体后由 SDL_ttf 合成粗体
    candidates = [(_WINDOWS_FONT_BOLD, False)] if bold else []
    candidates += [(_WINDOWS_FONT_NORMAL, bold), (_WINDOWS_FONT_FALLBACK, bold)]
    for path, synthesize in candidates:
        if os.path.exists(path):
            try:
                font = pygame.font.Font(path, size)
                font.set_bold(synthesize)
                return font
            except Exception:
                continue
    return None


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """带缓存的中文字体。Windows 直接按路径加载，其他平台走 SysFont。"""
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        if os.name == "nt":
            font = _load_windows_font(size, bold)
        if font is None:
            try:
                font = pygame.font.SysFont(FONT_CANDIDATES, size, bold=bold)
            except Exception:
                font = pygame.font.Font(None, size)
        _FONT_CACHE[key] = font
    return font


def draw_text(surface, text, pos, size=22, color=config.TEXT, bold=False,
              anchor="topleft"):
    """按锚点绘制单行文字，返回文字矩形。"""
    img = get_font(size, bold).render(text, True, color)
    rect = img.get_rect()
    setattr(rect, anchor, pos)
    surface.blit(img, rect)
    return rect


def draw_text_center(surface, text, center, size=22, color=config.TEXT, bold=False):
    return draw_text(surface, text, center, size, color, bold, anchor="center")


def _lighten(color, amount):
    return tuple(min(255, c + amount) for c in color)


def _darken(color, amount):
    return tuple(max(0, c - amount) for c in color)


_ARROW_CACHE = {}


def draw_arrow(surface, center, direction, size, color, alpha=255, angle_offset=0.0):
    """在 center 处绘制一支指向 direction 的箭头。

    实现方式：先画一支朝右的箭头底图，再按方向旋转。注意 pygame 的
    rotate 正角度为屏幕顺时针方向（已验证），因此映射为：
    右 0° / 上 90° / 左 180° / 下 270°，旋转结果带缓存。
    angle_offset 为附加的瞬时旋转角（用于碰撞晃动时的小幅摇摆）。
    """
    key = (size, color, direction)
    rotated = _ARROW_CACHE.get(key)
    if rotated is None:
        base = pygame.Surface((size, size), pygame.SRCALPHA)
        s = size
        points = [  # 朝右的箭头多边形：箭杆 + 三角箭头
            (s * 0.10, s * 0.38), (s * 0.58, s * 0.38),
            (s * 0.58, s * 0.16), (s * 0.90, s * 0.50),
            (s * 0.58, s * 0.84), (s * 0.58, s * 0.62),
            (s * 0.10, s * 0.62),
        ]
        shadow = [(x + s * 0.03, y + s * 0.035) for x, y in points]
        pygame.draw.polygon(base, (30, 40, 55, 90), shadow)  # 右下投影
        pygame.draw.polygon(base, (*color, 255), points)
        pygame.draw.polygon(base, (*_darken(color, 45), 255), points, 2)
        angle = {(-1, 0): 90, (1, 0): 270, (0, -1): 180, (0, 1): 0}[direction]
        rotated = pygame.transform.rotate(base, angle)
        _ARROW_CACHE[key] = rotated

    if angle_offset or alpha != 255:
        rotated = rotated.copy()
        if angle_offset:
            rotated = pygame.transform.rotate(rotated, angle_offset)
        if alpha != 255:
            rotated.set_alpha(alpha)
    surface.blit(rotated, rotated.get_rect(center=center))


def draw_star(surface, center, radius, color):
    """绘制五角星（外径 radius，内径 radius*0.45）。"""
    points = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        r = radius if i % 2 == 0 else radius * 0.45
        points.append((center[0] + r * math.cos(ang), center[1] - r * math.sin(ang)))
    pygame.draw.polygon(surface, color, points)


# ---------------------------------------------------------------------------
# 音效合成：所有音效均由代码实时生成（正弦波/方波 + 包络），无外部素材
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050


def _tone(freq, seconds, volume=0.5, sweep=0.0, shape="sine") -> bytes:
    """合成一段单声道 16bit 音：freq 起始频率，sweep 为每秒频率增量。

    包络：前 60 个采样快速起音避免爆音，随后指数衰减模拟打击感。
    """
    n = int(SAMPLE_RATE * seconds)
    out = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        f = freq + sweep * t
        phase += 2 * math.pi * f / SAMPLE_RATE
        v = math.sin(phase) if shape == "sine" \
            else (1.0 if math.sin(phase) >= 0 else -1.0)
        env = min(1.0, i / 60) * math.exp(-4.0 * t)
        out += struct.pack("<h", int(v * volume * env * 32767))
    return bytes(out)


def _to_wav(frames: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)
    return buf.getvalue()


def make_sounds() -> dict:
    """合成并返回音效字典；音频设备不可用时返回空 dict（静音运行）。"""
    try:
        return {
            # 飞出：短促的上滑音
            "launch": pygame.mixer.Sound(
                buffer=_to_wav(_tone(300, 0.22, 0.5, sweep=5400))),
            # 碰撞：低频方波闷响
            "blocked": pygame.mixer.Sound(
                buffer=_to_wav(_tone(150, 0.14, 0.6, shape="square"))),
            # 按钮点击：清脆短音
            "click": pygame.mixer.Sound(
                buffer=_to_wav(_tone(900, 0.05, 0.35))),
            # 通关：上行琶音 C5-E5-G5-C6
            "win": pygame.mixer.Sound(
                buffer=_to_wav(b"".join(_tone(f, 0.13, 0.45) for f in (523, 659, 784, 1047)))),
            # 失败：下行三音
            "fail": pygame.mixer.Sound(
                buffer=_to_wav(b"".join(_tone(f, 0.18, 0.45) for f in (392, 311, 233)))),
        }
    except pygame.error:
        return {}
