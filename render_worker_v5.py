#!/usr/bin/env python3
"""v5 worker: static cover, beat-sensitive whole-frame rotation (sway+twist),
heavier shake (peak ~130px), stronger punchier flash, faster hue cycling."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import subprocess

W, H = 1920, 1080
FPS = 24
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
N_HUE = 16
PAD = 80

def smooth(x, k=5):
    k = max(1, k)
    return np.convolve(x, np.ones(k) / k, mode="same")

def rgb2hsv(rgb):
    rgb = rgb.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b); mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    idx = m & (mx == r); h[idx] = ((g[idx] - b[idx]) / d[idx]) % 6
    idx = m & (mx == g); h[idx] = (b[idx] - r[idx]) / d[idx] + 2
    idx = m & (mx == b); h[idx] = (r[idx] - g[idx]) / d[idx] + 4
    h = (h / 6.0) % 1.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return np.stack([h, s, mx], axis=-1)

def hsv2rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    h = h % 1.0
    i = (h * 6).astype(np.int32) % 6
    f = h * 6 - np.floor(h * 6)
    p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v]); g = np.choose(i, [t, v, v, q, p, p]); b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1) * 255.0

def text_layers(font, txt, y_top, h=190):
    def layer(color):
        img = Image.new("RGB", (W, h), (0, 0, 0))
        ImageDraw.Draw(img).text((W // 2, y_top), txt, font=font, fill=color, anchor="ma", stroke_width=2, stroke_fill=(0, 0, 0))
        return np.asarray(img).astype(np.float32)
    return layer((255, 255, 255)), layer((255, 70, 70)), layer((80, 220, 255))

def render_segment(part_path, start, end, seed):
    feats = np.load("assets/features.npz")
    bands = feats["bands"]; loud = feats["loud"]; sub = feats["sub"]; onset = feats["onset"]
    F = bands.shape[0]
    end = min(end, F)
    sub_s = smooth(sub, 5); loud_s = smooth(loud, 7)

    # ---- deterministic rotation curves (seamless across segment boundaries) ----
    # cover stays STATIC (no self-spin); whole-frame rotation reacts to music only.
    ts = np.arange(F) / FPS
    sway = (5.0 * loud_s * np.sin(ts * 2 * np.pi * 2.2)
            + 2.5 * loud_s * np.sin(ts * 2 * np.pi * 1.3 + 1.7))  # loud-driven sway
    # beat-driven transient twist: IIR lowpass of onset -> kick then settle back
    spin = np.zeros(F)
    s = 0.0
    for i in range(F):
        s = s * 0.86 + onset[i] * 5.0
        spin[i] = s
    rot_frame = sway + spin

    cover = Image.open("assets/cover_album_1024.jpg").convert("RGB")
    cover_orig = cover  # static reference, no spin
    bg_small = cover.resize((W // 8, H // 8), Image.LANCZOS).filter(ImageFilter.GaussianBlur(5))
    bg_hsv = rgb2hsv(np.asarray(bg_small).astype(np.float32))
    hues = np.linspace(0, 1, N_HUE, endpoint=False)
    bg_versions = np.stack([hsv2rgb(np.dstack([np.full_like(bg_hsv[..., 0], hh), bg_hsv[..., 1], bg_hsv[..., 2]])).astype(np.uint8) for hh in hues], 0)

    ANCHOR = 900
    anchor = cover.resize((ANCHOR, ANCHOR), Image.LANCZOS)
    anchor_arr = np.asarray(anchor).astype(np.float32)

    font = ImageFont.truetype(FONT, 92)
    white_l, red_l, cyan_l = text_layers(font, "DESTRUCTION 3,2,1", 40)

    N_BANDS = bands.shape[1]
    c0 = np.array([64, 112, 255], np.float32); c1 = np.array([150, 92, 246], np.float32); c2 = np.array([236, 96, 240], np.float32)
    tt = np.linspace(0, 1, N_BANDS)[:, None]
    grad = np.where(tt < 0.5, c0 + (c1 - c0) * (tt * 2), c1 + (c2 - c1) * (tt * 2 - 1)).astype(np.uint8)
    bar_w = W // N_BANDS
    BAR_TOP, BAR_BOTTOM = 925, 1075
    rng = np.random.default_rng(seed)
    cx, cy = W // 2, H // 2

    ff = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", part_path,
    ], stdin=subprocess.PIPE)

    flash, waves, bar_peak = 0.0, [], np.zeros(N_BANDS, np.float32)
    for i in range(start, end):
        # beat flash computed first so cover pulse can ride it
        flash = max(flash * 0.88, min(1.6, onset[i] * 1.15))

        hue = (i / F * 3.0 + sub_s[i] * 0.7) % 1.0
        fh = hue * N_HUE
        i0 = int(fh) % N_HUE; i1 = (i0 + 1) % N_HUE; frac = fh - int(fh)
        bga = bg_versions[i0].astype(np.float32) * (1 - frac) + bg_versions[i1].astype(np.float32) * frac
        frame = np.asarray(Image.fromarray(bga.astype(np.uint8)).resize((W, H), Image.BILINEAR)).astype(np.float32)
        frame *= (0.30 + 1.0 * float(loud_s[i]))

        # ---- STATIC COVER (pulse scale only, no spin) ----
        pulse = (1.0 + 0.08 * float(sub_s[i])) * (1.0 + 0.10 * flash)
        s = int(ANCHOR * pulse)
        a = anchor_arr if s == ANCHOR else np.asarray(anchor.resize((s, s), Image.BILINEAR)).astype(np.float32)
        x0 = int(cx - s / 2); y0 = int(cy - s / 2 - 20)
        x1 = min(W, x0 + s); y1 = min(H, y0 + s)
        x0 = max(0, x0); y0 = max(0, y0)
        if x1 > x0 and y1 > y0:
            frame[y0:y1, x0:x1] = a[0:y1 - y0, 0:x1 - x0]

        if loud_s[i] > 0.04:
            aa = 0.80 + 0.30 * loud_s[i]
            y = 36 + int(rng.integers(-3, 4)) + int(8 * np.sin(i * 0.13))
            seg = frame[y:y + 190]
            seg[..., 0] += red_l[..., 0] * aa * 0.95 + white_l[..., 0] * aa * 0.6
            seg[..., 1] += white_l[..., 1] * aa * 0.6 + cyan_l[..., 1] * aa * 0.5
            seg[..., 2] += cyan_l[..., 2] * aa * 0.95 + white_l[..., 2] * aa * 0.6

        sep = int(3 + 12 * loud_s[i])
        if sep > 1:
            r = frame[..., 0].copy(); b2 = frame[..., 2].copy()
            frame[..., 0] = np.roll(r, sep, axis=1); frame[..., 2] = np.roll(b2, -sep, axis=1)

        if rng.random() < 0.26:
            for _ in range(int(rng.integers(2, 6))):
                sy0 = int(rng.integers(160, H - 40)); sh = int(rng.integers(8, 26))
                frame[sy0:sy0 + sh] = np.roll(frame[sy0:sy0 + sh].copy(), int(rng.integers(-70, 71)), axis=1)

        if rng.random() < 0.05:
            small = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR)
            frame = np.asarray(small.resize((W, H), Image.NEAREST)).astype(np.float32)

        b = np.clip(bands[i] * 1.1 - 0.03, 0, 1)
        bar_peak = np.maximum(bar_peak * 0.78, b)
        bh = (b * 0.88 + bar_peak * 0.12) * (BAR_BOTTOM - BAR_TOP)
        for k in range(N_BANDS):
            hh = int(bh[k])
            if hh < 2:
                continue
            col = grad[k]; xa, xb = k * bar_w + 2, (k + 1) * bar_w - 1; yb0 = BAR_BOTTOM - hh
            frame[yb0:BAR_BOTTOM, xa:xb, 0] = col[0]; frame[yb0:BAR_BOTTOM, xa:xb, 1] = col[1]; frame[yb0:BAR_BOTTOM, xa:xb, 2] = col[2]
            g0 = max(0, yb0 - 26); frame[g0:yb0, xa:xb] += col * 0.22
        for k in range(N_BANDS):
            hh = int(bh[k])
            if hh > 4:
                yb0 = BAR_BOTTOM - hh
                frame[yb0:yb0 + max(2, hh // 7), k * bar_w + 2:(k + 1) * bar_w - 1] = 255

        # punchy brightness: instant attack on beats, smooth exponential decay
        frame *= (0.55 + 0.70 * flash)
        frame += flash * 70

        if onset[i] > 0.25:
            waves.append([140, 0.95])
        nw = []
        for r0_, al in waves:
            r0_ += 34 + 14 * float(sub_s[i]); al *= 0.84
            if r0_ > 1250 or al < 0.05:
                continue
            rw = max(5, int(r0_ * 0.035))
            xa = int(max(0, cx - r0_ - rw - 2)); xb = int(min(W, cx + r0_ + rw + 2))
            ya = int(max(0, cy - r0_ - rw - 2)); yb = int(min(H, cy + r0_ + rw + 2))
            if xb <= xa or yb <= ya:
                continue
            yy, xx = np.mgrid[ya:yb, xa:xb]
            ring = (np.abs(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - r0_) <= rw)
            if ring.any():
                frame[ya:yb, xa:xb][ring] += np.array([255, 170, 255]) * al
            nw.append([r0_, al])
        waves = nw

        # HEAVIER rhythmic shake: peak ~130px, faster sine, more noise
        A = int(8 + sub_s[i] * 120)
        if A > 0:
            tsi = i / FPS
            dx = A * (0.5 * np.sin(tsi * 2 * np.pi * 3.6) + 0.5 * rng.uniform(-1, 1))
            dy = A * (0.5 * np.sin(tsi * 2 * np.pi * 4.2 + 1.7) + 0.5 * rng.uniform(-1, 1))
            canvas = np.pad(frame, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="reflect")
            frame = canvas[PAD + int(dy):PAD + int(dy) + H, PAD + int(dx):PAD + int(dx) + W]

        # ---- WHOLE-FRAME SWAY ROTATION (deterministic, no black corners) ----
        rot_f = float(rot_frame[i])
        if abs(rot_f) > 0.05:
            pil = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8))
            r = pil.rotate(rot_f, resample=Image.BILINEAR, expand=True)
            w2, h2 = r.size
            x0 = (w2 - W) // 2; y0 = (h2 - H) // 2
            frame = np.asarray(r.crop((x0, y0, x0 + W, y0 + H))).astype(np.float32)

        ff.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
    ff.stdin.close()
    ff.wait()
    print(f"part done {start}-{end} -> {part_path}", flush=True)

if __name__ == "__main__":
    part, s, e, sd = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    render_segment(part, s, e, sd)
