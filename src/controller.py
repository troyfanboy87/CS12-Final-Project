"""
Controller layer — input, game loop, audio, collisions.

This is the only file outside of view.py that imports pyxel. Organized
top-to-bottom in the order the controller actually uses them:

    1. SOUND MANAGER     — SFX + BGM (channels and slots)
    2. INPUT HANDLER     — pyxel input -> high-level intents
    3. COLLISION SYSTEM  — bullet-vs-enemy resolution
    4. GAME CONTROLLER   — orchestrates one frame, calls all of the above

The frame plan for PLAYING state (see GameController._update_playing) is:
    spawn -> input -> player fire -> tower direction -> tick towers ->
    move bullets -> move enemies -> collisions -> cleanup -> win/lose check.
"""

import math
from typing import Callable, List, Optional

import pyxel

from .model import (
    Bullet,
    BULLET_RADIUS,
    Direction,
    Enemy,
    ENEMY_RADIUS,
    GameModel,
    GameState,
    Tower,
)


# ===========================================================================
# 1. SOUND MANAGER — SFX + background music
# ===========================================================================
#
# IMPORTANT Pyxel audio fact (bit us before):
#   Pyxel has 4 audio channels (0..3). pyxel.playm() plays a music's tracks
#   on specific channels. Any pyxel.play() on the SAME channel INTERRUPTS
#   the music. So we reserve channels 0 and 1 for BGM, and put all SFX on
#   channels 2 and 3.
#
# Phase 3d: SFX for defeating enemies.
# Phase 4d: Background music — a simple repeating phrase.

# Sound slot assignments (Pyxel has 64 slots, 0..63).
SFX_SHOOT      = 0
SFX_KILL       = 1
SFX_PLACE      = 2
SFX_LIFE_LOST  = 3
SFX_UPGRADE    = 4

BGM_MELODY_SLOT = 10
BGM_BASS_SLOT   = 11
BGM_TRACK       = 0

# Channels: 0+1 reserved for BGM, 2+3 free for SFX.
CHAN_BGM_MELODY = 0
CHAN_BGM_BASS   = 1
CHAN_SFX_A      = 2   # rapid SFX (shoot, place)
CHAN_SFX_B      = 3   # impact SFX (kill, life_lost, upgrade)


class SoundManager:
    """
    SRP: the ONLY thing this class does is talk to pyxel.sounds/pyxel.play.
    Everywhere else uses the named methods (shoot/kill/place/...).
    """

    def __init__(self):
        self._setup_sounds()
        self._setup_music()

    def _setup_sounds(self) -> None:
        # pyxel.sound.set(notes, tones, volumes, effects, speed)
        # tones: T=triangle, S=square, P=pulse, N=noise. Speed: lower = faster.
        pyxel.sounds[SFX_SHOOT].set("a3",         "p", "5", "f", 20)
        pyxel.sounds[SFX_KILL].set("e3c3",        "t", "6", "n", 12)
        pyxel.sounds[SFX_PLACE].set("c2g2c3",     "s", "5", "n", 15)
        pyxel.sounds[SFX_LIFE_LOST].set("c1",     "n", "7", "f", 8)
        pyxel.sounds[SFX_UPGRADE].set("c3e3g3c4", "s", "5", "n", 18)

    def _setup_music(self) -> None:
        # Phase 4d: simple repeating phrase. Quieter than SFX so action stays
        # in front. Loops continuously.
        pyxel.sounds[BGM_MELODY_SLOT].set(
            "c2 e2 g2 c3 e2 g2 c3 e3",
            "p", "3", "n", 22
        )
        pyxel.sounds[BGM_BASS_SLOT].set(
            "c1 c1 g1 g1 a1 a1 f1 f1",
            "t", "4", "n", 22
        )
        # musics[i].set(ch0, ch1, ch2, ch3) — lists of sound IDs per channel.
        pyxel.musics[BGM_TRACK].set(
            [BGM_MELODY_SLOT],   # channel 0
            [BGM_BASS_SLOT],     # channel 1
            [],                  # channel 2 free for SFX
            [],                  # channel 3 free for SFX
        )

    # ---- public API ----

    def shoot(self):     pyxel.play(CHAN_SFX_A, SFX_SHOOT)
    def kill(self):      pyxel.play(CHAN_SFX_B, SFX_KILL)
    def place(self):     pyxel.play(CHAN_SFX_A, SFX_PLACE)
    def life_lost(self): pyxel.play(CHAN_SFX_B, SFX_LIFE_LOST)
    def upgrade(self):   pyxel.play(CHAN_SFX_B, SFX_UPGRADE)

    def start_bgm(self):
        pyxel.playm(BGM_TRACK, loop=True)

    def stop_bgm(self):
        pyxel.stop(CHAN_BGM_MELODY)
        pyxel.stop(CHAN_BGM_BASS)


# ===========================================================================
# 2. INPUT HANDLER — pyxel input -> high-level intents
# ===========================================================================
#
# Why bother? Because GameController shouldn't be peppered with
# pyxel.btnp(pyxel.KEY_T) checks — those make it hard to test and tie the
# controller permanently to Pyxel. This class is the only place outside the
# View that imports pyxel key constants.
#
# If we ever wanted to swap input backends (e.g. recorded-input replay for
# tests), we'd reimplement THIS class only.

# Number keys 1..6 for ammo selection.
_NUMBER_KEYS = [
    pyxel.KEY_1, pyxel.KEY_2, pyxel.KEY_3,
    pyxel.KEY_4, pyxel.KEY_5, pyxel.KEY_6,
]

# WASD -> Direction. Phase 4: aims the currently-selected tower.
_DIRECTION_KEYS = {
    pyxel.KEY_W: Direction.UP,
    pyxel.KEY_S: Direction.DOWN,
    pyxel.KEY_A: Direction.LEFT,
    pyxel.KEY_D: Direction.RIGHT,
}


class InputHandler:
    """Stateless wrapper around pyxel input — returns high-level intents."""

    # ---- global ----
    @staticmethod
    def wants_quit() -> bool:
        return pyxel.btnp(pyxel.KEY_Q)

    @staticmethod
    def wants_restart() -> bool:
        return pyxel.btnp(pyxel.KEY_R)

    # ---- mouse ----
    @staticmethod
    def mouse_pos() -> tuple[int, int]:
        return pyxel.mouse_x, pyxel.mouse_y

    @staticmethod
    def wants_start() -> bool:
        return (pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
                or pyxel.btnp(pyxel.KEY_SPACE))

    @staticmethod
    def fire_held() -> bool:
        # btn (continuous) so holding click sprays. btnp would be one-shot.
        return pyxel.btn(pyxel.MOUSE_BUTTON_LEFT)

    # ---- ammo color cycling ----
    def ammo_number_pressed(self, num_colors: int) -> Optional[int]:
        for i, key in enumerate(_NUMBER_KEYS):
            if i < num_colors and pyxel.btnp(key):
                return i
        return None

    @staticmethod
    def wheel_delta() -> int:
        return pyxel.mouse_wheel

    # ---- between-rounds keys ----
    @staticmethod
    def wants_place_tower() -> bool:
        return pyxel.btnp(pyxel.KEY_T)

    @staticmethod
    def wants_upgrade_tower() -> bool:
        return pyxel.btnp(pyxel.KEY_U)

    @staticmethod
    def wants_next_round() -> bool:
        return pyxel.btnp(pyxel.KEY_SPACE)

    # ---- tower selection (Phase 4) ----
    @staticmethod
    def wants_select_tower() -> bool:
        """Right-click to select the tower nearest the cursor."""
        return pyxel.btnp(pyxel.MOUSE_BUTTON_RIGHT)

    @staticmethod
    def wants_cycle_tower() -> bool:
        """TAB to cycle through placed towers."""
        return pyxel.btnp(pyxel.KEY_TAB)

    @staticmethod
    def direction_pressed() -> Optional[Direction]:
        """Phase 4: WASD sets selected tower's firing direction."""
        for key, direction in _DIRECTION_KEYS.items():
            if pyxel.btnp(key):
                return direction
        return None


# ===========================================================================
# 3. COLLISION SYSTEM — bullet-vs-enemy resolution
# ===========================================================================

class CollisionSystem:
    """
    Naive O(N*M) bullet-vs-enemy check. With N, M <= ~50 in practice that's
    <= 2500 checks per frame, way under the 30 Hz budget. If we ever need
    to scale, swap in a spatial hash here — nothing else changes.

    Phase 4b: tunneled enemies are SHIELDED. We skip them.

    Squared-distance check avoids a sqrt per pair (compare dx*dx + dy*dy to
    the squared hit radius). Beginner code calls math.hypot here and is
    needlessly slow.
    """

    HIT_RADIUS_SQ = (ENEMY_RADIUS + BULLET_RADIUS) ** 2

    def __init__(
        self,
        on_kill: Callable[[Enemy], None],
        on_hit:  Optional[Callable[[Enemy, Bullet], None]] = None,
    ):
        """
        on_kill: called when an enemy's HP hits zero. Lets the controller
                 add EXP and play the kill SFX without us knowing about either.
        on_hit : called for every same-color hit (even non-lethal). Useful
                 for future hit-spark FX.
        """
        self._on_kill = on_kill
        self._on_hit  = on_hit

    def resolve(self, bullets: List[Bullet], enemies: List[Enemy]) -> None:
        for b in bullets:
            if not b.alive:
                continue
            for e in enemies:
                if not e.alive:
                    continue
                if e.in_tunnel:  # Phase 4b immunity
                    continue
                dx = b.x - e.x
                dy = b.y - e.y
                if dx * dx + dy * dy > self.HIT_RADIUS_SQ:
                    continue
                # Same-color hit consumes the bullet AND damages the enemy.
                if e.take_damage(b.color):
                    b.kill()
                    if self._on_hit:
                        self._on_hit(e, b)
                    if not e.alive:
                        self._on_kill(e)
                    break  # bullet gone; stop checking other enemies


# ===========================================================================
# 4. GAME CONTROLLER — orchestrates one frame
# ===========================================================================

class GameController:
    """
    Pyxel calls update() at the configured FPS. Each call:
        1. Read input (InputHandler).
        2. Branch on model.state and dispatch to a per-state handler.
        3. Each handler mutates the model and calls SoundManager /
           CollisionSystem as needed.

    The View is NOT called here — Pyxel calls view.draw() separately, after
    update(). Keeping draw() out of the controller is what makes MVC work.

    What this class is NOT:
      - It does not draw anything (View's job).
      - It does not own collision math (CollisionSystem's job).
      - It does not read raw pyxel key constants (InputHandler's job).
      - It does not own spawn timing or round counters (RoundManager's job).

    What it IS:
      - The glue. Every frame it asks each subsystem to do its piece in order.
    """

    # Frames between consecutive player shots. Stops holding-click from
    # firing 30 bullets a second.
    SHOOT_COOLDOWN_FRAMES = 6
    # Minimum pixel distance between a tower and a path / another tower.
    MIN_TOWER_DIST_FROM_PATH  = 12
    MIN_TOWER_DIST_FROM_TOWER = 14

    def __init__(self, settings: dict):
        self.settings = settings
        self.model    = GameModel(settings)
        self.input    = InputHandler()
        self.sound    = SoundManager()
        self.collisions = CollisionSystem(on_kill=self._on_enemy_killed)
        self._shoot_cd = 0
        self._selected_tower: Optional[Tower] = None
        self._bgm_playing = False

    # ----- Pyxel entry point -----

    def update(self) -> None:
        if self.input.wants_quit():
            pyxel.quit()

        state = self.model.state
        if state == GameState.MENU:
            self._update_menu()
        elif state == GameState.PLAYING:
            self._update_playing()
        elif state == GameState.BUILDING:
            self._update_building()
        elif state in (GameState.GAME_OVER, GameState.WIN):
            self._update_endgame()

    # ----- per-state handlers -----

    def _update_menu(self) -> None:
        if self.input.wants_start():
            self.model.start_next_round()
            self._ensure_bgm_playing()

    def _update_playing(self) -> None:
        # 1. spawn
        self.model.maybe_spawn_enemy()

        # 2. player aim + ammo
        self._handle_aim_and_color()

        # 3. player fire (rate-limited)
        if self._shoot_cd > 0:
            self._shoot_cd -= 1
        if self.input.fire_held() and self._shoot_cd == 0:
            self._fire_player_bullet()
            self._shoot_cd = self.SHOOT_COOLDOWN_FRAMES

        # 4. tower direction control (Phase 4: settable DURING rounds)
        self._handle_tower_direction_input()

        # 5. tick + fire towers
        self._update_towers()

        # 6. move bullets, cull off-screen
        self._update_bullets()

        # 7. move enemies, handle escapes
        self._update_enemies()

        # 8. collisions
        self.collisions.resolve(self.model.bullets, self.model.enemies)

        # 9. cull dead bullets/enemies AFTER collisions
        self.model.bullets = [b for b in self.model.bullets if b.alive]
        self.model.enemies = [e for e in self.model.enemies if e.alive]

        # 10. end-of-round / game-over checks
        if self.model.lives <= 0:
            self.model.state = GameState.GAME_OVER
            self.sound.stop_bgm()
            self._bgm_playing = False
        elif self.model.round_complete():
            self.model.end_round()

    def _update_building(self) -> None:
        # Place / upgrade / select / cycle towers, then SPACE -> next round.
        if self.input.wants_place_tower():
            self._try_place_tower()
        if self.input.wants_upgrade_tower():
            self._try_upgrade_tower()
        if self.input.wants_select_tower():
            self._select_nearest_tower_to_cursor()
        if self.input.wants_cycle_tower():
            self._cycle_selected_tower()
        # Phase 4: allow direction set between rounds too — nicer UX.
        self._handle_tower_direction_input()
        if self.input.wants_next_round():
            self.model.start_next_round()

    def _update_endgame(self) -> None:
        if self.input.wants_restart():
            # Easiest reliable reset: rebuild a fresh model.
            self.model = GameModel(self.settings)
            self.model.state = GameState.MENU
            self.sound.stop_bgm()
            self._bgm_playing = False
            self._selected_tower = None
            self._shoot_cd = 0

    # ----- helpers -----

    def _ensure_bgm_playing(self) -> None:
        if not self._bgm_playing:
            self.sound.start_bgm()
            self._bgm_playing = True

    def _handle_aim_and_color(self) -> None:
        mx, my = self.input.mouse_pos()
        self.model.shooter.aim_at(mx, my)

        idx = self.input.ammo_number_pressed(self.settings["num_colors"])
        if idx is not None:
            self.model.shooter.set_color_index(idx)

        wheel = self.input.wheel_delta()
        if wheel != 0:
            self.model.shooter.cycle_color(1 if wheel > 0 else -1)

    def _fire_player_bullet(self) -> None:
        speed = self.settings["bullet_speed"]
        bullets = self.model.shooter.produce_bullets(speed)
        self.model.bullets.extend(bullets)
        self.sound.shoot()

    # ---- towers ----

    def _handle_tower_direction_input(self) -> None:
        """Phase 4a: WASD sets the firing direction of the SELECTED tower."""
        if self._selected_tower is None:
            return
        if self._selected_tower not in self.model.towers:
            self._selected_tower = None
            return
        d = self.input.direction_pressed()
        if d is not None:
            self._selected_tower.set_direction(d)

    def _update_towers(self) -> None:
        # Sync .selected flags for the View based on our tracked selection.
        for t in self.model.towers:
            t.selected = (t is self._selected_tower)
            t.update()

        if not any(e.alive for e in self.model.enemies):
            return  # don't fire when the field is empty

        speed = self.settings["bullet_speed"]
        for t in self.model.towers:
            if t.can_fire():
                self.model.bullets.extend(t.produce_bullets(speed))

    def _update_bullets(self) -> None:
        sw = self.settings["screen_width"]
        sh = self.settings["screen_height"]
        for b in self.model.bullets:
            if not b.alive:
                continue
            b.update()
            if b.is_offscreen(sw, sh):
                b.kill()

    def _update_enemies(self) -> None:
        for e in self.model.enemies:
            if not e.alive and not e.escaped:
                continue
            path = self.model.paths[e.path_index]
            e.update(path)
            if e.escaped:
                self.model.lives -= 1
                self.sound.life_lost()
                e.escaped = False  # consume event so we don't double-count

    # ---- collision callback ----

    def _on_enemy_killed(self, enemy: Enemy) -> None:
        self.model.exp += enemy.exp_value
        self.sound.kill()

    # ---- tower placement / upgrade / selection ----

    def _try_place_tower(self) -> None:
        mx, my = self.input.mouse_pos()
        if not self._is_legal_tower_spot(mx, my):
            return
        if not self.model.can_afford_tower():
            return
        tower = self.model.place_tower(mx, my)
        if tower is not None:
            self.sound.place()
            # Auto-select so WASD aims it immediately.
            self._selected_tower = tower

    def _try_upgrade_tower(self) -> None:
        # Prefer the explicitly-selected tower, else the nearest to cursor.
        target = self._selected_tower
        if target is None or target not in self.model.towers:
            mx, my = self.input.mouse_pos()
            target = self._nearest_tower(mx, my)
        if target is None or not self.model.can_afford_upgrade():
            return
        if self.model.upgrade_tower(target):
            self.sound.upgrade()

    def _select_nearest_tower_to_cursor(self) -> None:
        mx, my = self.input.mouse_pos()
        t = self._nearest_tower(mx, my)
        if t is not None:
            self._selected_tower = t

    def _cycle_selected_tower(self) -> None:
        if not self.model.towers:
            return
        if self._selected_tower not in self.model.towers:
            self._selected_tower = self.model.towers[0]
        else:
            i = self.model.towers.index(self._selected_tower)
            self._selected_tower = self.model.towers[(i + 1) % len(self.model.towers)]

    def _is_legal_tower_spot(self, x: float, y: float) -> bool:
        # Not too close to any path.
        for path in self.model.paths:
            for i in range(1, len(path.waypoints)):
                x0, y0 = path.waypoints[i - 1]
                x1, y1 = path.waypoints[i]
                if self._dist_to_segment(x, y, x0, y0, x1, y1) < self.MIN_TOWER_DIST_FROM_PATH:
                    return False
        # Not on top of another tower.
        for t in self.model.towers:
            if math.hypot(t.x - x, t.y - y) < self.MIN_TOWER_DIST_FROM_TOWER:
                return False
        # Not on top of the shooter.
        s = self.model.shooter
        if math.hypot(s.x - x, s.y - y) < self.MIN_TOWER_DIST_FROM_TOWER:
            return False
        return True

    @staticmethod
    def _dist_to_segment(px, py, x0, y0, x1, y1) -> float:
        """Standard point-to-line-segment distance. Comes up everywhere in 2D."""
        dx, dy = x1 - x0, y1 - y0
        if dx == 0 and dy == 0:
            return math.hypot(px - x0, py - y0)
        t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
        cx = x0 + t * dx
        cy = y0 + t * dy
        return math.hypot(px - cx, py - cy)

    def _nearest_tower(self, x: float, y: float) -> Optional[Tower]:
        if not self.model.towers:
            return None
        return min(self.model.towers,
                   key=lambda t: math.hypot(t.x - x, t.y - y))
