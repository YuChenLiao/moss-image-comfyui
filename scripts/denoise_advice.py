#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改动类型 → denoise 建议。把“这次该给多少”从回忆变成查表。

    python denoise_advice.py 改衣物
    python denoise_advice.py pose --steps 24 --cfg 1.5
    python denoise_advice.py 纠裁切 --dmd --steps 50

依据全部来自本机实测（SKILL.md 硬性原则 2、replication.md「i2i 里动作漂了先降 denoise」）：

    0.85 是硬下限，0.8 出噪点、0.45 是纯噪声；
    0.88–0.89 锁骨相（动作/构图要贴参考时）；
    0.90 是改衣物、裸露度、层级的安全档；
    0.91–0.92 只用来纠轮廓（体型、裁切、放大主体），大改衣物时会脱锁（头朝下、腿交叉）。
"""

import argparse
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TABLE = [
    # (匹配词, 归档, denoise 区间, 依据 / 副作用)
    (["seed", "换种子", "变体"], "仅换 seed", None,
     "参数不变时 seed 不参与 denoise 决策；注意 ComfyUI 有节点级缓存，同参同 seed 会直接复用产物"),
    (["衣物", "衣服", "换衣", "服装", "outfit", "clothing", "裸露", "内衣", "裤袜"], "改衣物/裸露度", (0.90, 0.90),
     "布料归属变化大，0.90 够改又不脱锁；同时要点名部件与层级"),
    (["姿势", "动作", "pose", "关节", "朝向"], "改动作/姿势", (0.88, 0.89),
     "动作来自参考图骨相，denoise 越低越贴；配合四维描述（朝向/重心/关节角度/手脚落点）"),
    (["体型", "胸部", "臀部", "proportion", "丰满"], "纠体型", (0.91, 0.92),
     "要靠重绘压掉参考图轮廓的体量；配否定句与 large breasts 等负面"),
    (["裁切", "裁手", "画幅", "构图", "占比", "crop"], "纠裁切/构图", (0.91, 0.92),
     "先把参考图垫成 4:5 再谈；高 denoise 让模型有空间重排画面"),
    (["光影", "光线", "lighting", "明暗"], "改光影", (0.90, 0.90),
     "光影主要靠描述与负面推，denoise 不必上 0.92；上了容易连同结构一起改掉"),
    (["细节", "手指", "细化", "detail"], "提细节", (0.88, 0.89),
     "细节靠低 denoise 保留参考信息，而不是靠重绘；也可以直接加步数到 24"),
    (["表情", "expression"], "改表情", (0.89, 0.90),
     "表情区域小，0.89 就够；同时写嘴形+眼型+脸红三件事"),
]

CFG_NOTE = "CFG < 2 时负面基本失效（DMD 档固定 1.5），要压东西只能写进正向的删除性描述"


def match(word):
    w = word.lower()
    for keys, name, rng, why in TABLE:
        if any(k.lower() in w for k in keys):
            return name, rng, why
    return None, None, None


def main():
    ap = argparse.ArgumentParser(description="改动类型 → denoise 建议")
    ap.add_argument("change", nargs="?", help="要改什么，如 衣物 / 姿势 / 体型 / 裁切")
    ap.add_argument("--steps", type=int, help="计划用的步数")
    ap.add_argument("--cfg", type=float, help="计划用的 CFG")
    ap.add_argument("--dmd", action="store_true", help="是否挂 DMD 加速 LoRA")
    ap.add_argument("--list", action="store_true", help="打印整张表")
    args = ap.parse_args()

    if args.list or not args.change:
        print("改动类型            denoise      依据")
        for keys, name, rng, why in TABLE:
            r = "—" if rng is None else (f"{rng[0]:.2f}" if rng[0] == rng[1] else f"{rng[0]:.2f}–{rng[1]:.2f}")
            print(f"{name:<18}{r:<12}{why}")
        if not args.change:
            return

    name, rng, why = match(args.change)
    if name is None:
        print(f"没匹配到「{args.change}」。可用类型见 --list", file=sys.stderr)
        sys.exit(2)

    print(f"改动类型  {name}")
    if rng is None:
        print("denoise   保持原值")
    elif rng[0] == rng[1]:
        print(f"denoise   {rng[0]:.2f}")
    else:
        print(f"denoise   {rng[0]:.2f}–{rng[1]:.2f}（先给低的，不行再往上加）")
    print(f"依据      {why}")

    notes = []
    if args.steps is not None:
        if args.dmd and args.steps > 24:
            notes.append(f"步数 {args.steps} 超过 DMD 的蒸馏目标：16–24 是上限，50 步会散结构")
        elif not args.dmd and args.steps >= 50:
            notes.append(f"步数 {args.steps}：这是非 DMD 档的定稿步数（约 210s@2.3MP）")
        elif args.steps <= 8:
            notes.append(f"步数 {args.steps}：只适合试构图，细节与光影都撑不住")
    if args.cfg is not None:
        if args.cfg < 2:
            notes.append(f"CFG {args.cfg}：{CFG_NOTE}")
        if args.dmd and abs(args.cfg - 1.5) > 0.001:
            notes.append(f"DMD 档实测 CFG 1.5 最稳（1.0 会出圆形破洞伪影），当前 {args.cfg}")
    notes.append("硬下限：任何情况下 denoise 不低于 0.85")
    for n in notes:
        print(f"注意      {n}")


if __name__ == "__main__":
    main()
