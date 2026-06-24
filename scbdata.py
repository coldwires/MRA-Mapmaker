"""
scbdata.py — palette type labels, reverse-engineered from SCB.EXE.

Authoritative id->label mappings the original editor displayed, extracted from the tooltip
dispatch in FUN_00407a34 and the click-handler id formulas (verified), with the few unnamed
strings read directly from the binary's data section. The id is the value written to the .SEC.

id formulas (screen col c770 / row f9b0, step 0x11):
  terrain: ((c770-0x47)/0x11)*6 + ((f9b0-0x18b)/0x11)
  wall:    ((c770-0x47)/0x11)*8 + ((f9b0-0x1f3)/0x11)
  door:     (f9b0-0x1f3)/0x11
  object:  ((c770-0xcf)/0x11)*8 + ((f9b0-0x1f3)/0x11)
Two original SCB typos kept faithful: "Shallow Waterr", "Pub Flor".
"""

# terrain id -> label
TERRAIN = {
    0: "CLEAR All", 2: "No see through", 3: "Veil of Darkness (po)", 4: "Go to sector below",
    5: "Go to sector above", 6: "Indoor Air (fall through)", 7: "Outdoor Air (fall through)",
    15: "Shallow Waterr", 16: "Wood Panel Floor", 17: "Light Wood Panel Floor", 18: "Stone Floor",
    19: "Marble Floor", 20: "Grass", 21: "Deep Water", 22: "Solid Wood Floor",
    23: "Darkened Stone Floor", 24: "Dark Wood Panel Floor", 25: "Styled White Floor",
    26: "Styled Pub Floor", 27: "Cave Stone Floor", 28: "Dirt", 29: "Refuse Hole",
    30: "Plowed Ground", 31: "Plowed Ground", 32: "Do NOT use", 33: "Blackened Marble Floor",
    34: "Blackened Wood Floor", 35: "Marsh", 36: "Shallow Swamp Water", 37: "Deep Swamp Water",
    38: "Blue Sky Grass", 39: "Wood Panel Floor", 40: "Wood Panel Floor", 41: "Wood Panel Floor",
    42: "Brick Floor", 43: "Sand", 44: "Light Dirt", 45: "Gravel", 46: "Gravel",
    47: "East landing, south part", 48: "Stairs", 49: "Stairs", 50: "Stairs", 51: "Stairs",
    52: "Stairs Landing", 53: "Marketplace Pool", 54: "Marketplace Pool", 55: "Marketplace Pool",
    56: "Stone Floor", 57: "Stone Floor", 60: "Brick Floor", 61: "Standing Water", 62: "Moss",
    120: "Marsh with Fog", 121: "Swamp with Fog", 122: "Dirt with LimVis", 123: "Gravel with LimVis",
    124: "Moss with LimVis", 126: "Dark Stone (No Exit Game)", 127: "Light Wood (No Exit Game)",
    128: "Stone (No NPC Move)", 129: "Wood (No NPC Move)", 130: "No Restore Loss", 131: "Stone PvP",
    132: "Grass PvP", 133: "Wood PvP", 134: "Dirt PvP", 135: "Wood Party Brawl",
    136: "Pub Flor Party Brawl", 137: "Light Wood Party Brawl", 138: "Reserved", 139: "Reserved",
    140: "Reserved",
}

# wall type (5-bit) -> label
WALL = {
    0: "CLEAR Walls", 1: "Stone Wall", 2: "Dark Wood Panel Wall", 3: "Brick Wall", 4: "Cave Wall",
    5: "Marble Wall", 6: "Light Wood Panel Wall", 7: "Blackened Wall", 8: "Granite Wall",
    9: "Outdoor Cliffside", 10: "Tunnel Wall", 29: "Ruined Stone Wall", 31: "Flower Bed Wall",
}

# door type (4-bit) -> label (0 = clear; "CLEAR Walls" clears both walls and doors)
DOOR = {
    0: "Clear", 1: "Wooden Door", 2: "Metal Door", 3: "Illusionary Wall",
    4: "Blackened Metal Door", 5: "Dark Wood Door",
}

# object (b1) -> label
OBJECT = {
    0: "CLEAR Objects", 1: "Teleportal", 2: "Room Teleportal", 3: "Instant Teleportal",
    4: "Invisible Teleportal", 5: "Special Function", 6: "Marsh Fog", 7: "Hole", 8: "Rune Square",
    9: "LimVis", 14: "Counter N", 15: "Counter E", 16: "Counter S", 17: "Counter W",
    22: "Table w Bench N", 23: "Table w Bench E", 24: "Table w Bench S", 25: "Table w Bench W",
    26: "Bar N", 27: "Bar S", 30: "Chair N", 31: "Chair E", 32: "Chair S", 33: "Chair W",
    34: "Locker N", 35: "Locker E", 36: "Locker S", 37: "Locker W", 38: "Table w Book N",
    39: "Table w Book E", 40: "Table w Book W", 41: "Desk N", 42: "Desk E", 43: "Desk W",
    44: "Bed against West Wall", 45: "Bed against East Wall", 46: "Throne N", 47: "Throne S",
    48: "Path", 56: "Path", 57: "Path", 58: "Path", 59: "Flowers", 60: "Bushes", 61: "Small Tree",
    70: "Crate", 71: "Crate", 72: "Straw bed", 73: "Straw bed", 74: "Grafitte N Wall",
    75: "Grafitte E Wall", 76: "Grafitte W Wall", 77: "Plaque", 78: "Gravestone",
}

# ordered id lists for the palette (selectable)
TERRAIN_IDS = sorted(TERRAIN)
WALL_IDS = sorted(WALL)
DOOR_IDS = sorted(DOOR)
OBJECT_IDS = sorted(OBJECT)
