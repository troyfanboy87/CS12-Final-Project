import math
import pyxel

from .model import (
    Chameleon,
    COLOR_ORDER,
    COLOR_PALETTE,
    DIRECTION_VECTORS,
    ENEMY_RADIUS,
    GameState,
    Regenerator,
)


class GameView:

    def __init__(self, controller):
        self.controller = controller

        import pathlib
        self._sprites_loaded = False
        _res = pathlib.Path(__file__).resolve().parent.parent / "enemies.pyxres"
        if _res.exists():
            try:
                pyxel.load(str(_res), excl_images=False,
                           excl_tilemaps=True, excl_sounds=True,
                           excl_musics=True)
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
        elif state == GameState.CHOOSE:
            self._draw_play_field()
            self._draw_choose_overlay()
            self._draw_hud()
        elif state == GameState.BUILDING:
            self._draw_play_field()
            self._draw_build_overlay()
            self._draw_hud()
        elif state == GameState.PAUSED:
            self._draw_play_field()
            self._draw_pause()
        elif state == GameState.LEADERBOARD:
            self._draw_leaderboard()
        elif state in (GameState.GAME_OVER, GameState.WIN):
            self._draw_game_over()

    def _draw_menu(self) -> None:
        sw, sh = pyxel.width, pyxel.height

        title = "ZUMA: TOWER DEFENSE"
        x = sw // 2 - len(title) * 2
        pyxel.text(x + 1, sh // 3 + 1, title, 1)
        pyxel.text(x,     sh // 3,     title, 10)

        if (pyxel.frame_count // 15) % 2 == 0:
            prompt = "Click or SPACE to start"
            pyxel.text(sw // 2 - len(prompt) * 2, sh // 2 + 8, prompt, 7)

        help_lines = [
            "Mouse: aim & shoot",
            "1..5 / Wheel: change ammo color",
            "B: enter build phase after round",
            "T (build): place tower",
            "U (build): upgrade tower",
            "C (build): cycle tower color",
            "RClick / TAB: select tower",
            "WASD: aim selected tower",
            "SPACE: next round",
            "+ = Regenerator (heals over distance)",
            "* = Chameleon (changes color!)",
            "Q: quit   R: restart on game over",
        ]
        for i, line in enumerate(help_lines):
            pyxel.text(8, sh - 8 * (len(help_lines) - i + 1), line, 6)

        options = [
            "1 - Campaign Mode",
            "2 - Endless Mode", 
            "L - Leaderboard",
            "M - Toggle Music"
        ]

        for i, opt in enumerate(options):
            pyxel.text(sw // 2 - len(opt) * 2, sh // 2 -30 + i * 10, opt, 7)


    def _draw_play_field(self) -> None:
        self._draw_grid()
        self._draw_paths()
        self._draw_towers()
        self._draw_enemies()
        self._draw_bullets()
        self._draw_shooter()

    def _draw_choose_overlay(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        msgs = [
            f"Round {self.model.current_round} cleared!",
            "",
            "B - Build towers",
            "SPACE - Next round",
        ]
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
        self._draw_cursor_cell()

        sw, sh = pyxel.width, pyxel.height
        cost_tower   = self.model.settings["tower_cost"]
        cost_upgrade = self.model.settings["tower_upgrade_cost"]

        msgs = [
            f"BUILD MODE — EXP: {self.model.exp}",
            f"T: place tower ({cost_tower} EXP)",
            f"U: upgrade selected ({cost_upgrade} EXP)",
            "C: cycle tower color",
            "RClick/TAB: select   WASD: aim",
            "SPACE: start next round",
        ]
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
            color = 10 if i == 0 else 7
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
        pyxel.rect(0, sh // 2 - 16, sw, 32, 0)
        msg = "GAME OVER"
        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 4, msg, 8)
        sub = "Press R to restart"
        pyxel.text(sw // 2 - len(sub) * 2, sh // 2 + 6, sub, 7)
        name = self.model.player_name
        pyxel.text(sw // 2 - 20, sh // 2 + 20, f"Name: {name}", 7)
        pyxel.text(sw//2 - 30, sh//2 + 30, "ENTER to submit", 6)

    def _draw_win(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        pyxel.rect(0, sh // 2 - 16, sw, 32, 0)

        if self.model.state == GameState.WIN:
            msg = "YOU WIN!"
            color = 11
        else:
            msg = "GAME OVER"
            color = 8

        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 4, msg, color)

        name = self.model.player_name
        pyxel.text(sw // 2 - 40, sh // 2, f"Name: {name}", 7)

        pyxel.text(sw // 2 - 60, sh // 2 + 10, "ENTER to submit score", 6)
        pyxel.text(sw // 2 - 50, sh // 2 + 20, "R to restart", 6)

    def _draw_pause(self):
        sw, sh = pyxel.width, pyxel.height

        for y in range(0, sh, 2):
            for x in range(0, sw, 2):
                pyxel.pset(x, y, 1)  # dark pixels

        panel_w = 100
        panel_h = 40
        px = sw // 2 - panel_w // 2
        py = sh // 2 - panel_h // 2

        pyxel.rect(px, py, panel_w, panel_h, 0)
        pyxel.rectb(px, py, panel_w, panel_h, 7)

        pyxel.text(sw // 2 - len("PAUSED") * 2, py + 8, "PAUSED", 7)

        pyxel.text(sw // 2 - 30, py + 20, "P - Resume", 6)
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
        for path in self.model.paths:
            wp = path.waypoints
            for i in range(1, len(wp)):
                x0, y0 = wp[i - 1]
                x1, y1 = wp[i]
                for dx, dy in [(-1, 0), (0, 0), (1, 0), (0, -1), (0, 1)]:
                    pyxel.line(x0 + dx, y0 + dy, x1 + dx, y1 + dy, 5)

            for tunnel in path.tunnels:
                self._draw_tunnel(path, tunnel)

            sx, sy = wp[0]
            ex, ey = wp[-1]
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

    def _draw_bullets(self) -> None:
        for b in self.model.bullets:
            if not b.alive:
                continue
            color_idx = COLOR_PALETTE[b.color]
            pyxel.circ(int(b.x), int(b.y), 2, color_idx)
            pyxel.pset(int(b.x), int(b.y), 7)

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

            if t.selected:
                pyxel.rectb(x - 7, y - 7, 14, 14, 10)

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

    def _draw_hud(self) -> None:
        sw = pyxel.width
        pyxel.rect(0, 0, sw, 9, 1)
        pyxel.text(2,  2, f"LIVES:{self.model.lives}", 8)
        pyxel.text(40, 2, f"EXP:{self.model.exp}",     10)
        pyxel.text(80, 2,
                   f"R:{self.model.current_round}/{self.model.total_rounds}", 7)

        s = self.model.shooter
        label = f"AMMO:{s.color.upper()}"
        pyxel.text(sw - len(label) * 4 - 2, 2, label, COLOR_PALETTE[s.color])

        pyxel.text(2, pyxel.height - 16, "+ Regen", 11)
        pyxel.text(2, pyxel.height - 8,  "* Cham",  10)

        sel = self.controller._selected_tower
        if sel is not None and sel in self.model.towers:
            dirname = sel.direction.value.upper()
            txt = f"SEL DIR:{dirname}"
            pyxel.text(sw - len(txt) * 4 - 2, pyxel.height - 8, txt, 7)
