# `.SEC` — Sector File Format

**6534 bytes = 33×33 cells × 6 bytes.** 32×32 playable + a Void margin at row/col 32.
Cells are row-major: cell `(r,c)` at byte offset `(r*33 + c) * 6`.

## The 6-byte cell  [binary-verified]
For example, `EWGB194225b` cell (6,3) = `17 01 e0 00 00 00`:

| Byte | Meaning | Notes |
|------|---------|-------|
| **b0** | **terrain** type | e.g. `0x12`=Stone Floor, `0x14`=Grass, `0x10`=Wood Panel Floor, `0x0f`=Shallow Water, `0x00`=Void. **Names in the Type Tables below** (from SCB.EXE). |
| **b1** | **object / feature overlay** | `0`=none, **`1`=teleportal (public/blue)**; other values = placed objects (trees, furniture, etc.). |
| **b2–b3** | **walls + N-door** (16-bit LE) | `word = b2 | (b3<<8)`; `n_wall = word & 31`; `w_wall = (word>>5) & 31`; `n_door = (word>>10) & 15`. |
| **b4** | **W-door** | `w_door = (b4>>1) & 15`. |
| **b5** | **entity-index** | index into the sector's entity/critter table (links to `.CRT` placement). |

Verified against the game's `.SEC` data — the `EWGB194225b` teleportal example confirms
`b0`/`b1`/`b4`/`b5`.

## Type tables — display names  [reverse-engineered from SCB.EXE, authoritative]

The exact type names SCB's editor showed, extracted from its tooltip dispatch (`FUN_00407a34`) and
verified against the click-handler id formulas (the values actually written to `b0` / `b1` /
wall-bits). The 8 strings Ghidra left unnamed were read from the binary's data section.

Two original SCB typos are kept verbatim: `Shallow Waterr`, `Pub Flor`.

Palette id formulas (screen col `c770` / row `f9b0`, step `0x11`):
`terrain = ((c770-0x47)/0x11)*6 + ((f9b0-0x18b)/0x11)` ·
`wall = ((c770-0x47)/0x11)*8 + ((f9b0-0x1f3)/0x11)` · `door = (f9b0-0x1f3)/0x11` ·
`object = ((c770-0xcf)/0x11)*8 + ((f9b0-0x1f3)/0x11)`. Machine-readable copy: `scbdata.py`.

### Terrain (`b0`)
```
0=CLEAR All  2=No see through  3=Veil of Darkness (po)  4=Go to sector below  5=Go to sector above
6=Indoor Air (fall through)  7=Outdoor Air (fall through)  15=Shallow Waterr  16=Wood Panel Floor
17=Light Wood Panel Floor  18=Stone Floor  19=Marble Floor  20=Grass  21=Deep Water
22=Solid Wood Floor  23=Darkened Stone Floor  24=Dark Wood Panel Floor  25=Styled White Floor
26=Styled Pub Floor  27=Cave Stone Floor  28=Dirt  29=Refuse Hole  30,31=Plowed Ground  32=Do NOT use
33=Blackened Marble Floor  34=Blackened Wood Floor  35=Marsh  36=Shallow Swamp Water
37=Deep Swamp Water  38=Blue Sky Grass  39,40,41=Wood Panel Floor  42=Brick Floor  43=Sand
44=Light Dirt  45,46=Gravel  47=East landing, south part  48,49,50,51=Stairs  52=Stairs Landing
53,54,55=Marketplace Pool  56,57=Stone Floor  60=Brick Floor  61=Standing Water  62=Moss
120=Marsh with Fog  121=Swamp with Fog  122=Dirt with LimVis  123=Gravel with LimVis
124=Moss with LimVis  126=Dark Stone (No Exit Game)  127=Light Wood (No Exit Game)
128=Stone (No NPC Move)  129=Wood (No NPC Move)  130=No Restore Loss  131=Stone PvP  132=Grass PvP
133=Wood PvP  134=Dirt PvP  135=Wood Party Brawl  136=Pub Flor Party Brawl
137=Light Wood Party Brawl  138,139,140=Reserved
```
(Stair/landing semantics confirmed by SCB.TXT: `Go to sector above` = UP ARROW, `Go to sector below`
= DOWN ARROW; up/down must overlap on adjacent — not same — squares.)

### Walls (`n_wall` / `w_wall`, 5-bit)
```
0=CLEAR Walls  1=Stone Wall  2=Dark Wood Panel Wall  3=Brick Wall  4=Cave Wall  5=Marble Wall
6=Light Wood Panel Wall  7=Blackened Wall  8=Granite Wall  9=Outdoor Cliffside  10=Tunnel Wall
29=Ruined Stone Wall  31=Flower Bed Wall
```

### Doors (`n_door` / `w_door`, 4-bit)
```
1=Wooden Door  2=Metal Door  3=Illusionary Wall  4=Blackened Metal Door  5=Dark Wood Door
```
(`CLEAR Walls` clears both walls and doors; a door requires its parent wall to be non-zero.)

### Objects (`b1`)
```
0=CLEAR Objects  1=Teleportal  2=Room Teleportal  3=Instant Teleportal  4=Invisible Teleportal
5=Special Function  6=Marsh Fog  7=Hole  8=Rune Square  9=LimVis  14,15,16,17=Counter N/E/S/W
22,23,24,25=Table w Bench N/E/S/W  26,27=Bar N/S  30,31,32,33=Chair N/E/S/W  34,35,36,37=Locker N/E/S/W
38,39,40=Table w Book N/E/W  41,42,43=Desk N/E/W  44=Bed against West Wall  45=Bed against East Wall
46,47=Throne N/S  48,56,57,58=Path  59=Flowers  60=Bushes  61=Small Tree  70,71=Crate
72,73=Straw bed  74,75,76=Grafitte N/E/W Wall  77=Plaque  78=Gravestone
```

## Seam / adjacency (for world reassembly)
Playable area is cols/rows 0–31 with a Void margin at 32. True neighbors share a content seam:
`west.col[31] == east.col[0]` and `north.row[31] == south.row[0]` (verified on the `thfif` 2×2 set).

## Why this matters for the world map
Terrain (`b0`) alone is too homogeneous (grass everywhere) for reliable edge-matching. The
**walls (`b2–b3`) and objects (`b1`) are far more distinctive**, so matching seams on the full
cell — terrain + objects + walls — sharpens neighbor detection and should resolve the regions
that terrain-only matching couldn't (`ucm`, inter-region joins). It also lets the renderer
overlay walls/doors/objects so dungeons (mostly Void terrain) become legible.

## Naming
- **Area-named set** (`data/area-maps/`): adjacency encoded in the filename (`thfif1north`,
  `iun3south`, numbered grids `ucm1..24`).
- **Coordinate set** (`data/coordinate-maps/`): `<prefix><Ystart><Yend><layer>`, e.g. `EWGB194225b` =
  x-block `EWGB`, Y 194–225, layer `b`. Prefix→X-block and Y-range→Y-block per `world_map.json`
  `coordinate_system`.
