"""
View layer — all Pyxel drawing.

Pyxel uses an immediate-mode API: every frame we redraw the whole scene from
scratch. There is no scene graph or double-buffer for us to manage. This
makes the View "stateless" — it has no internal data beyond a reference to
the controller (so it can find the current model after restart).

Organized top-to-bottom by what gets drawn:

    1. Pyxel entry point      — draw() dispatches by state
    2. Top-level screens      — menu, play field, build overlay, game over
    3. World rendering        — paths (incl. tunnels), enemies, bullets, shooter, towers
    4. HUD and overlays       — top bar, build prompt, game-over banner
"""

import math
import pyxel

from .model import (
    COLOR_PALETTE,
    DIRECTION_VECTORS,
    ENEMY_RADIUS,
    GameState,
)


class GameView:

    def __init__(self, controller):
        # Hold the controller, NOT the model directly.
        # The controller swaps its `.model` on restart; reading through the
        # controller each frame keeps us pinned to the live model.
        # (Direct-reference caused a "frozen-after-restart" bug previously.)
        self.controller = controller

    @property
    def model(self):
        return self.controller.model

    # =======================================================================
    # 1. Pyxel entry point
    # =======================================================================

    def draw(self) -> None:
        pyxel.cls(0)  # 0 = black

        state = self.model.state
        if state == GameState.MENU:
            self._draw_menu()
        elif state == GameState.PLAYING:
            self._draw_play_field()
            self._draw_hud()
        elif state == GameState.BUILDING:
            self._draw_play_field()
            self._draw_build_overlay()
            self._draw_hud()
        elif state == GameState.GAME_OVER:
            self._draw_play_field()
            self._draw_game_over()
        elif state == GameState.WIN:
            self._draw_play_field()
            self._draw_win()

    # =======================================================================
    # 2. Top-level screens
    # =======================================================================

    def _draw_menu(self) -> None:
        sw, sh = pyxel.width, pyxel.height

        title = "ZUMA: TOWER DEFENSE"
        x = sw // 2 - len(title) * 2
        pyxel.text(x + 1, sh // 3 + 1, title, 1)   # dark shadow
        pyxel.text(x,     sh // 3,     title, 10)  # yellow

        # Blinking prompt — uses frame_count for timing.
        if (pyxel.frame_count // 15) % 2 == 0:
            prompt = "Click or SPACE to start"
            pyxel.text(sw // 2 - len(prompt) * 2, sh // 2 + 8, prompt, 7)

        help_lines = [
            "Mouse: aim & shoot",
            "1..4 / Wheel: change ammo color",
            "T (build phase): place tower",
            "U (build phase): upgrade tower",
            "RClick / TAB: select tower",
            "WASD: aim selected tower",
            "SPACE (build phase): next round",
            "Q: quit   R: restart on game over",
        ]
        for i, line in enumerate(help_lines):
            pyxel.text(8, sh - 8 * (len(help_lines) - i + 1), line, 6)

    def _draw_play_field(self) -> None:
        # Grid first, behind everything else, so the path/enemies/bullets
        # overdraw it. Hidden on the menu screen — see draw() dispatch.
        self._draw_grid()
        self._draw_paths()
        self._draw_towers()
        self._draw_enemies()
        self._draw_bullets()
        self._draw_shooter()

    def _draw_build_overlay(self) -> None:
        # Cursor cell highlight first — sits behind the text banner so
        # the prompt remains readable.
        self._draw_cursor_cell()

        sw, sh = pyxel.width, pyxel.height
        cost_tower   = self.model.settings["tower_cost"]
        cost_upgrade = self.model.settings["tower_upgrade_cost"]
        msgs = [
            f"Round {self.model.current_round} cleared!",
            f"T: tower ({cost_tower} EXP)  U: upgrade ({cost_upgrade} EXP)",
            "RClick/TAB: select tower   WASD: aim it",
            "SPACE: start next round",
        ]
        for i, m in enumerate(msgs):
            x = sw // 2 - len(m) * 2
            y = sh // 2 - 16 + i * 8
            pyxel.text(x + 1, y + 1, m, 0)
            pyxel.text(x,     y,     m, 7)

    def _draw_game_over(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        pyxel.rect(0, sh // 2 - 16, sw, 32, 0)
        msg = "GAME OVER"
        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 4, msg, 8)
        sub = "Press R to restart"
        pyxel.text(sw // 2 - len(sub) * 2, sh // 2 + 6, sub, 7)

    def _draw_win(self) -> None:
        sw, sh = pyxel.width, pyxel.height
        pyxel.rect(0, sh // 2 - 16, sw, 32, 0)
        msg = "YOU WIN!"
        pyxel.text(sw // 2 - len(msg) * 2, sh // 2 - 4, msg, 11)
        sub = "Press R to play again"
        pyxel.text(sw // 2 - len(sub) * 2, sh // 2 + 6, sub, 7)

    # =======================================================================
    # 3. World rendering
    # =======================================================================

    def _draw_grid(self) -> None:
        """
        Draws a subtle dot at every cell intersection.

        The grid is the underlying spatial unit the spec talks about ("the
        stage consists of cells"; "tunnels are 2..5 cells long"). Making it
        visible helps the player line up tower placement and read the
        relationship between enemy speed and cell size.

        Implementation: a single pset (one pixel) at each (x, y) where both
        x and y are multiples of cell_size. Cheap and unobtrusive — Pyxel
        only has 16 colors and the path already uses gray (5), so we use
        navy (1) for the dots to stay out of the way visually.
        """
        cs = self.model.settings["cell_size"]
        sw = pyxel.width
        sh = pyxel.height
        # Skip the top HUD strip (9 px) so dots don't punch through the bar.
        for y in range(0, sh, cs):
            if y < 9:
                continue
            for x in range(0, sw, cs):
                pyxel.pset(x, y, 1)

    def _draw_cursor_cell(self) -> None:
        """
        BUILDING state only: outline the cell under the cursor so the player
        sees exactly where a tower will land if they press T. Colored by
        whether the spot is currently legal for tower placement.

        We delegate BOTH the cell-center calculation AND the legality check
        to the controller. That guarantees the highlight always matches what
        will actually happen when the player presses T — no drift between
        what's drawn and what's placed.
        """
        cs = self.model.settings["cell_size"]
        # Ask the controller where the snapped cell center is, then derive
        # the cell's top-left corner for the rectb outline.
        cx, cy = self.controller._cursor_cell_center()
        cell_x = int(cx - cs / 2)
        cell_y = int(cy - cs / 2)
        legal = self.controller._is_legal_tower_spot(cx, cy)
        color = 11 if legal else 8   # green if legal, red if not
        pyxel.rectb(cell_x, cell_y, cs, cs, color)

    def _draw_paths(self) -> None:
        for path in self.model.paths:
            wp = path.waypoints
            # Pyxel has no line thickness — stack parallels for a thick look.
            for i in range(1, len(wp)):
                x0, y0 = wp[i - 1]
                x1, y1 = wp[i]
                for dx, dy in [(-1, 0), (0, 0), (1, 0), (0, -1), (0, 1)]:
                    pyxel.line(x0 + dx, y0 + dy, x1 + dx, y1 + dy, 5)

            # Phase 4b: tunnels drawn as dark covered segments along the path.
            for tunnel in path.tunnels:
                self._draw_tunnel(path, tunnel)

            # Endpoints: green = entry, red = exit (where lives are lost).
            sx, sy = wp[0]
            ex, ey = wp[-1]
            pyxel.circb(sx, sy, 3, 11)
            pyxel.circb(ex, ey, 3, 8)

    def _draw_tunnel(self, path, tunnel) -> None:
        """Sample along the tunnel interval, paint a "covered" band."""
        steps = max(2, int(tunnel.length // 2))
        for i in range(steps + 1):
            p = tunnel.start + (tunnel.length * i / steps)
            x, y = path.position_at(p)
            pyxel.rect(int(x) - 4, int(y) - 4, 9, 9, 1)    # dark fill
            pyxel.rectb(int(x) - 4, int(y) - 4, 9, 9, 13)  # gray border
        # Bracket markers at the entry/exit.
        sx, sy = path.position_at(tunnel.start)
        ex, ey = path.position_at(tunnel.end)
        pyxel.text(int(sx) - 6, int(sy) - 3, "[", 13)
        pyxel.text(int(ex) - 0, int(ey) - 3, "]", 13)

    def _draw_enemies(self) -> None:
        for e in self.model.enemies:
            if not e.alive:
                continue
            color_idx = COLOR_PALETTE[e.color]
            # Tunneled -> gray ring so player can see "currently safe."
            if e.in_tunnel:
                pyxel.circ(int(e.x), int(e.y), ENEMY_RADIUS, color_idx)
                pyxel.circb(int(e.x), int(e.y), ENEMY_RADIUS, 13)
            else:
                pyxel.circ(int(e.x), int(e.y), ENEMY_RADIUS, color_idx)
                pyxel.circb(int(e.x), int(e.y), ENEMY_RADIUS, 0)
            # HP bar when damaged
            if e.hp < e.max_hp:
                bar_w = 10
                filled = int(bar_w * e.hp / e.max_hp)
                pyxel.rect(int(e.x) - 5, int(e.y) - 9, bar_w, 1, 0)
                pyxel.rect(int(e.x) - 5, int(e.y) - 9, filled, 1, 11)

    def _draw_bullets(self) -> None:
        for b in self.model.bullets:
            if not b.alive:
                continue
            color_idx = COLOR_PALETTE[b.color]
            pyxel.circ(int(b.x), int(b.y), 2, color_idx)
            pyxel.pset(int(b.x), int(b.y), 7)  # white core

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

            # Selection halo so player sees which tower WASD controls.
            if t.selected:
                pyxel.rectb(x - 7, y - 7, 14, 14, 10)  # yellow

            pyxel.rect(x - 5, y - 5, 10, 10, base_color)
            pyxel.rectb(x - 5, y - 5, 10, 10, 0)

            # Phase 4: barrel points in t.direction.
            dx, dy = DIRECTION_VECTORS[t.direction]
            bx = x + dx * 8
            by = y + dy * 8
            pyxel.line(x, y, bx, by, 6)
            pyxel.pset(bx, by, 7)

            if t.upgraded and t.color_b is not None:
                second = COLOR_PALETTE[t.color_b]
                pyxel.circ(x + 3, y - 7, 1, second)
                pyxel.text(x - 2, y - 2, "+", 7)

    # =======================================================================
    # 4. HUD
    # =======================================================================

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

        # Selected-tower info on the bottom right.
        sel = self.controller._selected_tower  # ok: View reads, doesn't mutate
        if sel is not None and sel in self.model.towers:
            dirname = sel.direction.value.upper()
            txt = f"SEL DIR:{dirname}"
            pyxel.text(sw - len(txt) * 4 - 2, pyxel.height - 8, txt, 7)
