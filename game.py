import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

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

    pyxel.init(
        settings["screen_width"],
        settings["screen_height"],
        title="Zuma: Tower Defense",
        fps=settings["fps"],     
        display_scale=3,
        capture_scale=1,
        quit_key=pyxel.KEY_NONE
    )
    pyxel.mouse(True)

    controller = GameController(settings)
    view       = GameView(controller)

    pyxel.run(controller.update, view.draw)


if __name__ == "__main__":
    main()
