#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""算 MOSS 该用什么像素，或者校验一组像素。

三种用法：

    # 给 megapixels 与比例，算像素对
    python frame.py 2.3 --ratio 3:4

    # 给像素，看它落在什么区间
    python frame.py --pixels 1344x1792

    # 读一张图的比例，算 mp 对应的像素（需要 Pillow）
    python frame.py 2.3 --from-image ref.png

    # 附崩图排查清单
    python frame.py --pixels 2688x1536 --factors

态度：**面积不是硬上限。**
    latent 是 16 倍下采样，宽高必须对齐 16——这条是硬的；
    2.3MP 只是舒适区，2.4MP（1344×1792）在本机实测照样出图；
    面积变大只是把显存余量压薄，崩图另有诱因（权重精度、碎片、同进程切档、
    注意力实现、VAE 解码峰值、文本长度、驱动），所以这里只给观察，不判对错。
    低于 1.5MP 时五官会糊，那是画质约束，和崩不崩没关系。

退出码：只有输入非法（比例非正、像素不可解析）才非零，方便串联而不误杀大图。
"""

import argparse
import json
import math
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

COMFORT = 2.3      # 舒适区，不是上限
HEAVY = 4.0        # 到这一步显存余量已经很薄
MP_MIN = 1.5       # 低于此值五官会糊（画质约束）
ALIGN = 16

FACTORS = """崩图排查顺序（面积只是其中一项）
  1 阶段定位     日志掉在采样阶段 → 显存/注意力；掉在 VAEDecode → 解码峰值；跑完慢 → 碎片
  2 显存余量     /system_stats 的 vram_free，干净时约 19.4GB；只剩零点几 GB 就是碎片态，重启
  3 权重精度     bf16 约 18.6GB，int8_convrot 约 12GB；同一进程里来回换档必然变慢
  4 注意力与节点  sparse / blockcache 之类插件的实现与版本，换版本后先用小图验证
  5 文本长度     超长 prompt 抬高编码器显存与耗时，先砍重复措辞
  6 batch 与其他  同时跑图、开着大页面的浏览器都会抢显存
  7 VAE 与大图   大画幅的解码峰值常高于采样峰值，可用 tiled decode
  8 驱动与系统   ROCm 版本、32GB 内存下的 swap，都会表现为“随机崩”
结论：同样的 2688×1536 这次崩、下次不一定崩，别用一个像素数字背锅。"""


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


def verdict(mp):
    """只给观察，不判定对错。"""
    out = []
    if mp >= HEAVY:
        out.append(f"实际 {mp:.2f}MP：显存余量已经很薄。先看 vram_free 与权重精度，再决定要不要降")
    elif mp > COMFORT:
        out.append(f"实际 {mp:.2f}MP：略高于舒适区 {COMFORT}MP，本机能出图，留意碎片累积")
    if mp < MP_MIN:
        out.append(f"实际 {mp:.2f}MP 低于 {MP_MIN}MP：人物脸只有几十像素，五官会被平均掉"
                   "（画质问题，不是崩图问题）")
    return out


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
    ap = argparse.ArgumentParser(description="算 MOSS 像素对，或看一组像素落在什么区间")
    ap.add_argument("megapixels", nargs="?", type=float, help="目标面积，单位 MP（如 2.3）")
    ap.add_argument("--ratio", help="宽:高，如 3:4 / 9:16 / 3:2")
    ap.add_argument("--pixels", help="直接给像素，如 1344x1792")
    ap.add_argument("--from-image", help="读这张图的宽高比（需要 Pillow）")
    ap.add_argument("--align", choices=["ceil", "round"], default="ceil",
                    help="对齐方式，默认 ceil（ComfyUI 实际行为）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--factors", action="store_true", help="附崩图排查清单")
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
            source = f"{iw}×{ih} → 比例 {ratio_hint:.4f}"
        elif args.ratio:
            ratio_hint = parse_ratio(args.ratio)
            source = f"设定比例 {args.ratio}"
        else:
            fail("给 --ratio 或 --from-image 之一")
        w, h = from_mp(args.megapixels, ratio_hint, args.align)
        rows, mp = report(args.megapixels, w, h, ratio_hint)
        rows.insert(0, ("输入", source))

    issues = verdict(mp)

    if args.json:
        print(json.dumps({
            "width": w, "height": h, "megapixels": round(mp, 4),
            "ratio": round(w / h, 4),
            "aligned16": w % ALIGN == 0 and h % ALIGN == 0,
            "notes": issues,
        }, ensure_ascii=False, indent=2))
    else:
        width = max(len(k) for k, _ in rows)
        for k, v in rows:
            print(f"{k.ljust(width)}  {v}")
        for i in issues:
            print(f"提示：{i}")
        if args.factors:
            print()
            print(FACTORS)

    # 面积大不算失败，只有输入非法才非零
    sys.exit(0)


if __name__ == "__main__":
    main()
