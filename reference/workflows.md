# 工作流与运维

## 四种工作流

| 场景 | 链路要点 |
|---|---|
| 文生图 | `EmptyFlux2LatentImage` → KSampler(denoise 1.0) |
| 图生图 | `LoadImage` → `ImageScaleToTotalPixels(megapixels=2.3, resolution_steps=16)` → `VAEEncode` → KSampler(denoise 0.9) |
| 局部重绘 | 蒙版取红通道 → `GrowMask(expand=12)` → `SetLatentNoiseMask` → KSampler(denoise 1.0) → `ImageCompositeMasked` 按蒙版贴回原图 |
| 高分辨率 | 直接给 2MP 尺寸，不要低分放大（MOSS 的 i2i 会重绘，放大不增细节） |

**`ImageScaleToTotalPixels` 的 megapixels 决定输出画布**，默认 1.0 会把输出压到 1MP。参考图再大也没用，这一项不调高，出来就是 832×1264 这种尺寸。

局部重绘的合成步骤很关键：蒙版外像素可做到字节级不变（实测 99.49% 像素零变化），因为非编辑区是贴回原图而不是重新生成。

蒙版图白色 = 重绘区，尺寸可与原图不同（用 `GetImageSize` + `ImageScale` 动态对齐）。

## 性能

- 冷启动第一张含模型加载，比热缓存慢 1.5~3 倍。
- 连续出图 6~8 张后显存碎片累积，耗时会从 70s 涨到 700s；重启 ComfyUI 后显存从 12.4GB 回落到 4.4GB，速度恢复。
- 20GB 显存下 bf16 DiT + int8 文本编码器 = 19GB，每张图都要重新 staged 一遍，这是慢的主因，换量化权重能根治。
- 实测耗时参考：2.3MP / 60 步约 225~240s；1MP / 50 步约 70s（量化）；1MP / 20 步约 35s。

### 700s 的第二个诱因：同进程内切换权重（2026-10 实测补充）

上一版把"700s"只归因于连续出图的显存碎片，不完整。同一进程里**从 bf16 切到量化版后的第一张**同样会飙：

| 场景 | 参数 | 耗时 |
|---|---|---|
| bf16 首张（18.6GB 占用） | 2.4MP / 50 步 | 706s |
| 紧跟其后、同进程内的量化版 | 2.4MP / 50 步 | **826s** |
| 显存干净时的量化版 | 2.4MP / 50 步 | **205s** |

826s 比 bf16 还慢，原因不是量化无效，而是前一个任务卸载 18.6GB 后显存没有清干净，量化版的 12GB 权重还要重新 staged 一遍。判别方法：队列为空、但 `/system_stats` 里 `vram_free` 只剩零点几 GB，就是碎片态；真正干净时 20GB 卡应显示空闲约 19.4GB。

**结论：不要在同一进程里来回切 bf16 与量化权重。** 二选一用到底；要换档就重启 ComfyUI 再跑。205s 才是这台机器 2.4MP / 50 步的真值。

### 测速前必须换 seed（否则读数是假的）

ComfyUI 有**节点级执行缓存**：提示词、seed、输入图与全部参数一致时，它直接复用上次的结果，几秒就返回，产物连编号都沿用上次的。实测遇到过"5 秒完成"。

判断方法：产物字节数与上次完全一致、文件名编号相同，就是缓存命中。要测真速度，改 seed 或改任一参数让缓存失效。

### megapixels 会略超设定值

`ImageScaleToTotalPixels` 的 `megapixels` 是**目标面积**，宽高各自向上对齐到 16 的倍数之后会溢出。实测 1200×844 的参考图设 `megapixels=2.3`，输出 1856×1296 = **2.41MP**，比设定值高约 5%。按 2.3 设不会爆显存，但别以为拿到的就是 2.3MP。

## 8 步 DMD 加速

上游仓库 `lodestones/MOSS-Image-SFT-8-steps-dmd`（apache-2.0，从 MOSS-Image-SFT 的 50 步 CFG 3 蒸馏）。它把 8 次网络评估替代 50 步采样，理论上是"8 步、无 CFG"。

**装法**：下载 `lora.safetensors`（1.13GB，252 组 kohya 键）到 `models/loras/`，用 `LoraLoaderModelOnly` 接在 `UNETLoader` 之后。仓库里另有 `lora_latest.safetensors`，作者建议 0.7 强度。

```
UNETLoader → LoraLoaderModelOnly(1.0) → KSampler
```

**必须去掉 SLG**。`SkipLayerGuidanceDiTSimple` 每步要跑两次前向，8 步变 16 次，加速直接归零。

### 图生图也要接 LoRA

i2i 的加速链路把 LoRA 插在 VAEEncode 之后、KSampler 之前：

```
LoadImage → ImageScaleToTotalPixels(megapixels=2.3) → VAEEncode
  → LoraLoaderModelOnly(1.0) → KSampler(denoise 0.9, steps 12, cfg 1.5)
```

实测 1264×1904 约 58s。**同耗时下 i2i 的姿态比 t2i 更贴参考图**，因为 denoise 0.9 保留了参考图的构图轮廓，空间结构不会跑偏。但 denoise 意味着九成内容仍是重绘，精确的关节落点依旧不如 50 步。

| 配置 | 耗时 | 复杂姿态（一手撑地一手搭膝）的还原 |
|---|---|---|
| t2i 12 步 + LoRA | 58.8s | 右手抬到肩旁，退化 |
| i2i 12 步 + LoRA | 58.3s | 右手落在身侧裙边，接近 |
| t2i 50 步 | 190.6s | 右手正确搭在膝外侧 |

**复杂动作的推荐流程**：先用 i2i + 12 步快速确认构图与姿态方向（一分钟内），定稿再切 50 步 t2i 补精度。

### 实测参数（1264×1824，同一提示词与 seed）

| 配置 | 耗时 | 相对 50 步 | 画质 |
|---|---|---|---|
| 50 步 CFG 3.5（原版） | ~230s | 1× | 基准 |
| 8 步 CFG 1.0 | 30.2s | 7.6× | 连裤袜出现圆形破洞伪影，怀表退化成比手势 |
| 8 步 CFG 1.5 | 36.2s | 6.4× | 良，怀表正常、无破洞 |
| 8 步 CFG 2.0 | 36.3s | 6.4× | 良，手部略变形 |
| 12 步 CFG 1.5 | 50.1s | 4.6× | 最好，细节最干净 |
| 16 步 CFG 1.5 | 63.4s | 3.6× | 更细，收益递减 |

### 与上游说法相反的一条

README 写的是"8 步、no CFG"，实测 **CFG 1.0 会出伪影**——连裤袜长出一片圆形破洞、手里的怀表退化成手势。调到 1.5 立刻恢复正常。原因是这个蒸馏还不彻底，需要一点 CFG 把语义拉回来。CFG 低于 2 时负面提示词基本不起作用，负面里写的约束在这个档位要靠正向描述补。

**取舍**：8 步档的语义遵循度明显低于 50 步，细碎道具容易丢（实测两只手的手套被画成白色方块）。多道具、多角色的复杂场景建议 12 步起步；单角色、构图简单的图 8 步完全够用。

**推荐**：试构图 8 步 CFG 1.5（36 秒一版，迭代速度是原来的 6 倍）；定稿 12 步 CFG 1.5。

## 常见故障对照

| 症状 | 原因 |
|---|---|
| 输出纯彩色噪声 | 套了 `ModelSamplingSD3`；或 i2i 的 denoise < 0.85 |
| 五官糊、细节少 | 分辨率不足（<1.5MP）或人物占比太小 |
| 角色特征错（发色/瞳色不对） | 用了中文角色名或错误 tag；先查 Danbooru 官方标签 |
| 画面突然变水墨/厚涂 | 缺 `anime style, cel shading`；或换了 `@wlop` 这类半写实画师 |
| 生成到一半 ComfyUI 进程消失 | 分辨率过大导致显存溢出（4MP 必崩） |
| 提示词元素缺失 | 顺序错乱（中文描述混进了 character/series 段之间）；按官方顺序重排 |

## 配套节点

`MOSSPromptComposer`（MOSS 提示词编排器，`custom_nodes/moss_prompt_composer/`）：角色 3098 项（2138 中文名 + 960 Danbooru 英文补充）、画师 5000 项，按官方顺序自动重排传入的提示词，输出 `positive` / `breakdown`。选角色显示中文名、写入标签；`artist_custom` 可填列表外的画师。

`MOSSCharacterPrompt`（MOSS 角色提示词）：更轻量的角色/动作选择器，输出纯提示词字符串。
