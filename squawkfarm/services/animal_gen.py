import os, math, random, numpy as np, librosa

from PIL import Image, ImageDraw, ImageOps


def analyze_env(path, sr=16000, frame=1024, hop=256, offset=None, duration=None):
    y, sr = librosa.load(path, sr=sr, mono=True, offset=offset, duration=duration)
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]
    if rms.max() > 0: rms = rms / rms.max()
    rms = np.sqrt(rms)
    return y, sr, rms

def feature_summaries(y, sr):
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    rms      = float(librosa.feature.rms(y=y).mean())
    zcr      = float(librosa.feature.zero_crossing_rate(y=y).mean())
    f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr, frame_length=2048, hop_length=512)
    energy = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    voiced = energy > (energy.max() * 0.1)
    pitch  = float(np.median(f0[voiced])) if np.any(voiced) else 0.0
    return dict(centroid=centroid, rms=rms, zcr=zcr, pitch=pitch)

W_FRAME, H_FRAME = 420, 340

PALETTES = [
    dict(base=(242,204,38,255),  accent=(255,238,150,255), dark=(45,45,45,255)),
    dict(base=(160,231,229,255), accent=(200,245,244,255), dark=(40,60,60,255)),
    dict(base=(180,167,255,255), accent=(210,200,255,255), dark=(60,50,100,255)),
    dict(base=(255,174,188,255), accent=(255,210,220,255), dark=(50,30,50,255)),
    dict(base=(137,207,240,255), accent=(190,230,255,255), dark=(40,60,90,255)),
]

def mouth_sector_points(cx, cy, rx, ry, half_deg, center_deg=0.0, steps=72, rscale=1.16, ang_pad=6.0):
    a_lo = math.radians(center_deg - (half_deg + ang_pad))
    a_hi = math.radians(center_deg + (half_deg + ang_pad))
    pts = [(cx, cy)]
    for i in range(steps+1):
        a = a_lo + (a_hi - a_lo) * (i / steps)
        x = cx + (rx*rscale) * math.cos(a)
        y = cy - (ry*rscale) * math.sin(a)
        pts.append((x, y))
    return pts

def superellipse_points(cx, cy, rx, ry, n=2.0, steps=320):
    pts = []
    for i in range(steps):
        t = 2*math.pi * i/steps
        ct, st = math.cos(t), math.sin(t)
        x = cx + rx * (abs(ct) ** (2/n)) * (1 if ct>=0 else -1)
        y = cy - ry * (abs(st) ** (2/n)) * (1 if st>=0 else -1)
        pts.append((x,y))
    return pts

def superformula_points(cx, cy, rx, ry, m=0.0, n1=2.0, n2=2.0, n3=2.0, steps=360):
    pts = []
    for i in range(steps):
        phi = 2*math.pi * i/steps
        t1 = abs(math.cos(m*phi/4)) ** n2
        t2 = abs(math.sin(m*phi/4)) ** n3
        r = (t1 + t2) ** (-1.0/n1) if (t1+t2)!=0 else 0
        x = cx + rx * r * math.cos(phi)
        y = cy - ry * r * math.sin(phi)
        pts.append((x,y))
    return pts

def body_mask(size, cx, cy, rx, ry):
    W,H = size
    mask = Image.new("L", (W,H), 0)
    ImageDraw.Draw(mask).ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255)
    return mask

def draw_stripes_pattern(img, cx, cy, rx, ry, color):
    mask = body_mask(img.size, cx, cy, rx, ry)
    layer = Image.new("RGBA", img.size, (0,0,0,0))
    d = ImageDraw.Draw(layer)
    stripe_w = max(6, int(rx*0.18)); gap = stripe_w
    x = int(cx-rx)
    while x < int(cx+rx):
        d.rectangle([x, cy-ry, x+stripe_w, cy+ry], fill=color)
        x += stripe_w + gap
    img.paste(layer, (0,0), mask)

def draw_gradient_pattern(img, cx, cy, rx, ry, color_from, color_to):
    mask = body_mask(img.size, cx, cy, rx, ry)
    layer = Image.new("RGBA", img.size, (0,0,0,0))
    grad = Image.new("RGBA", (int(2*rx), int(2*ry)), (0,0,0,0))
    gd = ImageDraw.Draw(grad)
    span = int(min(2*rx, 2*ry))
    for i in range(span, 0, -4):
        t = i / float(span)
        r = int(color_from[0]*t + color_to[0]*(1-t))
        g = int(color_from[1]*t + color_to[1]*(1-t))
        b = int(color_from[2]*t + color_to[2]*(1-t))
        a = int(90*(1-t)+12)
        gd.ellipse([(grad.size[0]-i)/2, (grad.size[1]-i)/2, (grad.size[0]+i)/2, (grad.size[1]+i)/2], fill=(r,g,b,a))
    layer.paste(grad, (int(cx-rx), int(cy-ry)))
    img.paste(layer, (0,0), mask)

def body_top_y_at_x(cx, cy, rx, ry, oblong, x):
    dx2 = ((x - cx) / rx) ** 2
    if dx2 >= 1.0: return cy
    term = math.sqrt(max(0.0, 1.0 - dx2))
    return cy - (ry*oblong) * term

def draw_body(drw, cx, cy, rx, ry, pal, body_mode, body_param, oblong_scale=1.0):
    ry_scaled = ry * oblong_scale
    if body_mode == 'superellipse':
        n = 1.0 + 5.0*body_param
        pts = superellipse_points(cx, cy, rx, ry_scaled, n=n, steps=320)
    else:
        m = 6.0 * body_param
        n1 = 0.3 + 2.0*body_param
        n2 = n3 = 0.3 + 2.0*body_param
        pts = superformula_points(cx, cy, rx, ry_scaled, m=m, n1=n1, n2=n2, n3=n3, steps=360)
    drw.polygon(pts, fill=pal['base'])
    drw.line(pts + [pts[0]], fill=pal['dark'], width=3)

def draw_ears_flush_on_top(drw, cx, cy, rx, ry, oblong, ear_type, color):
    overlap = 2.0; back_shift = rx * 0.08; ex = rx * 0.36
    if ear_type == 'round':
        r = rx * 0.20
        for sx in (-1, +1):
            x_ear = cx + sx*ex - back_shift
            y_top = body_top_y_at_x(cx, cy, rx, ry, oblong, x_ear)
            cy_e = (y_top + overlap) - r
            drw.ellipse([x_ear - r, cy_e - r, x_ear + r, cy_e + r], fill=color)
    elif ear_type == 'long':
        w, h = rx*0.22, ry*0.55
        for sx in (-1, +1):
            x_ear = cx + sx*ex - back_shift
            y_top = body_top_y_at_x(cx, cy, rx, ry, oblong, x_ear)
            y_bottom = y_top + overlap
            drw.ellipse([x_ear - w/2, y_bottom - h, x_ear + w/2, y_bottom], fill=color)
    else:
        base_w = rx*0.26; h = ry*0.58
        for sx in (-1, +1):
            x_ear = cx + sx*ex - back_shift
            y_top = body_top_y_at_x(cx, cy, rx, ry, oblong, x_ear)
            y_base = y_top + overlap
            b0 = (x_ear - base_w/2, y_base)
            b1 = (x_ear + base_w/2, y_base)
            apex = (x_ear, y_base - h)
            drw.polygon([apex, b0, b1], fill=color)

def draw_eye(drw, cx, cy, rx, ry, pal, eye_shape='circle', eye_scale=1.0):
    ex = cx - rx + 0.54*(2*rx); ey = cy - ry + 0.28*(2*ry)
    base = max(5, int(min(rx, ry)*0.08)); r = max(4, int(base * eye_scale))
    if eye_shape == 'circle':
        drw.ellipse([ex-r, ey-r, ex+r, ey+r], fill=pal['dark'])
    elif eye_shape == 'h_oval':
        drw.ellipse([ex-1.6*r, ey-0.9*r, ex+1.6*r, ey+0.9*r], fill=pal['dark'])
    elif eye_shape == 'v_oval':
        drw.ellipse([ex-0.9*r, ey-1.6*r, ex+0.9*r, ey+1.6*r], fill=pal['dark'])
    elif eye_shape == 'diamond':
        drw.polygon([(ex, ey-1.1*r), (ex+1.1*r, ey), (ex, ey+1.1*r), (ex-1.1*r, ey)], fill=pal['dark'])
    else:
        drw.polygon([(ex, ey-1.2*r), (ex+1.1*r, ey+0.8*r), (ex-1.1*r, ey+0.8*r)], fill=pal['dark'])
    drw.ellipse([ex - 0.25*r, ey - 0.15*r, ex + 0.5*r, ey + 0.25*r], fill=(255,255,255,160))

def draw_mouth(drw, cx, cy, rx, ry, open_deg):
    pts = mouth_sector_points(cx, cy, rx, ry, half_deg=open_deg, center_deg=0.0, steps=72, rscale=1.16, ang_pad=6.0)
    drw.polygon(pts, fill=(0,0,0,255))

def fit_body_to_canvas(cx, cy, rx, ry, oblong, margin=18):
    left = cx - rx; right = cx + rx
    top = cy - ry*oblong; bottom = cy + ry*oblong
    sx = sy = 1.0
    if left < margin:  sx = min(sx, (cx - margin) / rx)
    if right > W_FRAME - margin: sx = min(sx, (W_FRAME - margin - cx) / rx)
    if top < margin:   sy = min(sy, (cy - margin) / (ry*oblong))
    if bottom > H_FRAME - margin: sy = min(sy, (H_FRAME - margin - cy) / (ry*oblong))
    scale = min(sx, sy, 1.0)
    if scale < 1.0: rx *= scale; ry *= scale
    return rx, ry

def params_from_audio(y, sr, seed=None):
    rnd = random.Random(seed)
    f0 = feature_summaries(y, sr)['pitch'] if len(y) else 220.0
    if not (f0 and f0 > 0): f0 = 220.0
    f0 = float(np.clip(f0, 60, 1200))
    t_pitch = (math.log2(f0) - math.log2(60)) / (math.log2(1200) - math.log2(60))
    t_pitch = max(0.0, min(1.0, t_pitch))
    rx = 45 + (170 - 45) * (1.0 - t_pitch)
    ry = 40 + (160 - 40) * (1.0 - t_pitch)
    pal      = rnd.choice(PALETTES)
    oblong   = rnd.uniform(0.6, 1.6)
    body_mode  = rnd.choice(['superellipse', 'superformula'])
    body_param = rnd.uniform(0.0, 1.0)
    ear_type   = rnd.choice(['round', 'long', 'pointy'])
    pattern    = rnd.choice(['none', 'gradient', 'stripes'])
    eye_shape  = rnd.choice(['circle','h_oval','v_oval','diamond','tri'])
    eye_scale  = rnd.uniform(0.6, 1.8)
    return dict(palette=pal, rx=rx, ry=ry, oblong=oblong, body_mode=body_mode, body_param=body_param, ear_type=ear_type, pattern=pattern, eye_shape=eye_shape, eye_scale=eye_scale)

def fill_body_opaque(img, cx, cy, rx, ry, color):
    mask = body_mask(img.size, cx, cy, rx, ry)
    solid = Image.new("RGBA", img.size, color)
    img.paste(solid, (0, 0), mask)

def _ear_up_extent(rx, ry, oblong, ear_type):
    if ear_type == 'round':
        return rx * 0.20
    elif ear_type == 'long':
        return ry * 0.55
    else:
        return ry * 0.58

def render_creature_image(wav_path, out_dir, size=(W_FRAME, H_FRAME), offset=None, duration=None, seed=None):
    os.makedirs(out_dir, exist_ok=True)
    closed_path = os.path.join(out_dir, "closed.png")
    open_path   = os.path.join(out_dir, "open.png")

    y, sr, _env = analyze_env(wav_path, sr=16000, offset=offset, duration=duration)
    params = params_from_audio(y, sr, seed=seed)

    W, H = int(size[0]), int(size[1])
    pal = params['palette']
    rx, ry, oblong = params['rx'], params['ry'], params['oblong']

    ear_up = _ear_up_extent(rx, ry, oblong, params['ear_type'])
    body_span = (rx + ry*oblong) / 2.0

    leg_len = max(32, int(body_span * 0.52))
    overlap_in = max(10, 0.22*ry*oblong)
    leg_down = leg_len - overlap_in

    half_w_needed = rx * 1.16
    above = ry*oblong + ear_up
    below = ry*oblong + leg_down
    margin = 20

    sx = (W/2 - margin) / max(half_w_needed, 1e-6)
    sy = (H/2 - margin) / max(above, below, 1e-6)
    s = min(1.0, sx, sy)

    if s < 1.0:
        rx *= s
        ry *= s
        ear_up *= s
        leg_len = int(leg_len * s)
        overlap_in *= s
        leg_down *= s

    cx = W * 0.5
    cy = H * 0.5 + (leg_down - ear_up) / 2.0

    for name, mouth_deg in (("closed", 8), ("open", 55)):
        path = os.path.join(out_dir, f"{name}.png")

        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        bottom_y = cy + ry * oblong
        leg_top  = bottom_y - overlap_in
        leg_w   = max(6, int(((rx + ry*oblong) / 2.0) * 0.12))
        base_x = cx - rx * 0.20
        spacing = rx * 0.28
        left_x  = base_x - spacing / 2
        right_x = base_x + spacing / 2

        d.rectangle(
            [left_x  - leg_w/2, leg_top, left_x  + leg_w/2, leg_top + leg_len],
            fill=pal['base'],
        )
        d.rectangle(
            [right_x - leg_w/2, leg_top, right_x + leg_w/2, leg_top + leg_len],
            fill=pal['base'],
        )
        fill_body_opaque(img, cx, cy, rx, ry, pal['base'])
        draw_ears_flush_on_top(d, cx, cy, rx, ry, oblong, params['ear_type'], pal['base'])
        draw_body(d, cx, cy, rx, ry, pal, params['body_mode'], params['body_param'], oblong_scale=oblong)

        if params['pattern'] == 'gradient':
            draw_gradient_pattern(img, cx, cy, rx, ry, pal['accent'], pal['base'])
        elif params['pattern'] == 'stripes':
            draw_stripes_pattern(img, cx, cy, rx, ry, pal['accent'])

        draw_eye(d, cx, cy, rx, ry, pal, eye_shape=params['eye_shape'], eye_scale=params['eye_scale'])
        draw_mouth(d, cx, cy, rx, ry, open_deg=mouth_deg)

        img.save(path)

        left_path = os.path.join(out_dir, f"{name}_left.png")
        flipped = ImageOps.mirror(img)
        flipped.save(left_path)

    return closed_path, open_path
