# 使用示例

全部为实测通过的完整提示词，可直接复制改参数。

## L1 极简

试构图，20 步。

```
masterpiece, best quality, anime style, miyo (blue archive), blue archive, @ciloranko, 1girl, sitting on windowsill, soft light
```

## L2 混合

出成品默认档。`seed=3557030566`，1888×1232 横。

```
masterpiece, best quality, anime style, cel shading, clean lineart, miyo (blue archive), blue archive, @ciloranko, 一位灰银色长卷发的少女，黄绿色眼睛，头顶悬浮着绿色花纹光环。她的长发在两侧编成细细的辫子，辫子上各系着一个洁白的大蝴蝶结。她坐在一架花园秋千上，双手握着缠满小花与绿叶的秋千绳，身体微微前倾。她身穿白色为主、配浅蓝与淡紫的洛丽塔洋装，多层裙摆镶着白色蕾丝，胸前一排金色小纽扣，腿上穿着白色过膝袜。她微微低着头看向镜头，脸上带着温柔腼腆的笑。背景是盛开的花园，右侧白色圆桌上摆着三层点心架与一杯红茶，柔和的日光从上方洒下。横构图。
```

## L3 全描述

复杂场景、多道具。`seed=3815440708`，1296×1792 竖。

```
masterpiece, best quality, anime style, cel shading, clean lineart, miyo (blue archive), blue archive, @ciloranko, 一位灰银色长卷发的少女，黄绿色眼睛，头顶悬浮着绿色花纹光环，头顶偏左系着一个白色大蝴蝶结。她身穿深墨绿色连衣裙，泡泡袖，裙摆是多层荷叶边并镶着白色蕾丝，内搭白色蕾丝衬衫，袖口是荷叶边宽袖，领口系着一条绿色领结。她侧坐在一把绿色金属框架的椅子上，双腿自然垂下，双手交叠放在膝前。她的双手五指分明、关节自然。背景是一个玻璃温室，大量金属框架的玻璃窗，空中悬挂着几个装满多肉植物的透明玻璃球，右侧圆桌上放着玻璃烧瓶、三脚架与一本摊开的书，整体是清新的绿色调与明亮的自然光，略带俯视视角，竖构图。
```

## 变量替换

同一套构图只换 `character_tag`，够做系列图。

```
# {{character_tag}} = miyo (blue archive)  → 灰银长卷发、黄绿眼、绿花纹光环
# {{character_tag}} = plana (blue archive) → 白发粉内层、遮一只眼、黑瞳、红色光环
masterpiece, best quality, anime style, cel shading, {{character_tag}}, blue archive, @ciloranko, 人物站在半开的房门口，身体前倾，从门缝望向镜头，嘴里含着粉色小圆环，脸颊泛红微微仰头。身穿白色蕾丝吊带裙，外搭浅蓝色宽松外套滑落手臂。右侧是深色门板与银色门链，左侧是明亮走廊。柔和的午后光线从左侧照入。竖构图。
```

两版构图、服装、光线、表情完全一致，可直接当同一企划的成对稿件。

## 双人构图

两个角色必须分别写明左右位置与各自特征，负面压对方的发色瞳色。`seed=1875618438`，1264×1808。

```
masterpiece, best quality, anime style, cel shading, clean lineart, miyo (blue archive), mari (blue archive), blue archive, @ciloranko, 两位少女的半身合影，镜头取景从头顶上方一直到腰腿处，完整看到肩膀、手臂与上身，头部大小与肩宽比例协调自然，头身比例正常。画面左侧后方是一位灰银色长卷发的少女，黄绿色眼睛，头顶悬浮着绿色花纹光环，编发上系着白色蝴蝶结，穿着红色无袖连衣裙，一只手举起来开心地打招呼，眼睛发亮张嘴笑。画面右侧前景是另一位橙色长发的少女，蓝色眼睛，头顶悬浮着黄色光环，穿着红色圣诞装，领口与袖口镶白色绒毛，头戴红色圣诞帽，嘴里叼着一根红白条纹的拐杖糖，睁大眼睛露出惊喜的表情。背景是装饰着彩球和星星挂饰的圣诞树，温暖的室内灯光，节日气氛。
```
