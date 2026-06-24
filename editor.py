"""
editor.py — MRA visual map editor (Pygame).

Two integrated modes:
  WORLD  — place/move/remove .SEC tiles on the MP grid across floors (a/b/c = 45/50/55),
           '50' cartographer map as backdrop, area labels, stair badges. Export placement JSON.
  SECTOR — SCB-style cell editor: paint terrain / walls / doors / objects per cell, save .SEC.

Run:   python editor.py            (interactive)
       python editor.py --smoke    (headless init + one frame each mode, for testing)
"""
import os, sys, json, glob
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
if "--smoke" in sys.argv:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
from secio import Sector, PLAY
from render import render_sector
import render
import art
import scbdata
import sectext

HERE = ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MAPS = os.path.join(DATA, "coordinate-maps")
AREA = os.path.join(DATA, "area-maps")
BUNDLE = os.path.join(DATA, "sectors.sectext")
EDITED = os.path.join(HERE, "edited")
LAYOUT_JSON = os.path.join(DATA, "world_layout_full.json")
WORLD_MAP_JSON = os.path.join(DATA, "world_map.json")
BACKDROP_PNG = os.path.join(DATA, "ods_50_world.png")
PLACEMENT_OUT = os.path.join(HERE, "placement.json")

GW, GH = 19, 17                      # world grid cells (MP 10..100 / 5)
FLOORS = [45, 50, 55]
FLOOR_LABEL = {45: "45 (a/lower)", 50: "50 (b/ground)", 55: "55 (c/upper)"}
LAYER_OF = {45: "a", 50: "b", 55: "c"}
PANEL_W = 330
BG = (24, 24, 30)
PANEL_BG = (34, 34, 42)
ACCENT = (90, 160, 230)
WHITE = (235, 235, 240)
GREY = (150, 150, 160)


def discover_sectors():
    """name(lower) -> Sector. Prefer the single .sectext bundle; else scan loose .SEC dirs."""
    if os.path.exists(BUNDLE):
        return sectext.load_bundle(BUNDLE)
    out = {}
    for p in glob.glob(os.path.join(MAPS, "*.SEC")):
        out.setdefault(os.path.splitext(os.path.basename(p))[0].lower(), Sector.load(p))
    for root, _, files in os.walk(AREA):
        for f in files:
            if f.lower().endswith(".sec"):
                out.setdefault(os.path.splitext(f)[0].lower(), Sector.load(os.path.join(root, f)))
    return out


def load_placement():
    """floor_z -> {(gx,gy): sector_name}, from world_map.json."""
    pl = {z: {} for z in FLOORS}
    try:
        wm = json.load(open(WORLD_MAP_JSON))
    except Exception:
        return pl
    for s in wm.get("sectors", {}).values():
        if s.get("mp_x") and s.get("mp_y"):
            z = {"a": 45, "b": 50, "c": 55}.get(s.get("layer"), 50)
            gx, gy = (s["mp_x"] - 10) // 5, (s["mp_y"] - 10) // 5
            if 0 <= gx < GW and 0 <= gy < GH:
                pl[z][(gx, gy)] = os.path.splitext(s["filename"])[0]
    return pl


def load_labels():
    out = {}
    try:
        for k, nm in json.load(open(LAYOUT_JSON)).items():
            mx, my = map(int, k.split(","))
            out[((mx - 10) // 5, (my - 10) // 5)] = nm
    except Exception:
        pass
    return out


class App:
    def __init__(self):
        pygame.init()
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = 1440, 900
        self.W, self.H = min(1400, dw - 80), min(860, dh - 140)   # fit on-screen (title bar visible)
        self.screen = pygame.display.set_mode((self.W, self.H), pygame.RESIZABLE)
        pygame.display.set_caption("MRA Map Editor")
        self.font = pygame.font.SysFont("consolas", 14)
        self.bigfont = pygame.font.SysFont("consolas", 18, bold=True)
        self.clock = pygame.time.Clock()

        self.sectors = discover_sectors()
        self.placement = load_placement()
        self.labels = load_labels()
        self.sec_cache = {}             # name -> Sector
        self.thumb_cache = {}           # (name, px) -> Surface

        # world view state
        self.mode = "world"
        self.floor = 50
        self.cell_px = 46
        self.cam = [40, 60]             # top-left pixel of grid origin
        self.sel_tile = None            # palette-selected sector name to place
        self.sel_cell = None            # (gx,gy) selected on grid
        self.show_backdrop = False
        self.backdrop = None
        self.pal_scroll = 0
        self.pal_filter = ""
        self.typing_filter = False
        self.status = "WORLD mode. Click a palette tile then a cell to place. Double-click a tile to edit. H=help"

        # sector editor state
        self.cur = None                 # Sector being edited
        self.cur_name = None
        self.tool_cat = "terrain"
        self.sel_type = {"terrain": 20, "wall": 1, "door": 1, "object": 1}
        self.edge = "N"
        self.sec_scale = 22
        self.sec_cam = [20.0, 60.0]
        self._sec_render = None
        self._sec_render_scale = None
        self.dirty = False
        self.type_scroll = 0
        self.cat_rects = []
        self.type_rowh = 20
        self.type_ids = []

        os.makedirs(EDITED, exist_ok=True)

    # ---------- sector / thumbnail helpers ----------
    def get_sector(self, name):
        if name in self.sec_cache:
            return self.sec_cache[name]
        # prefer an already-edited copy on disk; otherwise the decoded bundle sector
        ep = os.path.join(EDITED, name + ".SEC")
        sec = Sector.load(ep) if os.path.exists(ep) else self.sectors.get(name.lower())
        self.sec_cache[name] = sec
        return sec

    def thumb(self, name, px):
        key = (name, px)
        if key in self.thumb_cache:
            return self.thumb_cache[key]
        sec = self.get_sector(name)
        if sec is None:
            surf = pygame.Surface((px, px)); surf.fill((60, 30, 30))
        else:
            base = render_sector(sec, scale=max(2, px // 16), boundary=True)
            surf = pygame.transform.smoothscale(base, (px, px))
        self.thumb_cache[key] = surf
        return surf

    def invalidate(self, name):
        for k in [k for k in self.thumb_cache if k[0] == name]:
            del self.thumb_cache[k]
        self.sec_cache.pop(name, None)

    # ================= WORLD MODE =================
    def world_cell_at(self, mx, my):
        if mx >= self.W - PANEL_W:
            return None
        gx = int((mx - self.cam[0]) // self.cell_px)
        gy = int((my - self.cam[1]) // self.cell_px)
        if 0 <= gx < GW and 0 <= gy < GH:
            return (gx, gy)
        return None

    def draw_world(self):
        self.screen.fill(BG)
        px = self.cell_px
        # backdrop (loose reference, scaled to the grid box)
        if self.show_backdrop and self.backdrop:
            bw = GW * px; bh = GH * px
            self.screen.blit(pygame.transform.smoothscale(self.backdrop, (bw, bh)), (self.cam[0], self.cam[1]))
        pl = self.placement[self.floor]
        for gy in range(GH):
            for gx in range(GW):
                x = self.cam[0] + gx * px; y = self.cam[1] + gy * px
                if x > self.W - PANEL_W or y > self.H or x + px < 0 or y + px < 0:
                    continue
                rect = pygame.Rect(x, y, px, px)
                name = pl.get((gx, gy))
                if name:
                    self.screen.blit(self.thumb(name, px), (x, y))
                    sec = self.get_sector(name)
                    if sec and sec.has_stairs():
                        pygame.draw.circle(self.screen, (60, 230, 230), (x + px - 7, y + 7), 4)
                elif not self.show_backdrop:
                    lbl = self.labels.get((gx, gy), "")
                    if lbl and lbl != "Void":
                        pygame.draw.rect(self.screen, (30, 30, 38), rect)
                pygame.draw.rect(self.screen, (54, 54, 64), rect, 1)
                lbl = self.labels.get((gx, gy), "")
                if lbl and lbl != "Void" and px >= 40:
                    t = self.font.render(lbl[:px // 7], True, (255, 255, 170))
                    self.screen.blit(t, (x + 2, y + px - 15))
        if self.sel_cell:
            gx, gy = self.sel_cell
            pygame.draw.rect(self.screen, ACCENT, (self.cam[0] + gx * px, self.cam[1] + gy * px, px, px), 3)
        self.draw_world_panel()
        self.draw_status()

    def draw_world_panel(self):
        x0 = self.W - PANEL_W
        pygame.draw.rect(self.screen, PANEL_BG, (x0, 0, PANEL_W, self.H))
        y = 8
        # floor tabs
        for i, z in enumerate(FLOORS):
            r = pygame.Rect(x0 + 8 + i * 104, y, 100, 26)
            pygame.draw.rect(self.screen, ACCENT if z == self.floor else (60, 60, 72), r)
            self.screen.blit(self.font.render(FLOOR_LABEL[z], True, WHITE), (r.x + 5, r.y + 6))
        y += 34
        self.screen.blit(self.font.render(f"backdrop[B]:{'on' if self.show_backdrop else 'off'}  "
                                          f"placed:{len(self.placement[self.floor])}", True, GREY), (x0 + 8, y))
        y += 22
        self.screen.blit(self.font.render(f"filter[/]: {self.pal_filter}_" if self.typing_filter
                                          else f"filter[/]: {self.pal_filter}", True, WHITE), (x0 + 8, y))
        y += 22
        sel = self.sel_tile or "(none)"
        self.screen.blit(self.font.render("place: " + sel[:34], True, (170, 230, 170)), (x0 + 8, y))
        y += 24
        # palette grid of sector thumbnails
        names = [n for n in sorted(self.sectors) if self.pal_filter.lower() in n]
        self.pal_top = y
        cols = 4; tp = (PANEL_W - 16) // cols
        self.pal_cols = cols; self.pal_tp = tp; self.pal_names = names
        start = self.pal_scroll
        i = 0
        while True:
            idx = start + i
            if idx >= len(names):
                break
            gx = i % cols; gy = i // cols
            tx = x0 + 8 + gx * tp; ty = y + gy * (tp + 14)
            if ty > self.H - 20:
                break
            nm = names[idx]
            self.screen.blit(self.thumb(nm, tp - 4), (tx, ty))
            if nm == self.sel_tile:
                pygame.draw.rect(self.screen, ACCENT, (tx, ty, tp - 4, tp - 4), 2)
            self.screen.blit(self.font.render(nm[:tp // 7], True, GREY), (tx, ty + tp - 4))
            i += 1
        self.pal_visible = i

    def world_event(self, e):
        px = self.cell_px
        if e.type == pygame.KEYDOWN:
            if self.typing_filter:
                if e.key == pygame.K_RETURN or e.key == pygame.K_ESCAPE:
                    self.typing_filter = False
                elif e.key == pygame.K_BACKSPACE:
                    self.pal_filter = self.pal_filter[:-1]
                elif e.unicode and e.unicode.isprintable():
                    self.pal_filter += e.unicode.lower()
                return
            if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.floor = FLOORS[e.key - pygame.K_1]
            elif e.key == pygame.K_b:
                self.show_backdrop = not self.show_backdrop
                if self.show_backdrop and self.backdrop is None and os.path.exists(BACKDROP_PNG):
                    self.backdrop = pygame.image.load(BACKDROP_PNG).convert()
            elif e.key == pygame.K_SLASH:
                self.typing_filter = True; self.pal_scroll = 0
            elif e.key in (pygame.K_DELETE, pygame.K_x) and self.sel_cell:
                self.placement[self.floor].pop(self.sel_cell, None)
            elif e.key == pygame.K_LEFT: self.cam[0] += 60
            elif e.key == pygame.K_RIGHT: self.cam[0] -= 60
            elif e.key == pygame.K_UP: self.cam[1] += 60
            elif e.key == pygame.K_DOWN: self.cam[1] -= 60
            elif e.key == pygame.K_e and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.export_placement()
            elif e.key == pygame.K_h:
                self.status = ("[1/2/3]floor  [B]backdrop  [/]filter  click tile+cell=place  click=select  "
                               "DBLCLICK=edit cells  [X/Del]remove  wheel=zoom(center)  mid-drag/arrows=pan  [Ctrl+E]export")
        elif e.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if mx >= self.W - PANEL_W:
                self.pal_scroll = max(0, self.pal_scroll - e.y * self.pal_cols)
            else:
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_CTRL:                         # Ctrl+wheel = zoom at cursor
                    old = self.cell_px
                    self.cell_px = max(8, min(512, old + e.y * max(2, old // 6)))
                    f = self.cell_px / old
                    self.cam[0] = mx - (mx - self.cam[0]) * f
                    self.cam[1] = my - (my - self.cam[1]) * f
                elif mods & pygame.KMOD_SHIFT:                      # Shift+wheel = pan horizontal
                    self.cam[0] += e.y * 60
                else:                                              # wheel = pan (vert + horiz)
                    self.cam[0] += e.x * 60
                    self.cam[1] += e.y * 60
        elif e.type == pygame.MOUSEMOTION and e.buttons[1]:        # middle-drag = pan
            self.cam[0] += e.rel[0]; self.cam[1] += e.rel[1]
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if mx >= self.W - PANEL_W:
                self.click_palette(mx, my)
            else:
                cell = self.world_cell_at(mx, my)
                if cell is None:
                    return
                now = pygame.time.get_ticks()
                dbl = (cell == getattr(self, "_last_cell", None) and now - getattr(self, "_last_click", 0) < 350)
                self._last_cell, self._last_click = cell, now
                occupied = self.placement[self.floor].get(cell)
                if dbl and occupied:
                    self.enter_sector(occupied)
                elif self.sel_tile:
                    self.placement[self.floor][cell] = self.sel_tile
                    self.sel_cell = cell
                else:
                    self.sel_cell = cell
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            cell = self.world_cell_at(*e.pos)
            if cell:
                self.placement[self.floor].pop(cell, None)

    def click_palette(self, mx, my):
        if my < self.pal_top:
            return
        rel = my - self.pal_top
        col = (mx - (self.W - PANEL_W) - 8) // self.pal_tp
        row = rel // (self.pal_tp + 14)
        if 0 <= col < self.pal_cols:
            idx = self.pal_scroll + row * self.pal_cols + col
            if 0 <= idx < len(self.pal_names):
                self.sel_tile = self.pal_names[idx]

    def export_placement(self):
        # list of {filename, mp_x, mp_y, mp_z, layer, place_name}
        out = []
        for z in FLOORS:
            for (gx, gy), name in sorted(self.placement[z].items()):
                out.append({"filename": name + ".SEC", "mp_x": gx * 5 + 10, "mp_y": gy * 5 + 10,
                            "mp_z": z, "layer": LAYER_OF[z],
                            "place_name": self.labels.get((gx, gy))})
        json.dump({"_meta": "exported by MRA map editor", "sectors": out}, open(PLACEMENT_OUT, "w"), indent=1)
        self.status = f"exported {len(out)} placements -> {os.path.relpath(PLACEMENT_OUT, ROOT)}"

    # ================= SECTOR MODE =================
    def enter_sector(self, name):
        sec = self.get_sector(name)
        if sec is None:
            self.status = f"cannot load sector {name}"; return
        self.cur = sec.copy(); self.cur_name = name; self.dirty = False
        self.mode = "sector"
        self.sec_cam = [20.0, 60.0]; self.sec_scale = 22; self._sec_render = None
        self.status = (f"SECTOR {name}: click T/W/D/O + a type (icons, right), edge=arrows, "
                       f"LMB paint / RMB erase, wheel=zoom@cursor, mid-drag=pan, Ctrl+S save, Esc back")

    def sec_cell_at(self, mx, my):
        if mx >= self.W - PANEL_W:
            return None
        gx = int((mx - self.sec_cam[0]) // self.sec_scale)
        gy = int((my - self.sec_cam[1]) // self.sec_scale)
        if 0 <= gx < PLAY and 0 <= gy < PLAY:
            return (gx, gy)
        return None

    def draw_sector(self):
        self.screen.fill(BG)
        sc = self.sec_scale
        ox, oy = int(self.sec_cam[0]), int(self.sec_cam[1])
        if self._sec_render is None or self._sec_render_scale != sc:
            self._sec_render = render_sector(self.cur, scale=sc, boundary=True)
            self._sec_render_scale = sc
        self.screen.blit(self._sec_render, (ox, oy))
        if sc >= 14:                                   # grid overlay only when cells are big enough
            for i in range(PLAY + 1):
                pygame.draw.line(self.screen, (50, 50, 60), (ox + i * sc, oy), (ox + i * sc, oy + PLAY * sc))
                pygame.draw.line(self.screen, (50, 50, 60), (ox, oy + i * sc), (ox + PLAY * sc, oy + i * sc))
        pygame.draw.rect(self.screen, (16, 16, 20), (0, 0, self.W - PANEL_W, 38))
        self.screen.blit(self.bigfont.render(f"SECTOR  {self.cur_name}{'  *' if self.dirty else ''}", True, WHITE), (20, 10))
        self.draw_sector_panel()
        self.draw_status()

    def type_icon(self, cat, tid, px):
        """small preview Surface for a palette type."""
        if cat == "terrain":
            s = art.terrain_surface(tid, px) if render.USE_ART else None
            if s is not None:
                return s
            surf = pygame.Surface((px, px)); surf.fill(render.tcolor(tid)); return surf
        if cat == "object":
            surf = pygame.Surface((px, px)); surf.fill((16, 16, 24))
            s = art.object_surface(tid, px) if render.USE_ART else None
            if s is not None:
                surf.blit(s, (0, 0))
            elif tid:
                m = px // 3
                surf.fill(render.TELE if tid in (1, 2, 3, 4) else render.OBJ, (m, m, m, m))
            return surf
        # wall / door — real sprite (N edge), color swatch fallback
        surf = pygame.Surface((px, px)); surf.fill((30, 30, 38))
        if tid:
            sp = None
            if render.USE_ART:
                sp = art.wall_surface(tid, "N", px) if cat == "wall" else art.door_surface(tid, "N", px)
            if sp is not None:
                surf.blit(sp, (0, 0))
            else:
                surf.fill(render.WALL if cat == "wall" else render.DOOR, (0, 0, px, max(3, px // 4)))
        return surf

    def draw_sector_panel(self):
        x0 = self.W - PANEL_W
        pygame.draw.rect(self.screen, PANEL_BG, (x0, 0, PANEL_W, self.H))
        y = 10
        cats = [("terrain", "Terrain [T]"), ("wall", "Wall [W]"), ("door", "Door [D]"), ("object", "Object [O]")]
        self.cat_rects = []
        for i, (c, lab) in enumerate(cats):
            r = pygame.Rect(x0 + 8 + (i % 2) * 158, y + (i // 2) * 28, 150, 24)
            pygame.draw.rect(self.screen, ACCENT if c == self.tool_cat else (60, 60, 72), r)
            self.screen.blit(self.font.render(lab, True, WHITE), (r.x + 6, r.y + 5))
            self.cat_rects.append((r, c))
        y += 62
        if self.tool_cat in ("wall", "door"):
            self.screen.blit(self.font.render(f"edge [arrows / NESW]: {self.edge}", True, (170, 230, 170)), (x0 + 8, y)); y += 20
        tbl = {"terrain": scbdata.TERRAIN, "wall": scbdata.WALL, "door": scbdata.DOOR, "object": scbdata.OBJECT}[self.tool_cat]
        ids = sorted(tbl)
        self.type_top = y; self.type_ids = ids; self.type_rowh = 36
        ic = 32
        self.type_scroll = max(0, min(self.type_scroll, max(0, len(ids) - 1)))
        for i, tid in enumerate(ids[self.type_scroll:]):
            ty = y + i * self.type_rowh
            if ty > self.H - 38:
                break
            selected = self.sel_type[self.tool_cat] == tid
            if selected:
                pygame.draw.rect(self.screen, (60, 80, 110), (x0 + 2, ty, PANEL_W - 6, self.type_rowh - 2))
            self.screen.blit(self.type_icon(self.tool_cat, tid, ic), (x0 + 6, ty + 2))
            self.screen.blit(self.font.render(f"{tid:3} {tbl[tid]}", True, WHITE if selected else GREY),
                             (x0 + 6 + ic + 8, ty + 12))

    def sector_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.invalidate(self.cur_name); self.mode = "world"; self.thumb_cache.clear()
                return
            elif e.key == pygame.K_t: self.tool_cat = "terrain"; self.type_scroll = 0
            elif e.key == pygame.K_w: self.tool_cat = "wall"; self.type_scroll = 0
            elif e.key == pygame.K_d: self.tool_cat = "door"; self.type_scroll = 0
            elif e.key == pygame.K_o: self.tool_cat = "object"; self.type_scroll = 0
            elif e.key == pygame.K_n: self.edge = "N"
            elif e.key == pygame.K_UP: self.edge = "N"
            elif e.key == pygame.K_DOWN: self.edge = "S"
            elif e.key == pygame.K_LEFT: self.edge = "W"
            elif e.key == pygame.K_RIGHT: self.edge = "E"
            elif e.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.save_sector()
            elif e.key in (pygame.K_EQUALS, pygame.K_PLUS): self.sec_scale = min(80, self.sec_scale + 2); self._sec_render = None
            elif e.key == pygame.K_MINUS: self.sec_scale = max(6, self.sec_scale - 2); self._sec_render = None
        elif e.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if mx >= self.W - PANEL_W:                              # scroll the type list
                self.type_scroll = max(0, self.type_scroll - e.y)
            else:                                                  # zoom the sector at the cursor
                old = self.sec_scale
                self.sec_scale = max(6, min(80, old + e.y * max(1, old // 6)))
                f = self.sec_scale / old
                self.sec_cam[0] = mx - (mx - self.sec_cam[0]) * f
                self.sec_cam[1] = my - (my - self.sec_cam[1]) * f
                self._sec_render = None
        elif e.type == pygame.MOUSEMOTION and e.buttons[1]:        # middle-drag = pan
            self.sec_cam[0] += e.rel[0]; self.sec_cam[1] += e.rel[1]
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            mx, my = e.pos
            if mx >= self.W - PANEL_W:
                if e.button == 1:
                    for rect, c in self.cat_rects:
                        if rect.collidepoint(mx, my):
                            self.tool_cat = c; self.type_scroll = 0; break
                    else:
                        self.click_type(my)
            else:
                self.paint(self.sec_cell_at(mx, my), erase=(e.button == 3))
        elif e.type == pygame.MOUSEMOTION and (e.buttons[0] or e.buttons[2]):
            mx, my = e.pos
            if mx < self.W - PANEL_W:
                self.paint(self.sec_cell_at(mx, my), erase=bool(e.buttons[2]))

    def click_type(self, my):
        if my < self.type_top:
            return
        i = (my - self.type_top) // self.type_rowh + self.type_scroll
        if 0 <= i < len(self.type_ids):
            self.sel_type[self.tool_cat] = self.type_ids[i]

    def _ensure_wall(self, r, c, edge):
        """a door needs a wall on that edge to be stored/shown — add one if absent."""
        s = self.cur
        cur = {"N": s.n_wall(r, c), "W": s.w_wall(r, c),
               "S": s.n_wall(r + 1, c) if r + 1 < 33 else 1,
               "E": s.w_wall(r, c + 1) if c + 1 < 33 else 1}[edge]
        if cur == 0:
            s.paint_wall(r, c, edge, self.sel_type["wall"] or 1)

    def paint(self, cell, erase=False):
        if not cell:
            return
        gx, gy = cell
        cat = self.tool_cat
        if cat == "terrain":
            self.cur.set_terrain(gy, gx, 0 if erase else self.sel_type["terrain"])
        elif cat == "object":
            self.cur.set_obj(gy, gx, 0 if erase else self.sel_type["object"])
        elif cat == "wall":
            self.cur.paint_wall(gy, gx, self.edge, 0 if erase else self.sel_type["wall"])
        elif cat == "door":
            if not erase:
                self._ensure_wall(gy, gx, self.edge)
            self.cur.paint_door(gy, gx, self.edge, 0 if erase else self.sel_type["door"])
        self.dirty = True
        self._sec_render = None      # re-render on next frame to show the edit

    def save_sector(self):
        path = os.path.join(EDITED, self.cur_name + ".SEC")
        self.cur.save(path)
        self.sec_cache[self.cur_name] = self.cur.copy()
        self.invalidate(self.cur_name)
        self.dirty = False
        self.status = f"saved -> editor/edited/{self.cur_name}.SEC"

    # ================= shared =================
    def draw_status(self):
        pygame.draw.rect(self.screen, (16, 16, 20), (0, self.H - 22, self.W - PANEL_W, 22))
        self.screen.blit(self.font.render(self.status[: (self.W - PANEL_W) // 8], True, (200, 210, 220)), (6, self.H - 19))

    def run(self, smoke=False):
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit(); return
                if e.type == pygame.VIDEORESIZE:
                    self.W, self.H = e.w, e.h
                    self.screen = pygame.display.set_mode((self.W, self.H), pygame.RESIZABLE)
                if self.mode == "world":
                    self.world_event(e)
                else:
                    self.sector_event(e)
            if self.mode == "world":
                self.draw_world()
            else:
                self.draw_sector()
            pygame.display.flip()
            self.clock.tick(60)
            if smoke:
                # render one frame of each mode then exit
                if self.mode == "world" and self.placement[50]:
                    any_name = next(iter(self.placement[50].values()))
                    self.enter_sector(any_name); self.draw_sector(); pygame.display.flip()
                print("SMOKE OK: sectors=%d placed(b)=%d labels=%d" %
                      (len(self.sectors), len(self.placement[50]), len(self.labels)))
                pygame.quit(); return


if __name__ == "__main__":
    App().run(smoke="--smoke" in sys.argv)
