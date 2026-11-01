#!/usr/bin/env python3
"""v3: color-shifting background (hue follows music) + strong whole-frame shake + stable cover anchor"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import subprocess

W, H = 1920, 1080
FPS = 24
SEED = 42
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
N_HUE = 16

def smooth(x, k=5):
    k = max(1, k)
    return np.convolve(x, np.ones(k) / k, mode="same")

def rgb2hsv(rgb):
    rgb = rgb.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
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
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1) * 255.0

def text_layers(font, txt, y_top, h=190):
    def layer(color):
        img = Image.new("RGB", (W, h), (0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((W // 2, y_top), txt, font=font, fill=color, anchor="ma",
               stroke_width=2, stroke_fill=(0, 0, 0))
        return np.asarray(img).astype(np.float32)
    return layer((255, 255, 255)), layer((255, 70, 70)), layer((80, 220, 255))

def main():
    feats = np.load("assets/features.npz")
    bands = feats["bands"]; loud = feats["loud"]; sub = feats["sub"]; onset = feats["onset"]
    F = bands.shape[0]
    sub_s = smooth(sub, 5); loud_s = smooth(loud, 7)

    cover = Image.open("assets/cover_album_1024.jpg").convert("RGB")

    # ---------- color-shifting background: 16 hue versions (small) ----------
    bg_small = cover.resize((W // 8, H // 8), Image.LANCZOS)          # 240x135
    bg_small = bg_small.filter(ImageFilter.GaussianBlur(5))
    bg_hsv = rgb2hsv(np.asarray(bg_small).astype(np.float32))
    hues = np.linspace(0, 1, N_HUE, endpoint=False)
    bg_versions = []
    for hh in hues:
        hsv = bg_hsv.copy(); hsv[..., 0] = hh
        bg_versions.append(hsv2rgb(hsv).astype(np.uint8))
    bg_versions = np.stack(bg_versions, 0)   # (N_HUE, 135, 240, 3)

    # stable cover anchor (keep original colors), slightly smaller
    ANCHOR = 900
    anchor = cover.resize((ANCHOR, ANCHOR), Image.LANCZOS)
    anchor_arr = np.asarray(anchor).astype(np.float32)

    # glitch title
    font = ImageFont.truetype(FONT, 92)
    white_l, red_l, cyan_l = text_layers(font, "DESTRUCTION 3,2,1", 40)

    N_BANDS = bands.shape[1]
    c0 = np.array([64, 112, 255], np.float32)
    c1 = np.array([150, 92, 246], np.float32)
    c2 = np.array([236, 96, 240], np.float32)
    t = np.linspace(0, 1, N_BANDS)[:, None]
    grad = np.where(t < 0.5, c0 + (c1 - c0) * (t * 2), c1 + (c2 - c1) * (t * 2 - 1)).astype(np.uint8)

    bar_w = W // N_BANDS
    BAR_TOP, BAR_BOTTOM = 925, 1075
    rng = np.random.default_rng(SEED)

    cx, cy = W // 2, H // 2
    PAD = 26

    out_path = "destruction_321_v3.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", "assets/song.mp3",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out_path,
    ], stdin=subprocess.PIPE)

    flash = 0.0
    waves = []
    bar_peak = np.zeros(N_BANDS, np.float32)

    for i in range(F):
        # ---------- color-shifting background (oversized, shake = crop window) ----------
        hue = (i / F * 2.5 + sub_s[i] * 0.55) % 1.0
        fh = hue * N_HUE
        i0 = int(fh) % N_HUE; i1 = (i0 + 1) % N_HUE; frac = fh - int(fh)
        bga = bg_versions[i0].astype(np.float32) * (1 - frac) + bg_versions[i1].astype(np.float32) * frac
        bg = Image.fromarray(bga.astype(np.uint8)).resize((W + 2 * PAD, H + 2 * PAD), Image.BILINEAR)
        bg_np = np.asarray(bg).astype(np.float32)
        bg_np *= (0.62 + 0.30 * float(sub_s[i]))      # brightness rides sub
        A = int(3 + sub_s[i] * 15)                     # shake amplitude
        dx = int(rng.uniform(-A, A)); dy = int(rng.uniform(-A, A))
        frame = bg_np[PAD + dy:PAD + dy + H, PAD + dx:PAD + dx + W]   # view, zero-copy

        # ---------- stable anchor cover (original colors, follows shake slightly) ----------
        pulse = 1.0 + 0.04 * float(sub_s[i])
        s = int(ANCHOR * pulse)
        a = anchor_arr if s == ANCHOR else np.asarray(anchor.resize((s, s), Image.BILINEAR)).astype(np.float32)
        x0 = int(cx - s / 2 + dx * 0.5); y0 = int(cy - s / 2 - 20 + dy * 0.5)
        x1 = min(W, x0 + s); y1 = min(H, y0 + s)
        x0 = max(0, x0); y0 = max(0, y0)
        if x1 > x0 and y1 > y0:
            frame[y0:y1, x0:x1] = a[0:y1 - y0, 0:x1 - x0]

        # ---------- glitch title ----------
        if loud_s[i] > 0.04:
            aa = 0.72 + 0.28 * loud_s[i]
            off = 3 + int(9 * loud_s[i])
            jit = int(rng.integers(-2, 3))
            y = 36 + jit + int(5 * np.sin(i * 0.11))
            seg = frame[y:y + 190]
            seg[..., 0] += red_l[..., 0] * aa * 0.85 + white_l[..., 0] * aa * 0.5
            seg[..., 1] += white_l[..., 1] * aa * 0.5 + cyan_l[..., 1] * aa * 0.4
            seg[..., 2] += cyan_l[..., 2] * aa * 0.85 + white_l[..., 2] * aa * 0.5

        # ---------- RGB aberration ----------
        sep = int(2 + 8 * loud_s[i])
        if sep > 1:
            r = frame[..., 0].copy(); b2 = frame[..., 2].copy()
            frame[..., 0] = np.roll(r, sep, axis=1)
            frame[..., 2] = np.roll(b2, -sep, axis=1)

        # ---------- random tear strips ----------
        if rng.random() < 0.17:
            for _ in range(int(rng.integers(1, 4))):
                sy0 = int(rng.integers(180, H - 40))
                sh = int(rng.integers(6, 22))
                strip = frame[sy0:sy0 + sh].copy()
                frame[sy0:sy0 + sh] = np.roll(strip, int(rng.integers(-46, 47)), axis=1)

        # ---------- pixelation flash ----------
        if rng.random() < 0.03:
            small = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR)
            frame = np.asarray(small.resize((W, H), Image.NEAREST)).astype(np.float32)

        # ---------- spectrum bars ----------
        b = bands[i]
        b = np.clip(b * 1.1 - 0.03, 0, 1)
        bar_peak = np.maximum(bar_peak * 0.80, b)
        bh = (b * 0.88 + bar_peak * 0.12) * (BAR_BOTTOM - BAR_TOP)
        for k in range(N_BANDS):
            hh = int(bh[k])
            if hh < 2:
                continue
            col = grad[k]
            xa, xb = k * bar_w + 2, (k + 1) * bar_w - 1
            yb0 = BAR_BOTTOM - hh
            frame[yb0:BAR_BOTTOM, xa:xb, 0] = col[0]
            frame[yb0:BAR_BOTTOM, xa:xb, 1] = col[1]
            frame[yb0:BAR_BOTTOM, xa:xb, 2] = col[2]
            g0 = max(0, yb0 - 26)
            frame[g0:yb0, xa:xb] += col * 0.22
        for k in range(N_BANDS):
            hh = int(bh[k])
            if hh > 4:
                yb0 = BAR_BOTTOM - hh
                frame[yb0:yb0 + max(2, hh // 7), k * bar_w + 2:(k + 1) * bar_w - 1] = 255

        # ---------- flash ----------
        flash = max(flash * 0.72, min(1.0, onset[i] * 0.5))
        if flash > 0.04:
            frame += flash * 22

        # ---------- shockwaves ----------
        if onset[i] > 0.30:
            waves.append([140, 0.85])
        nw = []
        for r0_, al in waves:
            r0_ += 26 + 10 * float(sub_s[i]); al *= 0.86
            if r0_ > 1250 or al < 0.05:
                continue
            rw = max(5, int(r0_ * 0.035))
            xa = int(max(0, cx - r0_ - rw - 2)); xb = int(min(W, cx + r0_ + rw + 2))
            ya = int(max(0, cy - r0_ - rw - 2)); yb = int(min(H, cy + r0_ + rw + 2))
            if xb <= xa or yb <= ya:
                continue
            yy, xx = np.mgrid[ya:yb, xa:xb]
            d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            ring = (np.abs(d - r0_) <= rw)
            if ring.any():
                frame[ya:yb, xa:xb][ring] += np.array([190, 150, 255]) * al * 0.85
            nw.append([r0_, al])
        waves = nw

        # ---------- STRONG whole-frame shake: already applied via crop window above ----------

        out = np.clip(frame, 0, 255).astype(np.uint8)
        ff.stdin.write(out.tobytes())
        if i % 300 == 0:
            print(f"frame {i}/{F}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done:", out_path)

if __name__ == "__main__":
    from PIL import ImageFilter
    main()
