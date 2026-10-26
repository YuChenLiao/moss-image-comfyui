#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Layout 草稿编译成 MOSS 要的成稿。

草稿：左上角原点的像素框，xyxy，带 width/height。
成稿：画布中心为原点的整数框，yxyx，不带 width/height。

用法：
    python compile_layout.py draft.json --output prompt.txt
    python compile_layout.py draft.json          # 直接打印到终端

转换： [x0,y0,x1,y1] -> [y0-H/2, x0-W/2, y1-H/2, x1-W/2]
带小数边时先向外取整（left/top 向下，right/bottom 向上），再减中心。

校验失败直接退出且不写文件，不做静默裁剪——越界就是设计错了，要改草稿。
"""

import argparse
import json
import sys

ROOT_KEYS = {"summary", "items", "width", "height", "bbox_coord_space", "bbox_format"}
ITEM_KEYS = {"label", "caption", "bbox", "text", "tags", "palette"}
LABELS = {"character", "object", "text"}


def fail(msg):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        fail(f"找不到草稿文件：{path}")
    except json.JSONDecodeError as exc:
        fail(f"草稿不是合法 JSON：{exc}")


def check_canvas(draft):
    w, h = num(draft.get("width")), num(draft.get("height"))
    if w is None or h is None:
        fail("草稿必须有数字型的 width 与 height")
    if w <= 0 or h <= 0:
        fail(f"画布尺寸必须为正：{w}×{h}")
    if w % 16 or h % 16:
        near_w, near_h = round(w / 16) * 16 or 16, round(h / 16) * 16 or 16
        fail(f"画布尺寸必须是 16 的倍数，收到 {int(w)}×{int(h)}；附近可用：{near_w}×{near_h}")
    if draft.get("bbox_coord_space") != "abs":
        fail('草稿的 bbox_coord_space 必须是 "abs"')
    if draft.get("bbox_format") != "xyxy":
        fail('草稿的 bbox_format 必须是 "xyxy"')
    return w, h


def check_items(draft, w, h):
    items = draft.get("items")
    if not isinstance(items, list) or not items:
        fail("items 必须是非空数组")

    for index, item in enumerate(items):
        where = f"items[{index}]"
        if not isinstance(item, dict):
            fail(f"{where} 不是对象")
        unknown = set(item) - ITEM_KEYS
        if unknown:
            fail(f"{where} 含不支持的字段：{', '.join(sorted(unknown))}")

        label = item.get("label")
        if label not in LABELS:
            fail(f'{where}.label 只能是 character / object / text，收到 {label!r}')

        caption = item.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            fail(f"{where}.caption 必须是非空字符串")

        if label == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text:
                fail(f"{where} 是 text 项，必须给非空 text 字段（存真正印出来的字）")

        box = item.get("bbox")
        if not isinstance(box, list) or len(box) != 4:
            fail(f"{where}.bbox 必须是四个数")
        values = [num(v) for v in box]
        if any(v is None for v in values):
            fail(f"{where}.bbox 含非数字：{box}")
        x0, y0, x1, y1 = values
        if x1 <= x0 or y1 <= y0:
            fail(f"{where}.bbox 面积为 0 或反了：{box}")
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
            fail(f"{where}.bbox 越界（画布 {int(w)}×{int(h)}）：{box}")
    return items


def check_summary(draft):
    summary = draft.get("summary")
    if not isinstance(summary, dict):
        fail("summary 必须是对象")
    caption = summary.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        fail("summary.caption 必须是非空字符串")
    for key in ("meta", "palette"):
        value = summary.get(key)
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(v, str) for v in value)
        ):
            fail(f"summary.{key} 必须是字符串数组")
    canvas = summary.get("canvas")
    if canvas is not None and canvas not in ("single", "multi_panel", "collage"):
        fail("summary.canvas 只能是 single / multi_panel / collage")
    # 尺寸与坐标空间留在草稿里，成稿不带这两个字段
    return {k: v for k, v in summary.items() if k in ("caption", "meta", "palette", "canvas")}


def convert(box, w, h):
    import math

    x0, y0, x1, y1 = [num(v) for v in box]
    x0, y0 = math.floor(x0), math.floor(y0)
    x1, y1 = math.ceil(x1), math.ceil(y1)
    cx, cy = w / 2, h / 2
    return [int(round(y0 - cy)), int(round(x0 - cx)), int(round(y1 - cy)), int(round(x1 - cx))]


def main():
    parser = argparse.ArgumentParser(description="编译 MOSS Layout 草稿")
    parser.add_argument("draft", help="草稿 JSON 路径")
    parser.add_argument("--output", "-o", help="成稿写入的文件；不给则打印到终端")
    args = parser.parse_args()

    draft = load(args.draft)
    if not isinstance(draft, dict):
        fail("草稿根节点必须是对象")
    unknown = set(draft) - ROOT_KEYS
    if unknown:
        fail(f"草稿含不支持的根字段：{', '.join(sorted(unknown))}")

    w, h = check_canvas(draft)
    summary = check_summary(draft)
    items = check_items(draft, w, h)

    compiled = {
        "summary": summary,
        "items": [
            {
                **{k: v for k, v in item.items() if k not in ("bbox",)},
                "bbox": convert(item["bbox"], w, h),
            }
            for item in items
        ],
        "bbox_coord_space": "abs_centralized",
        "bbox_format": "yxyx",
    }

    line = json.dumps(compiled, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"已写入 {args.output}（画布 {int(w)}×{int(h)}，{len(items)} 个 item）")
        print(f"提示词之外需要声明的尺寸：{int(w)}×{int(h)}")
    else:
        print(line)


if __name__ == "__main__":
    main()
