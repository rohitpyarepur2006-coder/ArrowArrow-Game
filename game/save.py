"""游戏进度存档：读写 JSON 文件（纯逻辑，不依赖 pygame）。

存档内容：
- unlocked：已解锁的关卡数量（完成第 i 关后解锁第 i+1 关）
- stars / scores：每关的历史最佳星级与最高分
- endless_best：无尽模式最高分
- mid_level：进行到一半的对局（继续游戏功能），None 表示无

打包成 exe 后存档保存在 exe 所在目录，源码运行时保存在项目根目录。
"""

import copy
import json
import sys
from pathlib import Path

DEFAULTS = {
    "unlocked": 1,
    "stars": {},          # {"0": 3, "1": 2, ...}
    "scores": {},         # {"0": 1250, ...}
    "endless_best": 0,
    "mid_level": None,
}


def save_path() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包后的 exe
        return Path(sys.executable).parent / "save.json"
    return Path(__file__).resolve().parent.parent / "save.json"


def load() -> dict:
    """读取存档；文件不存在或损坏时返回默认值。"""
    try:
        data = json.loads(save_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)
    merged = copy.deepcopy(DEFAULTS)
    if isinstance(data, dict):
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save(data: dict) -> bool:
    """写入存档；失败时静默返回 False（不影响游戏运行）。"""
    try:
        save_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False
