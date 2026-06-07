"""
TODO:
FIX MOUSE WARP OFFSET
Add multiple missiles
Add planets/missile into tutorial
Add buttons to leave tutorial and go back to home
level progression
comments
powerups (black/white hole and thrusters and nudgers)
"""
#Import libraries
#region imports
import pygame
import sys
import random
import math
import moderngl
import numpy as np
from enum import Enum

#This section code was created using Claude for the CRT visual effects. Sections created using Claude are within the hyphen lines
#region CRT
#------------------------------------------------------------------------------------------
#Sets the window and game resolution, initializes Pygame and creates an OpenGL window mode
WINDOW_SIZE = (1150, 640)
GAME_RES = (1150, 640)

# ── Init ────────────────────────────────────────────────────────────────────
pygame.init()
pygame.display.set_mode(WINDOW_SIZE, pygame.OPENGL | pygame.DOUBLEBUF)

#Creates ModernGL context (interface to GPU)
ctx = moderngl.create_context()

# ── Game surface (low res, drawn normally with pygame) ──────────────────────
#Creates a pygame surface that's drawn on normally before being sent to GPU
game_surface = pygame.Surface(GAME_RES)

# ── Texture ─────────────────────────────────────────────────────────────────
#Creates a GPU texture to hold the game surface. 4 means RGBA and linear causes smooth sampling rather than pixelating
texture = ctx.texture(GAME_RES, 4)
texture.filter = (moderngl.LINEAR, moderngl.LINEAR)  # LINEAR for smooth CRT blur

# ── Shaders ─────────────────────────────────────────────────────────────────
#Reads the shader files
with open("quad.vert") as f:
    vert_src = f.read()
with open("crt.frag") as f:
    frag_src = f.read()

#Compiles the shaders to a GPU program and sets the two uniforms
program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
program["Texture"] = 0
program["resolution"] = WINDOW_SIZE   # shader works in output pixel space

# ── Fullscreen quad ──────────────────────────────────────────────────────────
#Defines 2 triangles that cover the screen together; each vertex has position and UV coordinates
vertices = np.array([
    # pos (x,y)   uv (u,v)
    -1.0, -1.0,   0.0, 0.0,
     1.0, -1.0,   1.0, 0.0,
    -1.0,  1.0,   0.0, 1.0,

    -1.0,  1.0,   0.0, 1.0,
     1.0, -1.0,   1.0, 0.0,
     1.0,  1.0,   1.0, 1.0,
], dtype="f4")

#Uploads vertex data to GPU and tells the GPU how to read the VBO - 2 floats for position and UV each
vbo = ctx.buffer(vertices.tobytes())
vao = ctx.vertex_array(program, [(vbo, "2f 2f", "in_pos", "in_uv")])

# ── Game state ───────────────────────────────────────────────────────────────
#Control framerate with clock and set other game state variables
clock = pygame.time.Clock()
x = 30.0
speed = 1.5
font = pygame.font.SysFont(None, 16)
# Claude's CRT shader ends
#----------------------------------- CONSTANTS -----------------------------------#
#region constants
G = 0.2
LAUNCH_MULT = 0.02
PREDICT_STEPS = 50
TRAIL_MAX = 100
MISSILE_W = 36
MISSILE_H = 36
MIN_DIST = 75
class GameStates(Enum):
    TRANSITION_TO_HOME = "T_HOME"
    HOME = "HOME"
    TRANSITION_TO_TUTORIAL = "T_TUTORIAL"
    TUTORIAL = "TUTORIAL"
    TRANSITION_TO_GAME = "T_GAME"
    GAME = "GAME"

#the screen warp causes innacuracies in getting mouse position
#so use these constants to line up mouse position with visual position of each button
#only needed for corner and edge buttons because the warp is the most there
# x1, x2, y1, y2
HOME_BTN   = (995, 1064, 531, 598)
RESET_BTN   = (97, 154, 530, 587)
#----------------------------------- OTHER VARIABLES -----------------------------------#
#region variables
showText = True
currState = GameStates.TRANSITION_TO_HOME
timer = 0
reset = False

syncPlayButton = True
syncTutorialButton = True
syncHomeButton = True
syncResetButton = True
#----------------------------------- CLASSES -----------------------------------#
#region classes
#base class for all physics based objects
#region Body
class Body:
    #grav attractor, pass True to keep anchored
    def __init__(self, mass, x, y, vx, vy, radius, surface, anchor = False):
        self.mass = mass
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.radius = radius
        self.surface = surface
        self.trail: list[tuple[int, int]] = []
        self.anchor = anchor
        self.sprite_w = surface.get_width() / 2
        self.sprite_h = surface.get_height() / 2

    @property
    def cx(self):
        return self.x + self.sprite_w / 2
    @property
    def cy(self):
        return self.y + self.sprite_h / 2
    
    def update(self, others: list["Body"]):
        #Integrate gravity from all other planets, skips if anchored
        if self.anchor:
            return
        fx, fy = self.gravity_from(others)
        self.vx += fx / self.mass
        self.vy += fy / self.mass
        self.x += self.vx
        self.y += self.vy

    def gravity_from(self, others):
        #returns total grav force fx,fy on this body by every other body in others
        total_fx = 0.0
        total_fy = 0.0
        for o in others:
            dx = o.cx - self.cx
            dy = o.cy - self.cy
            dist = max(math.hypot(dx, dy), MIN_DIST)
            scale = G * o.mass * self.mass / dist ** 3
            total_fx += scale * dx
            total_fy += scale * dy
        return total_fx, total_fy
    
    def record_trail(self, offset_x = 0, offset_y = 0):
        self.trail.append((int(self.x) + offset_x, int(self.y) + offset_y))
        if len(self.trail) > TRAIL_MAX:
            self.trail.pop(0)
    
    def draw_trail(self, surface, color=(160, 2, 2)):
        if len(self.trail) > 1:
            pygame.draw.lines(surface, color, False, list(self.trail), 1)

    def draw(self, surface):
        surface.blit(self.surface, (int(self.x), int(self.y)))
    
#region Missile
class Missile(Body):
    #player controlled missile
    LAUNCH = "LAUNCH"
    FREE = "FREE"
 
    def __init__(self, x, y, image):
        super().__init__(mass=1, x=x, y=y, vx=0, vy=0, radius=2, surface=image)
        self.state = Missile.LAUNCH
        self.mask = pygame.mask.from_surface(image)
    
    def update(self, planets: list[Body]):
        if self.state != Missile.FREE:
            return
        fx, fy = self.gravity_from(planets)
        self.vx += fx / self.mass
        self.vy += fy / self.mass
        self.x += self.vx
        self.y += self.vy

    def launch(self, start_pos, end_pos):
        self.vx, self.vy = ((start_pos[i] - end_pos[i]) * LAUNCH_MULT for i in (0, 1))
        self.state = Missile.FREE
    
    def reset(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.trail.clear()
        self.state = Missile.LAUNCH
    
    def blit_rotated(self, surface, angle):
        rotated = pygame.transform.rotate(self.surface, -angle - 90)
        surface.blit(rotated, rotated.get_rect(center=(self.x + MISSILE_W/2, self.y + MISSILE_H/2)))

    def draw(self, surface):
        angle = math.degrees(math.atan2(self.vy, self.vx)) if (self.vx or self.vy) else 0
        self.blit_rotated(surface, angle)
 
    def draw_aimed(self, surface, drag_dx, drag_dy):
        self.blit_rotated(surface, math.degrees(math.atan2(drag_dy, drag_dx)))

#region Target
class Target:
    #the target the missile needs to hit
    UNHIT = "UNHIT"
    HIT = "HIT"
 
    def __init__(self, x, y, surface):
        self.x = x
        self.y = y
        self.surface = surface
        self.mask = pygame.mask.from_surface(surface)
        self.state = Target.UNHIT

    def check_hit(self, missile: Missile):
        offset = (int(missile.x - self.x), int(missile.y - self.y))
        return self.mask.overlap(missile.mask, offset) is not None

    def reset(self, x = 0, y = 0):
        if x == 0: self.x = random.randint(50, 1100)
        else: self.x = x
        if y == 0: self.y = random.randint(50, 600)
        else: self.y = y
        self.state = Target.UNHIT

    def draw(self, surface):
        if self.state == Target.UNHIT:
            surface.blit(self.surface, (self.x, self.y))
#----------------------------------- FUNCTIONS/HELPERS -----------------------------------#
#region functions
def draw_launch_line(surface, missile: Missile, planets: list[Body],
                     start_pos, current_pos):
    #Project and draw the predicted flight path while dragging
    drag_dx = start_pos[0] - current_pos[0]
    drag_dy = start_pos[1] - current_pos[1]
 
    vx = drag_dx * LAUNCH_MULT
    vy = drag_dy * LAUNCH_MULT
    px = missile.x + MISSILE_W / 2
    py = missile.y + MISSILE_H / 2
 
    pygame.draw.circle(surface, (255, 0, 0), (int(px), int(py)), 3)
 
    points = []
    for step in range(PREDICT_STEPS):
        fx = fy = 0.0
        for p in planets:
            dx, dy = p.x - px, p.y - py
            dist = max(math.hypot(dx, dy), MIN_DIST)
            scale = G * p.mass * missile.mass / dist ** 3
            fx += scale * dx
            fy += scale * dy
 
        vx += fx / missile.mass
        vy += fy / missile.mass
        px += vx
        py += vy
 
        if step % 4 == 0:
            points.append((int(px), int(py)))
 
    if len(points) > 1:
        pygame.draw.lines(surface, (255, 1, 1), False, points, 2)

def in_bounds(mx, my, bounds):
    x1, x2, y1, y2 = bounds
    return x1 < mx < x2 and y1 < my < y2
#----------------------------------- ASSETS -----------------------------------#
#region assets
missile_image = pygame.transform.scale(pygame.image.load("images/redscale spaceship with flames 1.png").convert_alpha(), (MISSILE_W, MISSILE_H))
target_surface = pygame.transform.scale(pygame.image.load("images/redscale target x.png").convert_alpha(), (MISSILE_W, MISSILE_H))

background_stars = [(random.randint(1, 3), (random.randint(1, 1150), random.randint(1, 600))) for _ in range(100)]
#preload stars
star_images = {i: pygame.transform.scale(pygame.image.load(f"images/redscale background star {i}.png").convert_alpha(),(9, 9)) for i in range(1, 4)}

titleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 192)
smallerFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 32)
smallerHighlightedFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 40)

button = pygame.transform.scale(pygame.image.load("images/redscale button 1.png").convert_alpha(), (252, 63))
homeButtonUnselected = pygame.transform.scale(pygame.image.load("images/home button unselected.png").convert_alpha(), (63, 63))
homeButtonSelectedOn = pygame.transform.scale(pygame.image.load("images/home button selected on.png").convert_alpha(), (63, 63))
homeButtonSelectedOff = pygame.transform.scale(pygame.image.load("images/home button selected off.png").convert_alpha(), (63, 63))
resetButtonUnselected = pygame.transform.scale(pygame.image.load("images/reset button unselected.png").convert_alpha(), (63, 63))
resetButtonSelectedOn = pygame.transform.scale(pygame.image.load("images/reset button selected on.png").convert_alpha(), (63, 63))
resetButtonSelectedOff = pygame.transform.scale(pygame.image.load("images/reset button selected off.png").convert_alpha(), (63, 63))

titleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 192)
titleText = titleFont.render("RED-EYE", True, (255, 1, 1))
titleRect = titleText.get_rect(center = (575, 100))

subtitleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 32)
subtitleText = subtitleFont.render("BY PRANAV RAMANATHAN AND ROHAN RANJESH", True, (255, 1, 1))
subtitleRect = subtitleText.get_rect(center = (575, 615))

tutorialText = smallerFont.render("CLICK AND DRAG THE MISSILE TO PULL IT BACK AND LAUNCH IT", True, (255, 1, 1))
tutorialRect = tutorialText.get_rect(center = (575, 50))

tutorialText2 = smallerFont.render("ONCE YOU'VE LAUNCHED, THERE IS NO CONTROL", True, (255, 1, 1))
tutorialRect2 = tutorialText2.get_rect(center = (575, 80))

tutorialText3 = smallerFont.render("WATCH OUT FOR GRAVITATIONAL FIELDS AND PRESS [R] TO RESET", True, (255, 1, 1))
tutorialRect3 = tutorialText3.get_rect(center = (575, 110))

tutorialText4 = smallerFont.render("THE LAUNCH LINE GIVES YOU AN APPROXIMATION", True, (255, 1, 1))
tutorialRect4 = tutorialText4.get_rect(center = (575, 140))

tutorialText5 = smallerFont.render("YOU MUST USE YOUR INTUITION TO SUCCEED", True, (255, 1, 1))
tutorialRect5 = tutorialText5.get_rect(center = (575, 170))

tutorialText6 = smallerFont.render("AIM FOR THE TARGETS, LIEUTENANT", True, (255, 1, 1))
tutorialRect6 = tutorialText6.get_rect(center = (575, 200))

#----------------------------------- SCENE -----------------------------------#
#region scene
bodies: list[Body] = [
    #Planet(
    #    mass = 20000, x = 583, y = 308, vx = 0, vy = 0, radius = 10,
    #    surface = pygame.transform.scale(
    #        pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)
    #    ),
    #    #this planet stays fixed
    #    anchor = True,
    #),
    #Planet(
    #    mass = 6000, x = 583, y = 133, vx = 5, vy = 0, radius = 5,
    #    surface = pygame.transform.scale(
    #        pygame.image.load("images/redscale moon.png").convert_alpha(), (42, 42)
    #    ),
    #)
]
 
missile = Missile(x = 557, y = 50, image = missile_image)
 
targets: list[Target] = []
 
 
def reset_field(tx = 0, ty = 0):
    tx = 0 if tx == 0 else tx
    ty = 0 if ty == 0 else ty
    for t in targets:
        t.reset(x = tx, y = ty)
    missile.reset(x = 250, y = 364)


is_dragging = False
mouse_start_pos = (0, 0)
mouse_current_pos = (0, 0)

#region Main Loop
# ── Loop ─────────────────────────────────────────────────────────────────────
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        #region home inputs
        elif currState == GameStates.HOME:
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if (618 <= mx <= 870) and (519 <= my <= 583):
                    currState = GameStates.TRANSITION_TO_TUTORIAL
                if (280 <= mx <= 532) and (519 <= my <= 583):
                    currState = GameStates.TRANSITION_TO_GAME

        #region game inputs
        elif currState == GameStates.GAME:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: reset_field()
                if event.key == pygame.K_RIGHT: missile.vx += 10
                if event.key == pygame.K_LEFT: missile.vx -= 10
                if event.key == pygame.K_UP: missile.vy -= 10
                if event.key == pygame.K_DOWN: missile.vy += 10
            elif event.type == pygame.MOUSEBUTTONDOWN and missile.state == Missile.LAUNCH:
                mx, my = event.pos
                if math.hypot(mx - missile.x, my - missile.y) < 40:
                    is_dragging = True
                    mouse_start_pos = mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)

        #region tutorial inputs
        elif currState == GameStates.TUTORIAL:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: reset = True
                if event.key == pygame.K_SPACE: print(pygame.mouse.get_pos())
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if 30 <= mx <= 93 and 557 <= my <= 620:
                    reset_field()
                elif 1057 <= mx <= 1120 and 557 <= my <= 620:
                    targets.clear()
                    showText = True
                    currState = GameStates.TRANSITION_TO_HOME
                elif missile.state == Missile.LAUNCH:
                    if math.hypot(mx - missile.x, my - missile.y) < 40:
                        is_dragging = True
                        mouse_start_pos = mouse_current_pos = (mx, my)
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                showText = False
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)

    #region t_home
    if currState == GameStates.TRANSITION_TO_HOME:
        bodies.append(Body(20000, 491, 246, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), True))
        missile.state = Missile.FREE
        missile.vx = 4.35
        currState = GameStates.HOME

    #region home
    elif currState == GameStates.HOME:
        game_surface.fill((35, 35, 55))
        for star_type, position in background_stars:
            game_surface.blit(star_images[star_type], position)
        missile.update(bodies)
        missile.record_trail(offset_x=18, offset_y=24)
        missile.draw_trail(game_surface)
        missile.draw(game_surface)
        
        for body in bodies:
            body.draw(game_surface)

        mouseX, mouseY = pygame.mouse.get_pos()

        if 280 < mouseX < 532 and 520 < mouseY < 583:
            playButtonText = smallerHighlightedFont.render("PLAY", True, (255, 1, 1))
            if syncPlayButton:
                timer = 0
                syncPlayButton = False
            if timer % 1 < 0.5:
                game_surface.blit(button, (280, 520))
        else: 
            game_surface.blit(button, (280, 520))
            playButtonText = smallerFont.render("PLAY", True, (255, 1, 1))
            syncPlayButton = True
        
        if 618 < mouseX < 870 and 520 < mouseY < 583:
            tutorialButtonText = smallerHighlightedFont.render("TUTORIAL", True, (255, 1, 1))
            if syncTutorialButton:
                timer = 0
                syncTutorialButton = False
            if timer % 1 < 0.5:
                game_surface.blit(button, (618, 520))
        else:
            game_surface.blit(button, (618, 520))
            tutorialButtonText = smallerFont.render("TUTORIAL", True, (255, 1, 1))
            syncTutorialButton = True
        
        playButtonRect = playButtonText.get_rect(center = (406, 551))
        tutorialButtonRect = tutorialButtonText.get_rect(center = (744, 551))

        game_surface.blit(playButtonText, playButtonRect)
        game_surface.blit(tutorialButtonText, tutorialButtonRect)
        game_surface.blit(titleText, titleRect)
        game_surface.blit(subtitleText, subtitleRect)

    #region t_tutorial
    elif currState == GameStates.TRANSITION_TO_TUTORIAL:
        tutorialTargets = 3
        bodies.clear()
        missile.reset(x = 250, y = 364)
        bodies = []
        bodies.append(Body(20000, 541, 308, 0, 0, 10, surface = pygame.transform.scale(
            pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)
        ),
        anchor = True))
        targets.append(Target(710, 355, target_surface))
        currState = GameStates.TUTORIAL

    #region tutorial
    elif currState == GameStates.TUTORIAL:
        game_surface.fill((35, 35, 55))
        for star_type, position in background_stars:
            game_surface.blit(star_images[star_type], position)

        missile.update(bodies)
        if missile.state == Missile.LAUNCH and is_dragging:
            ddx = mouse_start_pos[0] - mouse_current_pos[0]
            ddy = mouse_start_pos[1] - mouse_current_pos[1]
            missile.draw_aimed(game_surface, ddx, ddy)
        else:
            missile.draw(game_surface)

        missile.record_trail(18, 24)
        missile.draw_trail(game_surface)

        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile):
                t.state = Target.HIT
        if all(t.state == Target.HIT for t in targets):
            tutorialTargets -= 1
            reset = True

        if reset:
            reset = False
            if tutorialTargets == 3:
                reset_field(710, 355)
            elif tutorialTargets == 2:
                reset_field(650, 200)
            elif tutorialTargets == 1:
                reset_field(950, 325)
        
        for body in bodies:
            body.draw(game_surface)
        
        if showText:
            game_surface.blit(tutorialText, tutorialRect)
            game_surface.blit(tutorialText2, tutorialRect2)
            game_surface.blit(tutorialText3, tutorialRect3)
            game_surface.blit(tutorialText4, tutorialRect4)
            game_surface.blit(tutorialText5, tutorialRect5)
            game_surface.blit(tutorialText6, tutorialRect6)

        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

        
        mouseX, mouseY = pygame.mouse.get_pos()

        if in_bounds(mouseX, mouseY, RESET_BTN):
            if syncResetButton:
                timer = 0
                syncResetButton = False
            if timer % 1 < 0.5:
                game_surface.blit(resetButtonSelectedOn, (30, 557))
            else:
                game_surface.blit(resetButtonSelectedOff, (30, 557))
        else:
            game_surface.blit(resetButtonUnselected, (30, 557))
            syncResetButton = True

        if in_bounds(mouseX, mouseY, HOME_BTN):
            if syncHomeButton:
                timer = 0
                syncHomeButton = False
            if timer % 1 < 0.5:
                game_surface.blit(homeButtonSelectedOn, (1057, 557))
            else:
                game_surface.blit(homeButtonSelectedOff, (1057, 557))
        else:
            game_surface.blit(homeButtonUnselected, (1057, 557))
            syncHomeButton = True

    #region t_game
    elif currState == GameStates.TRANSITION_TO_GAME:
        bodies.clear()
        bodies.append(Body(20000, 491, 246, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)), True))
        missile.reset(x=250, y=364)
        currState = GameStates.GAME

    #region game
    elif currState == GameStates.GAME:
        missile.update(bodies)
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
        game_surface.fill((35, 35, 55))
        for star_type, position in background_stars:
            game_surface.blit(star_images[star_type], position)
        if missile.state == Missile.LAUNCH and is_dragging:
            ddx = mouse_start_pos[0] - mouse_current_pos[0]
            ddy = mouse_start_pos[1] - mouse_current_pos[1]
            missile.draw_aimed(game_surface, ddx, ddy)
        else:
            missile.draw(game_surface)
        missile.record_trail(offset_x=18, offset_y=24)
        missile.draw_trail(game_surface)
        for body in bodies:
            body.draw(game_surface)
        for target in targets:
            target.draw(game_surface)
            if target.state == Target.UNHIT and target.check_hit(missile):
                target.state = Target.HIT
        if all(t.state == Target.HIT for t in targets):
            reset_field()
        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

    #region gpu
    # ── GPU upload ────────────────────────────────────────────────────
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)
    ctx.clear(0.0, 0.0, 0.0)
    vao.render()
    pygame.display.flip()
    increment = clock.tick(60) / 1000
    timer += increment

pygame.quit()