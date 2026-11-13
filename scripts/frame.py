#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算 MOSS 该用什么像素，或者校验一组像素是否合法。

三种用法：

    # 给 megapixels 与比例，算像素对
    python frame.py 2.3 --ratio 4:5

    # 给像素，校验上限/下限/16 对齐
    python frame.py --pixels 1344x1792

    # 读一张图的比例，算 mp 对应的像素（需要 Pillow）
    python frame.py 2.3 --from-image ref.png

硬约束（来自 SKILL.md 与 reference/workflows.md 的实测）：
    2.3MP 是显存上限，4MP 必崩；低于 1.5MP 五官必糊；
    latent 是 16 倍下采样，宽高都要对齐 16。

对齐方式默认 ceil（向上取整），这也是 ComfyUI 的
ImageScaleToTotalPixels 的实际行为——所以算出来的 MP 会比设定值高几个百分点，
不是 bug，是那 5% 溢出的来源。
"""

import argparse
import json
import math
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MP_MAX = 2.3
MP_MIN = 1.5
ALIGN = 16


def fail(msg):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def align_up(v, step=ALIGN):
    return int(math.ceil(v / step) * step)


def parse_ratio(text):
    if ":" not in text:
        fail(f"比例要写成 4:5 这种形式，收到 {text!r}")
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


def verdict(mp, target=None):
    """设定值超限才算违规；对齐带来的几个百分点溢出是必然的，只做提示。"""
    base = target if target else mp
    out = []
    hard = []
    if base > MP_MAX:
        hard.append(f"设定 {base:.2f}MP 超过显存上限 {MP_MAX}MP")
    if mp > 3.0:
        hard.append(f"实际 {mp:.2f}MP 已进入崩进程区间（4MP 必崩）")
    elif mp > 2.45:
        out.append(f"实际 {mp:.2f}MP 比对上限 2.3MP 高出较多，注意显存")
    if mp < MP_MIN:
        hard.append(f"实际 {mp:.2f}MP 低于 {MP_MIN}MP：人物脸只有几十像素，五官会被平均掉")
    return hard + out, bool(hard)


def report(mp_target, w, h, ratio_hint=None):
    mp = w * h / 1e6
    ratio = w / h
    rows = [
        ("像素对", f"{w}×{h}"),
        ("实际 MP", f"{mp:.2f}"),
        ("宽高比", f"{ratio:.4f}（约 1:{1/ratio:.2f}）" if ratio < 1 else f"{ratio:.4f}（约 {ratio:.2f}:1）"),
        ("16 对齐", "✓" if (w % ALIGN == 0 and h % ALIGN == 0) else "✗"),
    ]
    if ratio_hint:
        drift = (ratio / ratio_hint - 1) * 100
        rows.append(("与目标比例偏差", f"{drift:+.2f}%"))
    if mp_target:
        over = (mp / mp_target - 1) * 100
        rows.append(("相对设定 MP 溢出", f"{over:+.2f}%"))
    return rows, mp


def main():
    ap = argparse.ArgumentParser(description="算 MOSS 像素对，或校验一组像素")
    ap.add_argument("megapixels", nargs="?", type=float, help="目标面积，单位 MP（如 2.3）")
    ap.add_argument("--ratio", help="宽:高，如 4:5 / 9:16 / 3:2")
    ap.add_argument("--pixels", help="直接给像素，如 1344x1792")
    ap.add_argument("--from-image", help="读这张图的宽高比（需要 Pillow）")
    ap.add_argument("--align", choices=["ceil", "round"], default="ceil",
                    help="对齐方式，默认 ceil（ComfyUI 实际行为）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    ratio_hint = None
    if args.pixels:
        w, h = parse_pixels(args.pixels)
        rows, mp = report(None, w, h)
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
            rows_ratio = f"{iw}×{ih} → 比例 {ratio_hint:.4f}"
        elif args.ratio:
            ratio_hint = parse_ratio(args.ratio)
            rows_ratio = f"设定比例 {args.ratio}"
        else:
            fail("给 --ratio 或 --from-image 之一")
        w, h = from_mp(args.megapixels, ratio_hint, args.align)
        rows, mp = report(args.megapixels, w, h, ratio_hint)
        rows.insert(0, ("输入", rows_ratio))

    issues, bad_issue = verdict(mp, args.megapixels if not args.pixels else None)

    if args.json:
        print(json.dumps({
            "width": w, "height": h, "megapixels": round(mp, 4),
            "ratio": round(w / h, 4),
            "aligned16": w % ALIGN == 0 and h % ALIGN == 0,
            "issues": issues,
            "exit_ok": not bad_issue,
        }, ensure_ascii=False, indent=2))
    else:
        width = max(len(k) for k, _ in rows)
        for k, v in rows:
            print(f"{k.ljust(width)}  {v}")
        for i in issues:
            print(f"注意：{i}")

    # 有硬性问题或没对齐时返回非零，方便脚本串联
    bad = bad_issue or w % ALIGN != 0 or h % ALIGN != 0
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
