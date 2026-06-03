#version 330

in vec2 texCoord;
in vec2 pixCoord;
out vec4 fragColor;

uniform sampler2D Texture;
uniform vec2 resolution;

// ─── Tuneable parameters ───────────────────────────────────────────────────
const float WARP_X        = 0.00;   // horizontal barrel distortion; was 0.065
const float WARP_Y        = 0.00;    // vertical barrel distortion; was 0.05

const float SCANLINE_DARK = 0.6;     // 0=no scanlines, 1=fully black gaps
const float SCANLINE_SOFT = 1.5;     // higher = softer scanline edges

const float MASK_STRENGTH = 0.25;    // phosphor RGB mask intensity
const float MASK_DOT_W    = 3.0;     // mask stripe width in pixels

const float BLOOM_SPREAD  = 2.5;     // bloom gaussian radius
const float BLOOM_AMOUNT  = 0.25;    // how much bloom adds to image

const float GAMMA_IN      = 2.4;     // input gamma
const float GAMMA_OUT     = 2.2;     // output gamma

const float VIGNETTE_STR  = 0.25;    // corner darkening strength
const float BRIGHTNESS    = 1.15;    // overall brightness boost

// ─── Helpers ───────────────────────────────────────────────────────────────

vec3 toLinear(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(GAMMA_IN));
}

vec3 toSRGB(vec3 c) {
    return pow(max(c, vec3(0.0)), vec3(1.0 / GAMMA_OUT));
}

// Barrel / pincushion warp. Input and output are 0..1 UV space.
vec2 warp(vec2 uv) {
    vec2 dc = uv * 2.0 - 1.0;               // centre at (0,0)
    vec2 offset = dc.yx * dc.yx * vec2(WARP_X, WARP_Y);
    dc += dc * offset;
    return dc * 0.5 + 0.5;                  // back to 0..1
}

// Sample with hard clamp — returns black outside screen area
vec3 fetchTexel(vec2 uv) {
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0)
        return vec3(0.0);
    return toLinear(texture(Texture, uv).rgb);
}

// Simple 9-tap Gaussian bloom (separable would be faster, fine for 600px)
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

// Scanline darkening — smooth sine-based dip between lines
float scanline(vec2 warpedUV) {
    // pixCoord equivalent for warped position
    float line = warpedUV.y * resolution.y;
    float phase = fract(line);   // 0..1 within each scanline
    // sine dip: darkest at phase=0 (line boundary), bright at 0.5 (centre)
    float s = sin(phase * 3.14159);
    s = pow(s, SCANLINE_SOFT);
    return mix(1.0 - SCANLINE_DARK, 1.0, s);
}

// RGB phosphor shadow mask — mimics aperture grille stripes
vec3 phosphorMask(vec2 px) {
    // cycle of 3 pixels wide, RGB stripes, shifted every other row
    float col = mod(px.x + mod(floor(px.y), 2.0) * 1.5, MASK_DOT_W * 3.0);
    vec3 mask = vec3(1.0 - MASK_STRENGTH);
    if      (col < MASK_DOT_W)             mask.r += MASK_STRENGTH;
    else if (col < MASK_DOT_W * 2.0)       mask.g += MASK_STRENGTH;
    else                                    mask.b += MASK_STRENGTH;
    return mask;
}

// Vignette — darkens corners
float vignette(vec2 uv) {
    vec2 d = uv * 2.0 - 1.0;
    return 1.0 - VIGNETTE_STR * dot(d, d);
}

// ─── Main ──────────────────────────────────────────────────────────────────
void main() {

    // 1. Barrel warp
    vec2 warpedUV = warp(texCoord);

    // 2. Black bezel outside warped screen
    if (warpedUV.x < 0.0 || warpedUV.x > 1.0 ||
        warpedUV.y < 0.0 || warpedUV.y > 1.0) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // 3. Base colour (linearised)
    vec3 col = fetchTexel(warpedUV);

    // 4. Bloom — mix bright halo into base
    vec3 blm = bloom(warpedUV);
    col = col + blm * BLOOM_AMOUNT;

    // 5. Scanlines
    col *= scanline(warpedUV);

    // 6. Phosphor mask — use warped pixel coords for correct alignment
    col *= phosphorMask(pixCoord);

    // 7. Vignette
    col *= vignette(warpedUV);

    // 8. Brightness boost
    col *= BRIGHTNESS;

    // 9. Back to sRGB
    fragColor = vec4(toSRGB(col), 1.0);
}