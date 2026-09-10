// pySilver universal UI primitive shader.
//
// Every UI element -- boxes, borders, shadows, glyphs, images -- is one instance
// of a unit quad, drawn in a SINGLE instanced draw call. The fragment shader
// branches on `flags.x` to choose behaviour. See ARCHITECTURE.md 5.8.
//
// Two properties depend on this being a true signed distance field:
//   * antialiasing is analytic (fwidth over the distance), so no MSAA and no
//     resolve target, correct at any corner radius;
//   * clipping is a second SDF evaluation rather than a scissor rect, which
//     would split the draw call and cannot express rounded corners at all.
//
// All colours here are LINEAR (ARCHITECTURE.md 5.6.1) and output is
// PREMULTIPLIED, matching the One / OneMinusSrcAlpha blend state.

const KIND_BOX:     u32 = 0u;
const KIND_GLYPH:   u32 = 1u;
const KIND_IMAGE:   u32 = 2u;
const KIND_SHADOW:  u32 = 3u;
const KIND_ARC:     u32 = 4u;
const KIND_POLYGON: u32 = 5u;
const KIND_SEGMENT: u32 = 6u;

const TAU: f32 = 6.28318530718;
const PI:  f32 = 3.14159265359;

// Sentinel meaning "use the literal colour, not a palette lookup".
const NO_TOKEN: u32 = 0xFFFFFFFFu;

struct Globals {
    projection : mat4x4<f32>,
    viewport   : vec2<f32>,
    pixel_ratio: f32,
    _pad       : f32,
};

@group(0) @binding(0) var<uniform> globals : Globals;
@group(0) @binding(1) var<storage, read> palette : array<vec4<f32>>;
@group(0) @binding(2) var glyph_atlas : texture_2d<f32>;
@group(0) @binding(3) var image_atlas : texture_2d<f32>;
@group(0) @binding(4) var atlas_sampler : sampler;

struct VertexIn {
    @location(0) corner     : vec2<f32>,   // unit quad, (0,0)..(1,1)
    // --- per instance ---
    @location(1) rect       : vec4<f32>,   // x, y, w, h  (physical px)
    @location(2) radii      : vec4<f32>,   // tl, tr, br, bl
                                           // KIND_SEGMENT: ax, ay, bx, by (endpoints, rect-centre-relative)
    @location(3) clip       : vec4<f32>,
    @location(4) clip_radii : vec4<f32>,
    @location(5) fill       : vec4<f32>,
    @location(6) border     : vec4<f32>,
    @location(7) uv         : vec4<f32>,   // u0, v0, u1, v1
    @location(8) params     : vec4<f32>,   // border_w, blur, shadow_dx, shadow_dy
                                           // KIND_ARC: thickness, start, sweep, _
                                           // KIND_POLYGON: border_w, sides, rot, corner_r
                                           // KIND_SEGMENT: thickness, _, _, _
    @location(9) flags      : vec4<u32>,   // kind, atlas, fill_token, border_token
};

struct VertexOut {
    @builtin(position)                 position   : vec4<f32>,
    @location(0)                       frag_pos   : vec2<f32>,
    @location(1)                       uv         : vec2<f32>,
    @location(2) @interpolate(flat)    rect       : vec4<f32>,
    @location(3) @interpolate(flat)    radii      : vec4<f32>,
    @location(4) @interpolate(flat)    clip       : vec4<f32>,
    @location(5) @interpolate(flat)    clip_radii : vec4<f32>,
    @location(6) @interpolate(flat)    fill       : vec4<f32>,
    @location(7) @interpolate(flat)    border     : vec4<f32>,
    @location(8) @interpolate(flat)    params     : vec4<f32>,
    @location(9) @interpolate(flat)    flags      : vec4<u32>,
};

@vertex
fn vs_main(in: VertexIn) -> VertexOut {
    var out: VertexOut;
    let kind = in.flags.x;

    // The quad is grown so antialiasing and shadow blur are not clipped by
    // their own geometry. Textured kinds need no padding -- the atlas sample is
    // already antialiased, and padding would break the UV mapping.
    var pad = 0.0;
    if (kind == KIND_BOX || kind == KIND_ARC || kind == KIND_POLYGON || kind == KIND_SEGMENT) {
        pad = 1.5;
    } else if (kind == KIND_SHADOW) {
        pad = in.params.y * 3.0 + max(abs(in.params.z), abs(in.params.w)) + 2.0;
    }

    let origin = in.rect.xy - vec2<f32>(pad);
    let extent = in.rect.zw + vec2<f32>(pad * 2.0);
    let pos    = origin + in.corner * extent;

    out.position   = globals.projection * vec4<f32>(pos, 0.0, 1.0);
    out.frag_pos   = pos;
    out.uv         = mix(in.uv.xy, in.uv.zw, in.corner);
    out.rect       = in.rect;
    out.radii      = in.radii;
    out.clip       = in.clip;
    out.clip_radii = in.clip_radii;
    out.fill       = in.fill;
    out.border     = in.border;
    out.params     = in.params;
    out.flags      = in.flags;
    return out;
}

// Resolve a colour: palette lookup when a token index is present, else literal.
// Deliberately in the FRAGMENT stage -- storage buffers are not guaranteed
// visible to the vertex stage on every backend, and the cost here is trivial.
fn resolve(literal: vec4<f32>, token: u32) -> vec4<f32> {
    if (token == NO_TOKEN) {
        return literal;
    }
    let c = palette[token];
    return vec4<f32>(c.rgb, c.a * literal.a);   // literal.a carries opacity
}

// Signed distance to a rounded box centred at the origin.
// Negative inside, zero on the edge, positive outside.
fn sd_rounded_box(p: vec2<f32>, half: vec2<f32>, r: vec4<f32>) -> f32 {
    // r is (tl, tr, br, bl); pick the radius for the quadrant p falls in.
    let pair   = select(r.wz, r.xy, p.y < 0.0);   // top pair vs bottom pair
    // Clamped to the box's own half-extent: this formula assumes radius never
    // exceeds it, and silently returns "fully outside" everywhere -- an
    // invisible box, not a pill -- when a caller passes a larger one. Match
    // CSS's own border-radius behaviour (clamp to a stadium/circle) instead.
    let radius = min(select(pair.y, pair.x, p.x < 0.0), min(half.x, half.y));
    let q = abs(p) - half + radius;
    return min(max(q.x, q.y), 0.0) + length(max(q, vec2<f32>(0.0))) - radius;
}

// Exact signed distance to a regular `n`-gon of circumradius `r`, centred on
// the origin with a vertex at 12 o'clock and turned `rot` radians clockwise --
// the same direction ARC measures, and for the same reason: screen y grows
// downward, so matching M3's clockwise convention keeps the two consistent.
//
// The point is folded into a single sector by its angle, then measured against
// that sector's one edge. **The cost does not grow with the number of sides**,
// which is what makes a 3-gon and a 64-gon the same price -- and why morphing
// between them is free rather than something to budget for.
//
// `n` is a float on purpose. Between whole numbers the shape passes through
// non-regular intermediates, so animating it is continuous instead of a jump.
fn sd_regular_polygon(p_in: vec2<f32>, r: f32, n: f32, rot: f32) -> f32 {
    let c = cos(rot);
    let s = sin(rot);
    // Rotate the sample point by -rot, which turns the shape by +rot.
    let q0 = vec2<f32>(c * p_in.x + s * p_in.y, c * p_in.y - s * p_in.x);
    let an  = PI / n;
    let acs = vec2<f32>(cos(an), sin(an));
    // Angle from screen-up, folded into one sector. **Negated y**: the frame
    // grows downward, so folding from +Y would put the first vertex at 6
    // o'clock -- a triangle pointing down. Found by evaluating the field at
    // the four compass points rather than by looking at it.
    let raw  = atan2(q0.x, -q0.y);
    let span = 2.0 * an;
    let bn   = raw - span * floor(raw / span) - an;
    var q = length(q0) * vec2<f32>(cos(bn), abs(sin(bn)));
    q = q - r * acs;
    q.y = q.y + clamp(-q.y, 0.0, r * acs.y);
    return length(q) * sign(q.x);
}

// Signed distance to a circular arc of half-aperture `sc` = (sin, cos), centre
// radius `ra` and half-thickness `rb`. The arc is symmetric about +Y.
//
// Two cases: inside the wedge the nearest point is on the circle, so the
// distance is to the ring; outside it the nearest point is the cap centre, so
// the distance is to that point -- which is what gives round caps for free,
// and is why M3's rounded progress ends need no extra geometry.
fn sd_arc(p: vec2<f32>, sc: vec2<f32>, ra: f32, rb: f32) -> f32 {
    let q = vec2<f32>(abs(p.x), p.y);
    if (sc.y * q.x > sc.x * q.y) {
        return length(q - sc * ra) - rb;
    }
    return abs(length(q) - ra) - rb;
}

// Signed distance to a full ring. A sweep of a full turn must not go through
// sd_arc: its wedge test degenerates at half-aperture pi and seams at the join.
fn sd_ring(p: vec2<f32>, ra: f32, rb: f32) -> f32 {
    return abs(length(p) - ra) - rb;
}

// Exact signed distance to the line segment from `a` to `b`. Subtracting a
// radius from this field gives a capsule, and every point on the segment is
// rounded uniformly by doing so -- the caps come out round with no extra
// geometry, the same way sd_arc's cap case falls out of the ring distance
// rather than being drawn separately.
//
// `max(dot(ba, ba), 1e-6)` guards a degenerate `a == b`: without it a
// zero-length segment divides by zero and the capsule becomes a disc, which
// is the only sane thing for a point to render as anyway.
fn sd_segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let pa = p - a;
    let ba = b - a;
    let h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
    return length(pa - ba * h);
}

// Analytic coverage from a distance field. This is the whole antialiasing story.
fn coverage(d: f32) -> f32 {
    let aa = max(fwidth(d), 1e-5);
    return 1.0 - smoothstep(-aa, aa, d);
}

fn premultiply(c: vec4<f32>) -> vec4<f32> {
    return vec4<f32>(c.rgb * c.a, c.a);
}

@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    let kind = in.flags.x;
    let fill   = resolve(in.fill, in.flags.z);
    let border = resolve(in.border, in.flags.w);

    let center = in.rect.xy + in.rect.zw * 0.5;
    let half   = in.rect.zw * 0.5;
    let p      = in.frag_pos - center;

    var color = vec4<f32>(0.0);

    if (kind == KIND_BOX) {
        let d = sd_rounded_box(p, half, in.radii);
        let outer = coverage(d);

        let bw = in.params.x;
        if (bw > 0.0) {
            // Inset the same field by the border width; the ring is the
            // difference of the two coverages, so fill and border never
            // double-composite.
            let inner = coverage(d + bw);
            color = premultiply(fill) * inner
                  + premultiply(border) * max(0.0, outer - inner);
        } else {
            color = premultiply(fill) * outer;
        }

    } else if (kind == KIND_SHADOW) {
        let blur = max(in.params.y, 1e-4);
        let offset = vec2<f32>(in.params.z, in.params.w);
        let d = sd_rounded_box(p - offset, half, in.radii);
        // Gaussian approximated by a smoothstep ramp across the blur radius.
        let a = 1.0 - smoothstep(-blur, blur, d);
        color = premultiply(fill) * a;

    } else if (kind == KIND_ARC) {
        // Angles are measured clockwise from 12 o'clock, matching M3
        // ("circular indicators animate from the top of the track, clockwise").
        // Screen y grows downward, so 12 o'clock is -Y.
        let thickness = in.params.x;
        let start     = in.params.y;
        let sweep     = in.params.z;
        let rb        = thickness * 0.5;
        let ra        = max(min(half.x, half.y) - rb, 0.0);

        var d: f32;
        if (sweep >= TAU - 1e-4) {
            d = sd_ring(p, ra, rb);
        } else {
            // Rotate so the arc's midpoint lands on -Y, then flip into the
            // +Y-symmetric frame sd_arc expects.
            let mid = start + sweep * 0.5;
            let c = cos(mid);
            let sn = sin(mid);
            let rotated = vec2<f32>(p.x * c + p.y * sn, -p.x * sn + p.y * c);
            let hb = sweep * 0.5;
            d = sd_arc(vec2<f32>(rotated.x, -rotated.y), vec2<f32>(sin(hb), cos(hb)), ra, rb);
        }
        color = premultiply(fill) * coverage(d);

    } else if (kind == KIND_POLYGON) {
        // Inscribed in the shorter side, as ARC is -- a non-square rect gives a
        // regular polygon rather than a stretched one. Non-uniform scaling
        // would break the distance field and with it the analytic AA.
        let n   = max(in.params.y, 3.0);
        let r   = min(half.x, half.y);
        let an  = PI / n;
        // Rounding offsets the shape inward then back out, so the polygon is
        // shrunk by the radius measured on the APOTHEM, not the circumradius --
        // otherwise a rounded hexagon would come out smaller than a sharp one.
        // At the maximum the polygon collapses to a point and the result is its
        // inscribed circle, which is one of the two ways to morph to a circle
        // (raising `sides` is the other).
        let cr  = clamp(in.params.w, 0.0, r * cos(an));
        let d   = sd_regular_polygon(p, r - cr / cos(an), n, in.params.z) - cr;
        let outer = coverage(d);

        let bw = in.params.x;
        if (bw > 0.0) {
            let inner = coverage(d + bw);
            color = premultiply(fill) * inner
                  + premultiply(border) * max(0.0, outer - inner);
        } else {
            color = premultiply(fill) * outer;
        }

    } else if (kind == KIND_SEGMENT) {
        // Endpoints travel in `radii` -- unused by a stroke, which has no
        // corners -- rather than `uv`, which is already spoken for by the
        // interpolated texture coordinate GLYPH and IMAGE need. Both ends are
        // in the same rect-centre-relative frame `p` is, matching every other
        // kind's convention.
        let d = sd_segment(p, in.radii.xy, in.radii.zw) - in.params.x * 0.5;
        color = premultiply(fill) * coverage(d);

    } else if (kind == KIND_GLYPH) {
        // R8 coverage atlas tinted by the fill colour.
        let cov = textureSample(glyph_atlas, atlas_sampler, in.uv).r;
        color = premultiply(fill) * cov;

    } else if (kind == KIND_IMAGE) {
        let texel = textureSample(image_atlas, atlas_sampler, in.uv);
        color = premultiply(texel * fill) * coverage(sd_rounded_box(p, half, in.radii));
    }

    // Rounded clipping, evaluated analytically so the draw call stays whole.
    // A zero-size clip rect means "unclipped".
    if (in.clip.z > 0.0 && in.clip.w > 0.0) {
        let cc = in.clip.xy + in.clip.zw * 0.5;
        let ch = in.clip.zw * 0.5;
        color *= coverage(sd_rounded_box(in.frag_pos - cc, ch, in.clip_radii));
    }

    return color;
}
