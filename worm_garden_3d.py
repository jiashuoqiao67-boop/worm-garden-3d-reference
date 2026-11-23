"""
=========================================================
 WORM'S GARDEN 3D  -  the same game, rebuilt in 3D
=========================================================

WHAT CHANGED vs the 2D version
---------------------------------------------------------
1. RENDERER
   The old code only knew (x, y) pixels.  This version has a tiny
   software 3D renderer written on top of pygame:

       world space (x right, y depth, z up)
           -> camera space   (Sutherland-Hodgman near-plane clip)
           -> screen space   (perspective divide)
           -> painter's algorithm (z-sorting, far polygons first)

   Nothing but pygame + numpy is needed (no OpenGL required).

2. WORLD
   * Maze walls are real 3D boxes (WALL_H high) with 4-5 shaded
     faces instead of 2D rectangles / thick lines.
   * The floor is a tiled 3D plane with maze cells + an outer lawn.
   * Every object lives in 3D: the worm, the apples, the birds
     (they fly low inside the corridors at BIRD_ALTITUDE), the water pools (flat decals),
     the flags (poles + waving cloth made of quads), the particles.
   * Jumping is a real vertical hop: the worm leaves the ground and
     its shadow shrinks.  Birds fly ABOVE the worm, so you must
     judge height while dodging.

3. CAMERA
   A perspective chase camera with smooth follow, a slight sway
   and a real FOV (FOCAL).  It never spins, so corridors stay
   readable while the maze turns around you.

4. LIGHT + AIR
   * Directional light: every face gets its own brightness
     (top > side facing the sun > side in shadow).
   * Spheres are shaded with 3 stacked blobs (shadow / base /
     highlight) which reads as a lit ball.
   * Depth fog fades everything into the sky colour, so the maze
     really has distance now.  Because the floor is a plane, its fog
     is drawn as one smooth screen-space gradient instead of per tile.
   * Gradient sky + a pre-rendered sun glow.

5. NEW PALETTE / FEATURES
   * Mossy green wall tops over warm weathered stone (a "garden ruin"
     look) instead of flat grey lines, plus contact shadows at the
     wall bases and flowers on some tops.
   * Ruby apples instead of plain red circles, gold apple glows.
   * Water pools are glossy 3D puddles with animated ripples.
   * Extra HUD: FPS, height meter while jumping, and a minimap
     (very helpful now that you cannot see the whole maze).
   * Left-click still fires fireworks, but the click is ray-cast
     onto the ground plane, so the burst happens where you clicked
     in the world - and it explodes upward in 3D.
   * A garden around the maze: trees, bushes, rocks and flowers.
   * The start now sits on the top edge and the finish opposite it,
     so the chase camera always looks down the maze.

CONTROLS
   WASD / Arrows : move        Space : jump
   Left click    : fireworks   R     : restart
=========================================================
"""

import math
import os
import random
import sys
import time

# Local dependency folder (pygame + numpy installed next to the game),
# so the game finds its packages without any PYTHONPATH setup.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _lib in (os.path.join(_HERE, "pylibs"),):
    if os.path.isdir(_lib) and _lib not in sys.path:
        sys.path.insert(0, _lib)

import numpy as np
import pygame

# =========================================================
# INITIALISATION
# =========================================================
pygame.init()
WIDTH, HEIGHT = 1250, 900
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Worm's Garden 3D")
clock = pygame.time.Clock()
FPS = 60

# =========================================================
# PALETTE  (re-lit for 3D, warmer greens + cool stone)
# =========================================================
SKY_TOP = (26, 62, 112)
SKY_MID = (92, 160, 212)
SKY_LOW = (184, 214, 228)
FOG_COLOR = (182, 212, 226)
SUN_DIR = np.array([-0.42, 0.66, 0.62])
SUN_DIR /= np.linalg.norm(SUN_DIR)

GROUND_A = (54, 118, 70)
GROUND_B = (47, 106, 63)
GROUND_OUT = (50, 110, 66)

WALL_TOP = (92, 152, 80)
WALL_TOP_B = (78, 132, 70)
WALL_FRONT = (172, 166, 154)
WALL_BACK = (96, 92, 86)
WALL_LEFT = (146, 140, 130)
WALL_RIGHT = (118, 112, 104)
WALL_RIM = (56, 60, 52)

WATER_DEEP = (10, 52, 96)
WATER_MID = (24, 134, 192)
WATER_LIGHT = (150, 232, 248)

APPLE_RED = (212, 40, 52)
APPLE_RED_L = (255, 134, 122)
APPLE_RED_D = (112, 16, 30)
APPLE_GOLD = (250, 186, 34)
APPLE_GOLD_L = (255, 238, 156)
APPLE_GOLD_D = (158, 100, 8)

WORM_MID = (86, 206, 118)
WORM_LIGHT = (178, 250, 188)
WORM_DARK = (22, 100, 56)

BIRD_BODY = (58, 50, 84)
BIRD_WING = (98, 88, 134)
BIRD_WING_D = (62, 54, 92)
BIRD_BEAK = (255, 184, 64)

START_GREEN = (46, 226, 122)
CHECK_BLACK = (26, 28, 34)
CHECK_WHITE = (242, 244, 248)
GOLD = (255, 200, 60)
WHITE = (245, 248, 255)
INK = (12, 20, 28)

SHADOW_1 = (38, 78, 48)
SHADOW_2 = (46, 94, 58)
WALL_SHADOW = (34, 76, 46)

FIREWORK_COLORS = [
    (70, 180, 255),
    (255, 90, 170),
    (190, 110, 255),
    (255, 214, 90),
]

# =========================================================
# GAME SETTINGS
# =========================================================
BALL_RADIUS = 11.0
BALL_SPEED = 210.0

JUMP_DURATION = 0.55
JUMP_COOLDOWN = 0.65
JUMP_HEIGHT = 34.0
jump_timer = 0.0
jump_cooldown = 0.0

WATER_HOLE_COUNT = 9
WATER_HOLE_RADIUS = 15.0
water_holes = []
water_hole_cells = set()

ENEMY_RADIUS = 9.0
ENEMY_SPEED = 74.0
BIRD_ALTITUDE = 13.0

COLS, ROWS = 23, 15
CELL = 50.0
WALL_T = 13.0
WALL_H = 46.0
ORIGIN_X, ORIGIN_Y = 30.0, 40.0

MAZE_WIDTH = COLS * CELL
MAZE_HEIGHT = ROWS * CELL
START_CELL = (COLS // 2, 1)
FINISH_CELL = (COLS // 2, ROWS - 1)

if CELL - WALL_T < BALL_RADIUS * 2:
    raise ValueError("The worm is too large for the corridors!")

START_POSITION = np.array([
    ORIGIN_X + START_CELL[0] * CELL + CELL * 0.5,
    ORIGIN_Y + START_CELL[1] * CELL + CELL * 0.5,
], dtype=float)
position = START_POSITION.copy()
facing = np.array([1.0, 0.0])
height = 0.0                     # jump height above ground (world units)

# Rewards
RUBY_VALUE = 50
GOLD_VALUE = 100
TOTAL_MEDALS = 4

# Particles (now 3D: every particle has a z component)
MAX_PARTICLES = 260
SPARK_INTERVAL = 0.015
spark_timer = 0.0
particles = []

# Progress
score = 0
collected_medals = 0
level = 1
start_time = time.time()

# Fonts
font = pygame.font.Font(None, 21)
small_font = pygame.font.Font(None, 16)
tiny_font = pygame.font.Font(None, 13)

# =========================================================
# 3D CAMERA  (perspective, follows the worm)
# =========================================================
CAM_BACK = 268.0        # how far behind the worm the camera sits
CAM_HEIGHT = 340.0      # how high above the floor
AIM_LIFT = 62.0         # look a little ahead of the worm
FOCAL = 960.0           # focal length in pixels -> FOV ~ 2*atan(450/FOCAL)
NEAR = 26.0             # near clipping plane
CX = WIDTH * 0.5
CY = HEIGHT * 0.62
FOG_START = 600.0
FOG_END = 1450.0
INV_FOG = 1.0 / (FOG_END - FOG_START)

cam_pos = np.array([0.0, 0.0, CAM_HEIGHT])
CAM_FWD = np.array([0.0, 1.0, 0.0])
CAM_RGT = np.array([1.0, 0.0, 0.0])
CAM_UP = np.array([0.0, 0.0, 1.0])

# plain-float copies of the camera basis: the inner render loop calls
# to_cam() thousands of times per frame, and Python floats beat numpy
# scalars there by a wide margin.
camx = camy = 0.0
camz = CAM_HEIGHT
cfx, cfy, cfz = 0.0, 1.0, 0.0
crx, cry, crz = 1.0, 0.0, 0.0
cux, cuy, cuz = 0.0, 0.0, 1.0

# ---- Switchable render options (mirroring the course-project keys) ----
projection = "perspective"   # "perspective" | "orthographic"
fog_enabled = True
view_mode = 2                # 0 overview, 1 side, 2 follow
quality = 2                  # 1 FAST, 2 BALANCED, 3 HIGH (detail level)
ORTHO_K = 1.05               # orthographic pixels per world unit


def proj_scale(cz):
    """Perceived size factor: perspective shrinks with depth; orthographic
    keeps a constant world-size-to-pixel scale."""
    return ORTHO_K if projection == "orthographic" else FOCAL / cz


def project_pt(cx, cy, cz):
    """Camera-space point -> screen pixels under the active projection."""
    k = proj_scale(cz)
    return CX + cx * k, CY - cy * k


def update_camera(dt, t):
    """Smooth chase camera. Yaw stays 0 so the maze never spins."""
    global cam_pos, CAM_FWD, CAM_RGT, CAM_UP
    global camx, camy, camz, cfx, cfy, cfz, crx, cry, crz, cux, cuy, cuz
    cx0 = ORIGIN_X + MAZE_WIDTH * 0.5
    cy0 = ORIGIN_Y + MAZE_HEIGHT * 0.5
    if view_mode == 0:          # elevated overview of the whole maze
        target = np.array([cx0, cy0, 760.0])
        look = np.array([cx0, cy0, 0.0])
    elif view_mode == 1:        # side view
        target = np.array([cx0, ORIGIN_Y - 260.0, 360.0])
        look = np.array([cx0, cy0, 0.0])
    else:                       # smooth chase behind the worm
        target = np.array([position[0], position[1] - CAM_BACK, CAM_HEIGHT])
        sway = math.sin(t * 0.9) * 26.0
        look = np.array([
            position[0] + sway * 0.12,
            position[1] + AIM_LIFT,
            6.0,
        ])
    k = 1.0 - math.exp(-dt * 6.5)
    cam_pos += (target - cam_pos) * k
    fwd = look - cam_pos
    fwd /= np.linalg.norm(fwd)
    rgt = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    rgt /= np.linalg.norm(rgt)
    CAM_FWD, CAM_RGT, CAM_UP = fwd, rgt, np.cross(rgt, fwd)

    camx, camy, camz = float(cam_pos[0]), float(cam_pos[1]), float(cam_pos[2])
    cfx, cfy, cfz = float(fwd[0]), float(fwd[1]), float(fwd[2])
    crx, cry, crz = float(rgt[0]), float(rgt[1]), float(rgt[2])
    cux, cuy = float(CAM_UP[0]), float(CAM_UP[1])
    cuz = float(CAM_UP[2])


def to_cam(p):
    """World point -> camera space (right, up, depth)."""
    dx = p[0] - camx
    dy = p[1] - camy
    dz = p[2] - camz
    return (
        dx * crx + dy * cry + dz * crz,
        dx * cux + dy * cuy + dz * cuz,
        dx * cfx + dy * cfy + dz * cfz,
    )


def clip_near(pts):
    """Sutherland-Hodgman clip against the d = NEAR plane."""
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        ain = a[2] >= NEAR
        bin_ = b[2] >= NEAR
        if ain:
            out.append(a)
        if ain != bin_:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append((
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                NEAR,
            ))
    return out


def shade_fog(color, factor, depth):
    """Apply directional light + depth fog to one base colour."""
    r = color[0] * factor
    g = color[1] * factor
    b = color[2] * factor
    if not fog_enabled:
        return (
            255 if r > 255 else int(r),
            255 if g > 255 else int(g),
            255 if b > 255 else int(b),
        )
    t = (depth - FOG_START) * INV_FOG
    if t > 0.0:
        if t > 1.0:
            t = 1.0
        r += (FOG_COLOR[0] - r) * t
        g += (FOG_COLOR[1] - g) * t
        b += (FOG_COLOR[2] - b) * t
    return (
        255 if r > 255 else int(r),
        255 if g > 255 else int(g),
        255 if b > 255 else int(b),
    )


# ---- the draw queue: (depth, kind, payload), drawn far -> near ----
QUEUE = []


def q_quad(cam_pts, color, factor=1.0, edge=None, edge_factor=0.42):
    """Queue a flat polygon. cam_pts are 4+ camera-space points."""
    pts = clip_near(cam_pts)
    if len(pts) < 3:
        return
    sp = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for cx, cy, cz in pts:
        sx, sy = project_pt(cx, cy, cz)
        sp.append((sx, sy))
        if sx < minx:
            minx = sx
        if sx > maxx:
            maxx = sx
        if sy < miny:
            miny = sy
        if sy > maxy:
            maxy = sy
    if maxx < 0 or minx > WIDTH or maxy < 0 or miny > HEIGHT:
        return
    avg_z = sum(p[2] for p in pts) / len(pts)
    col = shade_fog(color, factor, avg_z)
    if edge is not None and avg_z > 470.0:
        edge = None
    if edge is not None:
        ecol = shade_fog(edge, edge_factor, avg_z)
    else:
        ecol = None
    QUEUE.append((avg_z, 0, (sp, col, ecol)))


def q_world_quad(p0, p1, p2, p3, color, factor=1.0, edge=None, edge_factor=0.42):
    q_quad([to_cam(p0), to_cam(p1), to_cam(p2), to_cam(p3)],
           color, factor, edge, edge_factor)


def q_sphere(center, radius, color, light=None, dark=None, outline=False):
    """Shaded ball: 4 concentric blobs read as a lit sphere."""
    cx, cy, cz = to_cam(center)
    if cz < NEAR or cz > FOG_END:
        return
    r = radius * proj_scale(cz)
    if r < 0.8:
        return
    sx, sy = project_pt(cx, cy, cz)
    if sx + r < 0 or sx - r > WIDTH or sy + r < 0 or sy - r > HEIGHT:
        return
    base = shade_fog(color, 1.0, cz)
    hi = shade_fog(light if light else color, 1.0, cz)
    lo = shade_fog(dark if dark else color, 1.0, cz)
    QUEUE.append((cz, 1, (sx, sy, r, lo, base, hi, outline)))


def q_disc(center, radius, color, factor=1.0, seg=14, ring_color=None, ring_w=0):
    """Flat circle lying in a plane (water pools, shadows)."""
    if to_cam(center)[2] > FOG_END:
        return
    pts = []
    for i in range(seg):
        a = i / seg * math.tau
        pts.append(to_cam((
            center[0] + math.cos(a) * radius,
            center[1] + math.sin(a) * radius,
            center[2],
        )))
    p = clip_near(pts)
    if len(p) < 3:
        return
    sp = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for cxx, cyy, czz in p:
        sx, sy = project_pt(cxx, cyy, czz)
        sp.append((sx, sy))
        minx = min(minx, sx)
        maxx = max(maxx, sx)
        miny = min(miny, sy)
        maxy = max(maxy, sy)
    if maxx < 0 or minx > WIDTH or maxy < 0 or miny > HEIGHT:
        return
    depth = sum(q[2] for q in p) / len(p)
    col = shade_fog(color, factor, depth)
    ring = shade_fog(ring_color, factor, depth) if ring_color else None
    QUEUE.append((depth, 2, (sp, col, ring, ring_w)))


def q_line(a, b, color, world_w=3.0, factor=1.0):
    """A 3D segment drawn with a width that shrinks with distance."""
    ca = to_cam(a)
    cb = to_cam(b)
    if ca[2] < NEAR or cb[2] < NEAR:
        # cheap near clip: push the offending end to the near plane
        if ca[2] < NEAR and cb[2] < NEAR:
            return
        if ca[2] < NEAR:
            t = (NEAR - ca[2]) / (cb[2] - ca[2])
            ca = (
                ca[0] + (cb[0] - ca[0]) * t,
                ca[1] + (cb[1] - ca[1]) * t,
                NEAR,
            )
        else:
            t = (NEAR - cb[2]) / (ca[2] - cb[2])
            cb = (
                cb[0] + (ca[0] - cb[0]) * t,
                cb[1] + (ca[1] - cb[1]) * t,
                NEAR,
            )
    ax, ay = project_pt(ca[0], ca[1], ca[2])
    bx, by = project_pt(cb[0], cb[1], cb[2])
    depth = (ca[2] + cb[2]) * 0.5
    w = max(1, int(world_w * proj_scale(depth)))
    col = shade_fog(color, factor, depth)
    QUEUE.append((depth, 3, (ax, ay, bx, by, w, col)))


def q_tri(p0, p1, p2, color, factor=1.0):
    q_quad([to_cam(p0), to_cam(p1), to_cam(p2)], color, factor)


def flush_queue():
    QUEUE.sort(key=lambda it: -it[0])
    for depth, kind, data in QUEUE:
        if kind == 0:
            pts, col, ecol = data
            pygame.draw.polygon(screen, col, pts)
            if ecol is not None:
                pygame.draw.polygon(screen, ecol, pts, 1)
        elif kind == 1:
            sx, sy, r, lo, base, hi, outline = data
            ir = int(r)
            pygame.draw.circle(screen, lo, (int(sx), int(sy)), max(1, ir))
            pygame.draw.circle(
                screen, base, (int(sx - r * 0.10), int(sy - r * 0.12)),
                max(1, int(r * 0.88)))
            pygame.draw.circle(
                screen, hi, (int(sx - r * 0.34), int(sy - r * 0.38)),
                max(1, int(r * 0.38)))
            if outline:
                pygame.draw.circle(screen, lo, (int(sx), int(sy)), max(1, ir), 1)
        elif kind == 2:
            pts, col, ring, rw = data
            pygame.draw.polygon(screen, col, pts)
            if ring is not None:
                pygame.draw.polygon(screen, ring, pts, rw)
        elif kind == 3:
            ax, ay, bx, by, w, col = data
            pygame.draw.line(screen, col, (ax, ay), (bx, by), w)
        elif kind == 4:
            sx, sy, r, col = data
            pygame.draw.circle(screen, col, (int(sx), int(sy)), r)
    QUEUE.clear()


# =========================================================
# SKY  (pre-baked gradient + a pre-rendered sun glow)
# =========================================================
def make_sky():
    surf = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        if t < 0.55:
            k = t / 0.55
            c = [SKY_TOP[i] + (SKY_MID[i] - SKY_TOP[i]) * k for i in range(3)]
        else:
            k = (t - 0.55) / 0.45
            c = [SKY_MID[i] + (SKY_LOW[i] - SKY_MID[i]) * k for i in range(3)]
        pygame.draw.line(surf, (int(c[0]), int(c[1]), int(c[2])),
                         (0, y), (WIDTH, y))
    return surf


SKY_SURF = make_sky()


def make_glow(radius, inner, outer, alpha_in, alpha_out):
    """Round, soft radial glow, baked once at start-up."""
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(radius, 0, -1):
        k = i / radius
        c = [inner[j] * (1 - k) + outer[j] * k for j in range(3)]
        a = int(alpha_in * (1 - k) ** 2 + alpha_out * k)
        pygame.draw.circle(s, (int(c[0]), int(c[1]), int(c[2]), a),
                           (radius, radius), i)
    return s


SUN_GLOW = make_glow(150, (255, 255, 238), (255, 226, 180), 70, 0)


def draw_sky(t):
    screen.blit(SKY_SURF, (0, 0))
    # the sun is a very distant point, so it stays fixed in the world
    sun_pt = cam_pos + SUN_DIR * 6000.0
    cx, cy, cz = to_cam(sun_pt)
    if cz > 100:
        sx, sy = project_pt(cx, cy, cz)
        r = SUN_GLOW.get_width() * 0.5
        if -r < sx < WIDTH + r and -r < sy < HEIGHT + r:
            screen.blit(SUN_GLOW, (int(sx - r), int(sy - r)))


# =========================================================
# PARTICLE SYSTEM  (3D positions and velocities)
# =========================================================
def add_particle(particle):
    global quality
    limit = 120 if quality == 1 else MAX_PARTICLES
    particles.append(particle)
    if len(particles) > limit:
        del particles[:len(particles) - limit]


def create_spark(pos):
    angle = random.uniform(0, math.tau)
    speed = random.uniform(20, 90)
    add_particle({
        "pos": np.array([pos[0], pos[1], pos[2] - 2.0]),
        "vel": np.array([
            math.cos(angle) * speed,
            math.sin(angle) * speed,
            random.uniform(20, 70),
        ]),
        "life": random.uniform(0.35, 0.8),
        "max_life": 0.8,
        "size": random.uniform(1.4, 2.6),
        "color": (255, 196, 96),
        "gravity": 40.0,
    })


def create_firework(pos):
    for _ in range(random.randint(70, 110)):
        angle = random.uniform(0, math.tau)
        phi = random.uniform(-0.35, 1.0)
        speed = random.uniform(90, 300)
        add_particle({
            "pos": np.array(pos, dtype=float),
            "vel": np.array([
                math.cos(angle) * math.cos(phi) * speed,
                math.sin(angle) * math.cos(phi) * speed,
                math.sin(phi) * speed * 1.3,
            ]),
            "life": random.uniform(0.8, 1.7),
            "max_life": 1.7,
            "size": random.uniform(1.6, 3.4),
            "color": random.choice(FIREWORK_COLORS),
            "gravity": 70.0,
        })


def update_particles(dt):
    alive = []
    for p in particles:
        p["pos"] += p["vel"] * dt
        p["vel"] *= 0.97 ** (dt * FPS)
        p["vel"][2] -= p["gravity"] * dt
        if p["pos"][2] < 0.5:          # bounce softly off the floor
            p["pos"][2] = 0.5
            p["vel"][2] *= -0.28
        p["life"] -= dt
        if p["life"] > 0:
            alive.append(p)
    particles[:] = alive


def queue_particles():
    for p in particles:
        a = p["life"] / p["max_life"]
        cx, cy, cz = to_cam(p["pos"])
        if cz < NEAR:
            continue
        r = p["size"] * proj_scale(cz)
        if r < 0.7:
            continue
        sx, sy = project_pt(cx, cy, cz)
        if sx < -20 or sx > WIDTH + 20 or sy < -20 or sy > HEIGHT + 20:
            continue
        col = shade_fog(p["color"], 0.45 + 0.55 * a, cz)
        QUEUE.append((cz, 4, (sx, sy, max(1, int(r)), col)))


# =========================================================
# MAZE GENERATION  (identical logic, now extruded into 3D)
# =========================================================
DIRECTIONS = {
    "N": (0, -1, "S"),
    "E": (1, 0, "W"),
    "S": (0, 1, "N"),
    "W": (-1, 0, "E"),
}

maze = []
wall_boxes = []
wall_rectangles = []
wall_decor = []


def generate_maze():
    global maze
    maze = [[{"walls": {"N": True, "E": True, "S": True, "W": True},
              "visited": False}
             for _ in range(COLS)] for _ in range(ROWS)]
    stack = [START_CELL]
    sx, sy = START_CELL
    maze[sy][sx]["visited"] = True
    while stack:
        x, y = stack[-1]
        neighbors = []
        for direction, (dx, dy, opposite) in DIRECTIONS.items():
            nx = x + dx
            ny = y + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS and not maze[ny][nx]["visited"]:
                neighbors.append((nx, ny, direction, opposite))
        if neighbors:
            nx, ny, direction, opposite = random.choice(neighbors)
            maze[y][x]["walls"][direction] = False
            maze[ny][nx]["walls"][opposite] = False
            maze[ny][nx]["visited"] = True
            stack.append((nx, ny))
        else:
            stack.pop()
    # open the outer edge + the inner wall of both flag cells
    sx0, sy0 = START_CELL
    fx0, fy0 = FINISH_CELL
    maze[0][sx0]["walls"]["N"] = False          # entrance gap in the border
    maze[sy0][sx0]["walls"]["N"] = False
    maze[sy0 - 1][sx0]["walls"]["S"] = False
    maze[fy0][fx0]["walls"]["S"] = False        # exit, bottom edge
    maze[fy0][fx0]["walls"]["N"] = False
    maze[fy0 - 1][fx0]["walls"]["S"] = False


def build_wall_geometry():
    """Turn the maze walls into 3D boxes.  Collinear neighbours are merged
    into one long box, which both looks better (no seams) and keeps the
    polygon count low."""
    global wall_boxes, wall_rectangles
    raw = []
    half = WALL_T * 0.5
    for y in range(ROWS):
        for x in range(COLS):
            px = ORIGIN_X + x * CELL
            py = ORIGIN_Y + y * CELL
            cell = maze[y][x]["walls"]
            if cell["N"]:
                raw.append(("H", px - half, py - half, px + CELL + half, py + half))
            if cell["W"]:
                raw.append(("V", px - half, py - half, px + half, py + CELL + half))
            if x == COLS - 1 and cell["E"]:
                raw.append(("V", px + CELL - half, py - half,
                            px + CELL + half, py + CELL + half))
            if y == ROWS - 1 and cell["S"]:
                raw.append(("H", px - half, py + CELL - half,
                            px + CELL + half, py + CELL + half))

    merged = []
    for orient in ("H", "V"):
        groups = {}
        for o, x0, y0, x1, y1 in raw:
            if o != orient:
                continue
            key = ((round(y0, 2), round(y1, 2)) if orient == "H"
                   else (round(x0, 2), round(x1, 2)))
            groups.setdefault(key, []).append((x0, y0, x1, y1))
        for _, boxes in groups.items():
            boxes.sort(key=lambda b: b[0] if orient == "H" else b[1])
            ax0, ay0, ax1, ay1 = boxes[0]
            for bx0, by0, bx1, by1 in boxes[1:]:
                if orient == "H":
                    if bx0 <= ax1 + 0.01:
                        ax1 = max(ax1, bx1)
                        ay0, ay1 = min(ay0, by0), max(ay1, by1)
                        continue
                else:
                    if by0 <= ay1 + 0.01:
                        ay1 = max(ay1, by1)
                        ax0, ax1 = min(ax0, bx0), max(ax1, bx1)
                        continue
                merged.append((ax0, ay0, ax1, ay1))
                ax0, ay0, ax1, ay1 = bx0, by0, bx1, by1
            merged.append((ax0, ay0, ax1, ay1))

    wall_boxes = [(a, b, c, d, random.choice((WALL_TOP, WALL_TOP_B)))
                  for a, b, c, d in merged]
    global wall_decor
    wall_decor = []
    for a, b, c, d in merged:
        if random.random() < 0.13:
            if (c - a) > (d - b):
                t = random.uniform(0.2, 0.8)
                x, y = a + (c - a) * t, (b + d) * 0.5
            else:
                t = random.uniform(0.2, 0.8)
                x, y = (a + c) * 0.5, b + (d - b) * t
            wall_decor.append((x, y, random.uniform(3.0, 4.6),
                               random.choice(FLOWER_COLORS)))
    wall_rectangles = [pygame.Rect(int(a), int(b), int(c - a), int(d - b))
                       for a, b, c, d, _ in wall_boxes]


def cell_center(cell):
    x, y = cell
    return np.array([
        ORIGIN_X + x * CELL + CELL * 0.5,
        ORIGIN_Y + y * CELL + CELL * 0.5,
    ], dtype=float)


# =========================================================
# WATER POOLS  (flat 3D decals with ripples)
# =========================================================
def generate_water_holes():
    global water_holes, water_hole_cells
    water_holes = []
    water_hole_cells = set()
    available = [(x, y) for y in range(ROWS) for x in range(COLS)
                 if (x, y) != START_CELL and (x, y) != FINISH_CELL]
    random.shuffle(available)
    for cell in available[:WATER_HOLE_COUNT]:
        water_hole_cells.add(cell)
        water_holes.append({
            "pos": cell_center(cell),
            "phase": random.uniform(0, math.tau),
        })


def queue_water(t):
    for hole in water_holes:
        x, y = hole["pos"]
        ph = hole["phase"]
        # deep base
        q_disc((x, y, 1.0), WATER_HOLE_RADIUS + 2.0, WATER_DEEP, 0.85, 16)
        q_disc((x, y, 1.6), WATER_HOLE_RADIUS - 1.0, WATER_MID, 1.0, 16)
        # animated inner ripple rings
        for i in range(2):
            k = (math.sin(t * 2.0 + ph + i * 1.7) * 0.5 + 0.5)
            q_disc((x, y, 2.0), WATER_HOLE_RADIUS * (0.28 + 0.42 * k),
                   WATER_LIGHT, 0.92, 14, ring_color=WATER_LIGHT, ring_w=1)
        # specular glint
        q_disc((x - 4.0, y - 3.5, 2.4), 3.4, WATER_LIGHT, 1.35, 8)


def check_water_collision():
    if height > 4.0:
        return False
    for hole in water_holes:
        if np.linalg.norm(position - hole["pos"]) < BALL_RADIUS + WATER_HOLE_RADIUS - 4.0:
            reset_ball()
            return True
    return False


# =========================================================
# FLOOR / TERRAIN
# =========================================================
ground_tiles = []


def build_ground():
    global ground_tiles
    ground_tiles = []
    # maze floor: one tile per cell, subtle checker
    for y in range(ROWS):
        for x in range(COLS):
            x0 = ORIGIN_X + x * CELL
            y0 = ORIGIN_Y + y * CELL
            color = GROUND_A if (x + y) % 2 == 0 else GROUND_B
            ground_tiles.append((x0, y0, x0 + CELL, y0 + CELL, color))
    # outer lawn: finer grid so the fog gradient stays smooth
    step = 200.0
    m = 3
    for i in range(-m, int(MAZE_WIDTH / step) + m + 1):
        for j in range(-m, int(MAZE_HEIGHT / step) + m + 1):
            x0 = ORIGIN_X + i * step
            y0 = ORIGIN_Y + j * step
            x1 = x0 + step
            y1 = y0 + step
            inside = (x0 >= ORIGIN_X - 1.0 and y0 >= ORIGIN_Y - 1.0
                      and x1 <= ORIGIN_X + MAZE_WIDTH + 1.0
                      and y1 <= ORIGIN_Y + MAZE_HEIGHT + 1.0)
            if not inside:
                ground_tiles.append((x0, y0, x1, y1, GROUND_OUT))


def draw_ground():
    """The floor is coplanar, so it is drawn immediately (no depth sort)
    and its depth fog is added afterwards as one smooth screen gradient -
    see blit_ground_fog()."""
    for x0, y0, x1, y1, color in ground_tiles:
        # tiles overlap by 1 unit so no hairlines show between them
        c0 = to_cam((x0, y0, 0.0))
        c1 = to_cam((x1 + 1.0, y0, 0.0))
        c2 = to_cam((x1 + 1.0, y1 + 1.0, 0.0))
        c3 = to_cam((x0, y1 + 1.0, 0.0))
        if (c0[2] < NEAR or c1[2] < NEAR or c2[2] < NEAR or c3[2] < NEAR):
            continue
        if min(c0[2], c1[2], c2[2], c3[2]) > FOG_END:
            continue                      # lost in the fog anyway
        sx0, sy0 = project_pt(c0[0], c0[1], c0[2])
        sx1, sy1 = project_pt(c1[0], c1[1], c1[2])
        sx2, sy2 = project_pt(c2[0], c2[1], c2[2])
        sx3, sy3 = project_pt(c3[0], c3[1], c3[2])
        if max(sx0, sx1, sx2, sx3) < 0 or min(sx0, sx1, sx2, sx3) > WIDTH:
            continue
        if max(sy0, sy1, sy2, sy3) < 0 or min(sy0, sy1, sy2, sy3) > HEIGHT:
            continue
        pygame.draw.polygon(screen, color,
                            ((sx0, sy0), (sx1, sy1),
                             (sx2, sy2), (sx3, sy3)))


# one-column strip that gets scaled up into the ground fog gradient
fog_strip = pygame.Surface((1, HEIGHT), pygame.SRCALPHA)
fog_full = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)


def blit_ground_fog():
    """Because the floor is a plane, its depth only depends on the screen
    row.  So one smooth vertical gradient reproduces distance fog over the
    whole ground with zero banding."""
    for sy in range(0, HEIGHT, 3):
        dirz = cfz + cuz * ((CY - sy) / FOCAL)
        if dirz >= -1e-4:
            fog_strip.set_at((0, sy), (0, 0, 0, 0))
            continue
        depth = (-camz) / dirz
        f = (depth - FOG_START) * INV_FOG
        if f <= 0.0:
            a = 0
        elif f >= 1.0:
            a = 255
        else:
            a = int(f * 255)
        fog_strip.set_at((0, sy // 3), (FOG_COLOR[0], FOG_COLOR[1],
                                        FOG_COLOR[2], a))
    fog_strip.fill((FOG_COLOR[0], FOG_COLOR[1], FOG_COLOR[2], 0),
                   (0, (HEIGHT + 2) // 3, 1, HEIGHT))
    pygame.transform.smoothscale(fog_strip.subsurface((0, 0, 1, (HEIGHT + 2) // 3)),
                                 (WIDTH, HEIGHT), fog_full)
    screen.blit(fog_full, (0, 0))


# =========================================================
# GARDEN SCENERY  (bushes / rocks / flowers outside the maze)
# =========================================================
scenery = []
FLOWER_COLORS = ((252, 120, 160), (255, 216, 96), (150, 190, 255), (255, 160, 96))


def build_scenery():
    global scenery
    scenery = []
    tries = 0
    while len(scenery) < 54 and tries < 4000:
        tries += 1
        side = random.choice(("L", "R", "T", "B"))
        if side == "L":
            x = random.uniform(ORIGIN_X - 380, ORIGIN_X - 34)
            y = random.uniform(ORIGIN_Y - 200, ORIGIN_Y + MAZE_HEIGHT + 260)
        elif side == "R":
            x = random.uniform(ORIGIN_X + MAZE_WIDTH + 34,
                               ORIGIN_X + MAZE_WIDTH + 380)
            y = random.uniform(ORIGIN_Y - 200, ORIGIN_Y + MAZE_HEIGHT + 260)
        elif side == "T":
            x = random.uniform(ORIGIN_X - 380, ORIGIN_X + MAZE_WIDTH + 380)
            y = random.uniform(ORIGIN_Y - 320, ORIGIN_Y - 34)
        else:
            x = random.uniform(ORIGIN_X - 380, ORIGIN_X + MAZE_WIDTH + 380)
            y = random.uniform(ORIGIN_Y + MAZE_HEIGHT + 34,
                               ORIGIN_Y + MAZE_HEIGHT + 320)
        kind = random.choices(("bush", "rock", "flower", "tree"),
                              (6, 3, 3, 4))[0]
        scenery.append({
            "kind": kind,
            "pos": np.array([x, y]),
            "r": (random.uniform(9.0, 15.0) if kind == "bush"
                  else random.uniform(17.0, 26.0) if kind == "tree"
                  else random.uniform(6.0, 10.0)),
            "tint": random.uniform(-0.12, 0.12),
            "flower": random.choice(FLOWER_COLORS),
        })


def queue_scenery(t):
    for item in scenery:
        x, y = item["pos"]
        r = item["r"]
        tint = item["tint"]
        if to_cam((x, y, r))[2] > FOG_END * 0.72:
            continue                       # would float in the fog
        if item["kind"] == "tree":
            q_line((x, y, 0.0), (x, y + 3.0, r * 2.6), (92, 68, 44), 5.0, 0.8)
            base = tuple(int(c * (1 + tint)) for c in (48, 122, 62))
            light = (int(118 * (1 + tint)), 196, 108)
            dark = (16, 66, 30)
            for dz, rr in ((0.0, 1.0), (-0.5, 0.72), (0.45, 0.66)):
                q_sphere((x + dz * r * 0.8, y + 4.0, r * 2.5 + dz * 6.0),
                         r * rr, base, light, dark)
            queue_shadow(x, y, r * 0.55, 20.0)
            continue
        if item["kind"] == "bush":
            base = (int(60 * (1 + tint)), int(148 * (1 + tint)),
                    int(76 * (1 + tint)))
            light = (int(138 * (1 + tint)), 208, 118)
            dark = (18, 76, 32)
            for dx, dz, rr in ((-r * 0.6, 0.34, 0.78),
                               (r * 0.55, 0.30, 0.72),
                               (0.0, 0.62, 1.0)):
                q_sphere((x + dx, y + dz * r * 0.4, r * 0.55 + 1.0),
                         r * rr * 0.9, base, light, dark)
            queue_shadow(x, y, r * 0.8, r * 0.6)
        elif item["kind"] == "rock":
            q_sphere((x, y, r * 0.55), r * 0.95, (126, 130, 140),
                     (188, 194, 204), (58, 62, 74))
            q_sphere((x + r * 0.7, y, r * 0.30), r * 0.55, (138, 142, 152),
                     (196, 200, 210), (66, 70, 82))
            queue_shadow(x + r * 0.35, y, r * 0.9, r * 0.4)
        else:
            q_line((x, y, 0.0), (x, y + 1.0, 8.0), (72, 140, 66), 1.6)
            q_sphere((x, y + 1.0, 9.4), 2.8, item["flower"], None, None)


# =========================================================
# MAZE WALL RENDERING  (3D boxes: top + visible sides)
# =========================================================
def queue_walls():
    camx = cam_pos[0]
    camy = cam_pos[1]
    for bx0, by0, bx1, by1, top_color in wall_boxes:
        # cheap range cull before doing any projection
        cxm = (bx0 + bx1) * 0.5
        cym = (by0 + by1) * 0.5
        dx = cxm - camx
        dy = cym - camy
        if dy < -140.0 or dy > FOG_END * 0.75:
            continue
        if abs(dx) > dy * 2.4 + 500.0:
            continue
        # top face (lit by the sun from above)
        q_world_quad((bx0, by0, WALL_H), (bx1, by0, WALL_H),
                     (bx1, by1, WALL_H), (bx0, by1, WALL_H),
                     top_color, 1.04, WALL_RIM, 0.42)
        # side facing the camera
        if camy < by0:
            q_world_quad((bx0, by0, 0.0), (bx1, by0, 0.0),
                         (bx1, by0, WALL_H), (bx0, by0, WALL_H),
                         WALL_FRONT, 0.88)
        elif camy > by1:
            q_world_quad((bx1, by1, 0.0), (bx0, by1, 0.0),
                         (bx0, by1, WALL_H), (bx1, by1, WALL_H),
                         WALL_BACK, 0.50)
        # soft contact shadow on the floor so the walls feel grounded
        if camy < by0 and dy < 900.0:
            q_world_quad((bx0, by0 - 11.0, 0.10), (bx1, by0 - 11.0, 0.10),
                         (bx1, by0, 0.10), (bx0, by0, 0.10),
                         WALL_SHADOW, 1.0)
        # left / right sides, only when the camera is on that side
        if camx < bx0:
            q_world_quad((bx0, by1, 0.0), (bx0, by0, 0.0),
                         (bx0, by0, WALL_H), (bx0, by1, WALL_H),
                         WALL_LEFT, 0.72)
        elif camx > bx1:
            q_world_quad((bx1, by0, 0.0), (bx1, by1, 0.0),
                         (bx1, by1, WALL_H), (bx1, by0, WALL_H),
                         WALL_RIGHT, 0.62)


def queue_wall_decor():
    for x, y, r, color in wall_decor:
        if to_cam((x, y, WALL_H))[2] > FOG_END * 0.75:
            continue
        q_sphere((x, y, WALL_H + r * 0.7), r, color,
                 tuple(min(255, c + 60) for c in color),
                 tuple(max(0, c - 90) for c in color))


# =========================================================
# COLLISION  (2D on the floor plane - unchanged behaviour)
# =========================================================
def circle_hits_wall(pos, radius):
    for wall in wall_rectangles:
        cx = max(wall.left, min(pos[0], wall.right))
        cy = max(wall.top, min(pos[1], wall.bottom))
        dx = pos[0] - cx
        dy = pos[1] - cy
        if dx * dx + dy * dy < radius * radius:
            return True
    return False


def move_player(direction, dt):
    movement = direction * BALL_SPEED * dt
    max_step = max(2.0, WALL_T * 0.4)
    steps = max(1, math.ceil(max(abs(movement[0]), abs(movement[1])) / max_step))
    sx = movement[0] / steps
    sy = movement[1] / steps
    for _ in range(steps):
        newp = position.copy()
        newp[0] += sx
        if not circle_hits_wall(newp, BALL_RADIUS):
            position[0] = newp[0]
        newp = position.copy()
        newp[1] += sy
        if not circle_hits_wall(newp, BALL_RADIUS):
            position[1] = newp[1]


# =========================================================
# FLAGS  (3D poles + cloth built from quads)
# =========================================================
def queue_flag_pole(x, y, h, world_w=3.2):
    q_line((x, y, 0.0), (x, y, h), (92, 70, 44), world_w, 0.85)
    q_sphere((x, y, h + 3.0), 3.4, GOLD, (255, 240, 160), (150, 96, 12))


def queue_start_flag(x, y):
    h = 62.0
    queue_flag_pole(x, y, h)
    t = pygame.time.get_ticks() / 1000.0
    # cloth: 6 columns x 3 rows of quads, waving in the depth axis
    cw, ch, rows, colsn = 20.0, 15.0, 3, 5
    for i in range(colsn):
        for j in range(rows):
            u0, u1 = i / colsn, (i + 1) / colsn
            v0, v1 = j / rows, (j + 1) / rows
            def pt(u, v):
                w = math.sin(t * 4.2 - u * 3.0) * (6.0 * u)
                return (x + 3.0 + u * cw, y + w,
                        h - 4.0 - v * ch + math.sin(t * 4.2 - u * 3.0) * 1.4 * u)
            shade = 1.0 if (j + i) % 2 == 0 else 0.92
            q_world_quad(pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1),
                         START_GREEN, shade)


def queue_finish_flag(x, y):
    h = 62.0
    queue_flag_pole(x, y, h)
    t = pygame.time.get_ticks() / 1000.0
    cw, ch, rows, colsn = 26.0, 18.0, 4, 5
    for i in range(colsn):
        for j in range(rows):
            u0, u1 = i / colsn, (i + 1) / colsn
            v0, v1 = j / rows, (j + 1) / rows
            def pt(u, v):
                w = math.sin(t * 4.2 + u * 2.2) * (7.0 * u)
                return (x + 3.0 + u * cw, y + w,
                        h - 4.0 - v * ch + math.sin(t * 4.2 + u * 1.1) * 1.6 * u)
            color = CHECK_WHITE if (i + j) % 2 == 0 else CHECK_BLACK
            q_world_quad(pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1),
                         color, 1.0 if color == CHECK_WHITE else 0.85)


def queue_flags():
    sc = cell_center(START_CELL)
    fc = cell_center(FINISH_CELL)
    queue_start_flag(sc[0] - CELL * 0.46, sc[1] + 8.0)
    queue_finish_flag(fc[0], fc[1])


# =========================================================
# PLAYER WORM  (3D chain of shaded spheres + eyes)
# =========================================================
def jump_height():
    if jump_timer <= 0:
        return 0.0
    p = 1.0 - (jump_timer / JUMP_DURATION)
    return math.sin(p * math.pi) * JUMP_HEIGHT


def queue_shadow(x, y, radius, lift):
    k = max(0.30, 1.0 - lift * 0.011)
    q_disc((x, y, 0.35), radius * 1.10 * k, SHADOW_2, 1.0, 12)
    q_disc((x, y, 0.45), radius * 0.78 * k, SHADOW_1, 1.0, 12)


def queue_worm(t):
    lift = jump_height()
    hx, hy = position[0], position[1]
    base_z = BALL_RADIUS * 0.92 + lift
    side = np.array([facing[1], -facing[0], 0.0])
    fwd3 = np.array([facing[0], facing[1], 0.0])

    queue_shadow(hx, hy, BALL_RADIUS, lift)

    # body segments, trailing behind the facing direction
    offsets = [(10.0, 9.6, 1), (19.5, 8.8, 2), (29.0, 7.6, 3), (38.0, 6.4, 4)]
    for k, (dist, rad, idx) in enumerate(reversed(offsets)):
        wig = math.sin(t * 8.0 - idx * 1.55) * (2.0 + idx * 0.9)
        seg = np.array([hx, hy, 0.0]) - fwd3 * dist + side * wig
        seg[2] = base_z * (1.0 - idx * 0.10) + math.sin(t * 9.0 - idx * 1.15) * 1.3
        q_sphere(tuple(seg), rad, WORM_MID, WORM_LIGHT, WORM_DARK)

    head = (hx, hy, base_z + 1.0)
    q_sphere(head, BALL_RADIUS, WORM_MID, WORM_LIGHT, WORM_DARK, outline=True)

    # eyes: two white balls + pupils, placed relative to facing
    up3 = np.array([0.0, 0.0, 1.0])
    for s in (-1.0, 1.0):
        eye = (np.array(head) + fwd3 * 7.0 + side * (4.6 * s) + up3 * 4.2)
        q_sphere(tuple(eye), 3.4, WHITE, (255, 255, 255), (150, 168, 190))
        pupil = eye + fwd3 * 2.2 + up3 * 0.6
        q_sphere(tuple(pupil), 1.7, INK, (60, 80, 100), (0, 0, 0))


# =========================================================
# BIRDS  (fly above the worm, 3D wings + shadow)
# =========================================================
enemies = []


def get_available_neighbors(cell):
    x, y = cell
    out = []
    for direction, (dx, dy, _) in DIRECTIONS.items():
        if not maze[y][x]["walls"][direction]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                out.append((nx, ny))
    return out


def generate_enemies():
    global enemies
    enemies = []
    count = min(2 + level, 8)
    available = [(x, y) for y in range(ROWS) for x in range(COLS)
                 if (x, y) != START_CELL and (x, y) != FINISH_CELL
                 and (x, y) not in water_hole_cells]
    random.shuffle(available)
    for cell in available[:count]:
        neighbors = get_available_neighbors(cell)
        if not neighbors:
            continue
        enemies.append({
            "cell": cell,
            "target": random.choice(neighbors),
            "previous": cell,
            "pos": cell_center(cell),
            "dir": np.array([1.0, 0.0]),
            "speed": ENEMY_SPEED + random.uniform(-10, 20),
            "phase": random.uniform(0, math.tau),
        })


def update_enemies(dt):
    for enemy in enemies:
        current = enemy["pos"]
        target = cell_center(enemy["target"])
        delta = target - current
        dist = np.linalg.norm(delta)
        if dist <= 2.0:
            enemy["pos"] = target.copy()
            enemy["previous"] = enemy["cell"]
            enemy["cell"] = enemy["target"]
            neighbors = get_available_neighbors(enemy["cell"])
            if neighbors:
                alts = [n for n in neighbors if n != enemy["previous"]]
                choices = alts if alts else neighbors
                enemy["target"] = random.choice(choices)
        else:
            d = delta / dist
            enemy["dir"] = d
            step = enemy["speed"] * dt
            if step >= dist:
                enemy["pos"] = target.copy()
            else:
                enemy["pos"] += d * step


def queue_enemies(t):
    for enemy in enemies:
        x, y = enemy["pos"]
        z = BIRD_ALTITUDE + math.sin(t * 3.2 + enemy["phase"]) * 3.5
        d = enemy["dir"]
        fwd3 = np.array([d[0], d[1], 0.0])
        side3 = np.array([d[1], -d[0], 0.0])
        up3 = np.array([0.0, 0.0, 1.0])
        center = np.array([x, y, z])

        queue_shadow(x, y, 9.0, z)

        # wings: flapping quads
        flap = math.sin(t * 11.0 + enemy["phase"]) * 8.0
        for s in (-1.0, 1.0):
            inner_f = center + fwd3 * 4.0 + side3 * (2.0 * s)
            inner_b = center - fwd3 * 5.0 + side3 * (2.0 * s)
            tip = center + side3 * (19.0 * s) + up3 * (flap * s)
            q_tri(inner_f, inner_b, tip, BIRD_WING, 0.95 if s > 0 else 0.82)
            q_tri(inner_b, tip, center - fwd3 * 8.0 + side3 * (10.0 * s) + up3 * (flap * 0.7 * s),
                  BIRD_WING_D, 0.9)
        # tail
        q_tri(center - fwd3 * 6.0 + side3 * 3.0,
              center - fwd3 * 6.0 - side3 * 3.0,
              center - fwd3 * 17.0, BIRD_WING_D, 0.85)
        # body + head
        q_sphere(tuple(center), 8.2, BIRD_BODY, (110, 100, 150), (26, 22, 40))
        head = center + fwd3 * 8.0 + up3 * 1.5
        q_sphere(tuple(head), 6.6, BIRD_BODY, (110, 100, 150), (26, 22, 40))
        # beak
        q_tri(head + fwd3 * 5.0 + side3 * 2.4,
              head + fwd3 * 5.0 - side3 * 2.4,
              head + fwd3 * 13.0, BIRD_BEAK, 1.05)
        # eye
        for s in (-1.0, 1.0):
            eye = head + fwd3 * 3.0 + side3 * (3.3 * s) + up3 * 2.0
            q_sphere(tuple(eye), 2.4, WHITE, (255, 255, 255), (120, 130, 150))
            q_sphere(tuple(eye + fwd3 * 1.2), 1.1, INK, (40, 40, 60), (0, 0, 0))


def check_enemy_collision():
    if height > 10.0:
        return False     # jumped over the birds
    for enemy in enemies:
        if np.linalg.norm(position - enemy["pos"]) < BALL_RADIUS + ENEMY_RADIUS - 3.0:
            reset_ball()
            return True
    return False


# =========================================================
# APPLES  (3D spheres with stem, leaf and shadow)
# =========================================================
medals = []


def generate_medals():
    global medals
    medals = []
    available = []
    for y in range(ROWS):
        for x in range(COLS):
            cell = (x, y)
            if cell in (START_CELL, FINISH_CELL) or cell in water_hole_cells:
                continue
            available.append(cell)
    random.shuffle(available)
    rewards = [("ruby", RUBY_VALUE), ("ruby", RUBY_VALUE),
               ("ruby", RUBY_VALUE), ("gold", GOLD_VALUE)]
    for cell, reward in zip(available, rewards):
        medals.append({
            "pos": cell_center(cell),
            "type": reward[0],
            "value": reward[1],
            "phase": random.uniform(0, math.tau),
            "collected": False,
        })


def update_medals():
    global score, collected_medals
    for medal in medals:
        if medal["collected"]:
            continue
        if np.linalg.norm(position - medal["pos"]) < BALL_RADIUS + 13.0:
            medal["collected"] = True
            score += medal["value"]
            collected_medals += 1
            create_firework((medal["pos"][0], medal["pos"][1], 20.0))


def queue_medals(t):
    for medal in medals:
        if medal["collected"]:
            continue
        x, y = medal["pos"]
        bob = math.sin(t * 2.6 + medal["phase"]) * 3.5
        z = 15.0 + bob
        if medal["type"] == "ruby":
            base, light, dark = APPLE_RED, APPLE_RED_L, APPLE_RED_D
        else:
            base, light, dark = APPLE_GOLD, APPLE_GOLD_L, APPLE_GOLD_D

        queue_shadow(x, y, 8.0, z)
        q_sphere((x, y, z), 9.4, base, light, dark, outline=True)
        # stem + leaf
        q_line((x, y, z + 8.0), (x, y + 1.0, z + 16.0), (96, 64, 30), 2.6)
        lx, ly = x + 5.0, y + 0.5
        q_world_quad(
            (lx, ly, z + 15.0), (lx + 8.0, ly, z + 13.6),
            (lx + 9.0, ly + 2.0, z + 16.6), (lx, ly + 2.0, z + 18.0),
            (66, 176, 84), 1.0)


# =========================================================
# LEVEL SYSTEM
# =========================================================
def generate_level():
    global collected_medals, spark_timer, start_time
    reset_ball()
    collected_medals = 0
    spark_timer = 0.0
    particles.clear()
    generate_maze()
    build_wall_geometry()
    build_ground()
    build_scenery()
    generate_water_holes()
    generate_medals()
    generate_enemies()
    start_time = time.time()


def complete_level():
    global level
    level += 1
    generate_level()


def reset_ball():
    global spark_timer, jump_timer, jump_cooldown, height
    position[:] = START_POSITION
    spark_timer = 0.0
    jump_timer = 0.0
    jump_cooldown = 0.0
    height = 0.0


def start_jump():
    global jump_timer, jump_cooldown
    if jump_timer <= 0 and jump_cooldown <= 0:
        jump_timer = JUMP_DURATION
        jump_cooldown = JUMP_COOLDOWN


def check_finish():
    if np.linalg.norm(position - cell_center(FINISH_CELL)) < 19.0:
        if collected_medals == TOTAL_MEDALS:
            complete_level()
        else:
            reset_ball()


# =========================================================
# MOUSE -> WORLD  (ray / ground-plane intersection)
# =========================================================
def screen_to_ground(mx, my):
    cx = (mx - CX) / FOCAL
    cy = -(my - CY) / FOCAL
    d = CAM_RGT * cx + CAM_UP * cy + CAM_FWD
    if abs(d[2]) < 1e-6:
        return None
    t = -cam_pos[2] / d[2]
    if t <= 0 or t > 4000:
        return None
    return cam_pos + d * t


# =========================================================
# USER INTERFACE  (2D overlay on top of the 3D scene)
# =========================================================
hud_panel = pygame.Surface((WIDTH - 40, 62), pygame.SRCALPHA)
pygame.draw.rect(hud_panel, (10, 20, 30, 176), hud_panel.get_rect(),
                 border_radius=14)
hud_bar = pygame.Surface((WIDTH - 40, 3), pygame.SRCALPHA)
pygame.draw.rect(hud_bar, (120, 220, 150, 120), hud_bar.get_rect(),
                 border_radius=2)


def draw_text(text, font_obj, color, pos, shadow=True):
    if shadow:
        sh = font_obj.render(text, True, (8, 14, 20))
        screen.blit(sh, (pos[0] + 1, pos[1] + 1))
    screen.blit(font_obj.render(text, True, color), pos)


def draw_minimap():
    mw, mh = 246, 168
    mx, my = WIDTH - mw - 22, HEIGHT - mh - 22
    panel = pygame.Surface((mw, mh), pygame.SRCALPHA)
    pygame.draw.rect(panel, (8, 16, 24, 168), panel.get_rect(), border_radius=12)
    pygame.draw.rect(panel, (120, 190, 150, 90), panel.get_rect(), 1,
                     border_radius=12)
    screen.blit(panel, (mx, my))

    sx = (mw - 24) / MAZE_WIDTH
    sy = (mh - 30) / MAZE_HEIGHT
    ox, oy = mx + 12, my + 18

    def mp(wx, wy):
        return (ox + (wx - ORIGIN_X) * sx, oy + (wy - ORIGIN_Y) * sy)

    # walls
    for bx0, by0, bx1, by1, _ in wall_boxes:
        p0 = mp(bx0, by0)
        p1 = mp(bx1, by1)
        pygame.draw.rect(screen, (86, 118, 96),
                         pygame.Rect(p0[0], p0[1], max(1, p1[0] - p0[0]),
                                     max(1, p1[1] - p0[1]))
                         , 0)
    # apples
    for medal in medals:
        if medal["collected"]:
            continue
        p = mp(medal["pos"][0], medal["pos"][1])
        c = (230, 66, 74) if medal["type"] == "ruby" else (255, 200, 60)
        pygame.draw.circle(screen, c, (int(p[0]), int(p[1])), 3)
    # finish
    pf = mp(ORIGIN_X + COLS * CELL - 8.0, ORIGIN_Y + FINISH_CELL[1] * CELL + CELL * 0.5)
    pygame.draw.rect(screen, (255, 240, 240),
                     pygame.Rect(int(pf[0] - 3), int(pf[1] - 3), 6, 6))
    # player
    pp = mp(position[0], position[1])
    pygame.draw.circle(screen, (120, 255, 150), (int(pp[0]), int(pp[1])), 3)
    pygame.draw.circle(screen, (12, 20, 28), (int(pp[0]), int(pp[1])), 4, 1)
    draw_text("MAP", tiny_font, (170, 220, 190), (mx + 14, my + 5))


def draw_ui(dt):
    global projection, fog_enabled, view_mode, quality
    screen.blit(hud_panel, (20, 12))
    screen.blit(hud_bar, (20, 73))

    draw_text(f"LEVEL {level}", font, WHITE, (40, 26))
    draw_text(f"SCORE {score}", font, GOLD, (190, 26))
    draw_text(f"APPLES {collected_medals}/{TOTAL_MEDALS}", font,
              (255, 140, 140), (350, 26))

    elapsed = time.time() - start_time
    draw_text(f"TIME {int(elapsed // 60):02}:{int(elapsed % 60):02}",
              font, WHITE, (550, 26))

    fps_color = (150, 240, 170) if dt < 0.021 else (255, 170, 120)
    draw_text(f"{int(1 / max(dt, 1e-4))} FPS", small_font, fps_color, (760, 29))

    # height meter while airborne
    if height > 0.5:
        ratio = height / JUMP_HEIGHT
        bx, by = 1050, 26
        pygame.draw.rect(screen, (30, 46, 40), (bx, by, 120, 12), border_radius=6)
        pygame.draw.rect(screen, (120, 240, 170),
                         (bx, by, int(120 * ratio), 12), border_radius=6)
        draw_text("HEIGHT", tiny_font, (170, 230, 200), (bx + 122, by - 4))

    qname = {1: "FAST", 2: "BALANCED", 3: "HIGH"}[quality]
    draw_text(f"{projection.upper()}  |  VIEW {view_mode + 1}  |  "
              f"FOG {'ON' if fog_enabled else 'OFF'}  |  {qname}",
              tiny_font, (170, 190, 180), (40, HEIGHT - 48))

    draw_text("WASD MOVE  SPACE JUMP  CLICK FIREWORKS  P PROJECTION  F FOG  "
              "1/2/3 VIEW  F5 QUALITY  R RESTART",
              small_font, (220, 238, 228), (40, HEIGHT - 30))

    if collected_medals < TOTAL_MEDALS:
        msg = f"Collect all {TOTAL_MEDALS} apples to unlock the checkered exit"
        col = GOLD
    else:
        msg = "EXIT UNLOCKED - reach the checkered flag!"
        col = (120, 255, 160)
    mt = small_font.render(msg, True, col)
    sh = small_font.render(msg, True, (8, 14, 20))
    screen.blit(sh, (WIDTH // 2 - mt.get_width() // 2 + 1, 83))
    screen.blit(mt, (WIDTH // 2 - mt.get_width() // 2, 82))

    draw_minimap()


# =========================================================
# START
# =========================================================
generate_level()


# =========================================================
# MAIN LOOP
# =========================================================
def main(max_frames=None):
    global jump_timer, jump_cooldown, height
    global score, level, facing, spark_timer
    global projection, fog_enabled, view_mode, quality
    running = True
    frames = 0
    t_accum = 0.0

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        t_accum += dt
        frames += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                ground = screen_to_ground(*event.pos)
                if ground is not None:
                    create_firework((
                        min(max(ground[0], ORIGIN_X), ORIGIN_X + MAZE_WIDTH),
                        min(max(ground[1], ORIGIN_Y), ORIGIN_Y + MAZE_HEIGHT),
                        4.0,
                    ))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    start_jump()
                if event.key == pygame.K_r:
                    score = 0
                    level = 1
                    generate_level()
                if event.key == pygame.K_p:
                    projection = ("orthographic"
                                  if projection == "perspective" else "perspective")
                if event.key == pygame.K_f:
                    fog_enabled = not fog_enabled
                if event.key == pygame.K_1:
                    view_mode = 0
                if event.key == pygame.K_2:
                    view_mode = 1
                if event.key == pygame.K_3:
                    view_mode = 2
                if event.key == pygame.K_F5:
                    quality = quality % 3 + 1

        # ---- update ----
        if jump_timer > 0:
            jump_timer = max(0.0, jump_timer - dt)
        if jump_cooldown > 0:
            jump_cooldown = max(0.0, jump_cooldown - dt)
        height = jump_height()

        keys = pygame.key.get_pressed()
        direction = np.array([0.0, 0.0])
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            direction[1] += 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            direction[1] -= 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            direction[0] -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            direction[0] += 1

        moving = np.linalg.norm(direction) > 0
        if moving:
            direction /= np.linalg.norm(direction)
            facing += (direction - facing) * 0.22
            if np.linalg.norm(facing) > 1e-4:
                facing /= np.linalg.norm(facing)
            move_player(direction, dt)
            spark_timer += dt
            while spark_timer >= SPARK_INTERVAL:
                create_spark((position[0], position[1], height + BALL_RADIUS))
                spark_timer -= SPARK_INTERVAL
        else:
            spark_timer = 0.0

        check_water_collision()
        update_enemies(dt)
        check_enemy_collision()
        update_medals()
        check_finish()
        update_particles(dt)
        update_camera(dt, t_accum)

        # ---- render ----
        draw_sky(t_accum)
        draw_ground()
        blit_ground_fog()
        queue_walls()
        queue_wall_decor()
        if quality > 1:
            queue_scenery(t_accum)
        queue_water(t_accum)
        queue_flags()
        queue_medals(t_accum)
        queue_enemies(t_accum)
        queue_worm(t_accum)
        queue_particles()
        flush_queue()
        draw_ui(dt)
        pygame.display.flip()

        if max_frames is not None and frames >= max_frames:
            running = False

    pygame.quit()


if __name__ == "__main__":
    main()
