"""
TODO:
functionize all planets/targets
center planet sprites
planet collision?
level progression

"""
#Import libraries
import pygame
import sys
import random
import math
import moderngl
import numpy as np

#This section code was created using Claude for the CRT visual effects. Sections created using Claude are within the hyphen lines
#──────────────────────────────────────────────────────────────────
#Sets the window and game resolution, initializes Pygame and creates an OpenGL window mode
WINDOW_SIZE = (800, 600)
GAME_RES = (800, 600)
pygame.init()
pygame.display.set_mode(WINDOW_SIZE, pygame.OPENGL | pygame.DOUBLEBUF) #Uses DOUBLEBUF to prevent tearing by drawing one frame while displaying another

#Creates ModernGL context (interface to GPU)
ctx = moderngl.create_context()

#Creates a pygame surface that's drawn on normally before being sent to GPU
game_surface = pygame.Surface(GAME_RES)

#Creates a GPU texture to hold the game surface. 4 means RGBA and linear causes smooth sampling rather than pixelating
texture = ctx.texture(GAME_RES, 4)
texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

#Reads the shader files
with open("quad.vert") as f:
    vert_src = f.read()
with open("crt.frag") as f:
    frag_src = f.read()

#Compiles the shaders to a GPU program and sets the two uniforms
program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
program["Texture"]    = 0
program["resolution"] = WINDOW_SIZE

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

#Control framerate with clock and set other game state variables
clock = pygame.time.Clock()
x     = 30.0
speed = 1.5
#──────────────────────────────────────────────────────────────────


#----------------------------------- GAME VARIABLES -----------------------------------#
G = 0.2

isDragging = False
mouseStartPos = (0, 0)
mouseCurrentPos = (0, 0)
LaunchMultiplier = 0.02
predictSteps = 50

shipWidth = 42
shipHeight = 42
titleIsShown = True

#map of star locations
backgroundStarPositions = [
    (random.randint(1, 3), (random.randint(1, 800), random.randint(1, 700)))
    for _ in range(50)
]

planets = [
    {
        "mass": 10000, "x": 364, "y": 300,
        "vx": 0.0, "vy": 0.0, "radius": 10, "color": (0, 150, 255),
        "trail": [],
        "surface": pygame.transform.scale(pygame.image.load("images/redscale planet 1.png").convert_alpha(), (84, 84))
    },

    {
        "mass": 3000, "x": 364, "y": 150,
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
    "surface": shipImage,
    "mask": pygame.mask.from_surface(shipImage)
}

targetSurface = pygame.transform.scale(pygame.image.load("images/redscale target x.png").convert_alpha(), (shipWidth, shipHeight))
targets = [
    {
        "x": 650,
        "y": 300,
        "state": "UNHIT",
        "surface": targetSurface,
        "mask": pygame.mask.from_surface(targetSurface)
     },
     {
        "x": 300,
        "y": 100,
        "state": "UNHIT",
        "surface": targetSurface,
        "mask": pygame.mask.from_surface(targetSurface)
     }
    ]

#----------------------------------- GAME FUNCTIONS -----------------------------------#
def checkCollision(target):
    offset = (int(ship["x"] - target["x"]), int(ship["y"] - target["y"]))
    return target["mask"].overlap(ship["mask"], offset) is not None

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

def checkPlanetCollision():
    for p in planets:
        planet_cx = p["x"] + p["surface"].get_width() / 2
        planet_cy = p["y"] + p["surface"].get_height() / 2
        ship_cx = ship["x"] + shipWidth / 2
        ship_cy = ship["y"] + shipHeight / 2
        
        distance = math.sqrt((ship_cx - planet_cx)**2 + (ship_cy - planet_cy)**2)
        #use image size as radius
        collision_radius = p["surface"].get_width() / 2
        
        if distance < collision_radius:
            ship["vx"] = 0
            ship["vy"] = 0
            resetField()

def resetField():
    for t in targets:
        t["state"] = "UNHIT"
        t["x"] = random.randint(50, 750)
        t["y"] = random.randint(50, 500)
    ship["state"] = "LAUNCH"
    ship["x"], ship["y"] = 100, 364
    ship["trail"] = []

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                resetField()
        elif (event.type == pygame.MOUSEBUTTONDOWN and ship["state"] == "LAUNCH"):
            titleIsShown = False
            mouseX, mouseY = event.pos
            clickDist = math.sqrt((mouseX - ship["x"])**2 + (mouseY - ship["y"])**2)
            if clickDist < 40:
                isDragging = True
                mouseStartPos = event.pos
                mouseCurrentPos = event.pos
        elif event.type == pygame.MOUSEMOTION and isDragging:
            titleIsShown = False
            mouseCurrentPos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and isDragging:
            titleIsShown = False
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
        #checkPlanetCollision()

        ship["x"] += ship["vx"]
        ship["y"] += ship["vy"]
    calculateForces(planets[1], [planets[i] for i, v in enumerate(planets) if i != 1])
    #calculateForces(planets[2], [planets[i] for i, v in enumerate(planets) if i != 2])
    for p in planets:
        p["x"] += p["vx"]
        p["y"] += p["vy"]

    #Fill game surface to cover previous frame
    game_surface.fill((35, 35, 55))

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

    for t in targets:
        if t["state"] == "UNHIT":
            game_surface.blit(t["surface"], (t["x"], t["y"]))
            if checkCollision(t):
                t["state"] = "HIT"

    if all(t["state"] == "HIT" for t in targets):
        resetField()

    #Draw title
    if titleIsShown:
        titleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 128)
        titleText = titleFont.render("RED-EYE", True, (255, 1, 1))
        titleRect = titleText.get_rect(center = (400, 100))
        game_surface.blit(titleText, titleRect)
        subtitleFont = pygame.font.Font("fonts/VCR_OSD_MONO_1.001.ttf", 32)
        subtitleText = subtitleFont.render("PULL BACK SHIP TO START", True, (255, 1, 1))
        subtitleRect = subtitleText.get_rect(center = (400, 175))
        game_surface.blit(subtitleText, subtitleRect)

    drawLaunchLine(game_surface)

    #────────────────────────────────────────────────────────────────── Claude coded for CRT visuals
    #Converts game_surface to bytes and uploads it to GPU texture each frame. Binds texture to slot 0 to match earlier code
    texture.write(pygame.image.tobytes(game_surface, "RGBA", False))
    texture.use(0)

    #Clears the screen to black and runs shaders
    ctx.clear(0.0, 0.0, 0.0)
    vao.render()

    #Swaps buffers to show new frame and caps framerate at 60 fps
    pygame.display.flip()
    clock.tick(60)
    #──────────────────────────────────────────────────────────────────

pygame.quit()