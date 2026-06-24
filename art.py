"""
art.py — decode SCB's real tile art (SCBART.256 + PAL256) into pygame Surfaces.

SCBART.256 = 256-byte object-offset header, then terrain tiles at 256 + id*0x94, each
[w:u16][h:u16] (=12,12) + w*h palette-index pixels. Objects/walls/doors are RLE strips
addressed via the header / art bases (added incrementally).
PAL256 = N RGB triples (8-bit).

terrain_surface(id, px) returns a px-sized Surface, or None if the tile is blank/missing
(caller falls back to the flat color palette).
"""
import os
import struct
import pygame

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
TILE = 12
TERRAIN_BASE = 0x100
TERRAIN_STRIDE = 0x94
# the table-build skips terrain art slots 96..119 (if a797==0x60 -> 0x78), so only 120 blocks
# of terrain art precede the object region: object base = 0x100 + 120*0x94.
OBJ_BASE = 0x100 + 120 * TERRAIN_STRIDE     # 18016
WALL_STRIDE = 0xe4
DOOR_STRIDE = 0x80
WALL_EDGE = {"N": 0, "E": 0x1f, "W": 0x5c, "S": 0x7b}
DOOR_EDGE = {"N": 0, "E": 0x17, "W": 0x40, "S": 0x57}

_art = None
_pal = None
_hdr = None
_wall_base = None   # = OBJ_BASE + header[127]
_door_base = None   # = wall_base + 0xab0
_native = {}        # terrain id -> 12x12 Surface (or None)
_scaled = {}        # (id, px) -> Surface
_obj_native = {}    # obj id -> 12x12 SRCALPHA Surface (or None)
_obj_scaled = {}    # (obj id, px) -> Surface
_wall_native = {}; _wall_scaled = {}
_door_native = {}; _door_scaled = {}


def available():
    return os.path.exists(os.path.join(ASSETS, "SCBART.256")) and os.path.exists(os.path.join(ASSETS, "PAL256"))


def _load():
    global _art, _pal, _hdr, _wall_base, _door_base
    _art = open(os.path.join(ASSETS, "SCBART.256"), "rb").read()
    p = open(os.path.join(ASSETS, "PAL256"), "rb").read()
    _pal = [(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]) for i in range(len(p) // 3)]
    _hdr = struct.unpack("<128H", _art[:256])
    _wall_base = OBJ_BASE + _hdr[127]      # walls follow the object region (header[127]=its size)
    _door_base = _wall_base + 0xab0


def _col(v):
    return _pal[v] if v < len(_pal) else (255, 0, 255)


def _terrain_block(tid):
    """art block index for a terrain id (slots 96..119 are unused/blank)."""
    if tid < 96:
        return tid
    if tid >= 120:
        return tid - 24
    return None


def _native_tile(tid):
    if tid in _native:
        return _native[tid]
    if _art is None:
        _load()
    surf = None
    blk = _terrain_block(tid)
    if blk is not None:
        off = TERRAIN_BASE + blk * TERRAIN_STRIDE
        if off + 4 + TILE * TILE <= len(_art):
            w = _art[off] | (_art[off + 1] << 8)
            h = _art[off + 2] | (_art[off + 3] << 8)
            if w == TILE and h == TILE:
                px = _art[off + 4: off + 4 + TILE * TILE]
                if any(px):                   # blank -> None -> flat-color fallback
                    surf = pygame.Surface((TILE, TILE))
                    for i, v in enumerate(px):
                        surf.set_at((i % TILE, i // TILE), _col(v))
    _native[tid] = surf
    return surf


def terrain_surface(tid, px):
    """px-sized Surface for terrain id, or None if blank/missing."""
    key = (tid, px)
    if key in _scaled:
        return _scaled[key]
    nat = _native_tile(tid)
    out = pygame.transform.scale(nat, (px, px)) if nat is not None else None
    _scaled[key] = out
    return out


def _decode_rle(start, end):
    """RLE strips [x, y, len, bytes...]; terminator x>=0xc. Top-down (no flip)."""
    img = [[-1] * TILE for _ in range(TILE)]
    i, guard = start, 0
    while i + 2 < end and i + 2 < len(_art) and _art[i] < 0x0c and guard < 64:
        x, y, n = _art[i], _art[i + 1], _art[i + 2]
        i += 3
        for k in range(n):
            if 0 <= x + k < TILE and 0 <= y < TILE and i + k < len(_art):
                img[y][x + k] = _art[i + k]
        i += n
        guard += 1
    return img


def _img_to_surf(img):
    if not any(v >= 0 for row in img for v in row):
        return None
    surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    for y in range(TILE):
        for x in range(TILE):
            v = img[y][x]
            if v >= 0:
                surf.set_at((x, y), (*_col(v), 255))
    return surf


def _scaled_lookup(native_fn, key, px, cache):
    k = (key, px)
    if k in cache:
        return cache[k]
    nat = native_fn(key)
    out = pygame.transform.scale(nat, (px, px)) if nat is not None else None
    cache[k] = out
    return out


def _native_obj(oid):
    if oid in _obj_native:
        return _obj_native[oid]
    if _art is None:
        _load()
    surf = None
    if 1 <= oid < 128 and _hdr[oid] > _hdr[oid - 1] and _hdr[oid - 1] < 6900:
        surf = _img_to_surf(_decode_rle(OBJ_BASE + _hdr[oid - 1], OBJ_BASE + _hdr[oid]))
    _obj_native[oid] = surf
    return surf


def object_surface(oid, px):
    return _scaled_lookup(_native_obj, oid, px, _obj_scaled)


def _native_wall(key):
    t, edge = key
    if key in _wall_native:
        return _wall_native[key]
    if _art is None:
        _load()
    rt = 11 if t == 0x1d else (12 if t == 0x1f else t)   # remap per SCB
    surf = None
    if 1 <= rt <= 12:
        base = _wall_base + (rt - 1) * WALL_STRIDE + WALL_EDGE[edge]
        surf = _img_to_surf(_decode_rle(base, base + WALL_STRIDE))
    _wall_native[key] = surf
    return surf


def wall_surface(t, edge, px):
    return _scaled_lookup(_native_wall, (t, edge), px, _wall_scaled)


def _native_door(key):
    d, edge = key
    if key in _door_native:
        return _door_native[key]
    if _art is None:
        _load()
    surf = None
    if 1 <= d <= 5:
        base = _door_base + (d - 1) * DOOR_STRIDE + DOOR_EDGE[edge]
        surf = _img_to_surf(_decode_rle(base, base + DOOR_STRIDE))
    _door_native[key] = surf
    return surf


def door_surface(d, edge, px):
    return _scaled_lookup(_native_door, (d, edge), px, _door_scaled)
