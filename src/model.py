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


class Tower(Entity):
    FIRE_COOLDOWN_FRAMES = 30

    def __init__(self, x: float, y: float, color: str):
        super().__init__(x, y)
        self.color: str = color
        self.upgraded: bool = False
        self.color_b: Optional[str] = None
        self.cooldown: int = 0
        self.direction: Direction = Direction.UP
        self.selected: bool = False

    def upgrade(self, second_color: str) -> None:
        self.upgraded = True
        self.color_b = second_color

    def set_direction(self, direction: Direction) -> None:
        self.direction = direction

    def update(self) -> None:
        if self.cooldown > 0:
            self.cooldown -= 1

    def can_fire(self) -> bool:
        return self.cooldown == 0

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


class EnemyFactory:
    def __init__(self, settings: dict):
        self.settings = settings
        self._builders: Dict[str, Callable[..., Enemy]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("normal",      self._build_normal)
        self.register("regenerator", self._build_regenerator)
        self.register("chameleon",   self._build_chameleon)

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

    def pick_kind(self, current_round: int) -> str:
        # Rounds 1-3: normals only → gradually introduce specials
        # Rounds 4-6: mix in regenerators and chameleons
        # Rounds 7-9: heavier mix, more chameleons
        # Rounds 10-12: max difficulty — fewest normals
        if current_round <= 1:
            pool = ["normal"] * 10
        elif current_round == 2:
            pool = ["normal"] * 7 + ["regenerator"] * 3
        elif current_round == 3:
            pool = ["normal"] * 6 + ["regenerator"] * 2 + ["chameleon"] * 2
        elif current_round <= 6:
            pool = ["normal"] * 4 + ["regenerator"] * 3 + ["chameleon"] * 3
        elif current_round <= 9:
            pool = ["normal"] * 3 + ["regenerator"] * 3 + ["chameleon"] * 4
        else:
            pool = ["normal"] * 2 + ["regenerator"] * 4 + ["chameleon"] * 4
        return random.choice(pool)

    def pick_color(self) -> str:
        n = self.settings["num_colors"]
        return random.choice(COLOR_ORDER[:n])

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
            RoundData(1, 5, 35, 0.0, 2, 1, 0),
            RoundData(2, 8, 32, 0.0, 3, 1, 0, True, False, True),
            RoundData(3, 10, 32, 0.0, 3, 1, 0, True, False, True),
            RoundData(4, 12, 32, 0.0, 4, 1, 0, True, False, True),
            RoundData(5, 12, 30, 0.0, 4, 2, 1, True, True, True),
            RoundData(6, 13, 30, 0.0, 5, 2, 1, True, True, True),
            RoundData(7, 15, 30, 0.1, 5, 2, 1, True, True, True),
            RoundData(8, 16, 28, 0.1, 5, 2, 1, True, True, True),
            RoundData(9, 18, 28, 0.2, 6, 2, 2, True, True, True),
            RoundData(10, 18, 25, 0.4, 6, 2, 2, True, True, True),
            RoundData(11, 20, 25, 0.8, 6, 2, 2, True, True, True),
            RoundData(12, 20, 25, 1.0, 6, 2, 2, True, True, True),
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
            total_enemies=10 + round_number * 2,
            spawn_interval=max(8, 25 - round_number // 2),
            speed_boost=round_number * 0.01,
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

        self.shooter = Shooter(sw // 2, sh // 2, settings["num_colors"])

        self.lives: int = settings["player_lives"]
        self.exp: int   = 0
        self.state: GameState = GameState.MENU

        self.enemies: List[Enemy] = []
        self.bullets: List[Bullet] = []
        self.towers:  List[Tower]  = []

        self.enemy_factory = EnemyFactory(settings)
        
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
    
    def active_paths(self) -> List[Path]:
        if self.state == GameState.BUILDING:
            return self.paths[:self.preview_next_round_data.path_count]
        return self.paths[:self.round_data.path_count]

    def active_tunnel_count(self) -> int:
        return self.round_data.tunnels

    def tunnel_per_path(self) -> List[int]:
        rd = self.preview_next_round_data if self.state == GameState.BUILDING else self.round_data
        count = rd.tunnels
        paths = self.active_paths()

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

    def place_tower(self, x: float, y: float) -> Optional[Tower]:
        if not self.round_data.unlock_towers:
            return None
        if not self.can_afford_tower():
            return None
        self.exp -= self.settings["tower_cost"]
        n = self.settings["num_colors"]
        color = random.choice(COLOR_ORDER[:n])
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