# Claude's CRT shader starts
import pygame
import sys
import random
import math
import moderngl
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────
WINDOW_SIZE = (800, 600)
GAME_RES    = (800, 600)   # low-res game surface — CRT effect looks best here

# ── Init ────────────────────────────────────────────────────────────────────
pygame.init()
screen = pygame.display.set_mode(WINDOW_SIZE, pygame.OPENGL | pygame.DOUBLEBUF)

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
# Claude's CRT shader ends
#----------------------------------- GAME VARIABLES -----------------------------------#
G = 0.2

isDragging = False
mouseStartPos = (0, 0)
mouseCurrentPos = (0, 0)
LaunchMultiplier = 0.02
predictSteps = 50

shipWidth = 42
shipHeight = 42

#map of star locations
backgroundStarPositions = [
    (random.randint(1, 3), (random.randint(1, 800), random.randint(1, 700)))
    for _ in range(50)
]

planets = [
    {
        "mass": 10000, "x": 364, "y": 364,
        "vx": 0.0, "vy": 0.0, "radius": 10, "color": (0, 150, 255),
        "trail": [],
        "surface": pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84))
    },

    {
        "mass": 3000, "x": 364, "y": 200,
        "vx": 3.75, "vy": 0.0, "radius": 5, "color": (0, 255, 150),
        "trail": [], "surface": pygame.transform.scale(pygame.image.load("images/redscale moon.png").convert_alpha(), (42, 42))
    }
    #{
        #"mass": 3000, "x": 364, "y": 528,
        #"vx": -5.25, "vy": 0.0, "radius": 5, "color": (0, 255, 150),
        #"trail": [], "surface": pygame.transform.scale(pygame.image.load("images/redscale moon.png").convert_alpha(), (42, 42))
    #}
    ]


shipImage = pygame.transform.scale(pygame.image.load("images/redscale spaceship with flames 1.png").convert_alpha(), (shipWidth, shipHeight))
ship = {
    "mass": 1,
    "x": 100.0, "y": 364.0,
    "vx": 0, "vy": 0,
    "radius": 2,
    "color": (0, 150, 255),
    "trail": [],
    "state": "LAUNCH",
    "surface": shipImage
}

target = pygame.transform.scale(pygame.image.load("images/redscale target x.png").convert_alpha(), (shipWidth, shipHeight))

#----------------------------------- GAME FUNCTIONS -----------------------------------#
def calculateForces(body, factors):
    totalFx = 0
    totalFy = 0
    for i in factors:
        dx = i["x"] - body["x"]
        dy = i["y"] - body["y"]
        distance = math.sqrt(dx**2 + dy**2)
        #Change distances if multiple bodies happen to overlap perfectly and a divide by 0 error occurs
        if distance < 50: distance = 75
        force = G * (i["mass"] * body["mass"]) / (distance**2)
        totalFx += force * (dx / distance)
        totalFy += force * (dy / distance)
        body["vx"] += totalFx / body["mass"]
        body["vy"] += totalFy / body["mass"]
def drawLaunchLine(surface):
    if isDragging:
        #Calculate the starting velocity based on the current drag distance
        drag_dx = mouseStartPos[0] - mouseCurrentPos[0]
        drag_dy = mouseStartPos[1] - mouseCurrentPos[1]
        
        #Make temporary virtual copies of the ship's position and velocity
        virtual_x = ship["x"] + shipWidth/2
        virtual_y = ship["y"] + shipHeight/2
        pygame.draw.circle(surface, (255, 0, 0), (int(virtual_x), int(virtual_y)), 3)
        virtual_vx = drag_dx * LaunchMultiplier
        virtual_vy = drag_dy * LaunchMultiplier
        
        #Step forward in time to project the path
        predictionPoints = []
        for step in range(predictSteps):
            #Calculate total gravity acting on the virtual position
            v_total_fx = 0
            v_total_fy = 0
            
            for p in planets:
                v_dx = p["x"] - virtual_x
                v_dy = p["y"] - virtual_y
                v_distance = math.sqrt(v_dx**2 + v_dy**2)
                
                #Prevent divide by zero by overiding distance if too close
                if v_distance < 50: 
                    v_distance = 75
                
                v_force = G * (p["mass"] * ship["mass"]) / (v_distance**2)
                v_total_fx += v_force * (v_dx / v_distance)
                v_total_fy += v_force * (v_dy / v_distance)
            
            #Update virtual velocity and position (F=ma)
            virtual_vx += v_total_fx / ship["mass"]
            virtual_vy += v_total_fy / ship["mass"]
            virtual_x += virtual_vx
            virtual_y += virtual_vy
            
            #Save a point every 4 frames to create a clean dotted line effect
            if step % 4 == 0:
                #Add offset (+18, +24) to center the path on the spaceship texture
                predictionPoints.append((int(virtual_x), int(virtual_y)))
                
        #Draw the predicted path onto the screen
        if len(predictionPoints) > 1:
            #Draws a sequence of small connected lines showing the future gravity curve
            pygame.draw.lines(surface, (255, 1, 1), False, predictionPoints, 2)

# ── Loop ─────────────────────────────────────────────────────────────────────
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                ship["state"] = "LAUNCH"
                ship["x"], ship["y"] = 100, 364
                ship["trail"] = []
        elif (event.type == pygame.MOUSEBUTTONDOWN and ship["state"] == "LAUNCH"):
            mouseX, mouseY = event.pos
            clickDist = math.sqrt((mouseX - ship["x"])**2 + (mouseY - ship["y"])**2)
            if clickDist < 40:
                isDragging = True
                mouseStartPos = event.pos
                mouseCurrentPos = event.pos
        elif event.type == pygame.MOUSEMOTION and isDragging:
            mouseCurrentPos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and isDragging:
            isDragging = False
            dx = mouseStartPos[0] - mouseCurrentPos[0]
            dy = mouseStartPos[1] - mouseCurrentPos[1]
            ship["vx"] = dx * LaunchMultiplier
            ship["vy"] = dy * LaunchMultiplier
            ship["state"] = "FREE"

    #create variables for total forces acting on ship
    totalFx = 0
    totalFy = 0
    #Calculate distances
    calculateForces(ship, planets)
    
    #apply sum of all forces
    #F = ma -> a = F/m
    if ship["state"] == "FREE":
        ship["vx"] += totalFx / ship["mass"]
        ship["vy"] += totalFy / ship["mass"]

        ship["x"] += ship["vx"]
        ship["y"] += ship["vy"]
    calculateForces(planets[1], [planets[i] for i, v in enumerate(planets) if i != 1])
    #calculateForces(planets[2], [planets[i] for i, v in enumerate(planets) if i != 2])
    for p in planets:
        p["x"] += p["vx"]
        p["y"] += p["vy"]

    # ── Draw game at low resolution ──────────────────────────────────────────
    game_surface.fill((15, 15, 35))

    #Fake starfield
    for star in backgroundStarPositions:
        starType, position = star
        starSurface = pygame.transform.scale(pygame.image.load("images/redscale background star " + str(starType) + ".png").convert_alpha(), (9, 9))
        game_surface.blit(starSurface, position)

    x += speed
    if x > GAME_RES[0] - 20 or x < 20:
        speed *= -1

    if ship["state"] == "LAUNCH" and isDragging:
        drag_dx = mouseStartPos[0] - mouseCurrentPos[0]
        drag_dy = mouseStartPos[1] - mouseCurrentPos[1]
        angle = math.degrees(math.atan2(drag_dy, drag_dx))
        rotated_ship = pygame.transform.rotate(shipImage, -angle - 90)
    else:
        if ship["vx"] or ship["vy"] != 0:
            angle = math.degrees(math.atan2(ship["vy"], ship["vx"]))
        else: 
            angle = 0
        rotated_ship = pygame.transform.rotate(shipImage, -angle - 90)

    rotated_rect = rotated_ship.get_rect(center=(ship["x"] + shipWidth / 2, ship["y"] + shipHeight / 2))
    game_surface.blit(rotated_ship, rotated_rect)

    #Record planet's position for orbital trail
    ship["trail"].append((int(ship["x"] + 18), int(ship["y"] + 24)))
    if len(ship["trail"]) > 100:
        ship["trail"].pop(0)
        
    #Draw orbit line trail
    if len(ship["trail"]) > 1:
        pygame.draw.lines(game_surface, (160, 2, 2), False, ship["trail"], 1)

    for p in planets:
        game_surface.blit(p["surface"], (int(p["x"]), int(p["y"])))

    game_surface.blit(target, (550, 550))
    drawLaunchLine(game_surface)
    # Bouncing ball
    #pygame.draw.circle(game_surface, (255, 230, 80), (int(x), GAME_RES[1]//2), 14)
    #pygame.draw.circle(game_surface, (255, 255, 180), (int(x)-4, GAME_RES[1]//2-4), 5)

    # Some colourful rectangles so the mask is visible
    #pygame.draw.rect(game_surface, (200, 50, 50),  (10, 10, 40, 20))
    #pygame.draw.rect(game_surface, (50, 200, 50),  (60, 10, 40, 20))
    #pygame.draw.rect(game_surface, (50, 50, 200),  (110, 10, 40, 20))
    #pygame.draw.rect(game_surface, (200, 200, 200),(160, 10, 40, 20))

    # ── Upload to GPU ────────────────────────────────────────────────────────
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)

    ctx.clear(0.0, 0.0, 0.0)
    vao.render()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()