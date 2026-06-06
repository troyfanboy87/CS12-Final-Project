import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol, Tuple


COLOR_PALETTE: Dict[str, int] = {
    "red":    8,
    "green":  11,
    "blue":   12,
    "yellow": 10,
    "purple": 2,
    "orange": 9,
}

COLOR_ORDER: List[str] = ["red", "green", "blue", "yellow", "purple", "orange"]


class GameState(str, Enum):
    MENU      = "menu"
    PLAYING   = "playing"
    CHOOSE    = "choose"
    BUILDING  = "building"
    SHOP      = "shop"
    PAUSED    = "paused"
    GAME_OVER = "game_over"
    WIN       = "win"
    LEADERBOARD = "leaderboard"

class RoundType(str, Enum):
    CAMPAIGN = "campaign"
    ENDLESS = "endless"

class Direction(str, Enum):
    UP    = "up"
    DOWN  = "down"
    LEFT  = "left"
    RIGHT = "right"


DIRECTION_VECTORS: Dict[Direction, Tuple[int, int]] = {
    Direction.UP:    (0, -1),
    Direction.DOWN:  (0,  1),
    Direction.LEFT:  (-1, 0),
    Direction.RIGHT: (1,  0),
}


ENEMY_RADIUS:  int = 5
BULLET_RADIUS: int = 2
TOWER_HALF:    int = 5
SHOOTER_HALF:  int = 6


class TunnelSegment:
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
    def __init__(
        self,
        waypoints: List[Tuple[int, int]],
        tunnels_in_cells: Optional[List[Tuple[int, int]]] = None,
        cell_size: int = 16,
    ):
        assert len(waypoints) >= 2, "A path needs at least 2 waypoints"
        self.waypoints = list(waypoints)
        self.cell_size = cell_size

        self.cumulative_lengths: List[float] = [0.0]
        for i in range(1, len(self.waypoints)):
            x0, y0 = self.waypoints[i - 1]
            x1, y1 = self.waypoints[i]
            seg_len = math.hypot(x1 - x0, y1 - y0)
            self.cumulative_lengths.append(self.cumulative_lengths[-1] + seg_len)
        self.total_length: float = self.cumulative_lengths[-1]

        self.tunnels: List[TunnelSegment] = []
        if tunnels_in_cells:
            assert len(tunnels_in_cells) <= 2, "Phase 4b: a path can have at most two tunnels"
            for sc, ec in tunnels_in_cells:
                cells = ec - sc
                assert 2 <= cells <= 5, f"Phase 4b: each tunnel must be 2..5 cells long (got {cells})"
                self.tunnels.append(
                    TunnelSegment(sc * cell_size, ec * cell_size)
                )
            total_tunnel_len = sum(t.length for t in self.tunnels)
            assert total_tunnel_len <= self.total_length / 2, (
                "Phase 4b: total tunnel length must not exceed half the path "
                f"length (got {total_tunnel_len:.1f} > {self.total_length / 2:.1f})"
            )

    def position_at(self, progress: float) -> Tuple[float, float]:
        if progress <= 0:
            return self.waypoints[0]
        if progress >= self.total_length:
            return self.waypoints[-1]
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

    def active_tunnels(self, count: int) -> List[TunnelSegment]:
        return self.tunnels[:count]

    def is_progress_in_tunnel(self, progress: float, active_tunnels: List[TunnelSegment]) -> bool:
        for t in active_tunnels:
            if t.contains(progress):
                return True
        return False
    

class Entity(ABC):
    def __init__(self, x: float, y: float):
        self.x: float = float(x)
        self.y: float = float(y)
        self.alive: bool = True

    @abstractmethod
    def update(self, *args, **kwargs) -> None:
        ...

    def kill(self) -> None:
        self.alive = False

    def distance_to(self, other: "Entity") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


class BulletSource(Protocol):
    x: float
    y: float
    def produce_bullets(self, bullet_speed: float) -> List["Bullet"]: ...


class Bullet(Entity):
    def __init__(self, x: float, y: float, vx: float, vy: float, color: str):
        super().__init__(x, y)
        self.vx = vx
        self.vy = vy
        self.color = color

    def update(self) -> None:
        self.x += self.vx
        self.y += self.vy

    def is_offscreen(self, screen_w: int, screen_h: int) -> bool:
        return (self.x < 0 or self.x > screen_w or
                self.y < 0 or self.y > screen_h)


class SniperBullet(Bullet):
    """Piercing bullet: passes through enemies instead of stopping on first hit."""
    PIERCING = True

    def __init__(self, x: float, y: float, vx: float, vy: float, color: str):
        super().__init__(x, y, vx, vy, color)


class BombBullet(Bullet):
    """Splash bullet: on first hit, damages all color-matching enemies within splash_radius."""
    PIERCING = False
    SPLASH_RADIUS = 32

    def __init__(self, x: float, y: float, vx: float, vy: float, color: str):
        super().__init__(x, y, vx, vy, color)
        self.exploded = False


class Shooter(Entity):
    def __init__(self, x: float, y: float, num_colors: int):
        super().__init__(x, y)
        assert num_colors >= 1
        self.num_colors = num_colors
        self.color_idx = 0
        self.aim_angle = -math.pi / 2

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
        self.aim_angle = math.atan2(dy, dx)

    def update(self) -> None:
        pass

    def produce_bullets(self, bullet_speed: float) -> List[Bullet]:
        vx = math.cos(self.aim_angle) * bullet_speed
        vy = math.sin(self.aim_angle) * bullet_speed
        return [Bullet(self.x, self.y, vx, vy, self.color)]


class Enemy(Entity):
    KIND: str = "normal"

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
        self.speed: float = speed
        self.progress: float = 0.0
        self.escaped: bool = False
        self.exp_value: int = exp_value
        self.path_index: int = path_index
        self.in_tunnel: bool = False

    def take_damage(self, bullet_color: str, amount: int = 1) -> bool:
        if bullet_color != self.color:
            return False
        if self.in_tunnel:
            return False
        self.hp -= amount
        if self.hp <= 0:
            self.kill()
        return True

    def update(self, path: Path, tunnels_active: bool = True, active_tunnels: Optional[List[TunnelSegment]] = None) -> None:
        if not self.alive or self.escaped:
            return
        self.progress += self.speed
        if self.progress >= path.total_length:
            self.escaped = True
            self.kill()
            return
        self.x, self.y = path.position_at(self.progress)

        if tunnels_active:
            self.in_tunnel = path.is_progress_in_tunnel(self.progress, active_tunnels)
        else:
            self.in_tunnel = False


class Regenerator(Enemy):
    KIND: str = "regenerator"

    def __init__(
        self,
        color: str,
        hp: int,
        speed: float,
        regen_cell_interval: int,
        cell_size: int,
        exp_value: int = 1,
        path_index: int = 0,
    ):
        super().__init__(color, hp, speed, exp_value, path_index)
        self._regen_pixel_interval: float = regen_cell_interval * cell_size
        self._next_regen_at: float = self._regen_pixel_interval

    def update(self, path: Path, tunnels_active: bool = True, active_tunnels: Optional[List[TunnelSegment]] = None) -> None:
        if not self.alive or self.escaped:
            return
        self.progress += self.speed
        if self.progress >= path.total_length:
            self.escaped = True
            self.kill()
            return
        self.x, self.y = path.position_at(self.progress)
        
        if tunnels_active:
            self.in_tunnel = path.is_progress_in_tunnel(self.progress, active_tunnels)
        else:
            self.in_tunnel = False

        while self.progress >= self._next_regen_at:
            self._next_regen_at += self._regen_pixel_interval
            if self.hp < self.max_hp:
                self.hp += 1


class Chameleon(Enemy):
    KIND: str = "chameleon"

    def __init__(
        self,
        color: str,
        hp: int,
        speed: float,
        change_frames: int,
        num_colors: int,
        exp_value: int = 1,
        path_index: int = 0,
    ):
        super().__init__(color, hp, speed, exp_value, path_index)
        self._change_frames: int = change_frames
        self._num_colors: int = num_colors
        self._frame_counter: int = 0

    def update(self, path: Path, tunnels_active: bool = True, active_tunnels: Optional[List[TunnelSegment]] = None) -> None:
        if not self.alive or self.escaped:
            return
        self.progress += self.speed
        if self.progress >= path.total_length:
            self.escaped = True
            self.kill()
            return
        self.x, self.y = path.position_at(self.progress)

        if tunnels_active:
            self.in_tunnel = path.is_progress_in_tunnel(self.progress, active_tunnels)
        else:
            self.in_tunnel = False

        self._frame_counter += 1
        if self._frame_counter >= self._change_frames:
            self._frame_counter = 0
            choices = [c for c in COLOR_ORDER[:self._num_colors] if c != self.color]
            if choices:
                self.color = random.choice(choices)


class Saboteur(Enemy):
    """Walks the path like a normal enemy. On death, disables all towers within
    sabotage_radius for sabotage_frames frames."""
    KIND: str = "saboteur"
    SABOTAGE_RADIUS: int = 48
    SABOTAGE_FRAMES: int = 120   # 4 seconds at 30 fps

    def __init__(
        self,
        color: str,
        hp: int,
        speed: float,
        exp_value: int = 2,
        path_index: int = 0,
    ):
        super().__init__(color, hp, speed, exp_value, path_index)

    def update(self, path: Path, tunnels_active: bool = True,
               active_tunnels: Optional[List[TunnelSegment]] = None) -> None:
        if not self.alive or self.escaped:
            return
        self.progress += self.speed
        if self.progress >= path.total_length:
            self.escaped = True
            self.kill()
            return
        self.x, self.y = path.position_at(self.progress)
        if tunnels_active:
            self.in_tunnel = path.is_progress_in_tunnel(self.progress, active_tunnels)
        else:
            self.in_tunnel = False


class Ghost(Enemy):
    KIND: str = "ghost"

    def __init__(
            self,
            hp: int,
            speed: float,
            path_index: int = 0,
    ):
        super().__init__(
            color="red",
            hp=hp,
            speed=speed,
            exp_value= -5,
            path_index=path_index,
        )
    
    def take_damage(self, bullet_color: str, amount: int = 1) -> bool:
        if self.in_tunnel:
            return False
        
        self.hp -= amount

        if self.hp <= 0:
            self.kill()
        
        return True
    
class Heart(Entity):
    def __init__(self, x: float, y: float, lifetime: int = 600):
        super().__init__(x, y)
        self.lifetime = lifetime
    
    def update(self) -> None:
        self.lifetime -= 1
        
        if self.lifetime <= 0:
            self.kill()
    
    @staticmethod
    def max_hearts_per_round(round_number: int) -> int:
        if round_number <= 5:
            return 0
        elif round_number <= 12:
            return 1
        else:
            return 2

class Tower(Entity):
    FIRE_COOLDOWN_FRAMES = 30
    TOWER_TYPE: str = "normal"

    def __init__(self, x: float, y: float, color: str):
        super().__init__(x, y)
        self.color: str = color
        self.upgraded: bool = False
        self.color_b: Optional[str] = None
        self.cooldown: int = 0
        self.direction: Direction = Direction.UP
        self.selected: bool = False
        self.disabled_frames: int = 0   # >0 means sabotaged

    @property
    def is_disabled(self) -> bool:
        return self.disabled_frames > 0

    def disable(self, frames: int) -> None:
        self.disabled_frames = max(self.disabled_frames, frames)

    def upgrade(self, second_color: str) -> None:
        self.upgraded = True
        self.color_b = second_color

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction

    def update(self) -> None:
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.disabled_frames > 0:
            self.disabled_frames -= 1

    def can_fire(self) -> bool:
        return self.cooldown == 0 and not self.is_disabled

    def produce_bullets(self, bullet_speed: float) -> List[Bullet]:
        self.cooldown = self.FIRE_COOLDOWN_FRAMES
        dx, dy = DIRECTION_VECTORS[self.direction]
        vx = dx * bullet_speed
        vy = dy * bullet_speed
        bullets = [Bullet(self.x, self.y, vx, vy, self.color)]
        if self.upgraded and self.color_b is not None:
            ox, oy = -dy, dx
            bullets.append(
                Bullet(self.x + ox * 3, self.y + oy * 3,
                       vx, vy, self.color_b)
            )
        return bullets


class SlowTower(Tower):
    """Passively slows all enemies within its range rather than shooting."""
    TOWER_TYPE: str = "slow"
    FIRE_COOLDOWN_FRAMES = 999999
    SLOW_RADIUS: int = 40
    SLOW_FACTOR: float = 0.5

    def __init__(self, x: float, y: float, color: str):
        super().__init__(x, y, color)

    def can_fire(self) -> bool:
        return False


class BurstTower(Tower):
    """Fires in all four cardinal directions simultaneously."""
    TOWER_TYPE: str = "burst"
    FIRE_COOLDOWN_FRAMES = 90

    def __init__(self, x: float, y: float, color: str):
        super().__init__(x, y, color)

    def produce_bullets(self, bullet_speed: float) -> List[Bullet]:
        self.cooldown = self.FIRE_COOLDOWN_FRAMES
        bullets = []
        for direction in Direction:
            dx, dy = DIRECTION_VECTORS[direction]
            bullets.append(Bullet(self.x, self.y,
                                  dx * bullet_speed, dy * bullet_speed,
                                  self.color))
        if self.upgraded and self.color_b is not None:
            for direction in Direction:
                dx, dy = DIRECTION_VECTORS[direction]
                bullets.append(Bullet(self.x, self.y,
                                      dx * bullet_speed, dy * bullet_speed,
                                      self.color_b))
        return bullets


class EnemyFactory:
    def __init__(self, settings: dict):
        self.settings = settings
        self._builders: Dict[str, Callable[..., Enemy]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("normal",      self._build_normal)
        self.register("regenerator", self._build_regenerator)
        self.register("chameleon",   self._build_chameleon)
        self.register("ghost",       self._build_ghost)
        self.register("saboteur",    self._build_saboteur)

    def register(self, kind: str, builder: Callable[..., Enemy]) -> None:
        self._builders[kind] = builder
    
    # ------------------------------------------------------------------ #
    # Phase 6a: HP scales up every 3 rounds so later enemies are tougher. #
    # Round 1-3  → base HP (1)                                            #
    # Round 4-6  → base HP + 1                                            #
    # Round 7-9  → base HP + 2                                            #
    # Round 10+  → base HP + 3                                            #
    # ------------------------------------------------------------------ #
    def _hp_for_round(self, current_round: int, extra: int = 0) -> int:
        base = self.settings["enemy_hp"]
        bonus = (current_round - 1) // 3
        return base + bonus + extra
    
    def create(self, kind: str, *, color: str, path_index: int,
               current_round: int = 1, active_colors: int = 6) -> Enemy:
        if kind not in self._builders:
            raise ValueError(f"Unknown enemy kind: {kind!r}")

        enemy = self._builders[kind](color=color, path_index=path_index,
                                    current_round=current_round)

        if isinstance(enemy, Chameleon):
            enemy._num_colors = active_colors
        return enemy



    def _build_normal(self, *, color: str, path_index: int,
                      current_round: int = 1) -> Enemy:
        return Enemy(
            color=color,
            hp=self._hp_for_round(current_round),
            speed=self.settings["enemy_speed"],
            exp_value=self.settings["exp_per_kill"],
            path_index=path_index,
        )

    def _build_regenerator(self, *, color: str, path_index: int,
                           current_round: int = 1) -> Regenerator:
        return Regenerator(
            color=color,
            hp=self._hp_for_round(current_round, extra=1),
            speed=self.settings["enemy_speed"],
            regen_cell_interval=self.settings["regen_cell_interval"],
            cell_size=self.settings["cell_size"],
            exp_value=self.settings["exp_per_kill"] + 1,
            path_index=path_index,
        )

    def _build_chameleon(self, *, color: str, path_index: int,
                         current_round: int = 1) -> Chameleon:
        return Chameleon(
            color=color,
            hp=self._hp_for_round(current_round),
            speed=self.settings["enemy_speed"],
            change_frames=self.settings["chameleon_change_frames"],
            num_colors=self.settings["num_colors"],
            exp_value=self.settings["exp_per_kill"] + 1,
            path_index=path_index,
        )

    def _build_ghost(self, *, color: str, path_index: int,
                     current_round: int = 1) -> Ghost:
        return Ghost(
            hp=self._hp_for_round(current_round),
            speed=self.settings["enemy_speed"],
            path_index=path_index,
        )

    def pick_kind(self, current_round: int) -> str:
        if current_round <= 1:
            pool = ["normal"] * 10
        elif current_round == 3:
            pool = ["normal"] * 8 + ["regenerator"] * 2
        elif current_round == 4:
            pool = ["normal"] * 6 + ["regenerator"] * 2 + ["chameleon"] * 2
        elif current_round <= 6:
            pool = ["normal"] * 4 + ["regenerator"] * 3 + ["chameleon"] * 2 + ["ghost"] * 1
        elif current_round <= 9:
            pool = ["normal"] * 3 + ["regenerator"] * 2 + ["chameleon"] * 3 + ["ghost"] * 1 + ["saboteur"] * 1
        else:
            pool = ["normal"] * 2 + ["regenerator"] * 3 + ["chameleon"] * 3 + ["ghost"] * 1 + ["saboteur"] * 1
        return random.choice(pool)

    def pick_color(self) -> str:
        n = self.settings["num_colors"]
        return random.choice(COLOR_ORDER[:n])

    def _build_saboteur(self, *, color: str, path_index: int,
                        current_round: int = 1) -> "Saboteur":
        return Saboteur(
            color=color,
            hp=self._hp_for_round(current_round, extra=1),
            speed=self.settings["enemy_speed"] * 1.2,
            exp_value=self.settings["exp_per_kill"] + 2,
            path_index=path_index,
        )


# ── Shop system ────────────────────────────────────────────────────────────────

@dataclass
class ShopItem:
    key: str
    label: str
    description: str
    cost: int
    category: str   # "ammo" | "tower" | "life"


SHOP_ITEMS: List[ShopItem] = [
    ShopItem("sniper_ammo",  "Sniper Rounds  (x3)", "Pierce through enemies", 6,  "ammo"),
    ShopItem("bomb_ammo",    "Bomb Rounds    (x3)", "Splash damage on hit",   8,  "ammo"),
    ShopItem("extra_life",   "Extra Life     (+1)", "Gain 1 life",            10, "life"),
    ShopItem("slow_tower",   "Slow Tower",          "Slows nearby enemies",   12, "tower"),
    ShopItem("burst_tower",  "Burst Tower",         "Fires in all 4 dirs",    15, "tower"),
]


class Shop:
    def __init__(self) -> None:
        self.items: List[ShopItem] = list(SHOP_ITEMS)
        self.cursor: int = 0

    def selected_item(self) -> ShopItem:
        return self.items[self.cursor]

    def move_cursor(self, delta: int) -> None:
        self.cursor = (self.cursor + delta) % len(self.items)

    def can_buy(self, item: ShopItem, exp: int) -> bool:
        return exp >= item.cost

@dataclass(frozen=True, slots=True)
class RoundData:
    round_number: int
    total_enemies: int
    spawn_interval: int
    speed_boost: float
    active_colors: int
    path_count: int = 1
    tunnels: int = 0
    unlock_towers: bool = False
    unlock_upgrade: bool = False
    unlock_build_ui: bool = False

class GameMode(ABC):
    @abstractmethod
    def get_round_data(self, round_number: int, settings: dict) -> RoundData:
        ...
    @abstractmethod
    def can_continue(self, round_number: int, settings: dict) -> bool: 
        ...
    @abstractmethod
    def max_rounds(self) -> Optional[int]:
        ...

class CampaignMode(GameMode):
    _ROUNDS: List[RoundData] = [
            RoundData(1,  5,  40, 0.0, 2, 1, 0),
            RoundData(2, 8, 38, 0.0, 3, 1, 0, True, False, True),
            RoundData(3, 10, 38, 0.0, 3, 1, 0, True, False, True),
            RoundData(4, 12, 35, 0.0, 4, 1, 0, True, False, True),
            RoundData(5, 12, 35, 0.0, 4, 2, 1, True, True, True),
            RoundData(6, 13, 35, 0.0, 5, 2, 1, True, True, True),
            RoundData(7, 15, 32, 0.1, 5, 2, 1, True, True, True),
            RoundData(8, 16, 32, 0.1, 5, 2, 1, True, True, True),
            RoundData(9, 18, 32, 0.2, 6, 2, 2, True, True, True),
            RoundData(10, 18, 30, 0.4, 6, 2, 2, True, True, True),
            RoundData(11, 20, 30, 0.8, 6, 2, 2, True, True, True),
            RoundData(12, 20, 30, 1.0, 6, 2, 2, True, True, True),
            RoundData(13, 20, 28, 1.0, 6, 2, 2, True, True, True),
            RoundData(14, 20, 28, 1.0, 6, 2, 2, True, True, True),
        ]

    def get_round_data(self, round_number: int, settings: dict) -> RoundData:
        if round_number < 1 or round_number > len(self._ROUNDS):
            raise IndexError("All rounds completed.")
        return self._ROUNDS[round_number - 1]
    
    def can_continue(self, round_number: int, settings: dict) -> bool:
        return round_number <= len(self._ROUNDS)
    
    def max_rounds(self) -> Optional[int]:
        return len(self._ROUNDS)

class EndlessMode(GameMode):

    def get_round_data(self, round_number: int, settings: dict) -> RoundData:
        return RoundData(
            round_number=round_number,
            total_enemies=5 + round_number * 2,
            spawn_interval=max(10, 40 - round_number // 2),
            speed_boost=round_number * 0.001,
            active_colors=min(
                2 + round_number // 3,
                settings["num_colors"]
            ),
            path_count=2,
            tunnels=2,
            unlock_towers=True,
            unlock_upgrade=True,
            unlock_build_ui=True,
        )
 
    def can_continue(self, round_number: int, settings: dict) -> bool:
        return True  # endless
 
    def max_rounds(self) -> Optional[int]:
        return None

class RoundManager:
    def __init__(self, settings: dict, enemy_factory: EnemyFactory, game_mode: GameMode):
        self.settings = settings
        self.factory = enemy_factory
        self.mode = game_mode

        self.current_round: int = 0
        self._enemies_to_spawn: int = 0
        self._spawn_timer: int = 0

    def start_next_round(self) -> bool:
        if not self.mode.can_continue(self.current_round + 1, self.settings):
            return False

        self.current_round += 1
        round_data = self.mode.get_round_data(self.current_round, self.settings)

        self._enemies_to_spawn = round_data.total_enemies
        self._spawn_timer = 0
        return True

    def all_rounds_finished(self) -> bool:
        return not self.mode.can_continue(self.current_round + 1, self.settings)

    def maybe_spawn(self, num_paths: int) -> Optional[Enemy]:
        if self._enemies_to_spawn <= 0:
            return None

        if self._spawn_timer > 0:
            self._spawn_timer -= 1
            return None

        round_data = self.mode.get_round_data(
            self.current_round,
            self.settings
        )
        

        max_allowed_paths = min(num_paths, round_data.path_count)
        path_idx = random.randint(0, max_allowed_paths - 1)
        kind = self.factory.pick_kind(self.current_round)
        color = random.choice(COLOR_ORDER[:round_data.active_colors])

        enemy = self.factory.create(kind, color=color, path_index=path_idx,
                                    current_round=self.current_round,
                                    active_colors=round_data.active_colors)

        enemy.speed += round_data.speed_boost

        self._enemies_to_spawn -= 1
        self._spawn_timer = round_data.spawn_interval

        return enemy
    
    def round_complete(self, live_enemies: List[Enemy]) -> bool:
        return (
            self._enemies_to_spawn <= 0
            and not any(e.alive for e in live_enemies)
        )


class GameModel:
    def __init__(self, settings: dict, mode_type: RoundType = RoundType.CAMPAIGN):
        self.settings = settings
        self.mode_type = mode_type
        self.player_name: str = ""

        sw = settings["screen_width"]
        sh = settings["screen_height"]
        cs = settings["cell_size"]

        half = cs // 2

        path_a_x = sw - cs * 4 + half
        path_a_y = (sh // 2 // cs) * cs + half
        self.paths: List[Path] = [
            Path(
                waypoints=[
                    (half,       path_a_y),
                    (path_a_x,   path_a_y),
                    (path_a_x,   sh - half),
                ],
                tunnels_in_cells=[(5, 8)],
                cell_size=cs,
            ),
            Path(
                waypoints=[
                    (cs * 2 + half,   half),
                    (cs * 2 + half,   sh - cs * 5 + half),
                    (sw - half,       sh - cs * 5 + half),
                ],
                tunnels_in_cells=[(4, 7)],
                cell_size=cs,
            ),
        ]

        self.paths_dual_tunnel: List[Path] = [
            Path(
                waypoints=[
                    (half,      path_a_y),
                    (path_a_x,  path_a_y),
                    (path_a_x,  sh - half),
                ],
                tunnels_in_cells=[(3, 5), (10, 13)],
                cell_size=cs,
            ),

            Path(
                waypoints=[
                    (cs * 2 + half,     half),
                    (cs * 2 + half,     sh - cs * 5 + half),
                    (sw - half,         sh - cs * 5 + half),
                ],
                tunnels_in_cells=[(3, 5), (11, 14)],
                cell_size=cs
            ),
        ]

        self.shooter = Shooter(sw // 2, sh // 2, settings["num_colors"])

        self.lives: int = settings["player_lives"]
        self.exp: int   = 0
        self.state: GameState = GameState.MENU

        self.enemies: List[Enemy] = []
        self.bullets: List[Bullet] = []
        self.towers:  List[Tower]  = []
        self.hearts: List[Heart] = []

        self.enemy_factory = EnemyFactory(settings)
        self._hearts_spawned: int = 0
        self._heart_spawn_timer: int = 0

        # Phase 7 additions
        self.sniper_ammo: int = 0
        self.bomb_ammo: int   = 0
        self.active_special: str = ""       # "" | "sniper" | "bomb"
        self.shop: Shop = Shop()
        self._pending_tower_type: str = "normal"
        
        if mode_type == RoundType.ENDLESS:
            chosen_mode = EndlessMode()
        else:
            chosen_mode = CampaignMode()
            
        self.round_manager = RoundManager(self.settings, self.enemy_factory, chosen_mode)

    @property
    def active_colors(self) -> int:
        return self.round_data.active_colors
    
    @property
    def current_round(self) -> int:
        return self.round_manager.current_round

    @property
    def total_rounds(self) -> Optional[int]:
        return self.round_manager.mode.max_rounds()
    
    @property
    def round_data(self) -> RoundData:
        round_number = max(1, self.current_round)
        return self.round_manager.mode.get_round_data(round_number, self.settings)
    
    @property
    def towers_unlocked(self) -> bool:
        return self.round_data.unlock_towers

    @property
    def upgrades_unlocked(self) -> bool:
        return self.round_data.unlock_upgrade
    
    @property
    def is_endless(self) -> bool:
        return self.mode_type == RoundType.ENDLESS
    
    @property
    def preview_next_round_data(self) -> RoundData:
        next_round = self.current_round + 1
        try:
            return self.round_manager.mode.get_round_data(next_round, self.settings)
        except (IndexError, Exception):
            return self.round_data

    def start_next_round(self) -> None:
        self.enemies.clear()
        self.bullets.clear()
        if self.round_manager.start_next_round():
            self.hearts.clear()
            self._hearts_spawned = 0
            self._heart_spawn_timer = 90
            self.state = GameState.PLAYING
            if self.shooter.color_idx >= self.round_data.active_colors:
                self.shooter.color_idx = 0
        else:
            self.state = GameState.WIN

    def end_round(self) -> None:
        if self.mode_type == RoundType.CAMPAIGN:
            self.towers.clear()
            self.bullets.clear()
            self.enemies.clear()
        if self.mode_type == RoundType.CAMPAIGN and self.round_manager.all_rounds_finished():
            self.state = GameState.WIN
        else:
            self.state = GameState.CHOOSE

    def maybe_spawn_enemy(self) -> None:
        enemy = self.round_manager.maybe_spawn(len(self.active_paths()))
        if enemy is not None:
            self.enemies.append(enemy)

    def maybe_spawn_heart(self) -> bool:
        if self._hearts_spawned >= Heart.max_hearts_per_round(self.current_round):
            return False
        self._heart_spawn_timer -= 1
        if self._heart_spawn_timer > 0:
            return False

        self._heart_spawn_timer = 500
        return True

    def place_heart(self, x: float, y: float) -> None:
        self.hearts.append(Heart(x, y))
        self._hearts_spawned += 1
        self._heart_spawn_timer = 300

    def active_paths(self) -> List[Path]:
        if self.state == GameState.BUILDING:
            rd = self.preview_next_round_data
        else:
            rd = self.round_data
        pool = self.paths_dual_tunnel if rd.round_number >= 13 else self.paths
        return pool[:rd.path_count]

    def active_tunnel_count(self) -> int:
        return self.round_data.tunnels

    def tunnel_per_path(self) -> List[int]:
        rd = self.preview_next_round_data if self.state == GameState.BUILDING else self.round_data
        paths = self.active_paths()

        if rd.round_number >= 13:
            return [len(p.tunnels) for p in paths]
        else:
            count = rd.tunnels
            allocation = [0] * len(paths)
            for i in range(len(paths)):
                if count <= 0:
                    break
                allocation[i] = 1
                count -= 1
            return allocation
    
    def round_complete(self) -> bool:
        return self.round_manager.round_complete(self.enemies)

    def can_afford_tower(self) -> bool:
        return self.exp >= self.settings["tower_cost"]

    def can_afford_upgrade(self) -> bool:
        return self.exp >= self.settings["tower_upgrade_cost"]

    def place_tower(self, x: float, y: float,
                    tower_type: str = "normal") -> Optional[Tower]:
        if not self.round_data.unlock_towers:
            return None
        cost = self.settings["tower_cost"]
        if self.exp < cost:
            return None
        self.exp -= cost
        n = self.settings["num_colors"]
        color = random.choice(COLOR_ORDER[:n])
        if tower_type == "slow":
            tower: Tower = SlowTower(x, y, color)
        elif tower_type == "burst":
            tower = BurstTower(x, y, color)
        else:
            tower = Tower(x, y, color)
        self.towers.append(tower)
        return tower

    def upgrade_tower(self, tower: Tower) -> bool:
        if not self.round_data.unlock_upgrade:
            return False
        if tower.upgraded or not self.can_afford_upgrade():
            return False
        self.exp -= self.settings["tower_upgrade_cost"]
        n = self.settings["num_colors"]
        choices = [c for c in COLOR_ORDER[:n] if c != tower.color]
        second = random.choice(choices) if choices else tower.color
        tower.upgrade(second)
        return True

    # ── Shop helpers ──────────────────────────────────────────────────────────

    def shop_buy(self, item: ShopItem) -> bool:
        if self.exp < item.cost:
            return False
        self.exp -= item.cost
        if item.key == "sniper_ammo":
            self.sniper_ammo += 3
        elif item.key == "bomb_ammo":
            self.bomb_ammo += 3
        elif item.key == "extra_life":
            self.lives += 1
        elif item.key in ("slow_tower", "burst_tower"):
            ttype = "slow" if item.key == "slow_tower" else "burst"
            self._pending_tower_type = ttype
            # Refund — placement is handled separately with its own cost deduction
            self.exp += item.cost
        return True

    # ── Special bullet helpers ────────────────────────────────────────────────

    def produce_special_bullet(self, bullet_speed: float) -> Optional[Bullet]:
        s = self.shooter
        vx = math.cos(s.aim_angle) * bullet_speed
        vy = math.sin(s.aim_angle) * bullet_speed
        if self.active_special == "sniper" and self.sniper_ammo > 0:
            self.sniper_ammo -= 1
            if self.sniper_ammo == 0:
                self.active_special = ""
            return SniperBullet(s.x, s.y, vx, vy, s.color)
        if self.active_special == "bomb" and self.bomb_ammo > 0:
            self.bomb_ammo -= 1
            if self.bomb_ammo == 0:
                self.active_special = ""
            return BombBullet(s.x, s.y, vx, vy, s.color)
        return None

    def cycle_special(self) -> None:
        options = [""]
        if self.sniper_ammo > 0:
            options.append("sniper")
        if self.bomb_ammo > 0:
            options.append("bomb")
        if len(options) == 1:
            self.active_special = ""
            return
        try:
            idx = options.index(self.active_special)
        except ValueError:
            idx = 0
        self.active_special = options[(idx + 1) % len(options)]
