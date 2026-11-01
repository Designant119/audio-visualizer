# DESTRUCTION 3,2,1 — 音频可视化渲染源码

歌曲：DESTRUCTION 3,2,1（Phigros 第八章原创曲，Normal1zer vs. Broken Nerdz，Speedcore）
规格：158.5s / 1080p(1920x1080) / 24fps / 3804 帧

## 工作流
1. `python3 analyze.py` → 分析 assets/song.mp3，产出 assets/features.npz（52 频段 bands、loud、sub、onset，3804 帧）
2. `python3 render_worker_v14.py <part.mp4> <start_frame> <end_frame> <seed>` → 分段渲染
   （4 段：0-951 / 951-1902 / 1902-2853 / 2853-3804；0/1 可并行，2/3 建议串行避免 4GB 内存压力）
3. 拼接 + 合成音频：
   `ffmpeg -f concat -safe 0 -i list.txt -c copy video_only.mp4`
   `ffmpeg -i video_only.mp4 -i assets/song.mp3 -c:v copy -c:a aac -b:a 192k -shortest final.mp4`
4. 压缩上传版：`ffmpeg -i final.mp4 -c:v libx264 -preset fast -crf 24 -maxrate 10M -bufsize 20M -pix_fmt yuv420p -c:a copy upload.mp4`

## 版本演化
- v3：基础版 + flash 亮度脉冲 + 70px 峰值抖动 + 故障条/像素化/RGB 错位
- v4：封面持续旋转（用户"挺不错，旋转敏感些"）
- v5：整幅旋转 → 被否（黑边丑）
- v6/v7：背景旋转（overscan 仿射零黑边）→ 被否（背景不该持续移动）
- v8：背景震颤 spring 版
- v9：背景震颤 ±30° 上限
- v10：三层双向震颤（谐振器 QQ 弹 → 被否"太软"）
- v11：硬脉冲震颤（无谐振回弹，背景 ±30°、封面/歌名 ±15°）
- v12：新布局（封面左 650px、频谱右侧竖柱、歌名右上）+ 删除冲击波圆环 + 封面零黑框
- v13：修曲绘崩坏（统一采样路径）、频谱改竖柱、歌名贴回边界夹紧
- v14：修曲绘不完整（完整封面 + RGBA 透明角旋转，无黑框无裁剪）

## 关键参数（v14）
- 硬脉冲：decay=0.30, K=20.0，background ±30°，cover/title ±15°
- 布局：ANCHOR=650, CX=470, CY=540, TX=1420, TY_TOP=80, TITLE_FONT=85
- 频谱：BAR_LEFT=1000, BAR_RIGHT=1900, BAR_TOP_Y=250, BAR_BOTTOM_Y=1040（52 竖柱）
- 抖动：PAD=160（必须 ≥ 峰值 128）
- 零黑角：背景 OV=760 仿射；封面 RGBA 旋转 expand + 透明角混合

## 环境
Python3 + numpy + Pillow + ffmpeg（libx264）；4GB RAM 环境分段串行渲染最稳
