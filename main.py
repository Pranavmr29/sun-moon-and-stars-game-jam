#Import libraries
#all comments starting with "region" are used to mark sections of code in the scroll bar for navigation
#region imports
import pygame
import sys
import random
import math
import moderngl
import numpy as np
from enum import Enum

#This section code was created using Claude for the CRT visual effects. Sections created using Claude are under these lines: ─────────
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
#constant for gravity
G = 0.2
LAUNCH_MULT = 0.02
PREDICT_STEPS = 35
TRAIL_MAX = 100
MISSILE_W = 36
MISSILE_H = 36
MIN_DIST = 75
EXPLOSION_DURATION = 0.75
#enum for the state machine the game is run on
#contains all the possible states/screen the game can be in
#seperate into transitions for actions only carried out once and Levels for actions carried out repeatedly
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
    TRANSITION_TO_L6 = "T_L6"
    L6 = "L6"
    TRANSITION_TO_L7 = "T_L7"
    L7 = "L7"
    TRANSITION_TO_L8 = "T_L8"
    L8 = "L8"

#the screen warp causes innacuracies in getting mouse position
#so use these constants to line up mouse position with visual position of each button
#only needed for corner and edge buttons because the warp is the most there
#x1, x2, y1, y2
WIPE_BTN = (457, 691, 450, 509)
HOME_BTN = (995, 1064, 531, 598)
RESET_BTN = (97, 154, 530, 587)
BACK_BTN = (64, 123, 455, 510)
NEXT_BTN = (1026, 1084, 456, 510)
#----------------------------------- OTHER VARIABLES -----------------------------------#
#region variables
showEndText = False
showStartText = False
currState = GameStates.TRANSITION_TO_HOME
timer = 0
levelDone = False
missileCollided = False

#vars used for the blinking of buttons
syncWipeButton = True
syncPlayButton = True
syncTutorialButton = True
syncHomeButton = True
syncResetButton = True
syncNextButton = True
syncBackButton = True

missileLevelPos = (0,0)
unlockedLevels = [1]

explosion_active = False
explosion_pos = (0, 0)
explosion_timer = 0

#----------------------------------- CLASSES -----------------------------------#
#region classes
#base class for all physics based objects
#region Body
class Body:
    #every body has these qualitiesj9'
     
    #anchor determines whether an object is influenced by gravity or static and doesn't move
    #collider determines whether the missile will explode on impact with the body
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

    #define center x and center y because the x and y values are the top left of the image
    @property
    def cx(self):
        return self.x - self.sprite_w
    @property
    def cy(self):
        return self.y - self.sprite_h
    
    #this function updates a body's position based on the forces of all other bodies
    #others {list} a list of body objects that are not the self object the update function is being called on
    #no return type, just uses return to stop the function early if anchored
    def update(self, others: list["Body"]):
        #Integrate gravity from all other planets, skips if anchored
        if self.anchor:
            return
        fx, fy = self.gravity_from(others)
        #update vectors
        self.vx += fx / self.mass
        self.vy += fy / self.mass
        #use vectors to update position
        self.x += self.vx
        self.y += self.vy

    #this function finds the gravity forces acting on a single planet
    #others {list} a list of body objects that are not the self object the update function is being called on
    #return {tuple} total x and y vector forces on the body
    def gravity_from(self, others):
        #returns total grav force fx,fy on this body by every other body in others
        total_fx = 0.0
        total_fy = 0.0
        for o in others:
            #calculate each body's effect individually, and add up as we go
            #use cx/cy to get gravity from the body's center
            #find the distance from both bodies on the x and y axis
            dx = o.cx - self.cx
            dy = o.cy - self.cy
            #use the pythagorean theroem to find the distance from the two bodies
            #if the distance is less than the minimum defined, override the distance to the minimum
            dist = max(math.hypot(dx, dy), MIN_DIST)
            #use the equation (G*m1*m2)/r^3 to find the acceleration of the object
            scale = G * o.mass * self.mass / dist ** 3
            #add to the total forces
            total_fx += scale * dx
            total_fy += scale * dy
        return total_fx, total_fy
    
    #this function adds points to a list containing the path of travel of a body
    #offset_x {int} an optional offset to every point
    #offset_y {int} an optional offset to every point
    def record_trail(self, offset_x = 0, offset_y = 0):
        self.trail.append((int(self.x) + offset_x, int(self.y) + offset_y))
        #if the trail has become longer than the constant says, start getting rid of the oldest points
        if len(self.trail) > TRAIL_MAX:
            self.trail.pop(0)
    
    #this function draws a series of lines connecting all the points in the body's trail
    #surface {pygame.surface} the surface to draw the lines onto
    #color {tuple} optional line color
    def draw_trail(self, surface, color=(160, 2, 2)):
        #anytime the trail has at least one point, start drawing
        if len(self.trail) > 1:
            pygame.draw.lines(surface, color, False, list(self.trail), 1)

    #this function draws a body onto a provided surface
    #surface {pygame.surface} the surface to draw the lines onto
    def draw(self, surface):
        surface.blit(self.surface, (int(self.cx), int(self.cy)))
    
    #this function determines whether the missile has collided into the body the function is called upon
    #missile {Missile} the object of the missile
    #return {bool} whether the missile is touching the body or not
    def collided(self, missile):
        #if the body is not a collider, the missile cannot collide with it
        if self.collider == False:
            return False
        #find distance from the pythagorean theorem
        dx = missile.cx - self.cx
        dy = missile.cy - self.cy
        dist = math.hypot(dx, dy)
        if dist <= self.sprite_w:
            #if the distance is less than the radius of the body, the missile has collided
            return True
        else:
            return False
        
#region Missile
class Missile(Body):
    #player controlled missile
    #has two states: launch means the missile is stationary, free means gravity acts upon the missile
    LAUNCH = "LAUNCH"
    FREE = "FREE"
 
    def __init__(self, x, y, image):
        super().__init__(mass=1, x=x, y=y, vx=0, vy=0, radius=2, surface=image)
        self.state = Missile.LAUNCH
        self.mask = pygame.mask.from_surface(image)
    
    #this function updates the missile position based on the forces of all other bodies
    #planets {list} a list of body objects that are not the missile
    #no return type, just uses return to stop the function early if the missile is not freely moving
    def update(self, planets: list[Body]):
        #if the missile is not freely moving, then gravity cannot act on it
        if self.state != Missile.FREE:
            return
        fx, fy = self.gravity_from(planets)
        self.vx += fx / self.mass
        self.vy += fy / self.mass
        self.x += self.vx
        self.y += self.vy

    #this function calculates how much force to apply to the missile when it is launched by the user
    #start_pos {tuple} coordinates of the mouse location the user started launching from
    #end_pos {tuple} coordinates of the mouse location the user stopped launching from
    def launch(self, start_pos, end_pos):
        self.vx, self.vy = ((start_pos[i] - end_pos[i]) * LAUNCH_MULT for i in (0, 1))
        self.state = Missile.FREE
    
    #this function resets the position and state of the missile
    #x {int} the x-coord to reset to
    #y {int} the y-coord to reset to
    def reset(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.trail.clear()
        self.state = Missile.LAUNCH
    
    #this function draws the missile rotated to match it's current travel direction
    #surface {pygame.surface} the surface to draw the missile onto
    #angle {float} what angle the ship is currently traveling at, found from arctan
    def blit_rotated(self, surface, angle):
        rotated = pygame.transform.rotate(self.surface, -angle - 90)
        surface.blit(rotated, rotated.get_rect(center=(self.x + MISSILE_W/2, self.y + MISSILE_H/2)))

    #this function finds the angle for the blit_rotated function to draw with
    #surface {pygame.surface} the surface to draw the missile onto
    def draw(self, surface):
        angle = math.degrees(math.atan2(self.vy, self.vx)) if (self.vx or self.vy) else 0
        self.blit_rotated(surface, angle)
    
    #this function uses blit_rotated to draw the missile using the dx and dy vectors to find direction
    def draw_aimed(self, surface, drag_dx, drag_dy):
        self.blit_rotated(surface, math.degrees(math.atan2(drag_dy, drag_dx)))

    #this function increases the missile's vectors in the direction it is traveling
    def boost(self):
        speed = math.hypot(self.vx, self.vy)
        if speed == 0:
            return

        self.vx += self.vx / speed * 2
        self.vy += self.vy / speed * 2

#region Target
class Target:
    #the target the missile needs to hit
    #two states of being for a target
    UNHIT = "UNHIT"
    HIT = "HIT"
 
    def __init__(self, x, y, surface):
        self.x = x
        self.y = y
        self.surface = surface
        self.mask = pygame.mask.from_surface(surface)
        self.state = Target.UNHIT

    #this function checks if the missile has hit the target by comparing positions
    def check_hit(self, missile: Missile):
        offset = (int(missile.x - self.x), int(missile.y - self.y))
        return self.mask.overlap(missile.mask, offset) is not None

    #this function resets the targets state and position, random if no parameter provided
    def reset(self, x = 0, y = 0):
        if x == 0: self.x = random.randint(50, 1100)
        else: self.x = x
        if y == 0: self.y = random.randint(50, 600)
        else: self.y = y
        self.state = Target.UNHIT

    #this function draws the target onto the screen provided
    def draw(self, surface):
        if self.state == Target.UNHIT:
            surface.blit(self.surface, (self.x, self.y))
#----------------------------------- FUNCTIONS/HELPERS -----------------------------------#
#region functions
#this function draws the projected launch line from the missile
def draw_launch_line(surface, missile: Missile, planets: list[Body],
                     start_pos, current_pos):
    #Project and draw the predicted flight path while dragging
    drag_dx = start_pos[0] - current_pos[0]
    drag_dy = start_pos[1] - current_pos[1]

    #lower velocity using launch mult constant
    vx = drag_dx * LAUNCH_MULT
    vy = drag_dy * LAUNCH_MULT

    px = missile.cx
    py = missile.cy

    #draw circle as origin
    pygame.draw.circle(surface, (255, 0, 0), (int(px + 30), int(py + 40)), 3)

    points = []

    #append each predicted point to the points list
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

        #append every 4 points found to the list to draw
        if step % 4 == 0:
            points.append((int(px + 30), int(py + 40)))

    if len(points) > 1:
        pygame.draw.lines(surface, (255, 1, 1), False, points, 2)

#finds if the mouse is within specified button bounds
def in_bounds(mx, my, bounds):
    x1, x2, y1, y2 = bounds
    return x1 < mx < x2 and y1 < my < y2

#this function handles the missile launch
def handle_missile_drag(event):
    global is_dragging, mouse_start_pos, mouse_current_pos, showEndText, showStartText

    #when the user first clicks on the missile
    if event.type == pygame.MOUSEBUTTONDOWN:
        mx, my = event.pos
        #if the missile can be launched, and the click is close enough, dragging is happening
        if missile.state == Missile.LAUNCH:
            if math.hypot(mx - missile.x, my - missile.y) < 40:
                is_dragging = True
                mouse_start_pos = mouse_current_pos = event.pos
    #keeps updating position as user drags
    elif event.type == pygame.MOUSEMOTION and is_dragging:
        mouse_current_pos = event.pos
    #launches the missile and sets it's appropriate state
    elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
        is_dragging = False
        showStartText = False
        showEndText = False
        missile.launch(mouse_start_pos, mouse_current_pos)

#this function draws the button flashing when the mouse hovers over it
def draw_hover_button(surface, mouse_pos, bounds, pos, unselected, selected_on, selected_off, sync_flag, timer):
    #check if the mouse position is in bound of the button
    hovered = in_bounds(*mouse_pos, bounds)
    if hovered:
        if sync_flag:
            timer = 0
            sync_flag = False
        #sync the timing of the button to pulse on/off
        if timer % 1 < 0.5:
            surface.blit(selected_on, pos)
        else:
            surface.blit(selected_off, pos)
    #if the user is not hovering over button, dont flash
    else:
        surface.blit(unselected, pos)
        sync_flag = True

    return sync_flag, timer

def draw_level_background():
    game_surface.fill((35, 35, 55))

    for star_type, position in background_stars:
        game_surface.blit(star_images[star_type], position)

#draws missile and calculates it's position based on gravity
def draw_missile():
    missile.update(bodies)
    if missile.state == Missile.LAUNCH and is_dragging:
        ddx = mouse_start_pos[0] - mouse_current_pos[0]
        ddy = mouse_start_pos[1] - mouse_current_pos[1]
        missile.draw_aimed(game_surface, ddx, ddy)
        #draws the missile pointed towards aimed location
    else:
        missile.draw(game_surface)

    missile.record_trail(18, 24)
    missile.draw_trail(game_surface)

    if is_dragging:
        draw_launch_line(game_surface, missile, bodies, mouse_start_pos, mouse_current_pos)

#draws explosion animation when called
def update_explosion(restart_state):
    global explosion_active
    global explosion_timer
    global missileCollided
    global currState

    if not explosion_active:
        return

    game_surface.blit(explosion_image, explosion_pos)

    explosion_timer -= increment

    if explosion_timer <= 0:
        explosion_active = False

    #if the missile is the body that collided, restart level
    if missileCollided:
        currState = restart_state
        missileCollided = False
#----------------------------------- ASSETS -----------------------------------#
#region assets
missile_image = pygame.transform.scale(pygame.image.load("images/redscale spaceship with flames 1.png").convert_alpha(), (MISSILE_W, MISSILE_H))
target_surface = pygame.transform.scale(pygame.image.load("images/redscale target x.png").convert_alpha(), (MISSILE_W, MISSILE_H))

background_stars = [(random.randint(1, 3), (random.randint(1, 1150), random.randint(1, 600))) for _ in range(100)]
#preload stars
star_images = {i: pygame.transform.scale(pygame.image.load(f"images/redscale background star {i}.png").convert_alpha(),(9, 9)) for i in range(1, 4)}

explosion_image = pygame.transform.scale(pygame.image.load("images/explosion.png").convert_alpha(), (64, 64))
#preload fonts
titleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 192)
smallerFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 32)
smallerHighlightedFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 40)
#preload buttons
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
#preload texts
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

boostText = smallerFont.render("NEW UPGRADE UNLOCKED: BOOST", True, (255, 1, 1))
boostRect = boostText.get_rect(center = (575, 60))

boostText2 = smallerFont.render("PRESS SPACE TO GIVE THE MISSILE AN EXTRA BOOST", True, (255, 1, 1))
boostRect2 = boostText2.get_rect(center = (575, 90))

boostText3 = smallerFont.render("YOU CAN USE YOUR BOOST TO ESCAPE ORBIT", True, (255, 1, 1))
boostRect3 = boostText3.get_rect(center = (575, 60))

nudgeText = smallerFont.render("NEW UPGRADE UNLOCKED: NUDGE", True, (255, 1, 1))
nudgeRect = nudgeText.get_rect(center = (575, 60))

nudgeText2 = smallerFont.render("USE THE ARROW KEYS TO NUDGE THE MISSILE", True, (255, 1, 1))
nudgeRect2 = nudgeText2.get_rect(center = (575, 90))

l8Text = smallerFont.render("USE ALL THE TOOLS YOU HAVE TO HIT THE TARGETS", True, (255, 1, 1))
l8Rect = l8Text.get_rect(center = (575, 90))

#----------------------------------- SCENE -----------------------------------#
#region scene
#sets up variables needed prior to game starting
bodies: list[Body] = []
 
missile = Missile(x = 557, y = 50, image = missile_image)
 
targets: list[Target] = []

is_dragging = False
mouse_start_pos = (0, 0)
mouse_current_pos = (0, 0)

#region Main Loop
# the main loop is seperated into 3 pieces: inputs, which handle all user input; transitions, which are 1 time actions; and Levels, which are looping actions
running = True
while running:
    #keep track of the time elapsed between loops for the explosion animation
    increment = clock.tick(60) / 1000
    timer += increment
    for event in pygame.event.get():
        #handles if the user clicks the window X button
        if event.type == pygame.QUIT:
            running = False
        #region home inputs
        elif currState == GameStates.HOME:
            if event.type == pygame.MOUSEBUTTONDOWN:
                #get the mouse position to use for checking button clicks
                mx, my = event.pos
                #event.type already checks for a click, use this to check whether the mouse was on the button at the time of the click
                if (618 <= mx <= 870) and (519 <= my <= 583):
                    currState = GameStates.TRANSITION_TO_TUTORIAL
                if (280 <= mx <= 532) and (519 <= my <= 583):
                    currState = GameStates.TRANSITION_TO_L1
                if in_bounds(mx, my, WIPE_BTN):
                    #wipe all user progress for next user
                    unlockedLevels = [1]
                    currState = GameStates.TRANSITION_TO_HOME

        #region tutorial inputs
        elif currState == GameStates.TUTORIAL:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_TUTORIAL
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_TUTORIAL
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
            
        #region L1 inputs
        elif currState == GameStates.L1:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L1
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L1
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, NEXT_BTN):
                    if 2 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L2

        #region L2 inputs
        elif currState == GameStates.L2:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L2
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L2
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L1
                elif in_bounds(mx, my, NEXT_BTN):
                    if 3 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L3

        #region L3 inputs
        elif currState == GameStates.L3:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L3
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L3
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L2
                elif in_bounds(mx, my, NEXT_BTN):
                    if 4 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L4
    
        #region L4 inputs
        elif currState == GameStates.L4:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L4
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L4
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L3
                elif in_bounds(mx, my, NEXT_BTN):
                    if 5 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L5

        #region L5 inputs
        elif currState == GameStates.L5:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L5
                #at level 5, give the user boosting ability
                if event.key == pygame.K_SPACE: missile.boost()
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L5
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L4
                elif in_bounds(mx, my, NEXT_BTN):
                    if 6 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L6

        #region L6 inputs
        elif currState == GameStates.L6:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L6
                if event.key == pygame.K_SPACE: missile.boost()
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L6
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L5
                elif in_bounds(mx, my, NEXT_BTN):
                    if 6 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L7

        #region L7 inputs
        elif currState == GameStates.L7:
            if event.type == pygame.KEYDOWN:
                #shortcut for restarting level
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L7
                #at level 7, give the user nudging ability
                if event.key == pygame.K_RIGHT: missile.vx += 2.5
                if event.key == pygame.K_LEFT: missile.vx -= 2.5
                if event.key == pygame.K_UP: missile.vy -= 2.5
                if event.key == pygame.K_DOWN: missile.vy += 2.5
                if event.key == pygame.K_SPACE: missile.boost()
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L7
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L6
                elif in_bounds(mx, my, NEXT_BTN):
                    if 8 in unlockedLevels:
                        currState = GameStates.TRANSITION_TO_L8


        #region L8 inputs
        elif currState == GameStates.L8:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: currState = GameStates.TRANSITION_TO_L8
                #adds the keys for boosting and nudging for the user to use
                if event.key == pygame.K_RIGHT: missile.vx += 5
                if event.key == pygame.K_LEFT: missile.vx -= 5
                if event.key == pygame.K_UP: missile.vy -= 5
                if event.key == pygame.K_DOWN: missile.vy += 5
                if event.key == pygame.K_SPACE: missile.boost()
            handle_missile_drag(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if in_bounds(mx, my, RESET_BTN):
                    #when the reset button is pressed, reload level by going to the transition state, which then load the level again
                    currState = GameStates.TRANSITION_TO_L8
                elif in_bounds(mx, my, HOME_BTN):
                    currState = GameStates.TRANSITION_TO_HOME
                elif in_bounds(mx, my, BACK_BTN):
                    currState = GameStates.TRANSITION_TO_L7

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
        draw_level_background()
        missile.update(bodies)
        missile.record_trail(offset_x=18, offset_y=24)
        missile.draw_trail(game_surface)
        missile.draw(game_surface)
        
        #only 1 body on the home screen, so only draw the bodies, dont need to apply gravity
        for body in bodies:
            body.draw(game_surface)

        #get mouse position to use for triggering the blinking button animation
        mouseX, mouseY = pygame.mouse.get_pos()

        #cannot use the hover button function for these buttons because there is no image to show, just the button box
        if in_bounds(mouseX, mouseY, WIPE_BTN):
            wipeButtonText = smallerHighlightedFont.render("NEW PLAYER", True, (255, 1, 1))
            if syncWipeButton:
                timer = 0
                syncWipeButton = False
            if timer % 1 < 0.5:
                game_surface.blit(button, (448, 450))
        else: 
            game_surface.blit(button, (448, 450))
            wipeButtonText = smallerFont.render("NEW PLAYER", True, (255, 1, 1))
            syncWipeButton = True

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
        
        #set up the button boxes
        playButtonRect = playButtonText.get_rect(center = (406, 551))
        tutorialButtonRect = tutorialButtonText.get_rect(center = (744, 551))
        wipeButtonRect = wipeButtonText.get_rect(center = (574, 481))

        #blit all the text for the titles and each button
        game_surface.blit(playButtonText, playButtonRect)
        game_surface.blit(tutorialButtonText, tutorialButtonRect)
        game_surface.blit(wipeButtonText, wipeButtonRect)
        game_surface.blit(titleText, titleRect)
        game_surface.blit(subtitleText, subtitleRect)

    #region t_tutorial
    elif currState == GameStates.TRANSITION_TO_TUTORIAL:
        #clear all bodies and reset the missile positon
        bodies.clear()
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)
        bodies.append(Body(20000, 575, 340, 0, 0, 10, surface = pygame.transform.scale(
            pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84)
        ),
        anchor = True, collider = True))
        #clear all targets and create the one needed for this level
        targets.clear()
        targets.append(Target(719, 364, target_surface))

        #based on the level, there may or may not be start text to show
        #in this case, there is text to show at start, so True
        showStartText = True
        levelDone = False
        currState = GameStates.TUTORIAL

    #region tutorial
    elif currState == GameStates.TUTORIAL:
        #draw the background, including stars
        draw_level_background()
        draw_missile()

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile) and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])
        
        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            missile.reset(missileLevelPos[0], missileLevelPos[1])
        
        #draw each body and check for missile collision against the colliders
        for body in bodies:
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                missileCollided = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment

        update_explosion(GameStates.TRANSITION_TO_TUTORIAL)
        
        if showStartText:
            game_surface.blit(tutorialText, tutorialRect)
            game_surface.blit(tutorialText2, tutorialRect2)
            game_surface.blit(tutorialText3, tutorialRect3)
            game_surface.blit(tutorialText4, tutorialRect4)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()

        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)

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

        showStartText = False
        showEndText = False
        levelDone = False
        currState = GameStates.L1

    #region L1
    elif currState == GameStates.L1:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                missileCollided = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])

        update_explosion(GameStates.TRANSITION_TO_L1)
        
        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 2 not in unlockedLevels:
                unlockedLevels.append(2)

        infoText = smallerFont.render("LEVEL: [1]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)

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
        
        showStartText = False
        showEndText = False
        levelDone = False
        currState = GameStates.L2

    #region L2
    elif currState == GameStates.L2:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                missileCollided = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                missile.reset(x = missileLevelPos[0], y = missileLevelPos[1])

        update_explosion(GameStates.TRANSITION_TO_L2)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 3 not in unlockedLevels:
                unlockedLevels.append(3)

        infoText = smallerFont.render("LEVEL: [2]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
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
        showStartText = False
        showEndText = False
        levelDone = False
        currState = GameStates.L3

    #region L3
    elif currState == GameStates.L3:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                missileCollided = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L3)
            
        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 4 not in unlockedLevels:
                unlockedLevels.append(4)

        infoText = smallerFont.render("LEVEL: [3]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
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

    #region t_L4
    elif currState == GameStates.TRANSITION_TO_L4:
        bodies.clear()
        bodies.append(Body(50000, 442, 480, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), True, True))
        bodies.append(Body(500, 442, 400, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 442, 340, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 442, 280, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 442, 220, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 442, 160, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 442, 100, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))

        bodies.append(Body(50000, 700, 120, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 3.png").convert_alpha(), (84, 84)), True, True))
        bodies.append(Body(500, 700, 200, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 700, 260, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 700, 320, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 700, 380, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 700, 440, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(500, 700, 500, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))

        missile.reset(x = 230, y = 320)
        missileLevelPos = (230, 320)

        targets.clear()
        
        targets.append(Target(850, 320, target_surface))

        showStartText = False
        showEndText = False
        levelDone = False
        currState = GameStates.L4

    #region L4
    elif currState == GameStates.L4:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment
                missileCollided = True

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L4)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 5 not in unlockedLevels:
                unlockedLevels.append(5)

        infoText = smallerFont.render("LEVEL: [4]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
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

    #region t_L5
    elif currState == GameStates.TRANSITION_TO_L5:
        bodies.clear()
        bodies.append(Body(90000, 100, 364, 0, 0, 20, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (168, 168)), anchor=True, collider=True))
        bodies.append(Body(20000, 650, 364, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 3.png").convert_alpha(), (84, 84)), anchor=True, collider=True))

        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(750, 350, target_surface))

        showStartText = True
        showEndText = False
        levelDone = False
        currState = GameStates.L5

    #region L5
    elif currState == GameStates.L5:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment
                missileCollided = True
        
        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L5)

        if showStartText:
            game_surface.blit(boostText, boostRect)
            game_surface.blit(boostText2, boostRect2)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 6 not in unlockedLevels:
                unlockedLevels.append(6)

        infoText = smallerFont.render("LEVEL: [5]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
        if 6 in unlockedLevels:
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
    
    #region t_L6
    elif currState == GameStates.TRANSITION_TO_L6:
        bodies.clear()
        bodies.append(Body(90000, 400, 320, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), anchor=True, collider=True))
        
        missile.reset(200, 320)
        missileLevelPos = (200, 320)

        targets.clear()
        targets.append(Target(950, 120, target_surface))

        showStartText = True
        showEndText = False
        levelDone = False
        currState = GameStates.L6

    #region L6
    elif currState == GameStates.L6:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment
                missileCollided = True

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L6)

        if showStartText:
            game_surface.blit(boostText3, boostRect3)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 7 not in unlockedLevels:
                unlockedLevels.append(7)

        infoText = smallerFont.render("LEVEL: [6]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
        if 7 in unlockedLevels:
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

    #region t_L7
    elif currState == GameStates.TRANSITION_TO_L7:
        bodies.clear()
        bodies.append(Body(1000, 400, 130, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 400, 200, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 400, 270, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 400, 340, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 400, 410, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 400, 550, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        
        bodies.append(Body(1000, 575, 130, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 575, 270, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 575, 340, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 575, 410, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 575, 480, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 575, 550, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        
        bodies.append(Body(1000, 750, 130, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 750, 200, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 750, 270, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 750, 340, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 750, 410, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))
        bodies.append(Body(1000, 750, 550, 0, 0, 5, pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (42, 42)), True, True))

        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(775, 400, target_surface))

        showStartText = True
        showEndText = False
        levelDone = False
        currState = GameStates.L7

    #region L7
    elif currState == GameStates.L7:
        draw_level_background()
        missile.update(bodies)
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment
                missileCollided = True

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L7)

        if showStartText:
            game_surface.blit(nudgeText, nudgeRect)
            game_surface.blit(nudgeText2, nudgeRect2)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])
            if 8 not in unlockedLevels:
                unlockedLevels.append(8)

        infoText = smallerFont.render("LEVEL: [7]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)
        if 8 in unlockedLevels:
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
    
    #region t_L8
    elif currState == GameStates.TRANSITION_TO_L8:
        bodies.clear()
        bodies.append(Body(15000, 350, 200, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), anchor=True, collider=True))
        bodies.append(Body(15000, 800, 200, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), anchor=True, collider=True))
        bodies.append(Body(15000, 350, 500, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), anchor=True, collider=True))
        bodies.append(Body(15000, 800, 500, 0, 0, 10, pygame.transform.scale(pygame.image.load("images/redscale planet 2.png").convert_alpha(), (84, 84)), anchor=True, collider=True))
        missile.reset(x = 250, y = 364)
        missileLevelPos = (250, 364)

        targets.clear()
        targets.append(Target(425, 190, target_surface))
        targets.append(Target(240, 190, target_surface))
        targets.append(Target(875, 190, target_surface))
        targets.append(Target(690, 190, target_surface))

        targets.append(Target(425, 490, target_surface))
        targets.append(Target(240, 490, target_surface))
        targets.append(Target(875, 490, target_surface))
        targets.append(Target(690, 490, target_surface))

        showStartText = True
        showEndText = False
        levelDone = False
        currState = GameStates.L8

    #region L8
    elif currState == GameStates.L8:
        draw_level_background()
        draw_missile()

        #draw each body and check for missile collision against the colliders
        for body in bodies:
            others = [b for b in bodies if b is not body]
            body.update(others)
            body.draw(game_surface)
            if body.collided(missile):
                #if the missile collided, activate the explosion
                explosion_active = True
                explosion_pos = (int(missile.x + 16), int(missile.y))
                explosion_timer = EXPLOSION_DURATION
                explosion_timer -= increment
                missileCollided = True

        #draws all the targets and checks if they are hit
        for t in targets:
            t.draw(game_surface)
            if t.state == Target.UNHIT and t.check_hit(missile)  and not explosion_active:
                t.state = Target.HIT
                explosion_active = True
                explosion_pos = (int(missile.x), int(missile.y))
                explosion_timer = EXPLOSION_DURATION

        update_explosion(GameStates.TRANSITION_TO_L8)

        if showStartText:
            game_surface.blit(l8Text, l8Rect)

        #when all targets are hit, the level is done
        if all(t.state == Target.HIT for t in targets):
            levelDone = True

        #if the level is done, reset the missile and wait
        if levelDone:
            levelDone = False
            showEndText = True
            missile.reset(missileLevelPos[0], missileLevelPos[1])

        infoText = smallerFont.render("LEVEL: [8]", True, (255, 1, 1))
        infoRect = infoText.get_rect(center = (575, 615))
        game_surface.blit(infoText, infoRect)
    
        if showEndText:
            game_surface.blit(l1DoneText, l1DoneRect)

        #get mouse position for button checking
        mouseX, mouseY = pygame.mouse.get_pos()
        syncResetButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), RESET_BTN, (30,557), resetButtonUnselected, resetButtonSelectedOn, resetButtonSelectedOff, syncResetButton, timer)
        syncHomeButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), HOME_BTN, (1057,557), homeButtonUnselected, homeButtonSelectedOn, homeButtonSelectedOff, syncHomeButton, timer)
        syncBackButton, timer = draw_hover_button(game_surface, (mouseX, mouseY), BACK_BTN, (30,474), backButtonUnselected, backButtonSelectedOn, backButtonSelectedOff, syncBackButton, timer)

    #region gpu
    # ── GPU upload ────────────────────────────────────────────────────
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)
    ctx.clear(0.0, 0.0, 0.0)
    vao.render()
    pygame.display.flip()

pygame.quit()