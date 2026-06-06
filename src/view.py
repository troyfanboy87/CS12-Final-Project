import math
import pyxel

from .model import (
    BombBullet,
    BurstTower,
    Chameleon,
    COLOR_ORDER,
    COLOR_PALETTE,
    DIRECTION_VECTORS,
    ENEMY_RADIUS,
    GameState,
    Ghost,
    Regenerator,
    RoundType,
    Saboteur,
    SlowTower,
    SniperBullet,
    SHOP_ITEMS,
    TimeClock,
)


class GameView:

    def __init__(self, controller):
        self.controller = controller

        import pathlib
        self._sprites_loaded = False
        _res = pathlib.Path(__file__).resolve().parent.parent / "enemies.pyxres"
        if _res.exists():
            try:
                pyxel.load(str(_res), exclude_images=False,
                           exclude_tilemaps=True, exclude_sounds=True,
                           exclude_musics=True)
                self._sprites_loaded = True
            except Exception:
                pass

    @property
    def model(self):
        return self.controller.model

    def draw(self) -> None:
        pyxel.cls(0)

        state = self.model.state
        if state == GameState.MENU:
            self._draw_menu()
        elif state == GameState.PLAYING:
            self._draw_play_field()
            self._draw_hud()
            self._draw_intro()
        elif state == GameState.CHOOSE:
            self._draw_play_field()
            self._draw_choose_overlay()
            self._draw_hud()
        elif state == GameState.BUILDING:
            self._draw_play_field()
            self._draw_build_overlay()
            self._draw_hud()
        elif state == GameState.SHOP:
            self._draw_play_field()
            self._draw_shop_overlay()
            self._draw_hud()
        elif state == GameState.PAUSED:
            self._draw_play_field()
            self._draw_pause()
        elif state == GameState.LEADERBOARD:
            self._draw_leaderboard()
        elif state == GameState.GAME_OVER:
            self._draw_play_field()
            self._draw_game_over()
        elif state == GameState.WIN:
            self._draw_play_field()
            self._draw_win()

    # ── Big pixel font ────────────────────────────────────────────────────────
    # Each letter is a 5-wide × 5-tall bitmap (list of 5 strings, '1'=on '0'=off)
    _BIG_FONT = {
        'Z': ["11111","00011","00110","01100","11111"],
        'U': ["10001","10001","10001","10001","01110"],
        'M': ["10001","11011","10101","10001","10001"],
        'A': ["01110","10001","11111","10001","10001"],
        ':': ["00000","00100","00000","00100","00000"],
        'T': ["11111","00100","00100","00100","00100"],
        'O': ["01110","10001","10001","10001","01110"],
        'W': ["10001","10001","10101","11011","10001"],
        'E': ["11111","10000","11110","10000","11111"],
        'R': ["11110","10001","11110","10100","10011"],
        'D': ["11110","10001","10001","10001","11110"],
        'F': ["11111","10000","11110","10000","10000"],
        'N': ["10001","11001","10101","10011","10001"],
        'S': ["01111","10000","01110","00001","11110"],
        ' ': ["00000","00000","00000","00000","00000"],
    }

    def _draw_big_text(self, text: str, x: int, y: int,
                       color: int, scale: int = 2) -> int:
        """Draw text using the big pixel font. Returns total width drawn."""
        cx = x
        for ch in text.upper():
            bitmap = self._BIG_FONT.get(ch, self._BIG_FONT[' '])
            for row, bits in enumerate(bitmap):
                for col, bit in enumerate(bits):
                    if bit == '1':
                        pyxel.rect(cx + col * scale,
                                   y  + row * scale,
                                   scale, scale, color)
            cx += (5 + 1) * scale   # 5 cols + 1 gap
        return cx - x

    def _draw_ghost_sprite(self, x: int, y: int,
                           frame: int, color: int = 7) -> None:
        """Draw a small pixelated ghost at (x,y). frame drives the bobbing."""
        bob = 1 if (frame // 12) % 2 == 0 else 0
        gy = y + bob

        # Body — dome top
        body = [
            "01110",
            "11111",
            "11111",
            "11111",
            "11011",   # wavy bottom
        ]
        sc = 2
        for row, bits in enumerate(body):
            for col, bit in enumerate(bits):
                if bit == '1':
                    pyxel.rect(x + col * sc, gy + row * sc, sc, sc, color)

        # Eyes — two dark pixels
        eye_c = 0
        pyxel.rect(x + 1 * sc, gy + 1 * sc, sc, sc, eye_c)
        pyxel.rect(x + 3 * sc, gy + 1 * sc, sc, sc, eye_c)

        # Trailing squiggle below ghost (animated)
        trail_phase = (frame // 8) % 3
        trail_offsets = [(0, 0), (2, -1), (4, 0), (6, -1), (8, 0)]
        for i, (tx, ty_off) in enumerate(trail_offsets):
            ty_val = gy + 5 * sc + ty_off * sc + (1 if (i + trail_phase) % 2 == 0 else 0)
            pyxel.rect(x + tx, ty_val, sc, 1, color)

    def _draw_menu(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        fc = pyxel.frame_count

        # ── Starfield — full screen, deterministic twinkle ────────────────
        for i in range(48):
            sx = (i * 37 + 13) % sw
            sy = (i * 53 + 7)  % sh
            if (fc // (4 + i % 5) + i) % 3 != 0:
                pyxel.pset(sx, sy, 1 if i % 3 == 0 else 5)

        # ── Layout math ───────────────────────────────────────────────────
        scale = 2
        char_w = (5 + 1) * scale   # 12px per char
        line1, line2 = "ZUMA:", "TOWER DEFENSE"
        w1 = len(line1) * char_w - scale
        w2 = len(line2) * char_w - scale
        line_h = 5 * scale         # 10px tall per line

        # Total block height: line1 + gap4 + line2 + gap10 + panel + gap6 + music
        panel_items = [
            ("[1] Campaign Mode",  11),
            ("[2] Endless Mode",   12),
            ("[3] Time Attack",    9),
            ("[L] Leaderboard",    7),
            ("[K] Controls",       6),
            ("[M] Toggle Music",   6),
            ("[Q] Quit Game",      6),
        ]
        pw = 120
        ph = len(panel_items) * 12 + 5
        total_h = line_h + 4 + line_h + 10 + ph + 6 + 6
        start_y = (sh - total_h) // 2

        ty1 = start_y
        ty2 = ty1 + line_h + 4
        py  = ty2 + line_h + 10

        # ── Title ─────────────────────────────────────────────────────────
        c1 = 10 if (fc // 20) % 2 == 0 else 9
        # Shadow
        self._draw_big_text(line1, sw // 2 - w1 // 2 + 1, ty1 + 1, 1, scale)
        self._draw_big_text(line2, sw // 2 - w2 // 2 + 1, ty2 + 1, 1, scale)
        # Title
        self._draw_big_text(line1, sw // 2 - w1 // 2, ty1, c1, scale)
        self._draw_big_text(line2, sw // 2 - w2 // 2, ty2, 7,  scale)

        # ── Ghosts — just left and right of "ZUMA:" on the same row ───────
        ghost_y = ty1 - 1
        ghost_sc = 2   # ghost body is 5*sc=10px wide
        left_x  = sw // 2 - w1 // 2 - ghost_sc * 5 - 6
        right_x = sw // 2 + w1 // 2 + 6
        self._draw_ghost_sprite(left_x,  ghost_y, fc,      color=7)
        self._draw_ghost_sprite(right_x, ghost_y, fc + 24, color=5)

        # ── Menu panel ────────────────────────────────────────────────────
        px_panel = sw // 2 - pw // 2
        pyxel.rect(px_panel - 1, py - 1, pw + 2, ph + 2, 1)
        pyxel.rectb(px_panel - 1, py - 1, pw + 2, ph + 2, 5)

        for i, (label, color) in enumerate(panel_items):
            lx = sw // 2 - len(label) * 2
            ly = py + 5 + i * 12
            if i < 3 and (fc // 18) % 2 == 1:
                continue
            pyxel.text(lx, ly, label, color)

        # ── Music state ───────────────────────────────────────────────────
        music_on = self.controller._menu_bgm_playing or self.controller._bgm_playing
        state_str = "MUSIC: ON" if music_on else "MUSIC: OFF"
        mc = 11 if music_on else 8
        pyxel.text(sw // 2 - len(state_str) * 2, py + ph + 6, state_str, mc)

        # ── Controls overlay if toggled ───────────────────────────────────
        if self.controller._show_controls:
            self._draw_controls_overlay()

    def _draw_controls_overlay(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        lines = [
            ("-- SHOOTING --",        7),
            ("Mouse: aim",            6),
            ("Hold LClick: shoot",    6),
            ("1-6 / Wheel: ammo",     6),
            ("X: cycle special ammo", 6),
            ("",                      0),
            ("-- BUILD MODE --",      7),
            ("T: place tower",        6),
            ("U: upgrade tower",      6),
            ("C: cycle color",        6),
            ("RClick/TAB: select",    6),
            ("WASD: aim tower",       6),
            ("SPACE: next round",     6),
            ("",                      0),
            ("-- BETWEEN ROUNDS --",  7),
            ("B: build phase",        6),
            ("O: shop",               6),
            ("",                      0),
            ("-- ENEMIES --",         7),
            ("+ Regen  * Cham",       6),
            ("! Saboteur  ~ Ghost",   6),
            ("",                      0),
            ("[K] close",             5),
        ]
        pw = 140
        ph = len(lines) * 7 + 10
        ox = sw // 2 - pw // 2
        oy = max(4, sh // 2 - ph // 2)

        pyxel.rect(ox, oy, pw, ph, 0)
        pyxel.rectb(ox, oy, pw, ph, 6)

        for i, (text, color) in enumerate(lines):
            if text:
                pyxel.text(ox + 6, oy + 5 + i * 7, text, color)

    def _draw_play_field(self) -> None:
        self._draw_grid()
        self._draw_paths()
        self._draw_towers()
        self._draw_hearts()
        self._draw_clocks()
        self._draw_enemies()
        self._draw_bullets()
        self._draw_shooter()

    def _draw_intro(self) -> None:
        if self.controller._intro_timer <= 0:
            return

        sw, sh = pyxel.width, pyxel.height
        fc = pyxel.frame_count
        mode = self.model.mode_type

        for y in range(0, sh, 2):
            for x in range(0, sw, 2):
                pyxel.pset(x, y, 1)

        if mode == RoundType.CAMPAIGN:
            title  = "CAMPAIGN MODE"
            title_color = 5
            lines = [
                ("Survive all 14 rounds to win!",           6),
                ("",                                        0),
                ("Shoot enemies to gain EXP for towers.",   7),
                ("Towers unlocked for Round 3.",            7),
                ("Build, upgrade, and aim well.",           7),
                ("Collect hearts to gain lives!",           10),
                ("",                                        0),
                ("Enemies grow stronger each round.",       7),
                ("Don't let them escape!",                  7),
            ]

        elif mode == RoundType.ENDLESS:
            title  = "ENDLESS MODE"
            title_color = 5
            lines = [
                ("Survive as many rounds as you can!",  6),
                ("",                                    0),
                ("Build towers between rounds.",        7),
                ("Collect hearts to gain lives!",       10),
                ("",                                    0),
                ("Speed and enemy count rise",          7),
                ("with every round. Good luck!",        7),
            ]

        else:
            title  = "TIME ATTACK"
            title_color = 5
            lines = [
                ("You have 60 seconds.",        6),
                ("Try to kill all enemies!",    6),
                ("",                            0),
                ("Shoot enemies to earn EXP.",  7),
                ("Shoot clocks to add +5s!",   10),
                ("",                            0),
                ("Beat the clock!",             7),
            ]

        pw = 160
        ph = len(lines) * 8 + 44
        bx = sw // 2 - pw // 2
        by = sh // 2 - ph // 2
        pyxel.rect(bx, by, pw, ph, 0)
        pyxel.rectb(bx, by, pw, ph, 13)

        tx = sw // 2 - len(title) * 2
        pyxel.text(tx, by + 8, title, title_color)

        pyxel.line(bx + 4, by + 17, bx + pw - 4, by + 17, 13)

        for i, (text, color) in enumerate(lines):
            if text:
                lx = sw // 2 - len(text) * 2
                pyxel.text(lx, by + 24 + i * 8, text, color)

        if (fc // 20) % 2 == 0:
            hint = "Click or wait to start..."
            pyxel.text(sw // 2 - len(hint) * 2, by + ph - 10, hint, 13)

    def _draw_choose_overlay(self) -> None:
        if self.model.state == GameState.BUILDING:
            return
        
        sw, sh = pyxel.width, pyxel.height

        msgs = [
            f"Round {self.model.current_round} cleared!",
            "",
        ]
        if self.model.current_round == 2 and self.model.mode_type == RoundType.CAMPAIGN:
            msgs.extend([
                "NEW: Towers unlocked!",
                "Press B to enter Build Mode",
                "",
            ])
        elif self.model.towers_unlocked:
            msgs.append(" B - Build towers")
        msgs.append(" O - Shop")
        msgs.append("SPACE - Next round")

        max_len = max(len(m) for m in msgs)
        bw = max_len * 4 + 16
        bh = len(msgs) * 8 + 12
        bx = sw // 2 - bw // 2
        by = sh // 2 - bh // 2
        pyxel.rect(bx - 1, by - 1, bw + 2, bh + 2, 1)
        pyxel.rectb(bx - 1, by - 1, bw + 2, bh + 2, 6)
        for i, m in enumerate(msgs):
            x = sw // 2 - len(m) * 2
            y = by + 6 + i * 8
            if i == 0:
                pyxel.text(x, y, m, 10)
            elif m.startswith("B"):
                pyxel.text(x, y, m, 11)
            elif m.startswith("SPACE"):
                pyxel.text(x, y, m, 7)
            else:
                pyxel.text(x, y, m, 7)

    def _draw_build_overlay(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        cost_tower   = self.model.settings["tower_cost"]
        cost_upgrade = self.model.settings["tower_upgrade_cost"]

        towers_unlocked = self.model.towers_unlocked
        upgrades_unlocked = self.model.upgrades_unlocked

        if towers_unlocked:
            self._draw_cursor_cell()

        msgs = [
            f"BUILD MODE — EXP: {self.model.exp}",
        ]

        if towers_unlocked:
            msgs.extend([f"T: place tower ({cost_tower} EXP)", 
                        "C: cycle tower color",
                        "RClick/TAB: select   WASD: aim"])
        else:
            msgs.append("T: LOCKED")
        
        if upgrades_unlocked:
            msgs.append(f"U: upgrade selected ({cost_upgrade} EXP)")
        else:
            msgs.append("U: UPGRADES LOCKED")
            
        msgs.append("SPACE: start next round")

        max_len = max(len(m) for m in msgs)
        bw = max_len * 4 + 16
        bh = len(msgs) * 8 + 12
        bx = sw // 2 - bw // 2
        by = sh - bh - 12

        pyxel.rect(bx - 1, by - 1, bw + 2, bh + 2, 1)
        pyxel.rectb(bx - 1, by - 1, bw + 2, bh + 2, 6)

        for i, m in enumerate(msgs):
            x = sw // 2 - len(m) * 2
            y = by + 6 + i * 8
            
            color = 8 if "LOCKED" in m else (10 if i == 0 else 7)

            pyxel.text(x + 1, y + 1, m, 0)
            pyxel.text(x,     y,     m, color)

        sel = self.controller._selected_tower
        if sel is not None and sel in self.model.towers:
            swatch_color = COLOR_PALETTE[sel.color]
            label = f"SEL COLOR: {sel.color.upper()}"
            lx = sw // 2 - len(label) * 2
            ly = by - 10
            pyxel.rect(lx - 2, ly - 1, len(label) * 4 + 4, 9, 1)
            pyxel.rectb(lx - 2, ly - 1, len(label) * 4 + 4, 9, swatch_color)
            pyxel.text(lx, ly, label, swatch_color)

    def _draw_game_over(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        pyxel.rect(0, sh // 2 - 28, sw, 66, 0)
        msg = "GAME OVER"
        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 20, msg, 8)

        name = self.model.player_name
        cursor = "_" if (pyxel.frame_count // 15) % 2 == 0 else ""
        pyxel.text(sw // 2 - 36, sh // 2 - 8, f"Name: {name}{cursor}", 7)

        pyxel.text(sw // 2 - 44, sh // 2 + 4,  "ENTER: submit & view scores", 6)
        pyxel.text(sw // 2 - 32, sh // 2 + 14, "ESC: back to menu", 6)

    def _draw_win(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        pyxel.rect(0, sh // 2 - 28, sw, 66, 0)

        msg = "YOU WIN!"
        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 20, msg, 11)

        name = self.model.player_name
        cursor = "_" if (pyxel.frame_count // 15) % 2 == 0 else ""
        pyxel.text(sw // 2 - 36, sh // 2 - 8, f"Name: {name}{cursor}", 7)

        pyxel.text(sw // 2 - 44, sh // 2 + 4,  "ENTER: submit & view scores", 6)
        pyxel.text(sw // 2 - 32, sh // 2 + 14, "ESC: back to menu", 6)

    def _draw_pause(self):
        sw, sh = pyxel.width, pyxel.height

        for y in range(0, sh, 2):
            for x in range(0, sw, 2):
                pyxel.pset(x, y, 1)  # dark pixels

        options = [
            "Resume [P]",
            "Restart [R]",
            "Back to Menu [ESC]",
            "Quit Game [Q]"
        ]

        panel_w = 100
        panel_h = 60
        px = sw // 2 - panel_w // 2
        py = sh // 2 - panel_h // 2

        pyxel.rect(px, py, panel_w, panel_h, 0)
        pyxel.rectb(px, py, panel_w, panel_h, 7)

        pyxel.text(sw // 2 - len("PAUSED") * 2, py + 8, "PAUSED", 7)
        
        for i, opt in enumerate(options):
            pyxel.text(sw // 2 -  len(opt) * 2, py + 20 + i * 8, opt, 6)

    def _draw_leaderboard(self):
        sw, sh = pyxel.width, pyxel.height
        pyxel.text(sw//2 - 20, 20, "LEADERBOARD", 10)

        scores = self.controller._load_scores()

        for i, (mode, name, score) in enumerate(scores):
            line = f"{i+1}. {name} ({mode}) - {score}"
            pyxel.text(sw//2 - len(line)*2, 40 + i*10, line, 7)
        pyxel.text(10, sh - 10, "ESC to return", 6)

    def _draw_grid(self) -> None:
        cs = self.model.settings["cell_size"]
        sw = pyxel.width
        sh = pyxel.height
        for y in range(0, sh, cs):
            if y < 9:
                continue
            for x in range(0, sw, cs):
                pyxel.pset(x, y, 1)

    def _draw_cursor_cell(self) -> None:
        cs = self.model.settings["cell_size"]
        cx, cy = self.controller._cursor_cell_center()
        cell_x = int(cx - cs / 2)
        cell_y = int(cy - cs / 2)
        legal = self.controller._is_legal_tower_spot(cx, cy)
        color = 11 if legal else 8
        pyxel.rectb(cell_x, cell_y, cs, cs, color)

    def _draw_paths(self) -> None:

        active_paths = self.model.active_paths()
        tunnel_allocation = self.model.tunnel_per_path()
        
        for i, path in enumerate(active_paths):
            wp = path.waypoints

            if len(wp) < 2:
                continue

            for j in range(1, len(wp)):
                x0, y0 = wp[j - 1]
                x1, y1 = wp[j]
                for dx, dy in [(-1, 0), (0, 0), (1, 0), (0, -1), (0, 1)]:
                    pyxel.line(x0 + dx, y0 + dy, x1 + dx, y1 + dy, 5)

            tunnel_count = tunnel_allocation[i]
            visible_tunnels = path.active_tunnels(tunnel_count)

            for tunnel in visible_tunnels:
                self._draw_tunnel(path, tunnel)

            sx, sy = wp[0][0], wp[0][1]
            ex, ey = wp[-1][0], wp[-1][1]
            pyxel.circb(sx, sy, 3, 11)
            pyxel.circb(ex, ey, 3, 8)

    def _draw_tunnel(self, path, tunnel) -> None:
        steps = max(2, int(tunnel.length // 2))
        for i in range(steps + 1):
            p = tunnel.start + (tunnel.length * i / steps)
            x, y = path.position_at(p)
            pyxel.rect(int(x) - 4, int(y) - 4, 9, 9, 1)
            pyxel.rectb(int(x) - 4, int(y) - 4, 9, 9, 13)
        sx, sy = path.position_at(tunnel.start)
        ex, ey = path.position_at(tunnel.end)
        pyxel.text(int(sx) - 6, int(sy) - 3, "[", 13)
        pyxel.text(int(ex) - 0, int(ey) - 3, "]", 13)

    def _draw_enemies(self) -> None:
        _SPRITE_W = 8
        _SPRITE_H = 8
        for e in self.model.enemies:
            if not e.alive:
                continue
            color_idx = COLOR_PALETTE[e.color]
            ex, ey = int(e.x), int(e.y)

            if self._sprites_loaded:
                if isinstance(e, Ghost):
                    sx = 0
                    sy = 6 * _SPRITE_H
                else:
                    try:
                        row = COLOR_ORDER.index(e.color)
                    except ValueError:
                        row = 0
                    sx = 0
                    sy = row * _SPRITE_H
                draw_x = ex - _SPRITE_W // 2
                draw_y = ey - _SPRITE_H // 2
                pyxel.blt(draw_x, draw_y, 0, sx, sy, _SPRITE_W, _SPRITE_H, 0)
                if e.in_tunnel:
                    pyxel.rectb(draw_x, draw_y, _SPRITE_W, _SPRITE_H, 13)
            else:
                outline = 13 if e.in_tunnel else 0
                if isinstance(e, Ghost):
                    # Semi-transparent look: draw as a white circle with dark outline
                    pyxel.circ(ex, ey, ENEMY_RADIUS, 7)
                    pyxel.circb(ex, ey, ENEMY_RADIUS, 5 if not e.in_tunnel else 13)
                else:
                    pyxel.circ(ex, ey, ENEMY_RADIUS, color_idx)
                    pyxel.circb(ex, ey, ENEMY_RADIUS, outline)

            self._draw_enemy_badge(e, ex, ey)

            if e.hp < e.max_hp:
                bar_w = 10
                filled = int(bar_w * e.hp / e.max_hp)
                pyxel.rect(ex - 5, ey - 9, bar_w, 1, 0)
                pyxel.rect(ex - 5, ey - 9, filled, 1, 11)

    def _draw_enemy_badge(self, e, ex: int, ey: int) -> None:
        badge_y = ey - ENEMY_RADIUS - 5

        if isinstance(e, Regenerator):
            cx, cy = ex, badge_y
            pyxel.pset(cx,     cy,     11)
            pyxel.pset(cx,     cy - 2, 11)
            pyxel.pset(cx,     cy + 2, 11)
            pyxel.pset(cx - 2, cy,     11)
            pyxel.pset(cx + 2, cy,     11)

        elif isinstance(e, Chameleon):
            phase = (pyxel.frame_count // 8) % 4
            cx, cy = ex, badge_y
            tips = [
                [(cx, cy - 2), (cx, cy + 2), (cx - 2, cy), (cx + 2, cy)],
                [(cx - 1, cy - 1), (cx + 1, cy + 1), (cx - 2, cy), (cx + 2, cy)],
                [(cx - 2, cy), (cx + 2, cy), (cx, cy - 1), (cx, cy + 1)],
                [(cx - 1, cy + 1), (cx + 1, cy - 1), (cx - 2, cy), (cx + 2, cy)],
            ]
            badge_color = 10 if (pyxel.frame_count // 15) % 2 == 0 else 7
            for px, py in tips[phase]:
                pyxel.pset(px, py, badge_color)

        elif isinstance(e, Saboteur):
            cx, cy = ex, badge_y
            bolt_color = 10 if (pyxel.frame_count // 10) % 2 == 0 else 7
            pyxel.pset(cx + 1, cy - 2, bolt_color)
            pyxel.pset(cx,     cy - 1, bolt_color)
            pyxel.pset(cx + 1, cy,     bolt_color)
            pyxel.pset(cx,     cy + 1, bolt_color)
            pyxel.pset(cx + 1, cy + 2, bolt_color)

        elif isinstance(e, Ghost):
            # Flickering "~" tilde badge to signal EXP steal
            if (pyxel.frame_count // 8) % 2 == 0:
                pyxel.text(ex - 2, badge_y - 1, "~", 7)
    
    def _draw_hearts(self) -> None:
        _SPRITE_W = 8
        _SPRITE_H = 8
        sx = 0
        sy = 7 * _SPRITE_H

        for h in self.model.hearts:
            if not h.alive:
                continue
            hx, hy = int(h.x), int(h.y)
            if self._sprites_loaded:
                pyxel.blt(
                    hx - _SPRITE_W // 2,
                    hy - _SPRITE_H // 2,
                    0, sx, sy, _SPRITE_W, _SPRITE_H, 0
                )
            else:
                pyxel.circb(hx, hy, 5, 8)
        
        for h in self.model.hearts:
            if h.alive and (pyxel.frame_count // 20) % 2 == 0:
                hx, hy = int(h.x), int(h.y)
                pyxel.rectb(hx - 5, hy - 5, 10, 10, 7)

    def _draw_clocks(self) -> None:
        _SPRITE_W = 8
        _SPRITE_H = 8
        sx = 0
        sy = 8 * _SPRITE_H

        for c in self.model.time_clocks:
            if not c.alive:
                continue
            cx, cy = int(c.x), int(c.y)
            if self._sprites_loaded:
                pyxel.blt(cx - _SPRITE_W // 2, cy - _SPRITE_H // 2,
                        0, sx, sy, _SPRITE_W, _SPRITE_H, 0)
            else:
                pyxel.circb(cx, cy, 5, 7)
                pyxel.line(cx, cy - 3, cx, cy, 7)
                pyxel.line(cx, cy, cx + 3, cy, 7)

            if (pyxel.frame_count // 15) % 2 == 0:
                pyxel.rectb(cx - 6, cy - 6, 12, 12, 10)
            pyxel.text(cx - 5, cy + 7, "+5s", 10)

    def _draw_bullets(self) -> None:
        for b in self.model.bullets:
            if not b.alive:
                continue
            color_idx = COLOR_PALETTE[b.color]
            bx, by = int(b.x), int(b.y)
            if isinstance(b, SniperBullet):
                pyxel.line(bx - int(b.vx), by - int(b.vy), bx, by, color_idx)
                pyxel.pset(bx, by, 7)
            elif isinstance(b, BombBullet):
                r = 3 if (pyxel.frame_count // 4) % 2 == 0 else 4
                pyxel.circb(bx, by, r, color_idx)
                pyxel.pset(bx, by, 10)
            else:
                pyxel.circ(bx, by, 2, color_idx)
                pyxel.pset(bx, by, 7)

    def _draw_shooter(self) -> None:
        s = self.model.shooter
        x, y = int(s.x), int(s.y)

        pyxel.rect(x - 6, y - 6, 12, 12, 1)
        pyxel.rectb(x - 6, y - 6, 12, 12, 6)

        ammo_color = COLOR_PALETTE[s.color]
        pyxel.circ(x, y, 3, ammo_color)
        pyxel.circb(x, y, 3, 7)

        bx = x + int(math.cos(s.aim_angle) * 10)
        by = y + int(math.sin(s.aim_angle) * 10)
        pyxel.line(x, y, bx, by, 7)

    def _draw_towers(self) -> None:
        for t in self.model.towers:
            x, y = int(t.x), int(t.y)
            base_color = COLOR_PALETTE[t.color]

            if t.is_disabled:
                base_color = 8 if (pyxel.frame_count // 6) % 2 == 0 else 1

            if t.selected:
                pyxel.rectb(x - 7, y - 7, 14, 14, 10)

            if isinstance(t, SlowTower):
                pyxel.circ(x, y, 5, base_color)
                pyxel.circb(x, y, SlowTower.SLOW_RADIUS, 12)
                pyxel.text(x - 2, y - 2, "S", 7)
            elif isinstance(t, BurstTower):
                pyxel.rect(x - 5, y - 5, 10, 10, base_color)
                pyxel.rectb(x - 5, y - 5, 10, 10, 0)
                for d in DIRECTION_VECTORS:
                    ddx, ddy = DIRECTION_VECTORS[d]
                    pyxel.pset(x + ddx * 6, y + ddy * 6, 7)
            else:
                pyxel.rect(x - 5, y - 5, 10, 10, base_color)
                pyxel.rectb(x - 5, y - 5, 10, 10, 0)
                dx, dy = DIRECTION_VECTORS[t.direction]
                bx = x + dx * 8
                by = y + dy * 8
                pyxel.line(x, y, bx, by, 6)
                pyxel.pset(bx, by, 7)

            if t.upgraded and t.color_b is not None:
                second = COLOR_PALETTE[t.color_b]
                pyxel.circ(x + 3, y - 7, 1, second)
                pyxel.text(x - 2, y - 2, "+", 7)

    def _draw_shop_overlay(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        bw, bh = 162, 104
        bx = sw // 2 - bw // 2
        by = sh // 2 - bh // 2
        pyxel.rect(bx, by, bw, bh, 1)
        pyxel.rectb(bx, by, bw, bh, 9)

        pyxel.text(bx + bw // 2 - 10, by + 4, "SHOP", 9)
        pyxel.text(bx + 4, by + 4, f"EXP:{self.model.exp}", 10)

        shop = self.model.shop
        for i, item in enumerate(shop.items):
            iy = by + 16 + i * 14
            is_sel = (i == shop.cursor)
            can = self.model.exp >= item.cost
            fg = 10 if can else 8
            if is_sel:
                pyxel.rect(bx + 2, iy - 1, bw - 4, 12, 0)
                pyxel.rectb(bx + 2, iy - 1, bw - 4, 12, 9)
            pyxel.text(bx + 6, iy, item.label, 7 if is_sel else fg)
            cost_str = f"{item.cost}EXP"
            pyxel.text(bx + bw - len(cost_str) * 4 - 6, iy, cost_str, fg)

        footer = "UP/DN:select  ENTER:buy  ESC:back"
        pyxel.text(bx + bw // 2 - len(footer) * 2, by + bh - 10, footer, 6)

    def _draw_special_ammo_hud(self) -> None:
        parts = []
        active = self.model.active_special
        if self.model.sniper_ammo > 0:
            parts.append((f"SNP:{self.model.sniper_ammo}", active == "sniper"))
        if self.model.bomb_ammo > 0:
            parts.append((f"BOM:{self.model.bomb_ammo}", active == "bomb"))
        if not parts:
            return
        x = 2
        pyxel.text(x, 11, "X> ", 9)
        x += 12
        for label, is_active in parts:
            color = 10 if is_active else 6
            text = f"[{label}]" if is_active else label
            pyxel.text(x, 11, text, color)
            x += (len(text) + 1) * 4

    def _draw_hud(self) -> None:
        sw = pyxel.width
        pyxel.rect(0, 0, sw, 9, 1)

        if self.model.is_time_attack:
            pyxel.text(2, 2, f"EXP:{self.model.exp}",     10)
            secs = self.model.time_remaining_seconds
            mins = int(secs) // 60
            s    = int(secs) % 60
            timer_str = f"TIME {mins}:{s:02d}"
            t_color = 8 if secs < 10 else (10 if secs < 20 else 7)
            if not (secs < 10 and (pyxel.frame_count // 8) % 2 == 1):
                pyxel.text(55, 2, timer_str, t_color)
        else:
            pyxel.text(2,  2, f"LIVES:{self.model.lives}", 8)
            pyxel.text(40, 2, f"EXP:{self.model.exp}",     10)
            if self.model.mode_type == RoundType.ENDLESS:
                round_str = f"R:{self.model.current_round} (ENDLESS)"
            else:
                total = getattr(self.model, "total_rounds", 12)
                round_str = f"R:{self.model.current_round}/{total}"
            pyxel.text(80, 2, round_str, 7)

        s = self.model.shooter
        label = f"AMMO:{s.color.upper()}"
        pyxel.text(sw - len(label) * 4 - 2, 2, label, COLOR_PALETTE[s.color])

        self._draw_special_ammo_hud()

        if self.model.is_time_attack:
            pyxel.text(2, pyxel.height - 16, "+ Regen", 11)
            pyxel.text(2, pyxel.height - 8,  "* Cham",  10)
        else:
            pyxel.text(2, pyxel.height - 32, "~ Ghost", 11)
            pyxel.text(2, pyxel.height - 24, "! Sab",   10)
            pyxel.text(2, pyxel.height - 16, "+ Regen", 11)
            pyxel.text(2, pyxel.height - 8,  "* Cham",  10)

        sel = self.controller._selected_tower
        if sel is not None and sel in self.model.towers:
            dirname = sel.direction.value.upper()
            txt = f"SEL DIR:{dirname}"
            pyxel.text(sw - len(txt) * 4 - 2, pyxel.height - 8, txt, 7)

        self._draw_music_button()

    def _draw_music_button(self) -> None:
        music_on = self.controller._bgm_playing or self.controller._menu_bgm_playing
        state_text = "[ON]" if music_on else "[OFF]"
        display = f"MUSIC <M>: {state_text}"
        sw = pyxel.width
        color = 11 if music_on else 8
        pyxel.text(sw // 2 - len(display) * 2 + 45, 2, display, color)
