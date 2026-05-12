"""
Model layer — pure game logic. NO pyxel imports anywhere in this module.

That single rule (no pyxel here) is what makes the model unit-testable in a
headless terminal. The view and controller import pyxel; the model doesn't.

This file is organized top-to-bottom in the order you'd build the game:

    1. CONSTANTS       — colors, directions, sizes, GameState enum
    2. PATH            — polyline route enemies travel along (+ tunnels)
    3. ENTITIES        — Entity ABC, BulletSource Protocol, concrete classes
    4. ENEMY FACTORY   — registry pattern for current + future enemy types
    5. ROUND MANAGER   — spawn scheduling + round progression
    6. GAME MODEL      — top-level container that holds everything above

Use Ctrl+F on the section banners to jump around.
"""

import math
import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol, Tuple


# ===========================================================================
# 1. CONSTANTS
# ===========================================================================

# Pyxel's default 16-color palette indices. We keep our own name->index map
# so game logic refers to "red"/"green" instead of magic ints. The View is
# the one place that turns these names into Pyxel ints.
COLOR_PALETTE: Dict[str, int] = {
    "red":    8,
    "green":  11,
    "blue":   12,
    "yellow": 10,
    "purple": 2,
    "orange": 9,
}

# Phase N uses the first N colors. Phase 4 = 4, Phase 5 = 5, Phase 6 = 6.
COLOR_ORDER: List[str] = ["red", "green", "blue", "yellow", "purple", "orange"]


class GameState(str, Enum):
    """Top-level state machine. str-Enum so print(state) -> 'playing'."""
    MENU      = "menu"
    PLAYING   = "playing"
    BUILDING  = "building"
    GAME_OVER = "game_over"
    WIN       = "win"


class Direction(str, Enum):
    """Cardinal directions for towers (Phase 4: WASD-settable)."""
    UP    = "up"
    DOWN  = "down"
    LEFT  = "left"
    RIGHT = "right"


# Unit vectors per direction. Y grows DOWN in screen coords (standard 2D).
DIRECTION_VECTORS: Dict[Direction, Tuple[int, int]] = {
    Direction.UP:    (0, -1),
    Direction.DOWN:  (0,  1),
    Direction.LEFT:  (-1, 0),
    Direction.RIGHT: (1,  0),
}


# Hitbox sizes in pixels. Game logic uses these; the View uses the same
# numbers to draw circles the matching size.
ENEMY_RADIUS:  int = 5
BULLET_RADIUS: int = 2
TOWER_HALF:    int = 5   # tower is 10x10
SHOOTER_HALF:  int = 6


# ===========================================================================
# 2. PATH (with Phase 4 tunnels)
# ===========================================================================

class TunnelSegment:
    """
    A stretch of the path where bullets cannot hit enemies (Phase 4b).

    Stored as (start, end) in path-progress units (pixels of arc length).
    The Path's constructor converts spec-friendly *cell* indices into pixel
    intervals.
    """
    __slots__ = ("start", "end")

    def __init__(self, start: float, end: float):
        assert end > start, "tunnel must have positive length"
        self.start = start
        self.end   = end

    @property
    def length(self) -> float:
        return self.end - self.start

    def contains(self, progress: float) -> bool:
        return self.start <= progress <= self.end


class Path:
    """
    Polyline route enemies follow. Enemies move along it by storing one
    scalar `progress` (distance from start in pixels). Beats segment-index
    bookkeeping and generalizes trivially to curved paths later.

    Spec compliance:
      Phase 1b: single horizontal line  -> Path([(0, y), (w, y)])
      Phase 2b: right-angled polyline   -> Path([..., bends, ...])
      Phase 3b: at most two paths       -> GameModel holds a list of Paths
      Phase 4b: tunnels                 -> Path.tunnels, validated below
    """

    def __init__(
        self,
        waypoints: List[Tuple[int, int]],
        tunnels_in_cells: Optional[List[Tuple[int, int]]] = None,
        cell_size: int = 16,
    ):
        """
        waypoints       : list of (x, y) pixel coords. Must have >= 2 points.
        tunnels_in_cells: list of (start_cell, end_cell) measured in *cells*
                          from the path start. Phase 4b spec:
                            - each tunnel is 2..5 cells long
                            - at most 2 tunnels per path
                            - total tunnel length <= half the full path
                          Enforced via assert so the model rejects an illegal
                          configuration at construction time.
        cell_size       : pixels per cell. Used to convert above.
        """
        assert len(waypoints) >= 2, "A path needs at least 2 waypoints"
        self.waypoints = list(waypoints)
        self.cell_size = cell_size

        # Pre-compute cumulative arc length so position_at() is fast.
        self.cumulative_lengths: List[float] = [0.0]
        for i in range(1, len(self.waypoints)):
            x0, y0 = self.waypoints[i - 1]
            x1, y1 = self.waypoints[i]
            seg_len = math.hypot(x1 - x0, y1 - y0)
            self.cumulative_lengths.append(self.cumulative_lengths[-1] + seg_len)
        self.total_length: float = self.cumulative_lengths[-1]

        # Phase 4: build & validate tunnels.
        self.tunnels: List[TunnelSegment] = []
        if tunnels_in_cells:
            assert len(tunnels_in_cells) <= 2, \
                "Phase 4b: a path can have at most two tunnels"
            for sc, ec in tunnels_in_cells:
                cells = ec - sc
                assert 2 <= cells <= 5, \
                    f"Phase 4b: each tunnel must be 2..5 cells long (got {cells})"
                self.tunnels.append(
                    TunnelSegment(sc * cell_size, ec * cell_size)
                )
            total_tunnel_len = sum(t.length for t in self.tunnels)
            assert total_tunnel_len <= self.total_length / 2, (
                "Phase 4b: total tunnel length must not exceed half the path "
                f"length (got {total_tunnel_len:.1f} > {self.total_length / 2:.1f})"
            )

    # ---- position queries ----

    def position_at(self, progress: float) -> Tuple[float, float]:
        """Convert scalar progress (distance from start) to (x, y). Clamped."""
        if progress <= 0:
            return self.waypoints[0]
        if progress >= self.total_length:
            return self.waypoints[-1]
        # Linear scan: paths have ≤ 10 segments; binary search isn't worth it.
        for i in range(1, len(self.cumulative_lengths)):
            if progress <= self.cumulative_lengths[i]:
                seg_start = self.cumulative_lengths[i - 1]
                seg_end   = self.cumulative_lengths[i]
                seg_len   = seg_end - seg_start
                t = (progress - seg_start) / seg_len if seg_len > 0 else 0
                x0, y0 = self.waypoints[i - 1]
                x1, y1 = self.waypoints[i]
                return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        return self.waypoints[-1]

    def is_progress_in_tunnel(self, progress: float) -> bool:
        """Phase 4b: enemies inside a tunnel are shielded from bullets."""
        for t in self.tunnels:
            if t.contains(progress):
                return True
        return False


# ===========================================================================
# 3. ENTITIES — Entity ABC, BulletSource Protocol, concrete subclasses
# ===========================================================================

class Entity(ABC):
    """
    Base class for anything that lives at a position on the field and can die.

    Why an ABC?
      - Documents the contract once.
      - Lets us use isinstance checks in collision systems.
      - Forces subclasses to implement update() (the @abstractmethod).

    Why ABC rather than Protocol? Because we want the *implementation* —
    the shared x/y/alive fields and kill()/distance_to() — not just the
    contract. Protocols are for pure contracts; ABCs are for shared base
    behavior.
    """

    def __init__(self, x: float, y: float):
        self.x: float = float(x)
        self.y: float = float(y)
        self.alive: bool = True

    @abstractmethod
    def update(self, *args, **kwargs) -> None:
        """Advance this entity's state by one frame."""
        ...

    def kill(self) -> None:
        self.alive = False

    def distance_to(self, other: "Entity") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


class BulletSource(Protocol):
    """
    Structural type for anything that can fire bullets. Shooter and Tower
    both satisfy this WITHOUT inheriting it — that's the power of Protocol.

    Interface Segregation: we don't shove "can be a tower" stuff into
    Bullet just because they coexist; this protocol is the minimum we
    need from a thing-that-fires.
    """
    x: float
    y: float
    def produce_bullets(self, bullet_speed: float) -> List["Bullet"]: ...


class Bullet(Entity):
    """Straight-line projectile fired by Shooter or Tower."""

    def __init__(self, x: float, y: float, vx: float, vy: float, color: str):
        super().__init__(x, y)
        self.vx = vx
        self.vy = vy
        self.color = color

    def update(self) -> None:  # type: ignore[override]
        self.x += self.vx
        self.y += self.vy

    def is_offscreen(self, screen_w: int, screen_h: int) -> bool:
        return (self.x < 0 or self.x > screen_w or
                self.y < 0 or self.y > screen_h)


class Shooter(Entity):
    """
    The player-controlled turret. Sits at a fixed location, aims at the
    mouse cursor (Phase 3+), fires bullets of a chosen color.

    Phase 1: fires up.
    Phase 2: fires in cardinal directions (WASD).
    Phase 3+: aims at mouse cursor (any angle).
    """

    def __init__(self, x: float, y: float, num_colors: int):
        super().__init__(x, y)
        assert num_colors >= 1
        self.num_colors = num_colors
        self.color_idx = 0
        self.aim_angle = -math.pi / 2  # default: up

    @property
    def color(self) -> str:
        return COLOR_ORDER[self.color_idx]

    def cycle_color(self, direction: int = 1) -> None:
        self.color_idx = (self.color_idx + direction) % self.num_colors

    def set_color_index(self, idx: int) -> None:
        if 0 <= idx < self.num_colors:
            self.color_idx = idx

    def aim_at(self, target_x: float, target_y: float) -> None:
        dx = target_x - self.x
        dy = target_y - self.y
        if dx == 0 and dy == 0:
            return
        # atan2 (not atan): knows the quadrant, returns full -pi..pi range.
        self.aim_angle = math.atan2(dy, dx)

    def update(self) -> None:  # type: ignore[override]
        # Driven externally by the controller (aim + fire); nothing to tick.
        pass

    def produce_bullets(self, bullet_speed: float) -> List[Bullet]:
        vx = math.cos(self.aim_angle) * bullet_speed
        vy = math.sin(self.aim_angle) * bullet_speed
        return [Bullet(self.x, self.y, vx, vy, self.color)]


class Enemy(Entity):
    """
    Walks along the path. Has a color and HP.

    Spec: "An enemy loses a life if shot with a bullet of the same color."

    Open/Closed: Phase 5 introduces Regenerator (gains HP) and Chameleon
    (changes color). They subclass Enemy and override update() — no edits
    to this base class needed.
    """

    KIND: str = "normal"  # subclasses override for visual differentiation

    def __init__(
        self,
        color: str,
        hp: int,
        speed: float,
        exp_value: int = 1,
        path_index: int = 0,
    ):
        super().__init__(0.0, 0.0)
        self.color: str = color
        self.hp: int = hp
        self.max_hp: int = hp
        self.speed: float = speed       # pixels per frame
        self.progress: float = 0.0
        self.escaped: bool = False
        self.exp_value: int = exp_value
        self.path_index: int = path_index
        self.in_tunnel: bool = False    # filled in update() each frame

    def take_damage(self, bullet_color: str, amount: int = 1) -> bool:
        """Returns True if the bullet matched our color (and was consumed)."""
        if bullet_color != self.color:
            return False
        # Phase 4b: tunneled enemies are immune. Defense in depth — the
        # collision system also checks, but checking here too means any
        # future direct caller gets correct behavior.
        if self.in_tunnel:
            return False
        self.hp -= amount
        if self.hp <= 0:
            self.kill()
        return True

    def update(self, path: Path) -> None:  # type: ignore[override]
        if not self.alive or self.escaped:
            return
        self.progress += self.speed
        if self.progress >= path.total_length:
            self.escaped = True
            self.kill()
        self.x, self.y = path.position_at(self.progress)
        self.in_tunnel = path.is_progress_in_tunnel(self.progress)


class Tower(Entity):
    """
    Stationary structure placed between rounds.

    Phase 2: shoots upward, single color.
    Phase 3 upgraded: shoots two bullets of different colors.
    Phase 4: shoots in a CHOSEN cardinal direction, settable via WASD
             DURING ROUNDS (spec 4a). We store self.direction and rotate
             the velocity vector accordingly.
    """

    FIRE_COOLDOWN_FRAMES = 30  # 1 shot/sec at 30 FPS

    def __init__(self, x: float, y: float, color: str):
        super().__init__(x, y)
        self.color: str = color
        self.upgraded: bool = False
        self.color_b: Optional[str] = None
        self.cooldown: int = 0
        self.direction: Direction = Direction.UP   # Phase 4a default
        self.selected: bool = False   # UI: which tower WASD controls

    def upgrade(self, second_color: str) -> None:
        self.upgraded = True
        self.color_b = second_color

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction

    def update(self) -> None:  # type: ignore[override]
        if self.cooldown > 0:
            self.cooldown -= 1

    def can_fire(self) -> bool:
        return self.cooldown == 0

    def produce_bullets(self, bullet_speed: float) -> List[Bullet]:
        """Phase 4: fires in self.direction. Upgraded fires two bullets."""
        self.cooldown = self.FIRE_COOLDOWN_FRAMES
        dx, dy = DIRECTION_VECTORS[self.direction]
        vx = dx * bullet_speed
        vy = dy * bullet_speed
        bullets = [Bullet(self.x, self.y, vx, vy, self.color)]
        if self.upgraded and self.color_b is not None:
            # Offset second bullet perpendicular to firing direction so they
            # don't visually overlap.
            ox, oy = -dy, dx
            bullets.append(
                Bullet(self.x + ox * 3, self.y + oy * 3,
                       vx, vy, self.color_b)
            )
        return bullets


# ===========================================================================
# 4. ENEMY FACTORY — registry pattern for current + future enemy types
# ===========================================================================

class EnemyFactory:
    """
    Maps a 'kind' name to a builder function.

    Phase 4 only has 'normal'. Phase 5 will call factory.register("regenerator",
    builder_fn) and factory.register("chameleon", ...). The Controller and the
    rest of the codebase don't change. This is the textbook Open/Closed
    pattern: open for extension, closed for modification.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self._builders: Dict[str, Callable[..., Enemy]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("normal", self._build_normal)

    def register(self, kind: str, builder: Callable[..., Enemy]) -> None:
        self._builders[kind] = builder

    def create(self, kind: str, *, color: str, path_index: int) -> Enemy:
        if kind not in self._builders:
            raise ValueError(f"Unknown enemy kind: {kind!r}")
        return self._builders[kind](color=color, path_index=path_index)

    # ---- built-in builders ----

    def _build_normal(self, *, color: str, path_index: int) -> Enemy:
        return Enemy(
            color=color,
            hp=self.settings["enemy_hp"],
            speed=self.settings["enemy_speed"],
            exp_value=self.settings["exp_per_kill"],
            path_index=path_index,
        )

    # ---- selection policy ----

    def pick_kind(self, current_round: int) -> str:
        """
        Returns a kind string. Phase 4 always returns "normal".
        Phase 5 will replace this with weighted-random selection that
        includes "regenerator" and "chameleon" based on current_round.
        """
        return "normal"

    def pick_color(self) -> str:
        n = self.settings["num_colors"]
        return random.choice(COLOR_ORDER[:n])


# ===========================================================================
# 5. ROUND MANAGER — spawn scheduling + round progression
# ===========================================================================

class RoundManager:
    """
    Drives the spawn queue for the current round and decides when a round
    ends. Pulled out of GameModel because before the split GameModel had
    THREE responsibilities (state container, round progression, spawn
    scheduling) — that's a Single Responsibility violation.

    Does NOT mutate lives or EXP. That's the controller's call after reading
    round_complete() / state.
    """

    SPAWN_INTERVAL_FRAMES = 30  # ~1 second between spawns at 30 FPS

    def __init__(self, settings: dict, enemy_factory: EnemyFactory):
        self.settings = settings
        self.factory  = enemy_factory
        self.total_rounds: int   = settings["rounds"]
        self.current_round: int  = 0
        self._enemies_to_spawn: int = 0
        self._spawn_timer: int      = 0

    # ---- round flow ----

    def start_next_round(self) -> bool:
        """Returns True if a new round actually started; False if all done."""
        if self.current_round >= self.total_rounds:
            return False
        self.current_round += 1
        self._enemies_to_spawn = self.settings["enemies_per_round"]
        self._spawn_timer = 0
        return True

    def all_rounds_finished(self) -> bool:
        return self.current_round >= self.total_rounds

    # ---- spawning ----

    def maybe_spawn(self, num_paths: int) -> Optional[Enemy]:
        """
        Tick the spawn timer; if one fires, return a freshly-built Enemy.
        Otherwise return None. Caller appends to model.enemies.
        """
        if self._enemies_to_spawn <= 0:
            return None
        if self._spawn_timer > 0:
            self._spawn_timer -= 1
            return None

        # Path-assignment policy. Round 1 uses path 0 only (gentle intro);
        # round 2+ randomizes across all paths. Three lines = difficulty curve.
        if self.current_round <= 1 or num_paths < 2:
            path_idx = 0
        else:
            path_idx = random.randint(0, num_paths - 1)

        kind  = self.factory.pick_kind(self.current_round)
        color = self.factory.pick_color()
        enemy = self.factory.create(kind, color=color, path_index=path_idx)

        self._enemies_to_spawn -= 1
        self._spawn_timer = self.SPAWN_INTERVAL_FRAMES
        return enemy

    def round_complete(self, live_enemies: List[Enemy]) -> bool:
        """True when no more to spawn AND all spawned enemies are gone."""
        return (self._enemies_to_spawn == 0
                and not any(e.alive for e in live_enemies))


# ===========================================================================
# 6. GAME MODEL — top-level container that holds everything above
# ===========================================================================

class GameModel:
    """
    Single source of truth for game state. Holds:
      - Level geometry (paths)
      - Live entities (shooter, enemies, bullets, towers)
      - Player progression (lives, exp)
      - The state enum
      - A RoundManager that runs the spawn schedule

    Controller mutates this. View only reads it. That's the only MVC rule.
    """

    def __init__(self, settings: dict):
        self.settings = settings

        sw = settings["screen_width"]
        sh = settings["screen_height"]
        cs = settings["cell_size"]

        # -------- Paths (Phase 3b: at most two; Phase 4b: tunnels allowed) --
        # Path A: enters left-middle, goes right, turns down, exits bottom.
        # Path B: enters top-left, goes down, turns right, exits right edge.
        # Tunnel windows are measured from the path start in cells. Path A's
        # first leg is sw - cs*4 = 192 px wide (12 cells), so cells 5..8 is
        # a 3-cell tunnel. Path B's first leg is sh - cs*5 = 176 px (11 cells);
        # cells 4..7 is a 3-cell tunnel near the top.
        self.paths: List[Path] = [
            Path(
                waypoints=[
                    (0,            sh // 2),
                    (sw - cs * 4,  sh // 2),
                    (sw - cs * 4,  sh - cs),
                ],
                tunnels_in_cells=[(5, 8)],
                cell_size=cs,
            ),
            Path(
                waypoints=[
                    (cs * 2,       0),
                    (cs * 2,       sh - cs * 5),
                    (sw - cs,      sh - cs * 5),
                ],
                tunnels_in_cells=[(4, 7)],
                cell_size=cs,
            ),
        ]
        # Convenience alias for any code that references "the" single path.
        self.path = self.paths[0]

        # -------- Player-controlled entities --------
        self.shooter = Shooter(sw // 2, sh // 2, settings["num_colors"])

        # -------- Progression --------
        self.lives: int = settings["player_lives"]
        self.exp: int   = 0
        self.state: GameState = GameState.MENU

        # -------- Live entity lists --------
        self.enemies: List[Enemy] = []
        self.bullets: List[Bullet] = []
        self.towers:  List[Tower]  = []

        # -------- Round / spawn driver (SRP: pulled out) --------
        self.enemy_factory = EnemyFactory(settings)
        self.round_manager = RoundManager(settings, self.enemy_factory)

    # ---- accessors ----

    @property
    def current_round(self) -> int:
        return self.round_manager.current_round

    @property
    def total_rounds(self) -> int:
        return self.round_manager.total_rounds

    # ---- round flow (delegated) ----

    def start_next_round(self) -> None:
        # Wipe leftover state so the next round starts clean.
        self.enemies.clear()
        self.bullets.clear()
        if self.round_manager.start_next_round():
            self.state = GameState.PLAYING
        else:
            self.state = GameState.WIN

    def end_round(self) -> None:
        if self.round_manager.all_rounds_finished():
            self.state = GameState.WIN
        else:
            self.state = GameState.BUILDING

    def maybe_spawn_enemy(self) -> None:
        enemy = self.round_manager.maybe_spawn(len(self.paths))
        if enemy is not None:
            self.enemies.append(enemy)

    def round_complete(self) -> bool:
        return self.round_manager.round_complete(self.enemies)

    # ---- tower economics ----

    def can_afford_tower(self) -> bool:
        return self.exp >= self.settings["tower_cost"]

    def can_afford_upgrade(self) -> bool:
        return self.exp >= self.settings["tower_upgrade_cost"]

    def place_tower(self, x: float, y: float) -> Optional[Tower]:
        if not self.can_afford_tower():
            return None
        self.exp -= self.settings["tower_cost"]
        n = self.settings["num_colors"]
        color = random.choice(COLOR_ORDER[:n])
        tower = Tower(x, y, color)
        self.towers.append(tower)
        return tower

    def upgrade_tower(self, tower: Tower) -> bool:
        if tower.upgraded or not self.can_afford_upgrade():
            return False
        self.exp -= self.settings["tower_upgrade_cost"]
        n = self.settings["num_colors"]
        choices = [c for c in COLOR_ORDER[:n] if c != tower.color]
        second = random.choice(choices) if choices else tower.color
        tower.upgrade(second)
        return True
