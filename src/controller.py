import math
import random
from typing import Callable, List, Optional

import pyxel

from .model import (
    BombBullet,
    Bullet,
    BULLET_RADIUS,
    BurstTower,
    COLOR_ORDER,
    Direction,
    Enemy,
    ENEMY_RADIUS,
    GameModel,
    GameState,
    RoundType,
    Saboteur,
    SlowTower,
    SniperBullet,
    Tower,
)

# sound stuff
SFX_SHOOT      = 0
SFX_KILL       = 1
SFX_PLACE      = 2
SFX_LIFE_LOST  = 3
SFX_UPGRADE    = 4
SFX_SHOP_BUY   = 6
SFX_SABOTEUR   = 7
SFX_SPECIAL    = 8

BGM_MELODY_SLOT  = 10
BGM_BASS_SLOT    = 11
BGM_TRACK        = 0

MENU_MELODY_SLOT = 12
MENU_BASS_SLOT   = 13
MENU_TRACK       = 1

CHAN_BGM_MELODY = 0
CHAN_BGM_BASS   = 1
CHAN_SFX_A      = 2  
CHAN_SFX_B      = 3  


class SoundManager:
    def __init__(self):
        self._setup_sounds()
        self._setup_music()

    def _setup_sounds(self) -> None:
        pyxel.sounds[SFX_SHOOT].set("a3",         "p", "5", "f", 20)
        pyxel.sounds[SFX_KILL].set("e3c3",        "t", "6", "n", 12)
        pyxel.sounds[SFX_PLACE].set("c2g2c3",     "s", "5", "n", 15)
        pyxel.sounds[SFX_LIFE_LOST].set("c1",     "n", "7", "f", 8)
        pyxel.sounds[SFX_UPGRADE].set("c3e3g3c4", "s", "5", "n", 18)
        pyxel.sounds[SFX_SHOP_BUY].set("c3e3g3",  "s", "6", "n", 14)
        pyxel.sounds[SFX_SABOTEUR].set("b1g1e1",   "n", "7", "f", 12)
        pyxel.sounds[SFX_SPECIAL].set("a2e3a3",    "p", "6", "n", 16)

    def _setup_music(self) -> None:
        # Game BGM — upbeat loop
        pyxel.sounds[BGM_MELODY_SLOT].set(
            "c2 e2 g2 c3 e2 g2 c3 e3",
            "p", "3", "n", 22
        )
        pyxel.sounds[BGM_BASS_SLOT].set(
            "c1 c1 g1 g1 a1 a1 f1 f1",
            "t", "4", "n", 22
        )
        pyxel.musics[BGM_TRACK].set(
            [BGM_MELODY_SLOT], [BGM_BASS_SLOT], [], []
        )
        # Menu BGM — slower, more ambient feel
        pyxel.sounds[MENU_MELODY_SLOT].set(
            "c3 r r e3 r r g3 r r e3 r r c3 r r r",
            "t", "3", "f", 30
        )
        pyxel.sounds[MENU_BASS_SLOT].set(
            "c1 r r r g1 r r r a1 r r r f1 r r r",
            "s", "2", "f", 30
        )
        pyxel.musics[MENU_TRACK].set(
            [MENU_MELODY_SLOT], [MENU_BASS_SLOT], [], []
        )

    def shoot(self):      pyxel.play(CHAN_SFX_A, SFX_SHOOT)
    def kill(self):       pyxel.play(CHAN_SFX_B, SFX_KILL)
    def place(self):      pyxel.play(CHAN_SFX_A, SFX_PLACE)
    def life_lost(self):  pyxel.play(CHAN_SFX_B, SFX_LIFE_LOST)
    def upgrade(self):    pyxel.play(CHAN_SFX_B, SFX_UPGRADE)
    def shop_buy(self):   pyxel.play(CHAN_SFX_A, SFX_SHOP_BUY)
    def saboteur(self):   pyxel.play(CHAN_SFX_B, SFX_SABOTEUR)
    def special(self):    pyxel.play(CHAN_SFX_A, SFX_SPECIAL)

    def start_bgm(self):
        pyxel.stop(CHAN_BGM_MELODY)
        pyxel.stop(CHAN_BGM_BASS)
        pyxel.playm(BGM_TRACK, loop=True)

    def start_menu_bgm(self):
        pyxel.stop(CHAN_BGM_MELODY)
        pyxel.stop(CHAN_BGM_BASS)
        pyxel.playm(MENU_TRACK, loop=True)

    def stop_bgm(self):
        pyxel.stop(CHAN_BGM_MELODY)
        pyxel.stop(CHAN_BGM_BASS)


#handles input
_NUMBER_KEYS = [
    pyxel.KEY_1, pyxel.KEY_2, pyxel.KEY_3,
    pyxel.KEY_4, pyxel.KEY_5, pyxel.KEY_6,
]

_DIRECTION_KEYS = {
    pyxel.KEY_W: Direction.UP,
    pyxel.KEY_S: Direction.DOWN,
    pyxel.KEY_A: Direction.LEFT,
    pyxel.KEY_D: Direction.RIGHT,
}


class InputHandler:
    @staticmethod
    def wants_quit() -> bool:
        return pyxel.btnp(pyxel.KEY_Q)

    @staticmethod
    def wants_restart() -> bool:
        return pyxel.btnp(pyxel.KEY_R)

    @staticmethod
    def mouse_pos() -> tuple[int, int]:
        return pyxel.mouse_x, pyxel.mouse_y

    @staticmethod
    def wants_start() -> bool:
        return (pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
                or pyxel.btnp(pyxel.KEY_SPACE))
    
    @staticmethod
    def wants_campaign_mode() -> bool:
        return pyxel.btnp(pyxel.KEY_1)
    
    @staticmethod
    def wants_endless_mode() -> bool:
        return pyxel.btnp(pyxel.KEY_2)
    
    @staticmethod
    def wants_controls() -> bool:
        """K key: toggle controls overlay on menu."""
        return pyxel.btnp(pyxel.KEY_K)

    @staticmethod
    def wants_music() -> bool:
        return pyxel.btnp(pyxel.KEY_M)
    
    @staticmethod
    def wants_pause() -> bool:
        return pyxel.btnp(pyxel.KEY_P)
    
    @staticmethod
    def wants_back() -> bool:
        return pyxel.btnp(pyxel.KEY_ESCAPE)

    @staticmethod
    def fire_held() -> bool:
        return pyxel.btn(pyxel.MOUSE_BUTTON_LEFT)

    def ammo_number_pressed(self, num_colors: int) -> Optional[int]:
        for i, key in enumerate(_NUMBER_KEYS):
            if i < num_colors and pyxel.btnp(key):
                return i
        return None

    @staticmethod
    def wheel_delta() -> int:
        return pyxel.mouse_wheel

    @staticmethod
    def wants_build() -> bool:
        """B key: player wants to enter the build phase."""
        return pyxel.btnp(pyxel.KEY_B)

    @staticmethod
    def wants_place_tower() -> bool:
        return pyxel.btnp(pyxel.KEY_T)

    @staticmethod
    def wants_upgrade_tower() -> bool:
        return pyxel.btnp(pyxel.KEY_U)

    @staticmethod
    def wants_cycle_tower_color() -> bool:
        """C key: cycle the selected tower's color."""
        return pyxel.btnp(pyxel.KEY_C)

    @staticmethod
    def wants_next_round() -> bool:
        return pyxel.btnp(pyxel.KEY_SPACE)

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

    @staticmethod
    def wants_shop() -> bool:
        return pyxel.btnp(pyxel.KEY_O)

    @staticmethod
    def wants_cycle_special() -> bool:
        return pyxel.btnp(pyxel.KEY_X)

    @staticmethod
    def shop_up() -> bool:
        return pyxel.btnp(pyxel.KEY_UP)

    @staticmethod
    def shop_down() -> bool:
        return pyxel.btnp(pyxel.KEY_DOWN)

    @staticmethod
    def shop_buy() -> bool:
        return pyxel.btnp(pyxel.KEY_RETURN)


#handles when bullet collides with enemy
class CollisionSystem:
    HIT_RADIUS_SQ = (ENEMY_RADIUS + BULLET_RADIUS) ** 2

    def __init__(
        self,
        on_kill: Callable[[Enemy], None],
        on_hit:  Optional[Callable[[Enemy, Bullet], None]] = None,
    ):
        self._on_kill = on_kill
        self._on_hit  = on_hit

    def resolve(self, bullets: List[Bullet], enemies: List[Enemy]) -> None:
        for b in bullets:
            if not b.alive:
                continue
            for e in enemies:
                if not e.alive:
                    continue
                if e.in_tunnel:
                    continue
                dx = b.x - e.x
                dy = b.y - e.y
                if dx * dx + dy * dy > self.HIT_RADIUS_SQ:
                    continue
                if e.take_damage(b.color):
                    if isinstance(b, BombBullet) and not b.exploded:
                        b.exploded = True
                        self._splash(b, enemies)
                        b.kill()
                    elif not isinstance(b, SniperBullet):
                        b.kill()
                    if self._on_hit:
                        self._on_hit(e, b)
                    if not e.alive:
                        self._on_kill(e)
                    if not isinstance(b, SniperBullet):
                        break

    def _splash(self, bomb: "BombBullet", enemies: List[Enemy]) -> None:
        r2 = bomb.SPLASH_RADIUS ** 2
        for e in enemies:
            if not e.alive or e.in_tunnel:
                continue
            dx = bomb.x - e.x
            dy = bomb.y - e.y
            if dx * dx + dy * dy <= r2:
                if e.take_damage(bomb.color):
                    if not e.alive:
                        self._on_kill(e)

    def resolve_hearts(self, bullets: List[Bullet], hearts: list) -> int:
        lives_gained = 0
        for b in bullets:
            if not b.alive:
                continue
            for h in hearts:
                if not h.alive:
                    continue
                dx = b.x - h.x
                dy = b.y - h.y
                if dx*dx + dy*dy <= 64:
                    b.kill()
                    h.kill()
                    lives_gained += 1
                    break
        return lives_gained

#game controller
class GameController:
    SHOOT_COOLDOWN_FRAMES = 6
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
        self._menu_bgm_playing = False
        self._show_controls = False   # toggle for controls overlay on menu

    def update(self) -> None:
        # Start menu BGM on first frame
        if not self._menu_bgm_playing and not self._bgm_playing:
            self.sound.start_menu_bgm()
            self._menu_bgm_playing = True

        if self.input.wants_quit():
            pyxel.quit()
        
        if self.input.wants_back():
            if self.model.state == GameState.SHOP:
                self.model.state = GameState.CHOOSE
            elif self.model.state not in (GameState.MENU, GameState.LEADERBOARD):
                self._go_to_menu()
        
        if self.input.wants_music():
            self._toggle_bgm()

        state = self.model.state
        if state == GameState.MENU:
            self._update_menu()
        elif state == GameState.PLAYING:
            self._update_playing()
        elif state == GameState.PAUSED:
            self._update_paused()
        elif state == GameState.CHOOSE:
            self._update_choose()
        elif state == GameState.BUILDING:
            self._update_building()
        elif state == GameState.SHOP:
            self._update_shop()
        elif state == GameState.LEADERBOARD:
            self._update_leaderboard()
        elif state in (GameState.GAME_OVER, GameState.WIN):
            self._update_endgame()

    def _update_menu(self) -> None:
        # Ensure menu BGM plays when on menu (e.g. after returning from game)
        if not self._menu_bgm_playing:
            self.sound.start_menu_bgm()
            self._menu_bgm_playing = True

        if self.input.wants_controls():
            self._show_controls = not self._show_controls

        if self.input.wants_campaign_mode():
            self._show_controls = False
            self.model = GameModel(self.settings, mode_type=RoundType.CAMPAIGN)
            self.model.start_next_round()
            self._ensure_bgm_playing()

        elif self.input.wants_endless_mode():
            self._show_controls = False
            self.model = GameModel(self.settings, mode_type=RoundType.ENDLESS)
            self.model.start_next_round()
            self._ensure_bgm_playing()
        
        elif pyxel.btnp(pyxel.KEY_L):
            self.model.state = GameState.LEADERBOARD
            return

        if self.input.wants_start():
            self.model.start_next_round()
            self._ensure_bgm_playing()

    def _update_playing(self) -> None:
        if self.input.wants_pause():
            self.model.state = GameState.PAUSED
            return
        
        self.model.maybe_spawn_enemy()

        if self.model.maybe_spawn_heart():
            self._try_place_heart()

        self._handle_aim_and_color()

        if self.input.wants_cycle_special():
            self.model.cycle_special()

        if self._shoot_cd > 0:
            self._shoot_cd -= 1
        if self.input.fire_held() and self._shoot_cd == 0:
            self._fire_player_bullet()
            self._shoot_cd = self.SHOOT_COOLDOWN_FRAMES

        self._handle_tower_direction_input()

        self._apply_slow_towers()

        self._update_towers()

        self._update_bullets()

        self._update_enemies()

        self.collisions.resolve(self.model.bullets, self.model.enemies)
        self._update_hearts()

        self.model.bullets = [b for b in self.model.bullets if b.alive]
        self.model.enemies = [e for e in self.model.enemies if e.alive]

        if self.model.lives <= 0:
            self.model.state = GameState.GAME_OVER
            self.sound.stop_bgm()
            self._bgm_playing = False
            self._selected_tower = None
        elif self.model.round_complete():
            current = self.model.current_round

            if (not self.model.is_endless and 
                self.model.total_rounds is not None and 
                current >= self.model.total_rounds):
                self.model.state = GameState.WIN
                self.sound.stop_bgm()
                self._bgm_playing = False
                self._selected_tower = None
            else:
                self.model.end_round()
                if not self.model.is_endless:
                    self._selected_tower = None

    def _update_choose(self) -> None:
        if self.input.wants_shop():
            self.model.state = GameState.SHOP
        elif self.input.wants_build():
            self.model.state = GameState.BUILDING
        elif self.input.wants_next_round():
            if not getattr(self.model, "is_endless", False):
                self._selected_tower = None
            self.model.start_next_round()

    def _update_shop(self) -> None:
        if self.input.shop_up():
            self.model.shop.move_cursor(-1)
        elif self.input.shop_down():
            self.model.shop.move_cursor(1)
        elif self.input.shop_buy():
            item = self.model.shop.selected_item()
            if self.model.shop_buy(item):
                self.sound.shop_buy()
                if item.key in ("slow_tower", "burst_tower"):
                    ttype = "slow" if item.key == "slow_tower" else "burst"
                    self.model._pending_tower_type = ttype
                    self.model.state = GameState.BUILDING

    def _update_building(self) -> None:
        if self.input.wants_place_tower():
            self._try_place_tower()
        if self.input.wants_upgrade_tower():
            self._try_upgrade_tower()
        if self.input.wants_cycle_tower_color():
            self._cycle_selected_tower_color()
        if self.input.wants_select_tower():
            self._select_nearest_tower_to_cursor()
        if self.input.wants_cycle_tower():
            self._cycle_selected_tower()
        self._handle_tower_direction_input()
        if self.input.wants_next_round():
            self.model.start_next_round()

    def _update_endgame(self) -> None:
        # Type name freely — R is just the letter R now
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if pyxel.btnp(getattr(pyxel, f"KEY_{c}")):
                self.model.player_name += c

        if pyxel.btnp(pyxel.KEY_BACKSPACE):
            self.model.player_name = self.model.player_name[:-1]

        if pyxel.btnp(pyxel.KEY_RETURN):
            self._save_score()
            return

        # ESC returns to menu without saving
        if self.input.wants_back():
            self._go_to_menu()

    def _update_paused(self):
        if self.input.wants_pause():
            self.model.state = GameState.PLAYING

    def _update_leaderboard(self):
        if self.input.wants_back():
            self.model.state = GameState.MENU

    def _go_to_menu(self) -> None:
        self.model = GameModel(self.settings)
        self.model.state = GameState.MENU
        self.sound.stop_bgm()
        self._bgm_playing = False
        self._menu_bgm_playing = False   # will restart on next _update_menu
        self._selected_tower = None
        self._shoot_cd = 0
        self._show_controls = False

    def _save_score(self):
        score = self.model.exp
        name  = self.model.player_name.strip() or "AAA"
        mode  = "endless" if self.model.is_endless else "campaign"

        # Load all existing entries
        entries = self._load_all_scores()

        # Find existing entry with same name+mode and only keep if new score is higher
        existing_idx = None
        for i, (m, n, s) in enumerate(entries):
            if m == mode and n.lower() == name.lower():
                existing_idx = i
                break

        if existing_idx is not None:
            _, _, old_score = entries[existing_idx]
            if score > old_score:
                entries[existing_idx] = (mode, name, score)
            # else keep old (higher) score, don't overwrite
        else:
            entries.append((mode, name, score))

        # Write back
        with open("leaderboard.txt", "w") as f:
            for m, n, s in entries:
                f.write(f"{m},{n},{s}\n")

        self.model.state = GameState.LEADERBOARD

    def _load_all_scores(self) -> list:
        """Load every entry from leaderboard.txt, no filtering."""
        entries = []
        try:
            with open("leaderboard.txt", "r") as f:
                for line in f:
                    parts = line.strip().split(",", 2)
                    if len(parts) != 3:
                        continue
                    mode, name, score = parts
                    try:
                        entries.append((mode, name, int(score)))
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass
        return entries

    def _load_scores(self):
        """Return top-10 sorted entries for display."""
        return sorted(self._load_all_scores(),
                      key=lambda x: x[2], reverse=True)[:10]

    def _ensure_bgm_playing(self) -> None:
        if not self._bgm_playing:
            self.sound.start_bgm()
            self._bgm_playing = True
            self._menu_bgm_playing = False

    def _toggle_bgm(self):
        # If on menu, toggle menu BGM
        if self.model.state == GameState.MENU:
            if self._menu_bgm_playing:
                self.sound.stop_bgm()
                self._menu_bgm_playing = False
            else:
                self.sound.start_menu_bgm()
                self._menu_bgm_playing = True
            return
        # In-game BGM toggle
        if self._bgm_playing:
            self.sound.stop_bgm()
            self._bgm_playing = False
        else:
            self.sound.start_bgm()
            self._bgm_playing = True

    def _handle_aim_and_color(self) -> None:
        mx, my = self.input.mouse_pos()
        self.model.shooter.aim_at(mx, my)

        active_color = self.model.active_colors
        idx = self.input.ammo_number_pressed(active_color)
        if idx is not None:
            self.model.shooter.set_color_index(idx)

        wheel = self.input.wheel_delta()
        if wheel != 0:
            self.model.shooter.cycle_color(1 if wheel > 0 else -1)

    def _fire_player_bullet(self) -> None:
        speed = self.settings["bullet_speed"]
        if self.model.active_special:
            special = self.model.produce_special_bullet(speed)
            if special is not None:
                self.model.bullets.append(special)
                self.sound.special()
                return
        bullets = self.model.shooter.produce_bullets(speed)
        self.model.bullets.extend(bullets)
        self.sound.shoot()

    def _apply_slow_towers(self) -> None:
        slow_towers = [t for t in self.model.towers
                       if isinstance(t, SlowTower) and not t.is_disabled]
        if not slow_towers:
            return
        base_speed = self.settings["enemy_speed"]
        for e in self.model.enemies:
            if not e.alive:
                continue
            in_range = any(
                math.hypot(t.x - e.x, t.y - e.y) <= SlowTower.SLOW_RADIUS
                for t in slow_towers
            )
            if in_range:
                e.speed = base_speed * SlowTower.SLOW_FACTOR
            else:
                if e.speed < base_speed:
                    e.speed = base_speed

    def _on_enemy_killed(self, enemy: Enemy) -> None:
        self.model.exp = max(0, self.model.exp + enemy.exp_value)
        self.sound.kill()
        if isinstance(enemy, Saboteur):
            self.sound.saboteur()
            for t in self.model.towers:
                if math.hypot(t.x - enemy.x, t.y - enemy.y) <= Saboteur.SABOTAGE_RADIUS:
                    t.disable(Saboteur.SABOTAGE_FRAMES)

    def _try_place_tower(self) -> None:
        cx, cy = self._cursor_cell_center()
        if not self._is_legal_tower_spot(cx, cy):
            return
        ttype = self.model._pending_tower_type
        tower = self.model.place_tower(cx, cy, tower_type=ttype)
        if tower is not None:
            self.sound.place()
            self._selected_tower = tower
            if ttype != "normal":
                self.model._pending_tower_type = "normal"

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
        for t in self.model.towers:
            t.selected = (t is self._selected_tower)
            t.update()

        if not any(e.alive for e in self.model.enemies):
            return

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
        tunnels_allowed = self.model.round_data.tunnels > 0
        alloc = self.model.tunnel_per_path()
        for e in self.model.enemies:
            if not e.alive and not e.escaped:
                continue
            
            if e.path_index >= len(self.model.paths):
                e.path_index = 0

            path = self.model.paths[e.path_index]
            active = path.active_tunnels(alloc[e.path_index])
            e.update(path, tunnels_active=tunnels_allowed, active_tunnels=active)
            if e.escaped:
                self.model.lives -= 1
                self.sound.life_lost()
                e.escaped = False  
    
    def _update_hearts(self) -> None:
        s = self.model.shooter

        for heart in self.model.hearts:
            if heart.alive:
                heart.update()
        
        lives_gained = self.collisions.resolve_hearts(
            self.model.bullets, self.model.hearts
        )

        if lives_gained:
            self.model.lives += 1
            pyxel.play(CHAN_SFX_B, SFX_UPGRADE)
        
        self.model.hearts = [heart for heart in self.model.hearts if heart.alive]
    
    def _try_place_heart(self) -> None:
        cs = self.settings["cell_size"]
        sw = self.settings["screen_width"]
        sh = self.settings["screen_height"]
        for _ in range(30):
            x = random.randint(1, sw // cs - 2) * cs + cs // 2
            y = random.randint(1, sh // cs - 1) * cs + cs // 2
            if self._is_clear_of_paths(x, y):
                self.model.place_heart(x, y)
                return

    def _is_clear_of_paths(self, x: float, y: float, min_dist: int = 20) -> bool:
        for path in self.model.active_paths():
            for i in range(1, len(path.waypoints)):
                x0, y0 = path.waypoints[i - 1]
                x1, y1 = path.waypoints[i]
                dx, dy = x1 - x0, y1 - y0
                if dx == 0 and dy == 0:
                    dist = math.hypot(x - x0, y - y0)
                else:
                    t = max(0.0, min(1.0, ((x - x0)*dx + (y - y0)*dy) / (dx*dx + dy*dy)))
                    dist = math.hypot(x - (x0 + t*dx), y - (y0 + t*dy))
                if dist < min_dist:
                    return False
        return True
    

    def _cursor_cell_center(self) -> tuple[float, float]:
        cs = self.settings["cell_size"]
        mx, my = self.input.mouse_pos()
        cell_x = (mx // cs) * cs
        cell_y = (my // cs) * cs
        return cell_x + cs / 2, cell_y + cs / 2

    def _try_upgrade_tower(self) -> None:
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

    def _cycle_selected_tower_color(self) -> None:
        """C key: cycle the selected tower through the available colors."""
        if self._selected_tower is None or self._selected_tower not in self.model.towers:
            return
        n = self.settings["num_colors"]
        colors = COLOR_ORDER[:n]
        try:
            idx = colors.index(self._selected_tower.color)
        except ValueError:
            idx = 0
        self._selected_tower.color = colors[(idx + 1) % n]

    def _is_legal_tower_spot(self, x: float, y: float) -> bool:
        for path in self.model.active_paths():
            for i in range(1, len(path.waypoints)):
                x0, y0 = path.waypoints[i - 1]
                x1, y1 = path.waypoints[i]
                if self._dist_to_segment(x, y, x0, y0, x1, y1) < self.MIN_TOWER_DIST_FROM_PATH:
                    return False
        for t in self.model.towers:
            if math.hypot(t.x - x, t.y - y) < self.MIN_TOWER_DIST_FROM_TOWER:
                return False
        s = self.model.shooter
        if math.hypot(s.x - x, s.y - y) < self.MIN_TOWER_DIST_FROM_TOWER:
            return False
        return True

    @staticmethod
    def _dist_to_segment(px, py, x0, y0, x1, y1) -> float:
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
