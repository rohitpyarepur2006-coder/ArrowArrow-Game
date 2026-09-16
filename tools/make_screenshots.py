"""生成 README 与博客用的界面截图和演示 GIF（无头运行，不影响游戏本体）。

运行方法（项目根目录）：
    python tools/make_screenshots.py

产物输出到 screenshots/ 目录：
    01_start.png     开始界面
    02_playing.png   游戏界面
    03_collision.png 碰撞反馈
    04_win.png       通关界面
    05_fail.png      失败界面
    demo.gif         第一关自动通关演示动画
"""

import os

# 必须在导入 pygame 之前设置，使用无窗口/无音频驱动
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame

from game import config
from game.app import App, FailScene, GameScene, StartScene, WinScene
from game.levels import LEVELS
from game.model import solve

OUT_DIR = Path(__file__).resolve().parent.parent / "screenshots"


def snapshot(app: App, filename: str):
    app.scene.draw(app.screen)
    pygame.image.save(app.screen, str(OUT_DIR / filename))
    print("saved", filename)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    app = App(sound_enabled=False)

    # 1. 开始界面
    app.scene = StartScene(app)
    app.scene.update(0.7)  # 放出一支装饰飞箭
    snapshot(app, "01_start.png")

    # 2. 游戏界面（第二关）
    app.scene = GameScene(app, 1)
    snapshot(app, "02_playing.png")

    # 3. 碰撞反馈：点击第二关被阻挡的 (0,2)↓（被 (3,2) 阻挡）
    app.scene = gs = GameScene(app, 1)
    gs._click_board(gs.cell_rect(0, 2).center)
    gs.update(0.12)
    snapshot(app, "03_collision.png")

    # 4. 通关界面
    app.scene = WinScene(app, 1, mistakes_left=2)
    app.scene.update(0.5)
    snapshot(app, "04_win.png")

    # 5. 失败界面
    app.scene = FailScene(app, 2)
    snapshot(app, "05_fail.png")

    # 6. 演示 GIF：按求解顺序自动通关第一关
    make_demo_gif(app)
    print("done.")


def make_demo_gif(app: App):
    """脚本化通关第一关：每支箭点击后渲染动画帧，最后渲染通关界面。"""
    try:
        from PIL import Image
    except ImportError:
        print("未安装 pillow，跳过 GIF 生成")
        return

    app.scene = GameScene(app, 0)
    order = solve(LEVELS[0])
    frames = []
    step = 2  # 每 2 帧取 1 帧，60fps -> 30fps

    def capture():
        app.scene.draw(app.screen)
        data = pygame.image.tostring(app.screen, "RGB")
        frames.append(Image.frombytes("RGB", app.screen.get_size(), data))

    # 开场停留 0.5 秒
    for _ in range(int(0.5 * 60)):
        app.scene.update(1 / 60)
        if _ % step == 0:
            capture()

    # 依次点击每一支可消除的箭
    for arrow in order:
        gs = app.scene
        gs._click_board(gs.cell_rect(arrow.row, arrow.col).center)
        # 每支箭渲染 0.9 秒（飞出 0.35 秒 + 间隔），通关后场景会被自动切换
        for _ in range(int(0.9 * 60)):
            app.scene.update(1 / 60)
            if _ % step == 0:
                capture()
            if not isinstance(app.scene, GameScene):
                break

    # 通关界面停留 1 秒
    for _ in range(60):
        app.scene.update(1 / 60)
        if _ % step == 0:
            capture()

    # 缩放到 60% 控制文件大小
    frames = [f.resize((config.WINDOW_WIDTH * 3 // 5, config.WINDOW_HEIGHT * 3 // 5),
                       Image.LANCZOS) for f in frames]
    path = OUT_DIR / "demo.gif"
    frames[0].save(str(path), save_all=True, append_images=frames[1:],
                   duration=33, loop=0)
    # 注意：PIL 保存 GIF 时会合并与前一帧相同的帧（时长累加），
    # 因此文件中的帧数少于捕获数，但播放时长与节奏不变。
    with Image.open(path) as gif:
        print(f"saved {path.name}（捕获 {len(frames)} 帧，写入 {gif.n_frames} 个不重复帧）")


if __name__ == "__main__":
    main()
