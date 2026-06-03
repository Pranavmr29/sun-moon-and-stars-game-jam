# Claude's CRT shader starts
import pygame
import moderngl
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────
WINDOW_SIZE = (800, 600)
GAME_RES    = (320, 240)   # low-res game surface — CRT effect looks best here

# ── Init ────────────────────────────────────────────────────────────────────
pygame.init()
pygame.display.set_mode(WINDOW_SIZE, pygame.OPENGL | pygame.DOUBLEBUF)
pygame.display.set_caption("CRT demo")

ctx = moderngl.create_context()

# ── Game surface (low res, drawn normally with pygame) ──────────────────────
game_surface = pygame.Surface(GAME_RES)

# ── Texture ─────────────────────────────────────────────────────────────────
texture = ctx.texture(GAME_RES, 4)
texture.filter = (moderngl.LINEAR, moderngl.LINEAR)  # LINEAR for smooth CRT blur

# ── Shaders ─────────────────────────────────────────────────────────────────
with open("quad.vert") as f:
    vert_src = f.read()
with open("crt.frag") as f:
    frag_src = f.read()

program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
program["Texture"]    = 0
program["resolution"] = WINDOW_SIZE   # shader works in output pixel space

# ── Fullscreen quad ──────────────────────────────────────────────────────────
vertices = np.array([
    # pos (x,y)   uv (u,v)
    -1.0, -1.0,   0.0, 0.0,
     1.0, -1.0,   1.0, 0.0,
    -1.0,  1.0,   0.0, 1.0,

    -1.0,  1.0,   0.0, 1.0,
     1.0, -1.0,   1.0, 0.0,
     1.0,  1.0,   1.0, 1.0,
], dtype="f4")

vbo = ctx.buffer(vertices.tobytes())
vao = ctx.vertex_array(program, [(vbo, "2f 2f", "in_pos", "in_uv")])

# ── Game state ───────────────────────────────────────────────────────────────
clock = pygame.time.Clock()
x     = 30.0
speed = 1.5
font  = pygame.font.SysFont(None, 16)

# ── Loop ─────────────────────────────────────────────────────────────────────
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # ── Draw game at low resolution ──────────────────────────────────────────
    game_surface.fill((15, 15, 35))

    # Fake starfield
    rng = np.random.default_rng(42)
    for sx, sy in rng.integers(0, [GAME_RES[0], GAME_RES[1]], size=(60, 2)):
        game_surface.set_at((sx, sy), (200, 200, 220))

    # Bouncing ball
    pygame.draw.circle(game_surface, (255, 230, 80), (int(x), GAME_RES[1]//2), 14)
    pygame.draw.circle(game_surface, (255, 255, 180), (int(x)-4, GAME_RES[1]//2-4), 5)

    # Some colourful rectangles so the mask is visible
    pygame.draw.rect(game_surface, (200, 50, 50),  (10, 10, 40, 20))
    pygame.draw.rect(game_surface, (50, 200, 50),  (60, 10, 40, 20))
    pygame.draw.rect(game_surface, (50, 50, 200),  (110, 10, 40, 20))
    pygame.draw.rect(game_surface, (200, 200, 200),(160, 10, 40, 20))

    fps_surf = font.render(f"{clock.get_fps():.0f} fps", True, (0, 255, 0))
    game_surface.blit(fps_surf, (2, GAME_RES[1] - 14))

    x += speed
    if x > GAME_RES[0] - 20 or x < 20:
        speed *= -1

    # ── Upload to GPU ────────────────────────────────────────────────────────
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)

    ctx.clear(0.0, 0.0, 0.0)
    vao.render()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
# Claude's CRT shader ends