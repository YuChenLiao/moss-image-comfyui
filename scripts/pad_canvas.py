#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把参考图垫进更宽的画布，救回被裁掉的手脚。

    # 竖长参考图垫成 4:5，补边取边缘延展
    python pad_canvas.py ref.png --ratio 4:5 --out ref_wide.png

    # 直接指定目标宽度，补纯色
    python pad_canvas.py ref.png --width 1120 --fill '#141416' --out ref_wide.png

为什么需要它：i2i 的输出画幅跟随参考图（ImageScaleToTotalPixels 按原图比例缩放）。
9:16 的长条参考图会把人物撑满画面，手腕与脚踝顶到画框，被裁的那部分必然画崩。
把参考图垫进 4:5 / 3:4 再喂 `image`，配合提示词里的留白句，手就画得完整了。

补边方式：
    auto    取四周条带的中位色铺纯色（默认；黑床单、白背景这类均匀底最干净）
    #RRGGBB 指定颜色
    edge    拉伸最外侧像素铺满补边区，只适合边缘内容本身均匀的图；
            边缘有黑带/白条时会被拉成竖条纹，不如 auto

不裁剪原图、不缩放原图——只加画布。要改尺寸请用 frame.py 先算好再决定。
"""

import argparse
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageFilter
except ImportError:
    print("错误：需要 Pillow（pip install pillow）", file=sys.stderr)
    sys.exit(1)


def fail(msg):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def median_edge_color(im, band=6):
    """取四周条带的中位色，均匀背景近似得很准。"""
    w, h = im.size
    px = im.load()
    samples = []
    for x in range(0, w, max(1, w // 64)):
        for y in (0, 1, 2, h - 3, h - 2, h - 1):
            if 0 <= y < h:
                samples.append(px[x, y])
    for y in range(0, h, max(1, h // 64)):
        for x in (0, 1, 2, w - 3, w - 2, w - 1):
            if 0 <= x < w:
                samples.append(px[x, y])
    if not samples:
        return (255, 255, 255)
    channels = list(zip(*samples[: band * 4000]))
    return tuple(int(sorted(c)[len(c) // 2]) for c in channels)


def parse_fill(value, im):
    if value == "edge":
        return "edge", None
    if value == "auto":
        return "color", median_edge_color(im)
    v = value.lstrip("#")
    if len(v) == 6:
        try:
            return "color", tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    fail(f"--fill 只接受 edge / auto / #RRGGBB，收到 {value!r}")


def build(im, target_w, target_h, mode, color, feather):
    canvas = Image.new("RGB", (target_w, target_h), color if mode == "color" else (255, 255, 255))
    ox = (target_w - im.width) // 2
    oy = (target_h - im.height) // 2

    if mode == "edge":
        # 用最外侧一列/一行像素拉伸铺满补边区域，再轻微模糊——纵向渐变最自然，
        # 比镜像平铺少很多接缝
        if ox > 0:
            left = im.crop((0, 0, 1, im.height)).resize((ox, im.height))
            canvas.paste(left, (0, oy))
            right = im.crop((im.width - 1, 0, im.width, im.height)).resize((target_w - ox - im.width, im.height))
            canvas.paste(right, (ox + im.width, oy))
        if oy > 0:
            top = im.crop((0, 0, im.width, 1)).resize((im.width, oy))
            canvas.paste(top, (ox, 0))
            bottom = im.crop((0, im.height - 1, im.width, im.height)).resize((im.width, target_h - oy - im.height))
            canvas.paste(bottom, (ox, oy + im.height))
        canvas = canvas.filter(ImageFilter.GaussianBlur(max(2, feather // 3)))

    # 原图带边缘羽化贴回去
    if feather > 0:
        from PIL import ImageDraw
        mask = Image.new("L", im.size, 255)
        d = ImageDraw.Draw(mask)
        step = feather
        for i in range(step):
            alpha = int(255 * (i + 1) / step)
            d.rectangle([i, i, im.width - 1 - i, im.height - 1 - i], outline=alpha)
        canvas.paste(im, (ox, oy), mask)
    else:
        canvas.paste(im, (ox, oy))
    return canvas, ox, oy


def main():
    ap = argparse.ArgumentParser(description="把参考图垫进更宽的画布")
    ap.add_argument("image", help="输入图路径")
    ap.add_argument("--ratio", help="目标宽:高，如 4:5 / 3:4 / 1:1")
    ap.add_argument("--width", type=int, help="直接指定目标宽度（与 --ratio 二选一）")
    ap.add_argument("--fill", default="auto",
                    help="auto（取边缘中位色铺满，默认）/ #RRGGBB（指定色）/ edge（拉伸边缘像素，背景杂乱时会出竖条）")
    ap.add_argument("--feather", type=int, default=16, help="边缘羽化像素，默认 16")
    ap.add_argument("--align", type=int, default=16, help="目标宽度对齐到该倍数，默认 16（喂给 MOSS 的 latent 要求）")
    ap.add_argument("--out", required=True, help="输出路径")
    args = ap.parse_args()

    im = Image.open(args.image).convert("RGB")
    if args.ratio and args.width:
        fail("--ratio 与 --width 只能给一个")

    if args.ratio:
        if ":" not in args.ratio:
            fail(f"比例要写成 4:5，收到 {args.ratio!r}")
        a, b = (float(x) for x in args.ratio.split(":", 1))
        if a <= 0 or b <= 0:
            fail("比例必须为正")
        ratio = a / b
        target_h = im.height
        target_w = int(round(target_h * ratio))
        if target_w < im.width:
            # 目标比例更窄：保持宽度、加高
            target_w = im.width
            target_h = int(round(target_w / ratio))
    elif args.width:
        if args.width < im.width:
            fail(f"目标宽度 {args.width} 小于原图 {im.width}，本工具只加画布不裁剪")
        target_w = args.width
        target_h = im.height
    else:
        fail("给 --ratio 或 --width")

    if args.align > 1 and target_w % args.align:
        target_w = int(-(-target_w // args.align) * args.align)

    mode, color = parse_fill(args.fill, im)
    canvas, ox, oy = build(im, target_w, target_h, mode, color, args.feather)
    canvas.save(args.out)

    pad_w = (target_w - im.width) // 2
    print(f"输入     {im.width}×{im.height}（{im.width/im.height:.4f}）")
    print(f"输出     {target_w}×{target_h}（{target_w/target_h:.4f}）→ {args.out}")
    print(f"补边     左右各 {pad_w}px，上下各 {oy}px，羽化 {args.feather}px，填充 {args.fill}")
    print(f"面积     {target_w*target_h/1e6:.2f}MP")
    if pad_w <= 0 and oy <= 0:
        print("注意：目标画幅与原图一致，没有实际补边")


if __name__ == "__main__":
    main()
