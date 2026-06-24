"""
sectext.py — lossless .SEC <-> .sectext converter + single-blob bundler.

A `.SEC` sector is a 6534-byte binary blob (33x33 cells x 6 bytes). This tool
serialises the *decoded* map data to a plain-text, human-readable, diff-able
form (`.sectext`) and rebuilds the exact original bytes back from it, and it can
pack every sector in the project into one self-describing text blob that the map
editor decodes at runtime.

Why text:
  - The binary `.SEC` is opaque and only editable with the original (lost) tool.
  - The `.sectext` form exposes the actual design data — terrain, walls, doors,
    objects, entity links — as readable fields anyone can read, edit, diff, and
    build tooling on, without the original program.
  - Rebuild is byte-exact: text_to_sec(sec_to_text(x)) == x for every file, so
    the binary can always be regenerated and nothing is lost in the round trip.

A `.sectext` cell line:
  <r>,<c>: terrain=<n> [object=<n>] [nwall=<n>] [wwall=<n>] [ndoor=<n>]
           [wdoor=<n>] [entity=<n>]            # trailing names after # are comments
  Only cells that are not all-zero are listed; omitted fields default to 0.
  Guard fields `_wallword` / `_b4` are emitted only if a cell ever carries bits
  outside the documented layout (so the round trip stays exact regardless).

The bundle (`data/sectors.sectext`) concatenates every sector, each introduced by
  SECTOR <name>  set=<coordinate|area>  rel=<path/within/set.SEC>
The `set`/`rel` metadata is provenance only (not needed to rebuild the bytes); it
lets the original directory tree be regenerated and disambiguates duplicate names.

Run `python sectext.py selftest` to verify byte-exact round-trip on every map.
"""
import os, glob, sys
from secio import Sector, GRID, SEC_SIZE, _off

try:
    from scbdata import TERRAIN, WALL, DOOR, OBJECT
except Exception:
    TERRAIN = WALL = DOOR = OBJECT = {}

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
COORD_DIR = os.path.join(DATA, "coordinate-maps")
AREA_DIR = os.path.join(DATA, "area-maps")
BUNDLE = os.path.join(DATA, "sectors.sectext")

# the source sets, in precedence order (first occurrence of a name wins on load)
SETS = (("coordinate", COORD_DIR), ("area", AREA_DIR))

# documented bit coverage of the 6-byte cell record
_WORD_USED = 0x3FFF      # n_wall | w_wall | n_door  (bits 0-13 of the LE wall word)
_B4_USED = 0x1E          # w_door (bits 1-4 of byte 4)


def _cell_fields(s, r, c):
    """Return (dict of nonzero named fields, residual_word_bits, residual_b4_bits)."""
    o = _off(r, c)
    b0, b1 = s.buf[o], s.buf[o + 1]
    word = s.buf[o + 2] | (s.buf[o + 3] << 8)
    b4, b5 = s.buf[o + 4], s.buf[o + 5]
    f = {}
    if b0:
        f["terrain"] = b0
    if b1:
        f["object"] = b1
    nwall, wwall, ndoor = word & 31, (word >> 5) & 31, (word >> 10) & 15
    if nwall:
        f["nwall"] = nwall
    if wwall:
        f["wwall"] = wwall
    if ndoor:
        f["ndoor"] = ndoor
    wdoor = (b4 >> 1) & 15
    if wdoor:
        f["wdoor"] = wdoor
    if b5:
        f["entity"] = b5
    return f, word & ~_WORD_USED, b4 & ~_B4_USED


def _annotate(f):
    """Human-readable trailing comment naming the types in this cell (ignored on read)."""
    bits = []
    if f.get("terrain") in TERRAIN:
        bits.append(TERRAIN[f["terrain"]])
    if f.get("object") in OBJECT:
        bits.append(OBJECT[f["object"]])
    if f.get("nwall") in WALL:
        bits.append("N:" + WALL[f["nwall"]])
    if f.get("wwall") in WALL:
        bits.append("W:" + WALL[f["wwall"]])
    if f.get("ndoor") in DOOR:
        bits.append("Ndoor:" + DOOR[f["ndoor"]])
    if f.get("wdoor") in DOOR:
        bits.append("Wdoor:" + DOOR[f["wdoor"]])
    return "  # " + ", ".join(bits) if bits else ""


def sec_to_text(sec, meta=None):
    """Serialise a Sector to .sectext (a SECTOR header line + one line per non-empty cell)."""
    head = f"SECTOR {sec.name}"
    if meta:
        head += "  " + "  ".join(f"{k}={v}" for k, v in meta.items())
    lines = [head]
    for r in range(GRID):
        for c in range(GRID):
            f, rw, rb4 = _cell_fields(sec, r, c)
            if not f and not rw and not rb4:
                continue
            parts = [f"{k}={v}" for k, v in f.items()]
            if rw:
                parts.append(f"_wallword={rw}")   # guard, normally absent
            if rb4:
                parts.append(f"_b4={rb4}")
            lines.append(f"{r},{c}: " + " ".join(parts) + _annotate(f))
    return "\n".join(lines) + "\n"


def _apply_cell(s, line):
    coord, _, rest = line.partition(":")
    r, c = (int(x) for x in coord.split(","))
    kv = dict(tok.split("=") for tok in rest.split())
    g = lambda k: int(kv.get(k, 0))
    o = _off(r, c)
    s.buf[o] = g("terrain") & 0xFF
    s.buf[o + 1] = g("object") & 0xFF
    word = ((g("nwall") & 31) | ((g("wwall") & 31) << 5) |
            ((g("ndoor") & 15) << 10) | g("_wallword"))
    s.buf[o + 2] = word & 0xFF
    s.buf[o + 3] = (word >> 8) & 0xFF
    s.buf[o + 4] = (((g("wdoor") & 15) << 1) | g("_b4")) & 0xFF
    s.buf[o + 5] = g("entity") & 0xFF


def _parse_header(line):
    """'SECTOR <name>  k=v  k=v' -> (name, {k: v})."""
    toks = line.split()[1:]            # drop the leading 'SECTOR'
    name = toks[0] if toks else ""
    meta = dict(t.split("=", 1) for t in toks[1:] if "=" in t)
    return name, meta


def text_to_sec(text, name=""):
    """Rebuild a single Sector from .sectext text (first SECTOR header wins for the name)."""
    s = Sector(name=name)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("SECTOR"):
            s.name = _parse_header(line)[0] or s.name
            continue
        _apply_cell(s, line)
    return s


def iter_bundle(text):
    """Yield (name, meta, Sector) for each SECTOR block in a multi-sector .sectext blob."""
    name, meta, cur = None, {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("SECTOR"):
            if cur is not None:
                yield name, meta, cur
            name, meta = _parse_header(line)
            cur = Sector(name=name)
            continue
        if cur is not None:
            _apply_cell(cur, line)
    if cur is not None:
        yield name, meta, cur


def load_bundle(path=BUNDLE):
    """Decode the blob to {name(lower): Sector}; first occurrence of a name wins."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for name, _meta, sec in iter_bundle(fh.read()):
            out.setdefault(name.lower(), sec)
    return out


def _collect():
    """List (set, rel, path) for every source .SEC, coordinate set first."""
    entries = []
    for setname, d in SETS:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.SEC"), recursive=True)):
            rel = os.path.relpath(path, d).replace(os.sep, "/")
            entries.append((setname, rel, path))
    return entries


def build_bundle(out_path=BUNDLE):
    """Pack every source .SEC into one .sectext blob. Returns the entry count."""
    entries = _collect()
    parts = [
        "# MRA sector bundle — authored .sectext format (lossless round-trip to .SEC).",
        "# Rebuild binaries with:  python sectext.py unbundle",
        f"# {len(entries)} sectors from: " + ", ".join(s for s, _ in SETS),
        "",
    ]
    for setname, rel, path in entries:
        sec = Sector.load(path)
        parts.append(sec_to_text(sec, meta={"set": setname, "rel": rel}))
    text = "\n".join(parts)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return len(entries)


def unbundle(path=BUNDLE, dest=DATA):
    """Regenerate the original .SEC tree from the blob using each sector's set/rel meta."""
    n = 0
    setdir = {"coordinate": COORD_DIR, "area": AREA_DIR}
    with open(path, encoding="utf-8") as fh:
        for name, meta, sec in iter_bundle(fh.read()):
            base = setdir.get(meta.get("set"), AREA_DIR)
            rel = meta.get("rel", name + ".SEC")
            out = os.path.join(base, *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            sec.save(out)
            n += 1
    return n


def selftest():
    entries = _collect()
    bad = 0
    for setname, rel, path in entries:
        orig = open(path, "rb").read()
        rebuilt = bytes(text_to_sec(sec_to_text(Sector.load(path))).buf)
        if rebuilt != orig:
            bad += 1
            print("ROUND-TRIP MISMATCH:", setname, rel)
    # and verify the in-memory bundle decodes byte-identically to each source file
    text = "\n".join(sec_to_text(Sector.load(p), {"set": s, "rel": r}) for s, r, p in entries)
    decoded = {}
    for name, meta, sec in iter_bundle(text):
        decoded[(meta.get("set"), meta.get("rel"))] = bytes(sec.buf)
    bundle_bad = 0
    for setname, rel, path in entries:
        if decoded.get((setname, rel)) != open(path, "rb").read():
            bundle_bad += 1
            print("BUNDLE MISMATCH:", setname, rel)
    ok = bad == 0 and bundle_bad == 0
    print(f"round-trip: {len(entries)} files, {bad} per-file + {bundle_bad} bundle mismatches "
          f"({'PASS' if ok else 'FAIL'})")
    return ok


def _usage():
    print("usage: sectext.py [selftest | build | unbundle | "
          "encode <f.SEC> | decode <f.sectext> [out.SEC]]")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        sys.exit(0 if selftest() else 1)
    elif cmd == "build":
        print(f"wrote {build_bundle()} sectors -> {os.path.relpath(BUNDLE, HERE)}")
    elif cmd == "unbundle":
        print(f"wrote {unbundle()} .SEC files from {os.path.relpath(BUNDLE, HERE)}")
    elif cmd == "encode" and len(sys.argv) >= 3:
        sys.stdout.write(sec_to_text(Sector.load(sys.argv[2])))
    elif cmd == "decode" and len(sys.argv) >= 3:
        out = sys.argv[3] if len(sys.argv) > 3 else "out.SEC"
        text_to_sec(open(sys.argv[2], encoding="utf-8").read()).save(out)
        print("wrote", out)
    else:
        _usage()
