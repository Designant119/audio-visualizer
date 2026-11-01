#!/usr/bin/env python3
"""v12: HARD-PULSE tremor (no bounce), zero-black cover spin (overscan affine),
NEW LAYOUT: cover left/smaller, vertical spectrum right, title right-top.
No shockwave rings. Cover/title tremor ±15 deg, bg ±30 deg."""
import sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import subprocess

W, H = 1920, 1080
FPS = 24
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
N_HUE = 12
PAD = 160  # must exceed max shake A = 8 + sub*120 (peak 128), else slices shrink frames
# blurred background is rotated at small size then upscaled: cheap + no black corners
BG_W, BG_H = 640, 360
OV = 760  # overscan square source, covers diag sqrt(640^2+360^2)=734.5

# ---- NEW LAYOUT (v15: full-screen spectrum wall) ----
ANCHOR = 750          # cover display size (left)
CX, CY = 480, 540     # cover center (left side)
OVC = 1200            # (unused in v14: cover spins full-size w/ transparent corners)
TX = 1420             # title center x (right side)
TY_TOP = 80           # title band top y
TITLE_FONT = 85
# vertical spectrum on the right: low freq at bottom, high at top, bars grow left
BAR_LEFT, BAR_RIGHT = 0, W          # full-width spectrum wall
BAR_TOP_Y, BAR_BOTTOM_Y = 240, H          # top band reserved for title

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

def text_layers(font, txt, y_top, cx, h=190):
    def layer(color):
        img = Image.new("RGB", (W, h), (0, 0, 0))
        ImageDraw.Draw(img).text((cx, y_top), txt, font=font, fill=color, anchor="ma", stroke_width=2, stroke_fill=(0, 0, 0))
        return np.asarray(img).astype(np.float32)
    return layer((255, 255, 255)), layer((255, 70, 70)), layer((80, 220, 255))

def render_segment(part_path, start, end, seed):
    feats = np.load("assets/features.npz")
    bands = feats["bands"]; loud = feats["loud"]; sub = feats["sub"]; onset = feats["onset"]
    F = bands.shape[0]
    end = min(end, F)
    sub_s = smooth(sub, 5); loud_s = smooth(loud, 7)

    # ---- background TREMOR: HARD PULSE (no resonance, no bounce) ----
    # each drum hit snaps the angle toward its peak in 1-2 frames, then decays
    # to zero in ~2-3 frames. Zero oscillation -> hard, not bouncy. Deterministic.
    # bg clip ±30 deg; cover & title ride 0.5x -> ±15 deg.
    decay, K = 0.30, 20.0
    oin = np.clip(onset, 0.0, 1.5)
    angle = 0.0
    rot_bg = np.zeros(F)
    for i in range(F):
        angle = angle * decay + oin[i] * K
        rot_bg[i] = min(30.0, max(-30.0, angle))
    rot_fg = rot_bg * 0.5  # cover & title: ±15 deg, same phase

    cover = Image.open("assets/cover_album_1024.jpg").convert("RGB")
    # FULL cover is always shown (never cropped). Rotation: rotate the RGBA cover
    # with expand=True -> corners are transparent, so the live background shows
    # through instead of black boxes. Cover size stays constant while spinning.
    anchor = cover.resize((ANCHOR, ANCHOR), Image.LANCZOS)
    anchor_rgba = anchor.convert("RGBA")
    anchor_arr = np.asarray(anchor).astype(np.float32)
    # overscan background source: small square, blurred, hue-cycled (cheap)
    bg_src = cover.resize((OV, OV), Image.LANCZOS).filter(ImageFilter.GaussianBlur(8))
    bg_hsv = rgb2hsv(np.asarray(bg_src).astype(np.float32))
    hues = np.linspace(0, 1, N_HUE, endpoint=False)
    bg_versions = np.stack([hsv2rgb(np.dstack([np.full_like(bg_hsv[..., 0], hh), bg_hsv[..., 1], bg_hsv[..., 2]])).astype(np.uint8) for hh in hues], 0)

    font = ImageFont.truetype(FONT, TITLE_FONT)
    white_l, red_l, cyan_l = text_layers(font, "DESTRUCTION 3,2,1", TY_TOP, TX)
    # author line (static RGBA layer under the title, right-aligned to TX)
    font_a = ImageFont.truetype(FONT, 34)
    author_img = Image.new("RGBA", (W, 64), (0, 0, 0, 0))
    ImageDraw.Draw(author_img).text(
        (TX, 32), "Normal1zer vs. Broken Nerdz", font=font_a,
        fill=(255, 255, 255, 205), anchor="ma",
        stroke_width=2, stroke_fill=(0, 0, 0, 180))
    author_np = np.asarray(author_img).astype(np.float32)
    font_t = ImageFont.truetype(FONT, 30)
    timer_canvas = Image.new("RGBA", (360, 44), (0, 0, 0, 0))
    # rotatable RGBA title layer (color + alpha mask) for tremor rotation
    txt_rgb = np.clip(white_l * 0.6 + red_l * 0.95 + cyan_l * 0.95, 0, 255)
    txt_alpha = np.clip(np.maximum(white_l[..., 0], np.maximum(red_l[..., 0], cyan_l[..., 0])), 0, 255)
    txt_img = np.dstack([txt_rgb, txt_alpha])

    N_BANDS = bands.shape[1]
    c0 = np.array([64, 112, 255], np.float32); c1 = np.array([150, 92, 246], np.float32); c2 = np.array([236, 96, 240], np.float32)
    tt = np.linspace(0, 1, N_BANDS)[:, None]
    grad = np.where(tt < 0.5, c0 + (c1 - c0) * (tt * 2), c1 + (c2 - c1) * (tt * 2 - 1)).astype(np.uint8)
    grad_hsv = rgb2hsv(grad.astype(np.float32))  # for hue-rotating bars with the background
    bar_w = (BAR_RIGHT - BAR_LEFT) / N_BANDS  # vertical bars: width per column
    spec_h = BAR_BOTTOM_Y - BAR_TOP_Y
    rng = np.random.default_rng(seed)
    cx, cy = CX, CY  # cover center (left); shockwave rings removed

    # write raw frames to FILE (pipe writes were dropping tail frames deterministically)
    raw_path = part_path + ".raw"
    rawf = open(raw_path, "wb")

    def _drop_cache():
        # free page cache of the raw file so 3.7GB writes cannot exhaust the
        # 4GB cgroup (which silently kills concurrent/next segment)
        try:
            os.posix_fadvise(rawf.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        except Exception:
            pass

    flash, bar_peak = 0.0, np.zeros(N_BANDS, np.float32)
    for i in range(start, end):
        # beat flash computed first so cover pulse can ride it
        flash = max(flash * 0.88, min(1.6, onset[i] * 1.15))

        hue = (i / F * 3.0 + sub_s[i] * 0.7) % 1.0
        fh = hue * N_HUE
        i0 = int(fh) % N_HUE; i1 = (i0 + 1) % N_HUE; frac = fh - int(fh)
        bga = bg_versions[i0].astype(np.float32) * (1 - frac) + bg_versions[i1].astype(np.float32) * frac
        # rotate the BACKGROUND via affine transform from overscan source -> no black corners
        th = float(rot_bg[i]) * np.pi / 180.0
        co, si = np.cos(th), np.sin(th)
        cxs, cys = OV / 2, OV / 2
        aff = (co, si, cxs - co * BG_W / 2 - si * BG_H / 2,
               -si, co, cys + si * BG_W / 2 - co * BG_H / 2)
        small = Image.fromarray(bga.astype(np.uint8)).transform(
            (BG_W, BG_H), Image.AFFINE, aff, resample=Image.BILINEAR)
        frame = np.asarray(small.resize((W, H), Image.BILINEAR)).astype(np.float32)
        frame *= (0.30 + 1.0 * float(loud_s[i]))
        # brightness flash comes BEFORE the spectrum: the background lights up
        # first, then the bars sample the already-bright background colour, so
        # they stay bright (previously the flash after the bars crushed them).
        frame *= (0.55 + 0.30 * flash)
        frame += flash * 25

        # ---- SPECTRUM FUSED INTO BACKGROUND ----
        # bars take their colour from the background column directly below them
        # (same hue, brighter) -> spectrum looks like bright ridges growing out
        # of the background; whole layer is softly blurred afterwards.
        b = np.clip(bands[i] * 1.1 - 0.03, 0, 1)
        bar_peak = np.maximum(bar_peak * 0.78, b)
        bv = b * 0.88 + bar_peak * 0.12
        # sample each column's background colour BEFORE drawing any bar
        # DEEP variant: same hue as background, but saturation deepened and
        # brightness capped -> rich, dense bars instead of washed-out bright ones
        cols = np.zeros((N_BANDS, 3), np.float32)
        for k in range(N_BANDS):
            xm = int(BAR_LEFT + (k + 0.5) * bar_w)
            strip = frame[BAR_TOP_Y:BAR_BOTTOM_Y, max(0, xm - 8):min(W, xm + 9)]
            cols[k] = strip.mean(axis=(0, 1))
        chsv = rgb2hsv(cols)
        chsv[..., 1] = np.clip(chsv[..., 1] * 1.4, 0, 1.0)                      # deepen saturation
        chsv[..., 2] = np.clip(chsv[..., 2] * (1.15 + 0.25 * float(flash)), 0, 0.80)  # keep hue, cap brightness
        cols = hsv2rgb(chsv).astype(np.float32)
        alpha = 0.45 + 0.06 * float(flash)
        for k in range(N_BANDS):
            v = bv[k]
            if v < 0.03:
                continue
            hgt = int(v * spec_h)
            xa = int(BAR_LEFT + k * bar_w) + 1
            xb = int(BAR_LEFT + (k + 1) * bar_w) - 1
            if xb <= xa:
                continue
            y0 = BAR_BOTTOM_Y - hgt
            col = cols[k]
            seg = frame[y0:BAR_BOTTOM_Y, xa:xb]
            seg[..., 0] = seg[..., 0] * (1 - alpha) + col[0] * alpha
            seg[..., 1] = seg[..., 1] * (1 - alpha) + col[1] * alpha
            seg[..., 2] = seg[..., 2] * (1 - alpha) + col[2] * alpha
        # soft-fuse the spectrum into the background (background is already blurry)
        frame = np.asarray(Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(5))).astype(np.float32)

        # ---- COVER (left): FULL cover, HARD-PULSE tremor rotation ----
        # rotate the RGBA cover with expand=True: transparent corners reveal the
        # live background (no black box), cover content stays complete & full-size.
        pulse = (1.0 + 0.08 * float(sub_s[i])) * (1.0 + 0.10 * flash)
        s = int(ANCHOR * pulse)
        rc = float(rot_fg[i])
        if abs(rc) > 0.2:
            img = anchor_rgba if s == ANCHOR else anchor_rgba.resize((s, s), Image.BILINEAR)
            rot = img.rotate(rc, resample=Image.BILINEAR, expand=True)  # RGBA, transparent corners
            rw, rh = rot.size
            rarr = np.asarray(rot).astype(np.float32)
            tx = int(cx - rw / 2); ty = int(cy - rh / 2)
            xa = max(0, tx); xb = min(W, tx + rw); ya = max(0, ty); yb = min(H, ty + rh)
            if xb > xa and yb > ya:
                sub = rarr[ya - ty:yb - ty, xa - tx:xb - tx]
                seg = frame[ya:yb, xa:xb]
                al = sub[..., 3:4] / 255.0
                seg[..., 0] = seg[..., 0] * (1 - al[..., 0]) + sub[..., 0] * al[..., 0]
                seg[..., 1] = seg[..., 1] * (1 - al[..., 0]) + sub[..., 1] * al[..., 0]
                seg[..., 2] = seg[..., 2] * (1 - al[..., 0]) + sub[..., 2] * al[..., 0]
        else:
            a = anchor_arr if s == ANCHOR else np.asarray(anchor.resize((s, s), Image.BILINEAR)).astype(np.float32)
            x0 = int(cx - s / 2); y0 = int(cy - s / 2)
            x1 = min(W, x0 + s); y1 = min(H, y0 + s)
            x0 = max(0, x0); y0 = max(0, y0)
            if x1 > x0 and y1 > y0:
                frame[y0:y1, x0:x1] = a[0:y1 - y0, 0:x1 - x0]

        if loud_s[i] > 0.04:
            # title STAYS STILL: no rotation, no y-jitter (info text must be readable)
            aa = 0.80 + 0.30 * loud_s[i]
            y = TY_TOP
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

        # mild brightness boost for cover/title layer (main flash already applied
        # to the background before the spectrum)
        frame *= (1.0 + 0.25 * flash)
        frame += flash * 18

        # ---- AUTHOR + TIME COUNTER (always visible, top-right under title /
        # bottom-right) ----
        ay0 = TY_TOP + 126
        suba = author_np
        seg = frame[ay0:ay0 + 64, :, :]
        al = suba[..., 3:4] / 255.0
        seg[..., 0] = seg[..., 0] * (1 - al[..., 0]) + suba[..., 0] * al[..., 0]
        seg[..., 1] = seg[..., 1] * (1 - al[..., 0]) + suba[..., 1] * al[..., 0]
        seg[..., 2] = seg[..., 2] * (1 - al[..., 0]) + suba[..., 2] * al[..., 0]
        # time counter: M:SS / 2:38
        cur = i / FPS
        tstr = "%d:%02d / 2:38" % (int(cur // 60), int(cur % 60))
        timer_canvas.paste((0, 0, 0, 0), (0, 0, 360, 44))
        ImageDraw.Draw(timer_canvas).text(
            (354, 22), tstr, font=font_t, fill=(255, 255, 255, 175),
            anchor="rm", stroke_width=2, stroke_fill=(0, 0, 0, 160))
        tarr = np.asarray(timer_canvas).astype(np.float32)
        tx0 = W - 60 - 360; ty0 = H - 52
        seg = frame[ty0:ty0 + 44, tx0:tx0 + 360]
        al = tarr[..., 3:4] / 255.0
        seg[..., 0] = seg[..., 0] * (1 - al[..., 0]) + tarr[..., 0] * al[..., 0]
        seg[..., 1] = seg[..., 1] * (1 - al[..., 0]) + tarr[..., 1] * al[..., 0]
        seg[..., 2] = seg[..., 2] * (1 - al[..., 0]) + tarr[..., 2] * al[..., 0]

        # HEAVIER rhythmic shake: peak ~130px, faster sine, more noise
        A = int(8 + sub_s[i] * 120)
        if A > 0:
            tsi = i / FPS
            dx = A * (0.5 * np.sin(tsi * 2 * np.pi * 3.6) + 0.5 * rng.uniform(-1, 1))
            dy = A * (0.5 * np.sin(tsi * 2 * np.pi * 4.2 + 1.7) + 0.5 * rng.uniform(-1, 1))
            canvas = np.pad(frame, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="reflect")
            frame = canvas[PAD + int(dy):PAD + int(dy) + H, PAD + int(dx):PAD + int(dx) + W]

        rawf.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
        if i % 500 == 0:
            _drop_cache()
    rawf.close()
    _drop_cache()
    # transcode raw file -> part mp4 (file input is reliable)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", raw_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", part_path,
    ], check=True)
    _drop_cache()
    os.remove(raw_path)
    print(f"part done {start}-{end} -> {part_path}", flush=True)

if __name__ == "__main__":
    part, s, e, sd = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    render_segment(part, s, e, sd)
