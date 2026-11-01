#!/usr/bin/env python3
"""Render cover-based audio visualizer frames -> pipe to ffmpeg -> MP4"""
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageOps
import subprocess, sys, os

W, H = 1920, 1080
FPS = 24
COVER_SIZE = 920          # displayed cover square
COVER_CX, COVER_CY = 960, 455
BAR_TOP = 945             # spectrum bar area
BAR_BOTTOM = 1065
SEED = 42

def extract_colors(img):
    """pick accent colors from cover: cluster-ish sample of saturated pixels"""
    a = np.asarray(img.resize((64, 64), Image.LANCZOS)).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    sat = a.max(axis=2) - a.min(axis=2)
    mask = sat > 30
    if mask.sum() > 20:
        pr, pg, pb = r[mask].mean(), g[mask].mean(), b[mask].mean()
        return (int(pr), int(pg), int(pb))
    return (120, 110, 255)

def build_background(img):
    """blurred stretched cover as bg, darkened"""
    bg = img.resize((W, H), Image.LANCZOS)
    bg = bg.resize((W // 8, H // 8), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
    bg = bg.resize((W, H), Image.BILINEAR)
    a = np.asarray(bg).astype(np.float32)
    a *= 0.42
    a = np.clip(a, 0, 255).astype(np.uint8)
    return a

def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    v = np.clip(1.25 - d * 0.45, 0.25, 1.0)
    return v[..., None].astype(np.float32)

def smooth(x, k=5):
    k = max(1, k)
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")

def main():
    feats = np.load("assets/features.npz")
    bands = feats["bands"]          # (F, 64) 0..1
    loud = feats["loud"]
    sub = feats["sub"]
    onset = feats["onset"]
    F = bands.shape[0]
    sub_s = smooth(sub, 5)
    loud_s = smooth(loud, 5)

    cover = Image.open("assets/cover_album_1024.jpg").convert("RGB")
    cover_sq = ImageOps.fit(cover, (COVER_SIZE, COVER_SIZE), Image.LANCZOS)
    cover_arr = np.asarray(cover_sq).astype(np.float32)
    bg = build_background(cover)
    vig = make_vignette()
    accent = extract_colors(cover)
    print("accent color:", accent)

    # bar gradient: accent-ish blue -> purple -> pink
    N_BANDS = bands.shape[1]
    c0 = np.array([64, 112, 255], np.float32)
    c1 = np.array([150, 92, 246], np.float32)
    c2 = np.array([236, 96, 240], np.float32)
    t = np.linspace(0, 1, N_BANDS)[:, None]
    grad = np.where(t < 0.5, c0 + (c1 - c0) * (t * 2), c1 + (c2 - c1) * (t * 2 - 1)).astype(np.uint8)

    bar_w = W // N_BANDS
    rng = np.random.default_rng(SEED)

    out_path = "destruction_321_visual.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", "assets/song.mp3",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out_path,
    ], stdin=subprocess.PIPE)

    flash = 0.0
    bar_peak = np.zeros(N_BANDS, np.float32)   # peak hold for bar tops
    for i in range(F):
        frame = bg.copy().astype(np.float32)
        # --- bass pulse: cover scale + shake ---
        pulse = 1.0 + 0.035 * float(sub_s[i])
        shake = 0 if sub_s[i] < 0.15 else min(3, sub_s[i] * 3.2)
        sx = rng.uniform(-shake, shake); sy = rng.uniform(-shake, shake)
        s = int(COVER_SIZE * pulse)
        if s != COVER_SIZE:
            cv = np.asarray(cover_sq.resize((s, s), Image.BILINEAR)).astype(np.float32)
        else:
            cv = cover_arr
        x0 = int(COVER_CX - s / 2 + sx); y0 = int(COVER_CY - s / 2 + sy)
        x1 = min(W, x0 + s); y1 = min(H, y0 + s)
        x0 = max(0, x0); y0 = max(0, y0)
        if x1 > x0 and y1 > y0:
            cv_part = cv[:y1 - y0 - (H - (y0 + s)) if False else y1 - y0, :x1 - x0]
            # crop source to pasted region
            src = cv[0:y1 - y0, 0:x1 - x0]
            frame[y0:y1, x0:x1] = src
        # --- spectrum bars ---
        b = bands[i]
        b = np.clip(b * 1.1 - 0.03, 0, 1)   # mild contrast
        bar_peak = np.maximum(bar_peak * 0.82, b)
        bh = (b * 0.85 + bar_peak * 0.15) * (BAR_BOTTOM - BAR_TOP)
        for k in range(N_BANDS):
            h = int(bh[k])
            if h <= 1:
                h = 1 if b[k] > 0.02 else 0
            if h <= 0:
                continue
            col = grad[k]
            yb0 = BAR_BOTTOM - h
            frame[yb0:BAR_BOTTOM, k * bar_w:(k + 1) * bar_w, 0] = col[0]
            frame[yb0:BAR_BOTTOM, k * bar_w:(k + 1) * bar_w, 1] = col[1]
            frame[yb0:BAR_BOTTOM, k * bar_w:(k + 1) * bar_w, 2] = col[2]
        # white hot tops
        for k in range(N_BANDS):
            h = int(bh[k])
            if h > 4:
                yb0 = BAR_BOTTOM - h
                frame[yb0:yb0 + max(2, h // 6), k * bar_w:(k + 1) * bar_w] = 255
        # --- onset flash + edge glow ---
        flash = max(flash * 0.78, min(1.0, onset[i] * 0.55))
        if flash > 0.03:
            frame += flash * 26
        # --- vignette ---
        frame *= vig
        # --- subtle glitch: rare RGB shift ---
        if rng.random() < 0.04:
            sh = rng.integers(-7, 8)
            r = frame[..., 0].copy(); g = frame[..., 1].copy(); b2 = frame[..., 2].copy()
            frame[..., 0] = np.roll(r, sh, axis=1)
            frame[..., 2] = np.roll(b2, -sh, axis=1)
        out = np.clip(frame, 0, 255).astype(np.uint8)
        ff.stdin.write(out.tobytes())
        if i % 300 == 0:
            print(f"frame {i}/{F}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done:", out_path)

if __name__ == "__main__":
    main()
