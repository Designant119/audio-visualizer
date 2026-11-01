#!/usr/bin/env python3
"""v2: full-bleed dynamic cover + heavy glitch + shockwave + glitch title"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import subprocess

W, H = 1920, 1080
FPS = 24
SEED = 42
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def smooth(x, k=5):
    k = max(1, k)
    return np.convolve(x, np.ones(k) / k, mode="same")

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
    big = cover.resize((2400, 2400), Image.LANCZOS)

    # glitch title layers
    font = ImageFont.truetype(FONT, 92)
    white_l, red_l, cyan_l = text_layers(font, "DESTRUCTION 3,2,1", 40)

    N_BANDS = bands.shape[1]
    c0 = np.array([64, 112, 255], np.float32)
    c1 = np.array([150, 92, 246], np.float32)
    c2 = np.array([236, 96, 240], np.float32)
    t = np.linspace(0, 1, N_BANDS)[:, None]
    grad = np.where(t < 0.5, c0 + (c1 - c0) * (t * 2), c1 + (c2 - c1) * (t * 2 - 1)).astype(np.uint8)

    bar_w = W // N_BANDS          # ~36
    BAR_TOP, BAR_BOTTOM = 905, 1060
    rng = np.random.default_rng(SEED)

    # shockwave ring rendering (localized numpy)
    cx, cy = W // 2, H // 2

    out_path = "destruction_321_v2.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", "assets/song.mp3",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out_path,
    ], stdin=subprocess.PIPE)

    flash = 0.0
    waves = []                     # [(radius, alpha)]
    bar_peak = np.zeros(N_BANDS, np.float32)
    ken_phase = 0.0

    for i in range(F):
        # ---- full-bleed cover with ken burns + bass parallax ----
        ken_phase += 0.0065
        sc = 1.06 + 0.10 * (0.5 + 0.5 * np.sin(ken_phase))
        ww, wh = int(W * sc), int(H * sc)
        x0 = (2400 - ww) // 2 + int(9 * np.sin(i * 0.023)) + int(sub_s[i] * 22)
        y0 = (2400 - wh) // 2 + int(16 * np.sin(i * 0.017)) + int(sub_s[i] * 20)
        x0 = max(0, min(2400 - ww, x0)); y0 = max(0, min(2400 - wh, y0))
        win = big.crop((x0, y0, x0 + ww, y0 + wh)).resize((W, H), Image.BILINEAR)
        frame = np.asarray(win).astype(np.float32)
        frame *= 0.88

        # ---- bass pulse: whole-frame zoom pulse (approx via scale of copy is costly; do vignette-scale fake) ----
        pulse = 1.0 + 0.05 * float(sub_s[i])

        # ---- glitch title (pre-rendered layers, additive) ----
        if loud_s[i] > 0.04:
            a = 0.72 + 0.28 * loud_s[i]
            off = 3 + int(9 * loud_s[i])
            jit = int(rng.integers(-2, 3))
            y = 36 + jit + int(5 * np.sin(i * 0.11))
            seg = frame[y:y + 190]
            seg[..., 0] += red_l[..., 0] * a * 0.85 + white_l[..., 0] * a * 0.5
            seg[..., 1] += white_l[..., 1] * a * 0.5 + cyan_l[..., 1] * a * 0.4
            seg[..., 2] += cyan_l[..., 2] * a * 0.85 + white_l[..., 2] * a * 0.5

        # ---- RGB aberration, strength rides loudness ----
        sep = int(2 + 7 * loud_s[i])
        if sep > 1:
            r = frame[..., 0].copy(); b2 = frame[..., 2].copy()
            frame[..., 0] = np.roll(r, sep, axis=1)
            frame[..., 2] = np.roll(b2, -sep, axis=1)

        # ---- random horizontal tear strips ----
        if rng.random() < 0.16:
            n_strips = int(rng.integers(1, 4))
            for _ in range(n_strips):
                sy0 = int(rng.integers(180, H - 40))
                sh = int(rng.integers(6, 22))
                shift = int(rng.integers(-46, 47))
                strip = frame[sy0:sy0 + sh].copy()
                frame[sy0:sy0 + sh] = np.roll(strip, shift, axis=1)

        # ---- rare pixelation flash ----
        if rng.random() < 0.028:
            small = np.asarray(Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR))
            frame = np.asarray(Image.fromarray(small).resize((W, H), Image.NEAREST)).astype(np.float32)

        # ---- spectrum bars ----
        b = bands[i]
        b = np.clip(b * 1.1 - 0.03, 0, 1)
        bar_peak = np.maximum(bar_peak * 0.80, b)
        bh = (b * 0.88 + bar_peak * 0.12) * (BAR_BOTTOM - BAR_TOP)
        for k in range(N_BANDS):
            h = int(bh[k])
            if h < 2:
                continue
            col = grad[k]
            xa, xb = k * bar_w + 2, (k + 1) * bar_w - 1
            yb0 = BAR_BOTTOM - h
            frame[yb0:BAR_BOTTOM, xa:xb, 0] = col[0]
            frame[yb0:BAR_BOTTOM, xa:xb, 1] = col[1]
            frame[yb0:BAR_BOTTOM, xa:xb, 2] = col[2]
            # glow above bar
            g = 26
            yg0 = max(0, yb0 - g)
            frame[yg0:yb0, xa:xb] *= (1.0 - 0.5)  # dim area behind
            frame[yg0:yb0, xa:xb] += col * 0.22
        # white hot tops
        for k in range(N_BANDS):
            h = int(bh[k])
            if h > 4:
                yb0 = BAR_BOTTOM - h
                frame[yb0:yb0 + max(2, h // 7), k * bar_w + 2:(k + 1) * bar_w - 1] = 255

        # ---- onset flash ----
        flash = max(flash * 0.72, min(1.0, onset[i] * 0.5))
        if flash > 0.04:
            frame += flash * 22

        # ---- shockwaves from center ----
        if onset[i] > 0.30:
            waves.append([140, 0.85])
        new_waves = []
        for r0_, al in waves:
            r0_ += 26 + 10 * float(sub_s[i])
            al *= 0.86
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
            new_waves.append([r0_, al])
        waves = new_waves

        # ---- brightness pulse with bass (global) ----
        frame *= (0.94 + 0.08 * float(sub_s[i]))

        out = np.clip(frame, 0, 255).astype(np.uint8)
        ff.stdin.write(out.tobytes())
        if i % 300 == 0:
            print(f"frame {i}/{F}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done:", out_path)

if __name__ == "__main__":
    main()
