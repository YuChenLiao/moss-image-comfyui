#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提示词体检：把踩过的坑变成可执行的检查。

    # 直接给文本
    python prompt_lint.py -p "正向……" -n "lowres, bad hands" -c "miyo (blue archive)"

    # 从产物 sidecar 读（comfyui 输出的 *.png.json 里就存着 vars）
    python prompt_lint.py --from-sidecar ../../comfyui-output/xxx.png.json

规则编号对应 reference/composition.md 与 replication.md 的修正对照表：

    13 角色 tag 与外貌词冲突      有角色 tag 就别再写发色瞳色发型
    14 部件定色缺失              服装部件前没有颜色词
    15 层级描述缺失              内裤/丝袜、手套/指甲没说清谁在里面
    16 正负互斥                  负面词出现在正向里
    17 防护覆盖不足              遮胸/赤脚/裸下身场景缺必备负面
    18 构图三件套缺失            占比 / 边距 / 无裁切 三项
    19 光影四层缺失              固有 / 光线 / 曝光 / 后期
    20 体型否定句缺失            写了胸部臀部却没有"小巧/纤细/不要"
    21 长度分布                  字符、中文句、英文 tag、负面词数
    22 token 粗估

有 ERROR 时退出码为 1，可以直接接在生成流程前面。
"""

import argparse
import json
import re
import sys

# Windows 控制台默认 GBK，中文与符号会乱码或抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------- 词表 ----------

HAIR_COLOR = [
    "黑发", "白发", "银发", "银白", "灰发", "金发", "粉发", "蓝发", "浅蓝发",
    "红发", "绿发", "紫发", "棕发", "栗色发", "橙发", "青发", "亚麻色发",
    "浅蓝长发", "浅蓝色长发", "银白色长发", "金色长发", "黑色长发", "粉色长发",
]
EYE_COLOR = ["红瞳", "蓝瞳", "金瞳", "绿瞳", "紫瞳", "橙瞳", "琥珀色眼", "灰瞳", "异色瞳"]
HAIR_STYLE = [
    "长发", "短发", "双马尾", "单马尾", "马尾", "麻花辫", "侧编发", "直发", "卷发",
    "齐刘海", "呆毛", "齐肩发",
]

PARTS = [
    "连衣裙", "百褶裙", "短裙", "长裙", "裙子", "衬衫", "外套", "上衣",
    "胸衣", "抹胸", "内裤", "丝袜", "连裤袜", "裤袜", "过膝袜", "短袜", "袜子",
    "靴子", "短靴", "鞋", "手套", "围裙", "护士帽", "颈环", "吊袜带", "蝴蝶结",
]
COLORS = [
    "黑色", "白色", "红色", "粉色", "金色", "银色", "蓝色", "紫色", "绿色", "灰色",
    "棕色", "米色", "象牙", "深红", "深蓝", "浅蓝", "酒红", "墨绿", "藏青", "橘色",
    "黑", "白", "红", "粉", "金", "银", "蓝", "紫", "绿", "灰", "棕",
]

# 场景关键词 → 必备负面词（任一命中即要求）
GUARDS = [
    (["遮住", "遮挡", "手掌与手指", "手掌贴在"], ["nipples", "areola"]),
    (["不穿鞋", "赤脚", "赤裸", "脚趾清楚"], ["shoes", "boots"]),
    (["内裤完全露", "内裤露出来", "裙下", "露出内裤"], ["nude", "bottomless"]),
    (["兽耳", "猫耳", "兔耳", "狼耳"], ["animal ears"]),
]

EN_STOP = {"the", "and", "with", "her", "his", "a", "an", "of", "on", "in", "to"}


def load_text(args):
    if args.from_sidecar:
        with open(args.from_sidecar, encoding="utf-8") as f:
            data = json.load(f)
        vars_ = data.get("vars") or data.get("variables") or {}
        if not vars_:
            # 有的 sidecar 直接把参数平铺
            vars_ = data
        p = vars_.get("prompt") or vars_.get("positive") or ""
        n = vars_.get("negative_prompt") or vars_.get("negative") or ""
        c = args.character or vars_.get("character") or ""
        return p, n, c
    return args.prompt or "", args.negative or "", args.character or ""


def en_hit(word, text):
    """英文词按边界匹配，避免 hand 命中 hands。"""
    return re.search(r"(?<![a-z])" + re.escape(word.lower()) + r"(?![a-z])", text.lower()) is not None


def suspect_character_tags(prompt):
    """找出疑似 Danbooru 角色 tag：带括号或作品的英文短语。"""
    out = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9_\- ]*\([A-Za-z0-9_\- ]+\)", prompt):
        out.append(m.group(0).strip())
    return out


def lint(prompt, negative, character):
    errs, warns, infos = [], [], []

    chars = [c for c in ([character] if character else []) + suspect_character_tags(prompt) if c]

    # 13 角色 tag 与外貌词冲突
    if chars:
        hits = [w for w in HAIR_COLOR + EYE_COLOR + HAIR_STYLE if w in prompt]
        if hits:
            errs.append(("13", f"已有角色 tag（{', '.join(chars[:3])}），中文段又写了外貌词：{', '.join(hits)}。"
                               "这会顶掉 tag 的设定——测过写“浅蓝色长发”直接让灰发角色变浅蓝"))

    # 14 部件定色
    def colored_near(m):
        pre = prompt[max(0, m.start() - 8):m.start()]
        if any(k in pre for k in ("没有", "不穿", "无", "不用")):  # 否定语境，不是穿着物
            return True
        return any(c in pre for c in COLORS)

    missing_color = []
    for part in PARTS:
        occ = list(re.finditer(re.escape(part), prompt))
        if not occ:
            continue
        if not any(colored_near(m) for m in occ):
            missing_color.append(part)
    if missing_color:
        warns.append(("14", f"这些部件前 8 字内没有颜色词：{', '.join(missing_color)}。"
                            "颜色写在部件名前面，别指望模型自己补黑/白"))

    # 15 层级
    has_panty = "内裤" in prompt
    has_tights = any(k in prompt for k in ("丝袜", "连裤袜", "裤袜", "过膝袜"))
    if has_panty and has_tights and not any(k in prompt for k in ("里面", "外面", "包住", "覆盖", "穿在", "盖住")):
        warns.append(("15", "同时写了内裤与丝袜，但没说层级。补“内裤穿在丝袜里面/外面、覆盖胯部”，"
                            "否则会内裤外穿"))
    if "手套" in prompt and "指甲" in prompt and not any(k in prompt for k in ("没有指甲", "看不到指甲", "包住")):
        warns.append(("15", "同时写了手套与指甲，但没排除“手套上长指甲”。补“手套包住五根手指、表面没有指甲”"))

    # 16 正负互斥
    neg_words = [w.strip() for w in re.split(r"[,，]", negative) if w.strip()]
    conflicts = []
    for w in neg_words:
        core = re.sub(r"[【】()（）:：\d.]+", " ", w).strip().lower()
        if not core or len(core) < 4 or core in EN_STOP:
            continue
        # 整短语匹配：blue hair 不该命中 blue archive
        parts = [re.escape(x) for x in core.split() if x]
        if not parts:
            continue
        pattern = r"(?<![a-z])" + r"\s+".join(parts) + r"(?![a-z])"
        if re.search(pattern, prompt.lower()):
            conflicts.append(core)
    if conflicts:
        errs.append(("16", f"负面里这些词在正向也出现了：{', '.join(sorted(set(conflicts))[:6])}。"
                           "典型是正面要保留衬衫、负面却压着 shirt"))

    # 17 防护覆盖
    for triggers, needed in GUARDS:
        if any(t in prompt for t in triggers):
            miss = [w for w in needed if not en_hit(w, negative)]
            if miss:
                warns.append(("17", f"场景含「{triggers[0]}」类描述，但负面缺 {', '.join(miss)}"))

    # 17b 裙摆上滑却没写内裤——实测这是走光的直接原因
    if "裙摆" in prompt and any(k in prompt for k in ("腰上滑", "滑到腰", "翻到腰", "卷到腰")):
        if "内裤" not in prompt:
            warns.append(("17", "裙摆滑到腰上但没写内裤，一定会走光。补内裤并写清覆盖范围与层级"))

    # 18 构图三件套
    trio = {
        "主体占比": any(k in prompt for k in ("占画面", "占约", "占比")),
        "边距/留白": any(k in prompt for k in ("边距", "留白")),
        "无裁切": any(k in prompt for k in ("无裁切", "不被裁切", "完整入画", "不被画框裁切")),
    }
    lacking = [k for k, v in trio.items() if not v]
    if lacking:
        infos.append(("18", f"构图三件套缺：{', '.join(lacking)}（占比 / 边距 / 无裁切）。"
                            "补上能显著降低手被裁的概率"))

    # 19 光四层
    layers = {
        "固有属性": any(k in prompt for k in ("肤色", "布料", "棉", "蕾丝", "纱", "哑光", "材质")),
        "光线层": any(k in prompt for k in ("光从", "主光", "侧光", "顶光", "逆光", "轮廓光", "柔光", "斜射")),
        "曝光层": any(k in prompt for k in ("过曝", "溢出", "曝光", "明暗", "亮部", "暗部", "受光")),
        "后期层": any(k in prompt for k in ("柔焦", "颗粒", "锐化", "色偏", "美颜", "微对比", "高光")),
    }
    miss_layer = [k for k, v in layers.items() if not v]
    if miss_layer:
        infos.append(("19", f"光影四层里缺：{', '.join(miss_layer)}（不强制，但缺两层以上通常写成“氛围感很强”这种空话）"))

    # 20 体型否定句
    if any(k in prompt for k in ("胸部", "臀部", "身材", "体型")):
        if not any(k in prompt for k in ("小巧", "纤细", "平坦", "不要", "没有夸张", "与角色本身")):
            warns.append(("20", "提到体型却没有否定句。写“身材纤细、胸部小巧、不要夸张的胸部与臀部”，"
                                "形容词（丰满、曲线）会被正向强化"))

    # 21 长度
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", prompt))
    cn_sent = len([s for s in re.split(r"[。；\n]", prompt) if s.strip()])
    en_tags = len([t for t in re.split(r"[,，]", prompt) if re.search(r"[A-Za-z]", t)])
    infos.append(("21", f"中文 {cn_chars} 字 / 中文句 {cn_sent} / 英文 tag {en_tags} / 负面词 {len(neg_words)}；"
                        f"总字符 {len(prompt)}"))

    # 22 token 粗估
    en_words = len(re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", prompt))
    est = int(cn_chars * 0.7 + en_words * 1.3)
    if est > 500:
        warns.append(("22", f"token 粗估 {est}，偏长（实测 400–500 仍能正常出图，再往上收益递减）。先删重复措辞再谈加词"))
    else:
        infos.append(("22", f"token 粗估 {est}"))

    return errs, warns, infos


def main():
    ap = argparse.ArgumentParser(description="MOSS 提示词体检")
    ap.add_argument("-p", "--prompt", help="正向提示词")
    ap.add_argument("-n", "--negative", default="", help="负向提示词")
    ap.add_argument("-c", "--character", help="角色 tag，如 \"miyo (blue archive)\"")
    ap.add_argument("--from-sidecar", help="从产物 sidecar 读 vars")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    prompt, negative, character = load_text(args)
    if not prompt.strip():
        print("错误：没有正向提示词（给 -p 或 --from-sidecar）", file=sys.stderr)
        sys.exit(2)

    errs, warns, infos = lint(prompt, negative, character)

    if args.json:
        print(json.dumps({
            "error": [{"rule": r, "msg": m} for r, m in errs],
            "warn": [{"rule": r, "msg": m} for r, m in warns],
            "info": [{"rule": r, "msg": m} for r, m in infos],
        }, ensure_ascii=False, indent=2))
    else:
        for label, items in (("ERROR", errs), ("WARN", warns), ("INFO", infos)):
            for rule, msg in items:
                print(f"[{label} R{rule}] {msg}")
        if not errs and not warns:
            print("通过：没有发现已知冲突")
        print(f"\n合计 {len(errs)} error / {len(warns)} warn / {len(infos)} info")

    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
