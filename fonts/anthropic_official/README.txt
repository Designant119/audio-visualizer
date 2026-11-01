Anthropic 官网原版字体包（直接从 anthropic.com 抓取）
======================================================

抓取方式：
  从 https://www.anthropic.com/ 首页 HTML <link preload> + CSS @font-face
  直接下载官网实际加载的 woff2 文件，再用 fontTools 转成 TTF。

包含（每个家族 Roman 正体 + Italic 斜体）：
  AnthropicSerif_Roman_Web.ttf   衬线正体（视频标题在用）
  AnthropicSerif_Italic_Web.ttf  衬线斜体
  AnthropicSans_Roman_Web.ttf    无衬线正体（Claude 界面主要用）
  AnthropicSans_Italic_Web.ttf   无衬线斜体
  AnthropicMono_Roman_Web.ttf    等宽正体
  AnthropicMono_Italic_Web.ttf   等宽斜体

同时附原始 woff2 文件（网页直接可用）。

字符集：拉丁字母完整（A-Z a-z）+ 数字 + 常用符号，Serif 633 字符 / Sans 625 字符。
注意：这是官网 Web 子集，不含中文字形。

校验：与第三方仓库 devchauhann/fonts@1.1.0 的 AnthropicSerif woff2
MD5 完全一致（1ca11f68b43c5d09efbe5de98b02a085），证实转载版即官网原版。

版权：Anthropic 品牌字体，仅供个人学习/非商业视频二创参考，商用需官方授权。
