//This code was created using Claude for the CRT display visuals

//Uses GLSL version 30
#version 330

//Gets the flipped UV coordinate and pixel coordinate from UV shader and outputs the end RGBA result for the pixel
in vec2 texCoord;
in vec2 pixCoord;
out vec4 fragColor;

//Sets the resolution and game surface from pygame for every pixel
uniform sampler2D Texture;
uniform vec2 resolution;

//Adjustable constants for each CRT visual effect
const float WARP_X        = 0.26;   //horizontal barrel distortion; was 0.065
const float WARP_Y        = 0.2;    //vertical barrel distortion; was 0.05

const float SCANLINE_DARK = 0.5;     //scanline intensity from 0-1; was 0.6, then 0.95
const float SCANLINE_SOFT = 0.5;     //scanline edge softness (higher is softer); was 1.5, then 0.3

const float MASK_STRENGTH = 0.25;    //phosphor RGB mask intensity
const float MASK_DOT_W    = 3.0;     //mask stripe width in pixels

const float BLOOM_SPREAD  = 2.5;     //bloom gaussian radius
const float BLOOM_AMOUNT  = 0.25;    //how much bloom adds to image

const float GAMMA_IN      = 2.4;     //input gamma
const float GAMMA_OUT     = 2.2;     //output gamma

const float VIGNETTE_STR  = 0.25;    // corner darkening strength
const float BRIGHTNESS    = 1.15;    // overall brightness boost

//Converts characters between gamma-corrected and linear space to let math like bloom work properly
vec3 toLinear(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(GAMMA_IN));
}
vec3 toSRGB(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(1.0 / GAMMA_OUT));
}

//Takes a normal UV coordinate and curves it to achieve a "barrel warp" outward curve like on a CRT screen
vec2 warp(vec2 uv) {
    vec2 dc = uv * 2.0 - 1.0; // center at (0,0)
    vec2 offset = dc.yx * dc.yx * vec2(WARP_X, WARP_Y);
    dc += dc * offset;
    return dc * 0.5 + 0.5; // back to 0..1
}

//Samples an area from the pygame texture and returns black if it's outside a certain area to create a hard bezel
vec3 fetchTexel(vec2 uv) {
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0)
        return vec3(0.0);
    return toLinear(texture(Texture, uv).rgb);
}

//Samples 25 nearby pixels in a grid and blends them with gaussian weight to create a glow around bright areas
vec3 bloom(vec2 uv) {
    vec2 texel = 1.0 / resolution;
    vec3 sum = vec3(0.0);
    float total = 0.0;

    for (int x = -2; x <= 2; x++) {
        for (int y = -2; y <= 2; y++) {
            float w = exp(-float(x*x + y*y) / (2.0 * BLOOM_SPREAD * BLOOM_SPREAD));
            sum  += fetchTexel(uv + vec2(x, y) * texel) * w;
            total += w;
        }
    }
    return sum / total;
}

//Returns a brightness multiplier alternating dark and bright to create line gaps horizontally (scanlines)
float scanline(vec2 warpedUV) {
    float s = sin(gl_FragCoord.y * 3.14159 + warpedUV.y * 300.0);
    s = pow(abs(s), SCANLINE_SOFT);
    return mix(1.0 - SCANLINE_DARK, 1.0, s);
}

//Returns an RGB multiplier cycling R, G, and B every three pixels horizontally to create a phosphor mask CRT effect
vec3 phosphorMask(vec2 px) {
    float col = mod(px.x + mod(floor(px.y), 2.0) * 1.5, MASK_DOT_W * 3.0);
    vec3 mask = vec3(1.0 - MASK_STRENGTH);
    if      (col < MASK_DOT_W)             mask.r += MASK_STRENGTH;
    else if (col < MASK_DOT_W * 2.0)       mask.g += MASK_STRENGTH;
    else                                    mask.b += MASK_STRENGTH;
    return mask;
}

//Returns a multiplier that darkens at the edges for a vignette effect
float vignette(vec2 uv) {
    vec2 d = uv * 2.0 - 1.0;
    return 1.0 - VIGNETTE_STR * dot(d, d);
}

//Calls all the above functions and multiplies them to get the final color for each pixel
void main() {

    //Barrel warp
    vec2 warpedUV = warp(texCoord);

    //Hard bezel outside warped screen
    if (warpedUV.x < 0.0 || warpedUV.x > 1.0 ||
        warpedUV.y < 0.0 || warpedUV.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    //Base color, linearized
    vec3 col = fetchTexel(warpedUV);

    //Bloom
    vec3 blm = bloom(warpedUV);
    col = col + blm * BLOOM_AMOUNT;

    //Scanlines
    col *= scanline(warpedUV);

    //Phosphor mask, using the warped pixel coordinates to align properly
    col *= phosphorMask(pixCoord);

    //Vignette
    col *= vignette(warpedUV);

    //Brightness boost
    col *= BRIGHTNESS;

    //Turn back to sRGB
    fragColor = vec4(toSRGB(col), 1.0);
}