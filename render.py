"""
render.py — render a `Sector` to a pygame Surface.

Flat-color palette with bright walls so mazes are legible, tinted Void so dead-space reads as
boundary not missing. Draws per-cell N/W walls + the pad-row/col boundary walls + objects, and
blits real SCBART.256 tile art when available.
"""
import colorsys
import pygame
from secio import PLAY
import art

USE_ART = art.available()      # render real SCB tiles when SCBART.256/PAL256 are present

# terrain id -> RGB (Void tinted to (20,20,30) so it differs from walls)
C = {0:(20,20,30),2:(40,40,48),3:(150,40,160),4:(60,60,90),5:(110,110,150),6:(200,205,215),7:(225,230,240),
15:(120,180,235),21:(30,70,150),61:(70,120,190),16:(150,110,70),17:(180,140,95),24:(110,80,55),34:(70,50,35),
22:(90,65,45),18:(140,140,145),23:(85,85,92),27:(105,100,95),60:(170,90,70),19:(210,210,220),33:(60,60,70),
25:(235,235,240),20:(70,150,60),38:(120,190,110),26:(200,180,130),28:(150,120,80),30:(140,110,75),31:(140,110,75),
29:(120,120,40),35:(80,110,70),36:(90,130,90),37:(60,95,70),62:(90,140,80),44:(180,180,180)}
WALL = (225, 225, 235)
DOOR = (205, 160, 70)
TELE = (60, 230, 230)     # teleportal objects (ids 1-4)
OBJ  = (235, 235, 120)    # any other object

def tcolor(v):
    if v in C:
        return C[v]
    h = (v * 0.1379) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.5, 0.7)
    return (int(r * 255), int(g * 255), int(b * 255))


def _draw_edge(surf, x0, y0, scale, wt, wall_t, door_t, edge):
    """draw a cell edge: real wall+door sprite for the type, else a colored line."""
    if not (wall_t or door_t):
        return
    drew = False
    if USE_ART:
        if wall_t:
            ws = art.wall_surface(wall_t, edge, scale)
            if ws is not None:
                surf.blit(ws, (x0, y0)); drew = True
        if door_t:
            ds = art.door_surface(door_t, edge, scale)
            if ds is not None:
                surf.blit(ds, (x0, y0)); drew = True
    if not drew:
        col = DOOR if door_t else WALL
        rect = {"N": (x0, y0, scale, wt), "S": (x0, y0 + scale - wt, scale, wt),
                "W": (x0, y0, wt, scale), "E": (x0 + scale - wt, y0, wt, scale)}[edge]
        surf.fill(col, rect)


def render_sector(sec, scale=10, boundary=True):
    """Return a (PLAY*scale)^2 Surface of the sector's playable area."""
    size = PLAY * scale
    surf = pygame.Surface((size, size))
    surf.fill((10, 10, 12))
    wt = max(1, scale // 6)            # wall thickness
    for r in range(PLAY):
        for c in range(PLAY):
            x0, y0 = c * scale, r * scale
            tid = sec.terrain(r, c)
            ts = art.terrain_surface(tid, scale) if USE_ART else None
            if ts is not None:
                surf.blit(ts, (x0, y0))
            else:
                surf.fill(tcolor(tid), (x0, y0, scale, scale))
            _draw_edge(surf, x0, y0, scale, wt, sec.n_wall(r, c), sec.n_door(r, c), "N")
            _draw_edge(surf, x0, y0, scale, wt, sec.w_wall(r, c), sec.w_door(r, c), "W")
            o = sec.obj(r, c)
            if o:
                osurf = art.object_surface(o, scale) if USE_ART else None
                if osurf is not None:
                    surf.blit(osurf, (x0, y0))
                else:
                    col = TELE if o in (1, 2, 3, 4) else OBJ
                    m = max(2, scale // 3)
                    surf.fill(col, (x0 + (scale - m) // 2, y0 + (scale - m) // 2, m, m))
    if boundary:
        # east boundary = pad col 32's w_wall per row; south boundary = pad row 32's n_wall per col
        for r in range(PLAY):
            _draw_edge(surf, (PLAY - 1) * scale, r * scale, scale, wt, sec.w_wall(r, 32), sec.w_door(r, 32), "E")
        for c in range(PLAY):
            _draw_edge(surf, c * scale, (PLAY - 1) * scale, scale, wt, sec.n_wall(32, c), sec.n_door(32, c), "S")
    return surf
