#!/usr/bin/env python3
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
# 用第 100 帧（开头无故障，画面干净）
data = np.load('assets/features.npz')
bands = data['bands'][100]
loud = float(data['loud'][100])

# 背景：cover 模糊
bg = Image.open('assets/cover_album_1024.jpg').resize((W, H)).filter(ImageFilter.GaussianBlur(40))
bg = bg.filter(ImageFilter.GaussianBlur(3))

# 画 104 根频谱条（简化）
d = ImageDraw.Draw(bg)
n = 104
bw = W / n
for i in range(n):
    v = float(np.clip((bands[i % len(bands)] - 0.55) * 2.4, 0, 1))
    h = v * (H - 30)
    d.rectangle([i*bw+3, H-h, (i+1)*bw-3, H], fill=(int(120+loud*80), 90, 180))

# 曲绘
cover = Image.open('assets/cover_album_1024.jpg').resize((750, 750)).convert('RGBA')
bg.paste(cover, (105, 265), cover)

def draw_title(base, font_path, size, stroke_w, label):
    img = base.copy()
    dr = ImageDraw.Draw(img)
    f = ImageFont.truetype(font_path, size)
    fa = ImageFont.truetype(font_path, 34)
    # 标题（v37 布局：TX=1420, TY_TOP=80, anchor=ma, stroke=4）
    dr.text((1420, 80), "DESTRUCTION 3,2,1", font=f, fill=(255,255,255),
            anchor="ma", stroke_width=stroke_w, stroke_fill=(0,0,0))
    dr.text((1160, 265), "Normal1zer vs. Broken Nerdz", font=fa, fill=(255,255,255,230))
    dr.text((40, 40), label, font=ImageFont.truetype(font_path, 28), fill=(255,255,0))
    return img

old = draw_title(bg, 'fonts/AnthropicSerif-900.ttf', 100, 4, "OLD: Light300 + 描边4")
new = draw_title(bg, 'fonts/anthropic_official/instances/AnthropicSerif_Roman_800.ttf', 100, 2, "NEW: wght=800 真粗")

# 上下拼
combo = Image.new('RGB', (W, H*2))
combo.paste(old, (0,0))
combo.paste(new, (0,H))
combo.save('font_compare.png')
print("saved font_compare.png")
