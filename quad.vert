#version 330

in vec2 in_pos;
in vec2 in_uv;

out vec2 texCoord;
out vec2 pixCoord;

uniform vec2 resolution;

void main() {
    texCoord = vec2(in_uv.x, 1.0 - in_uv.y);
    pixCoord = texCoord * resolution;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}