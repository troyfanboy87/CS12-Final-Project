"""
game.py — entry point. Run with:

    uv sync
    source .venv/bin/activate
    pyxel run game.py

This file is intentionally tiny. All it does is:
  1. Load settings.json
  2. Initialize Pyxel
  3. Construct the Controller (which owns the Model)
  4. Construct the View (which reads through the Controller)
  5. Hand Pyxel two callbacks: update() and draw()

Pyxel then runs its main loop, calling update() then draw() once per frame
at the configured FPS. Everything else lives inside src/.
"""

import json
import pathlib
import sys

# `pyxel run game.py` uses runpy under the hood, which does NOT add the
# script's folder to sys.path the way `python game.py` does. Without this
# the `from src...` imports below raise ModuleNotFoundError.
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Diagnostics if `src` is mis-laid-out.
_src_dir = _HERE / "src"
if not _src_dir.is_dir():
    print("=" * 60, file=sys.stderr)
    print("ERROR: 'src' folder not found next to game.py", file=sys.stderr)
    print(f"  Looking in: {_HERE}", file=sys.stderr)
    print(f"  Contents:   {sorted(p.name for p in _HERE.iterdir())}",
          file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)
if not (_src_dir / "__init__.py").is_file():
    print("=" * 60, file=sys.stderr)
    print("ERROR: 'src/__init__.py' is missing.", file=sys.stderr)
    print("Make sure src/ contains __init__.py, model.py, view.py, controller.py.",
          file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    sys.exit(1)

import pyxel

from src.controller import GameController
from src.view import GameView


def main() -> None:
    here = pathlib.Path(__file__).parent
    with open(here / "settings.json", "r") as f:
        settings = json.load(f)

    # Initialize Pyxel BEFORE constructing the controller — SoundManager
    # uses pyxel.sounds[...] in its constructor, which needs init() done.
    pyxel.init(
        settings["screen_width"],
        settings["screen_height"],
        title="Zuma: Tower Defense",
        fps=settings["fps"],          # Phase 1e: FPS must be 30
        display_scale=3,
        capture_scale=1,
    )
    pyxel.mouse(True)

    controller = GameController(settings)
    view       = GameView(controller)

    pyxel.run(controller.update, view.draw)


if __name__ == "__main__":
    main()
