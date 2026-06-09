"""
TODO:
Add multiple missiles
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
PREDICT_STEPS = 35
TRAIL_MAX = 100
MISSILE_W = 36
MISSILE_H = 36
MIN_DIST = 75
EXPLOSION_DURATION = 0.75
class GameStates(Enum):
    TRANSITION_TO_HOME = "T_HOME"
    HOME = "HOME"
    TRANSITION_TO_TUTORIAL = "T_TUTORIAL"
    TUTORIAL = "TUTORIAL"
    TRANSITION_TO_L1 = "T_L1"
    L1 = "L1"
    TRANSITION_TO_L2 = "T_L2"
    L2 = "L2"
    TRANSITION_TO_L3 = "T_L3"
    L3 = "L3"
    TRANSITION_TO_L4 = "T_L4"
    L4 = "L4"
    TRANSITION_TO_L5 = "T_L5"
    L5 = "L5"

#the screen warp causes innacuracies in getting mouse position
#so use these constants to line up mouse position with visual position of each button
#only needed for corner and edge buttons because the warp is the most there
#x1, x2, y1, y2\
HOME_BTN = (995, 1064, 531, 598)
RESET_BTN = (97, 154, 530, 587)
BACK_BTN = (64, 123, 455, 510)
NEXT_BTN = (1026, 1084, 456, 510)
#----------------------------------- OTHER VARIABLES -----------------------------------#
#region variables
showText = True
currState = GameStates.TRANSITION_TO_HOME
timer = 0
reset = False
levelDone = False

syncPlayButton = True
syncTutorialButton = True
syncHomeButton = True
syncResetButton = True
syncNextButton = True
syncBackButton = True

missileLevelPos = (0,0)
unlockedLevels = [1, 2, 3]

explosion_active = False
explosion_pos = (0, 0)
explosion_timer = 0

#----------------------------------- CLASSES -----------------------------------#
#region classes
#base class for all physics based objects
#region Body
class Body:
    def __init__(self, mass, x, y, vx, vy, radius, surface, anchor = False, collider = False):
        self.mass = mass
        self.vx = float(vx)
        self.vy = float(vy)
        self.radius = radius
        self.surface = surface
        self.trail: list[tuple[int, int]] = []
        self.anchor = anchor
        self.sprite_w = surface.get_width() / 2
        self.sprite_h = surface.get_height() / 2
        self.x = float(x)
        self.y = float(y)
        self.collider = collider

    @property
    def cx(self):
        return self.x - self.sprite_w
    @property
    def cy(self):
        return self.y - self.sprite_h
    
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
        surface.blit(self.surface, (int(self.cx), int(self.cy)))
    
    def collided(self, missile):
        if self.collider == False:
            return False
        dx = missile.cx - self.cx
        dy = missile.cy - self.cy
        dist = math.hypot(dx, dy)
        if dist <= self.sprite_w:
            return True
        else:
            return False
        
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

    px = missile.cx
    py = missile.cy

    pygame.draw.circle(surface, (255, 0, 0), (int(px + 30), int(py + 40)), 3)

    points = []

    for step in range(PREDICT_STEPS):

        fx = 0.0
        fy = 0.0

        for p in planets:
            dx = p.cx - px
            dy = p.cy - py

            dist = max(math.hypot(dx, dy), 75)

            scale = G * p.mass * missile.mass / dist**3

            fx += scale * dx
            fy += scale * dy

        vx += fx / missile.mass
        vy += fy / missile.mass

        px += vx
        py += vy

        if step % 4 == 0:
            points.append((int(px + 30), int(py + 40)))

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

explosion_image = pygame.transform.scale(pygame.image.load("images/explosion.png").convert_alpha(), (64, 64))

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

backButtonUnselected = pygame.transform.scale(pygame.image.load("images/back button unselected.png").convert_alpha(), (63, 63))
backButtonSelectedOn = pygame.transform.scale(pygame.image.load("images/back button selected on.png").convert_alpha(), (63, 63))
backButtonSelectedOff = pygame.transform.scale(pygame.image.load("images/back button selected off.png").convert_alpha(), (63, 63))

nextButtonUnselected = pygame.transform.scale(pygame.image.load("images/next button unselected.png").convert_alpha(), (63, 63))
nextButtonSelectedOn = pygame.transform.scale(pygame.image.load("images/next button selected on.png").convert_alpha(), (63, 63))
nextButtonSelectedOff = pygame.transform.scale(pygame.image.load("images/next button selected off.png").convert_alpha(), (63, 63))

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

tutorialText4 = smallerFont.render("AIM FOR THE TARGETS, LIEUTENANT", True, (255, 1, 1))
tutorialRect4 = tutorialText4.get_rect(center = (575, 140))

l1DoneText = smallerFont.render("LEVEL COMPLETE: USE THE [->] BUTTON TO CONTINUE", True, (255, 1, 1))
l1DoneRect = l1DoneText.get_rect(center = (575, 80))

#----------------------------------- SCENE -----------------------------------#
#region scene
bodies: list[Body] = []
 
missile = Missile(x = 557, y = 50, image = missile_image)
 
targets: list[Target] = []

is_dragging = False
mouse_start_pos = (0, 0)
mouse_current_pos = (0, 0)

#region Main Loop
# ── Loop ─────────────────────────────────────────────────────────────────────
running = True
while running:
    increment = clock.tick(60) / 1000
    timer += increment
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
                    currState = GameStates.TRANSITION_TO_L1

        #region tutorial inputs
        elif currState == GameStates.TUTORIAL:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_TUTORIAL
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    currState = GameStates.TRANSITION_TO_TUTORIAL
                elif in_bounds(mx, my, HOME_BTN):
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

        #region L1 inputs
        elif currState == GameStates.L1:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L1
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    currState = GameStates.TRANSITION_TO_L1
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, NEXT_BTN):
                    currState = GameStates.TRANSITION_TO_L2
                elif missile.state == Missile.LAUNCH:
                    if math.hypot(mx - missile.x, my - missile.y) < 40:
                        is_dragging = True
                        mouse_start_pos = mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                showText = False
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)

        #region L2 inputs
        elif currState == GameStates.L2:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L2
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    currState = GameStates.TRANSITION_TO_L2
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L1
                elif in_bounds(mx, my, NEXT_BTN):
                    currState = GameStates.TRANSITION_TO_L3
                elif missile.state == Missile.LAUNCH:
                    if math.hypot(mx - missile.x, my - missile.y) < 40:
                        is_dragging = True
                        mouse_start_pos = mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                showText = False
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)

        #region L3 inputs
        elif currState == GameStates.L3:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L3
                if event.key == pygame.K_RIGHT: missile.vx += 5
                if event.key == pygame.K_LEFT: missile.vx -= 5
                if event.key == pygame.K_UP: missile.vy -= 5
                if event.key == pygame.K_DOWN: missile.vy += 5
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    currState = GameStates.TRANSITION_TO_L3
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L2
                elif in_bounds(mx, my, NEXT_BTN):
                    currState = GameStates.TRANSITION_TO_L4
                elif missile.state == Missile.LAUNCH:
                    if math.hypot(mx - missile.x, my - missile.y) < 40:
                        is_dragging = True
                        mouse_start_pos = mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                showText = False
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)
    
        #region L4 inputs
        elif currState == GameStates.L4:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L4
                if event.key == pygame.K_RIGHT: missile.vx += 5
                if event.key == pygame.K_LEFT: missile.vx -= 5
                if event.key == pygame.K_UP: missile.vy -= 5
                if event.key == pygame.K_DOWN: missile.vy += 5
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    currState = GameStates.TRANSITION_TO_L4
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L3
                elif in_bounds(mx, my, NEXT_BTN):
                    currState = GameStates.TRANSITION_TO_L5
                elif missile.state == Missile.LAUNCH:
                    if math.hypot(mx - missile.x, my - missile.y) < 40:
                        is_dragging = True
                        mouse_start_pos = mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                mouse_current_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                showText = False
                is_dragging = False
                missile.launch(mouse_start_pos, mouse_current_pos)


    #region t_home
    if currState == GameStates.TRANSITION_TO_HOME:
        missile.reset(x = 550, y = 40)
        missile.trail = []
        missile.vx = 4.35
        missile.state = Missile.FREE
        bodies.clear()
        bodies.append(Body(20000, 575, 340, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), True))
        targets.clear()
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
        bodies.clear()
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)
        bodies = []
        bodies.append(Body(20000, 575, 340, 0, 0, 10, surface = pygame.transform.scale(
            pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)
        ),
        anchor = True, collider = True))
        targets.clear()
        targets.append(Target(719, 364, target_surface))

        showText = True
        levelDone = False
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
            if t.state == Target.UNHIT and t.check_hit(missile) and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
        
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        if levelDone:
            levelDone = False
            missile.reset(missileLevelPos[0], missileLevelPos[1])
        
        for body in bodies:
            body.draw(game_surface)
            if body.collided(missile):
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
                explosion_timer -= increment

        if explosion_active:
            game_surface.blit(explosion_image, explosion_pos)
            explosion_timer -= increment
            if explosion_timer <= 0:
                explosion_active = False
        
        if showText:
            game_surface.blit(tutorialText, tutorialRect)
            game_surface.blit(tutorialText2, tutorialRect2)
            game_surface.blit(tutorialText3, tutorialRect3)
            game_surface.blit(tutorialText4, tutorialRect4)

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

    #region t_L1
    elif currState == GameStates.TRANSITION_TO_L1:
        bodies.clear()
        bodies.append(Body(20000, 575, 340, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)), True, True))
        bodies.append(Body(6000, 575, 158, -5, 0, 5,
            pygame.transform.scale(pygame.image.load("images/redscale moon.png").convert_alpha(), (42, 42)), collider=True))
        
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(719, 339, target_surface))

        showText = False
        levelDone = False
        currState = GameStates.L1

    #region L1
    elif currState == GameStates.L1:
        mouseX, mouseY = pygame.mouse.get_pos()
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
        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
                explosion_timer -= increment

        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])

        if explosion_active:
            game_surface.blit(explosion_image, explosion_pos)
            explosion_timer -= increment
            if explosion_timer <= 0:
                explosion_active = False

        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        if levelDone:
            levelDone = False
            showText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 2 not in unlockedLevels:
                unlockedLevels.append(2)

        infoText = smallerFont.render("LEVEL: [" + str(1) + "] | LAUNCHES LEFT: [" + str(1) + "]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showText:
            game_surface.blit(l1DoneText, l1DoneRect)

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

        if 2 in unlockedLevels:
            if in_bounds(mouseX, mouseY, NEXT_BTN):
                if syncNextButton:
                    timer = 0
                    syncNextButton = False
                if timer % 1 < 0.5:
                    game_surface.blit(nextButtonSelectedOn, (1057, 474))
                else:
                    game_surface.blit(nextButtonSelectedOff, (1057, 474))
            else:
                game_surface.blit(nextButtonUnselected, (1057, 474))
                syncNextButton = True

    #region t_L2
    elif currState == GameStates.TRANSITION_TO_L2:
        bodies.clear()
        bodies.append(Body(20000, 371, 196, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)), True, True))
        bodies.append(Body(20000, 575, 471, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)), True, True))
        bodies.append(Body(20000, 779, 196, 0, 0, 10,
            pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)), True, True))
        
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(759, 373, target_surface))
        
        showText = False
        levelDone = False
        currState = GameStates.L2

    #region L2
    elif currState == GameStates.L2:
        mouseX, mouseY = pygame.mouse.get_pos()
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
        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
                explosion_timer -= increment

        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])

        if explosion_active:
            game_surface.blit(explosion_image, explosion_pos)
            explosion_timer -= increment
            if explosion_timer <= 0:
                explosion_active = False

        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        if levelDone:
            levelDone = False
            showText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 3 not in unlockedLevels:
                unlockedLevels.append(3)

        infoText = smallerFont.render("LEVEL: [" + str(1) + "] | LAUNCHES LEFT: [" + str(1) + "]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showText:
            game_surface.blit(l1DoneText, l1DoneRect)

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

        if 3 in unlockedLevels:
            if in_bounds(mouseX, mouseY, NEXT_BTN):
                if syncNextButton:
                    timer = 0
                    syncNextButton = False
                if timer % 1 < 0.5:
                    game_surface.blit(nextButtonSelectedOn, (1057, 474))
                else:
                    game_surface.blit(nextButtonSelectedOff, (1057, 474))
            else:
                game_surface.blit(nextButtonUnselected, (1057, 474))
                syncNextButton = True
        
        if in_bounds(mouseX, mouseY, BACK_BTN):
            if syncBackButton:
                timer = 0
                syncBackButton = False
            if timer % 1 < 0.5:
                game_surface.blit(backButtonSelectedOn, (30, 474))
            else:
                game_surface.blit(backButtonSelectedOff, (30, 474))
        else:
            game_surface.blit(backButtonUnselected, (30, 474))
            syncBackButton = True

    #region t_L3
    elif currState == GameStates.TRANSITION_TO_L3:
        bodies.clear()
        bodies.append(Body(20000, 320, 302, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), anchor=True))
        bodies.append(Body(20000, 785, 302, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), anchor=True))
        missile.reset(x = 300, y = 450)
        missileLevelPos = (300, 450)

        targets.clear()
        targets.append(Target(775, 450, target_surface))
        targets.append(Target(775, 150, target_surface))
        showText = False
        levelDone = False
        currState = GameStates.L3

    #region L3
    elif currState == GameStates.L3:
        mouseX, mouseY = pygame.mouse.get_pos()
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
        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
                explosion_timer -= increment

        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        if explosion_active:
            game_surface.blit(explosion_image, explosion_pos)
            explosion_timer -= increment
            if explosion_timer <= 0:
                explosion_active = False

        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        if levelDone:
            levelDone = False
            showText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 4 not in unlockedLevels:
                unlockedLevels.append(4)

        infoText = smallerFont.render("LEVEL: [" + str(1) + "] | LAUNCHES LEFT: [" + str(1) + "]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showText:
            game_surface.blit(l1DoneText, l1DoneRect)

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

        if 4 in unlockedLevels:
            if in_bounds(mouseX, mouseY, NEXT_BTN):
                if syncNextButton:
                    timer = 0
                    syncNextButton = False
                if timer % 1 < 0.5:
                    game_surface.blit(nextButtonSelectedOn, (1057, 474))
                else:
                    game_surface.blit(nextButtonSelectedOff, (1057, 474))
            else:
                game_surface.blit(nextButtonUnselected, (1057, 474))
                syncNextButton = True
        
        if in_bounds(mouseX, mouseY, BACK_BTN):
            if syncBackButton:
                timer = 0
                syncBackButton = False
            if timer % 1 < 0.5:
                game_surface.blit(backButtonSelectedOn, (30, 474))
            else:
                game_surface.blit(backButtonSelectedOff, (30, 474))
        else:
            game_surface.blit(backButtonUnselected, (30, 474))
            syncBackButton = True

    #region t_L4
    elif currState == GameStates.TRANSITION_TO_L4:
        bodies.clear()
        bodies.append(Body(20000, 400, 150, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), anchor=True))
        bodies.append(Body(20000, 750, 450, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale star.png").convert_alpha(), (168, 168)), anchor=True))
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(775, 364, target_surface))
        #targets.append(Target(775, 150, target_surface))

        showText = False
        levelDone = False
        currState = GameStates.L4

    #region L4
    elif currState == GameStates.L4:
        mouseX, mouseY = pygame.mouse.get_pos()
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
        if is_dragging:
            draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
                explosion_timer -= increment

        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        if explosion_active:
            game_surface.blit(explosion_image, explosion_pos)
            explosion_timer -= increment
            if explosion_timer <= 0:
                explosion_active = False

        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        if levelDone:
            levelDone = False
            showText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 5 not in unlockedLevels:
                unlockedLevels.append(5)

        infoText = smallerFont.render("LEVEL: [" + str(1) + "] | LAUNCHES LEFT: [" + str(1) + "]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showText:
            game_surface.blit(l1DoneText, l1DoneRect)

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

        if 5 in unlockedLevels:
            if in_bounds(mouseX, mouseY, NEXT_BTN):
                if syncNextButton:
                    timer = 0
                    syncNextButton = False
                if timer % 1 < 0.5:
                    game_surface.blit(nextButtonSelectedOn, (1057, 474))
                else:
                    game_surface.blit(nextButtonSelectedOff, (1057, 474))
            else:
                game_surface.blit(nextButtonUnselected, (1057, 474))
                syncNextButton = True
        
        if in_bounds(mouseX, mouseY, BACK_BTN):
            if syncBackButton:
                timer = 0
                syncBackButton = False
            if timer % 1 < 0.5:
                game_surface.blit(backButtonSelectedOn, (30, 474))
            else:
                game_surface.blit(backButtonSelectedOff, (30, 474))
        else:
            game_surface.blit(backButtonUnselected, (30, 474))
            syncBackButton = True

    #region gpu
    # ── GPU upload ────────────────────────────────────────────────────
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)
    ctx.clear(0.0, 0.0, 0.0)
    vao.render()
    pygame.display.flip()

pygame.quit()