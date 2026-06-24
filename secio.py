"""
secio.py — read / write MRA `.SEC` sector files, byte-faithfully.

A `.SEC` is 6534 bytes = 33x33 cells x 6 bytes (32x32 playable + a dud pad row/col 32
that carries the shared south/east boundary walls). Per-cell 6-byte layout:
  b0 terrain  b1 object  b2-3 wall word (LE)  b4 w_door  b5 entity/critter id
Wall word bits:  n_wall = w&31 ; w_wall = (w>>5)&31 ; n_door = (w>>10)&15
w_door = (b4>>1)&15.  Walls are stored canonically as each cell's N and W edges; a
cell's S/E wall is the N/W wall of its south/east neighbour (matches SCB FUN_0040b0d0).
Door-requires-wall: a door is zeroed if its wall is absent.

Edits mutate the raw buffer in place, so untouched bytes round-trip exactly.
"""
import os

GRID = 33          # full dim incl. pad
PLAY = 32          # playable dim
REC = 6            # bytes per cell
SEC_SIZE = GRID * GRID * REC   # 6534

def _off(r, c): return (r * GRID + c) * REC


class Sector:
    def __init__(self, data=None, name=""):
        if data is None:
            data = bytes(SEC_SIZE)
        if len(data) != SEC_SIZE:
            raise ValueError(f"bad .SEC size {len(data)} (expected {SEC_SIZE})")
        self.buf = bytearray(data)
        self.name = name

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read(), os.path.splitext(os.path.basename(path))[0])

    def save(self, path):
        with open(path, "wb") as f:
            f.write(bytes(self.buf))

    def copy(self):
        return Sector(bytes(self.buf), self.name)

    # --- direct byte fields ---
    def terrain(self, r, c): return self.buf[_off(r, c)]
    def set_terrain(self, r, c, v): self.buf[_off(r, c)] = v & 0xFF
    def obj(self, r, c): return self.buf[_off(r, c) + 1]
    def set_obj(self, r, c, v): self.buf[_off(r, c) + 1] = v & 0xFF
    def entity(self, r, c): return self.buf[_off(r, c) + 5]
    def set_entity(self, r, c, v): self.buf[_off(r, c) + 5] = v & 0xFF

    def cell_raw(self, r, c):
        o = _off(r, c)
        return tuple(self.buf[o:o + REC])

    # --- wall word ---
    def _word(self, r, c):
        o = _off(r, c)
        return self.buf[o + 2] | (self.buf[o + 3] << 8)

    def _set_word(self, r, c, w):
        o = _off(r, c)
        self.buf[o + 2] = w & 0xFF
        self.buf[o + 3] = (w >> 8) & 0xFF

    def n_wall(self, r, c): return self._word(r, c) & 31
    def w_wall(self, r, c): return (self._word(r, c) >> 5) & 31
    def n_door(self, r, c): return (self._word(r, c) >> 10) & 15
    def w_door(self, r, c): return (self.buf[_off(r, c) + 4] >> 1) & 15

    def set_n_wall(self, r, c, t):
        w = self._word(r, c)
        w = (w & ~31) | (t & 31)
        if (t & 31) == 0:
            w &= ~(15 << 10)            # door requires wall
        self._set_word(r, c, w)

    def set_w_wall(self, r, c, t):
        w = self._word(r, c)
        w = (w & ~(31 << 5)) | ((t & 31) << 5)
        self._set_word(r, c, w)
        if (t & 31) == 0:
            o = _off(r, c)
            self.buf[o + 4] &= ~(15 << 1)

    def set_n_door(self, r, c, d):
        if self.n_wall(r, c) == 0:
            d = 0
        w = self._word(r, c)
        w = (w & ~(15 << 10)) | ((d & 15) << 10)
        self._set_word(r, c, w)

    def set_w_door(self, r, c, d):
        if self.w_wall(r, c) == 0:
            d = 0
        o = _off(r, c)
        self.buf[o + 4] = (self.buf[o + 4] & ~(15 << 1)) | ((d & 15) << 1)

    # --- edge-routed painting (N/E/S/W) -> canonical N/W on this or neighbour cell ---
    def paint_wall(self, r, c, edge, t):
        if edge == "N":
            self.set_n_wall(r, c, t)
        elif edge == "W":
            self.set_w_wall(r, c, t)
        elif edge == "S" and r + 1 < GRID:
            self.set_n_wall(r + 1, c, t)
        elif edge == "E" and c + 1 < GRID:
            self.set_w_wall(r, c + 1, t)

    def paint_door(self, r, c, edge, d):
        if edge == "N":
            self.set_n_door(r, c, d)
        elif edge == "W":
            self.set_w_door(r, c, d)
        elif edge == "S" and r + 1 < GRID:
            self.set_n_door(r + 1, c, d)
        elif edge == "E" and c + 1 < GRID:
            self.set_w_door(r, c + 1, d)

    def has_stairs(self):
        """True if any playable cell has a layer-transition terrain (4 below / 5 above)."""
        return any(self.terrain(r, c) in (4, 5) for r in range(PLAY) for c in range(PLAY))


# --- round-trip self-test ---
if __name__ == "__main__":
    import glob, sys
    here = os.path.dirname(__file__)
    maps = os.path.join(here, "data", "maps")
    files = sorted(glob.glob(os.path.join(maps, "*.SEC")))[:40]
    if not files:
        print("no .SEC files found at", maps); sys.exit(1)
    bad = 0
    for p in files:
        s = Sector.load(p)
        orig = open(p, "rb").read()
        if bytes(s.buf) != orig:
            bad += 1; print("MISMATCH on load/serialize:", os.path.basename(p))
    # round-trip a field edit then restore: set+restore terrain must be byte-identical
    s = Sector.load(files[0]); before = bytes(s.buf)
    t0 = s.terrain(5, 5); s.set_terrain(5, 5, 99); s.set_terrain(5, 5, t0)
    if bytes(s.buf) != before:
        bad += 1; print("MISMATCH on set/restore terrain")
    print(f"round-trip self-test: {len(files)} files, {bad} mismatches "
          f"({'PASS' if bad == 0 else 'FAIL'})")
