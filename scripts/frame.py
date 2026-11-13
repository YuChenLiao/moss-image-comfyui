#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算 MOSS 该用什么像素，或者看一组像素的几何属性。

    # 给 megapixels 与比例，算像素对
    python frame.py 2.3 --ratio 3:4

    # 给像素，看比例与对齐
    python frame.py --pixels 1344x1792

    # 读一张图的比例，算 mp 对应的像素（需要 Pillow）
    python frame.py 2.3 --from-image ref.png

    # 按人物占比与脸部占身高的比例，算脸有多少像素
    python frame.py --pixels 1344x1792 --face-frame 0.7 0.22

只做几何计算：像素对、实际面积、宽高比、16 对齐、脸部像素。
**不评价大小。** 能跑多大取决于显存、权重精度、注意力实现、VAE 解码峰值、
驱动与并发——这些每台机器不一样，写死区间只会误导。想定自己的基线，
就用同一张提示词在小图上跑一遍、逐步加面积、记下第一次失败的尺寸。

画质那边有条与机型无关的算法：人物脸在画面上占据的像素太少就会糊。
`--face-frame` 用它来判断，而不是拿总面积当代理指标。
"""

import argparse
import json
import math
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ALIGN = 16


def fail(msg):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(2)


def align_up(v, step=ALIGN):
    return int(math.ceil(v / step) * step)


def parse_ratio(text):
    if ":" not in text:
        fail(f"比例要写成 3:4 这种形式，收到 {text!r}")
    a, b = text.split(":", 1)
    try:
        w, h = float(a), float(b)
    except ValueError:
        fail(f"比例不是数字：{text!r}")
    if w <= 0 or h <= 0:
        fail(f"比例必须为正：{text!r}")
    return w / h


def parse_pixels(text):
    if "x" not in text.lower():
        fail(f"像素要写成 1344x1792，收到 {text!r}")
    a, b = text.lower().split("x", 1)
    try:
        return int(a), int(b)
    except ValueError:
        fail(f"像素不是整数：{text!r}")


def from_mp(mp, ratio, mode="ceil"):
    """按面积与比例反解像素对。"""
    h = math.sqrt(mp * 1e6 / ratio)
    w = h * ratio
    if mode == "round":
        f = lambda v: int(round(v / ALIGN) * ALIGN)
    else:
        f = align_up
    return f(w), f(h)


def face_pixels(w, h, subject_ratio, face_of_subject):
    """主角占画面高度比例 × 脸占主角身高比例 → 脸的像素边长。

    face_of_subject 的常见量级：全身像 0.18–0.25、半身 0.3–0.4、特写 0.6+。
    """
    if not (0 < subject_ratio <= 1) or not (0 < face_of_subject <= 1):
        fail("--face-frame 的两个比例都要在 (0, 1] 之间")
    face_h = h * subject_ratio * face_of_subject
    face_w = face_h * 0.75        # 动漫脸宽高比约 3:4
    return face_w, face_h


def main():
    ap = argparse.ArgumentParser(description="算 MOSS 像素对的几何属性")
    ap.add_argument("megapixels", nargs="?", type=float, help="目标面积，单位 MP")
    ap.add_argument("--ratio", help="宽:高，如 3:4 / 9:16 / 3:2")
    ap.add_argument("--pixels", help="直接给像素，如 1344x1792")
    ap.add_argument("--from-image", help="读这张图的宽高比（需要 Pillow）")
    ap.add_argument("--align", choices=["ceil", "round"], default="ceil",
                    help="对齐方式，默认 ceil（ComfyUI 实际行为）")
    ap.add_argument("--face-frame", nargs=2, type=float, metavar=("SUBJECT", "FACE"),
                    help="主体占画面高度比例 与 脸占主体身高比例，用来算脸部像素")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    ratio_hint = None
    if args.pixels:
        w, h = parse_pixels(args.pixels)
        rows = []
    else:
        if args.megapixels is None:
            fail("要么给 megapixels，要么给 --pixels")
        if args.from_image:
            try:
                from PIL import Image
            except ImportError:
                fail("--from-image 需要 Pillow")
            with Image.open(args.from_image) as im:
                iw, ih = im.size
            ratio_hint = iw / ih
            rows = [("输入", f"{iw}×{ih} → 比例 {ratio_hint:.4f}")]
        elif args.ratio:
            ratio_hint = parse_ratio(args.ratio)
            rows = [("输入", f"设定比例 {args.ratio}")]
        else:
            fail("给 --ratio 或 --from-image 之一")
        w, h = from_mp(args.megapixels, ratio_hint, args.align)

    mp = w * h / 1e6
    ratio = w / h
    rows += [
        ("像素对", f"{w}×{h}"),
        ("实际面积", f"{mp:.2f}MP"),
        ("宽高比", f"{ratio:.4f}（约 1:{1/ratio:.2f}）" if ratio < 1 else f"{ratio:.4f}（约 {ratio:.2f}:1）"),
        ("16 对齐", "✓" if (w % ALIGN == 0 and h % ALIGN == 0) else "✗ 需要向上对齐"),
    ]
    if ratio_hint:
        rows.append(("与目标比例偏差", f"{(ratio / ratio_hint - 1) * 100:+.2f}%"))
    if args.megapixels and not args.pixels:
        rows.append(("相对设定面积溢出", f"{(mp / args.megapixels - 1) * 100:+.2f}%"))

    face_h = None
    if args.face_frame:
        face_w, face_h = face_pixels(w, h, *args.face_frame)
        rows.append(("脸部像素", f"约 {int(face_w)}×{int(face_h)}（脸高 200px 以上五官才稳）"))

    if args.json:
        out = {"width": w, "height": h, "megapixels": round(mp, 4), "ratio": round(ratio, 4),
               "aligned16": w % ALIGN == 0 and h % ALIGN == 0}
        if face_h:
            out["face_pixels_height"] = round(face_h, 1)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        width = max(len(k) for k, _ in rows)
        for k, v in rows:
            print(f"{k.ljust(width)}  {v}")
        if face_h is not None and face_h < 200:
            print(f"提示：脸高只有 {int(face_h)}px（判据 200px），五官会被采样平均掉——"
                  "加大主体占比或换更近的景别，而不是单纯堆总像素")

    sys.exit(0)


if __name__ == "__main__":
    main()
