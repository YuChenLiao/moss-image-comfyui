# 工作流与运维

## 四种工作流

| 场景 | 链路要点 |
|---|---|
| 文生图 | `EmptyFlux2LatentImage` → KSampler(denoise 1.0) |
| 图生图 | `LoadImage` → `ImageScaleToTotalPixels(megapixels=1.0, resolution_steps=16)` → `VAEEncode` → KSampler(denoise 0.9) |
| 局部重绘 | 蒙版取红通道 → `GrowMask(expand=12)` → `SetLatentNoiseMask` → KSampler(denoise 1.0) → `ImageCompositeMasked` 按蒙版贴回原图 |
| 高分辨率 | 直接给 2MP 尺寸，不要低分放大（MOSS 的 i2i 会重绘，放大不增细节） |

局部重绘的合成步骤很关键：蒙版外像素可做到字节级不变（实测 99.49% 像素零变化），因为非编辑区是贴回原图而不是重新生成。

蒙版图白色 = 重绘区，尺寸可与原图不同（用 `GetImageSize` + `ImageScale` 动态对齐）。

## 性能

- 冷启动第一张含模型加载，比热缓存慢 1.5~3 倍。
- 连续出图 6~8 张后显存碎片累积，耗时会从 70s 涨到 700s；重启 ComfyUI 后显存从 12.4GB 回落到 4.4GB，速度恢复。
- 20GB 显存下 bf16 DiT + int8 文本编码器 = 19GB，每张图都要重新 staged 一遍，这是慢的主因，换量化权重能根治。
- 实测耗时参考：2.3MP / 60 步约 225~240s；1MP / 50 步约 70s（量化）；1MP / 20 步约 35s。

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
