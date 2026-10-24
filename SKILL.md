---
name: moss-image-comfyui
description: 在本地 ComfyUI 上用 MOSS-Image（OpenMOSS 的 5B DiT 文生图模型）出图的操作手册：权重选型与量化、采样配方、danbooru tag 与中文自然语言的混合提示词、参考图复刻流程、常见问题修正对照、图生图 denoise 区间、局部重绘、分辨率与显存上限。Use when generating images with MOSS / MOSS-Image in ComfyUI, replicating a reference image with a different character, or debugging noise / bad proportions / bad hands / drifted clothing / lost lighting.
---

# MOSS-Image 在 ComfyUI 上出图

5B 单流 DiT + Qwen3.5-9B 文本编码器 + FLUX.2 VAE。下面是在本机（RX 7900 XT 20GB / ROCm 7.14 / 32GB RAM / ComfyUI 0.41.0）实测出的参数与边界，不是文档转述。

## 硬性原则

1. **不要套 `ModelSamplingSD3`**。它的 `multiplier=1000` 与 MOSS 内置的 `multiplier=1.0 / shift=5.0` 冲突，sigma 时间步错放 1000 倍，输出退化成纯彩色噪声。shift 5.0 已内置，要改只能用 `ModelSamplingAuraFlow`。
2. **图生图 denoise 不得低于 0.85**。MOSS 没做 img2img 训练：0.9 正常、0.8 出现噪点、0.65 明显劣化、0.45 是纯噪声。它给的是"锁构图换风格"，不是"轻微修图"。
3. **分辨率上限 2.3MP**。2016×1152 稳定；2688×1536（4MP）会打爆 20GB 显存直接干掉进程。
4. **低于 1.5MP 五官必糊**。1MP 下人物脸只有几十像素，50 步会把小脸平均掉。要五官清晰就给到 2MP 以上，或让人物占画面更大比例。
5. **角色与画师用 tag 锚定，场景与氛围用中文写**。专有名词是成对训练的，tag 是短路；场景光线材质是组合语义，自然语言才准。

## 环境

ComfyUI ≥ 0.41.0（原生支持 `image_model: moss_image`）。文本编码器是 **Qwen3.5-9B**，`CLIPLoader` 的 type 选 `moss_image`。VAE 是 FLUX.2 VAE（128 通道 / 16 倍下采样），latent 尺寸必须对齐 16 的倍数。

| 用途 | 文件 | 体积 |
|---|---|---|
| DiT 首选 | `diffusion_models/moss_image_base_int8_convrot.safetensors` | 5.04 GB |
| DiT 质量优先 | `diffusion_models/moss_image_base_bf16.safetensors` | 9.47 GB |
| 文本编码器首选 | `text_encoders/qwen3.5_9b_w4a8_gptq.safetensors` | 6.84 GB |
| 文本编码器备选 | `text_encoders/qwen3.5_9b_int8_convrot.safetensors` | 9.08 GB |
| VAE | `vae/flux2-vae.safetensors` | 0.31 GB |

选 int8_convrot + w4a8 不只省显存：`comfy-kitchen` 的 HIP 后端有 `int8_linear` 与 `dequantize_int8_convrot_weight_dtype`，量化走真实 kernel，画质无明显损失而速度提升 3~10 倍（50 步 311s→70s）。

## 采样配方

```
UNETLoader(int8_convrot) → SkipLayerGuidanceDiTSimple → KSampler
CLIPLoader(type=moss_image) → CLIPTextEncode ×2
VAELoader(flux2-vae) → VAEDecode
```

| 参数 | 值 |
|---|---|
| steps | 50（定稿）/ 20（试构图） |
| cfg | 3.0 – 3.5 |
| sampler / scheduler | `euler` / `sgm_uniform` |
| shift | 5.0（内置，不要覆盖） |
| SLG | `SkipLayerGuidanceDiTSimple`，`single_layers="22"`，0→1.0 |
| denoise | 1.0（t2i）/ 0.9（i2i） |

latent 用 `EmptyFlux2LatentImage`（128 通道），不要用 SD 的 `EmptyLatentImage`。

### 加速档：8 步 DMD LoRA

装 `lodestones/MOSS-Image-SFT-8-steps-dmd` 的 `lora.safetensors`（1.13GB）到 `models/loras/`，链路改成 `UNETLoader → LoraLoaderModelOnly → KSampler`，**必须去掉 SLG**（每步两次前向，会把加速全吃掉）。

| 参数 | 值 |
|---|---|
| steps | 8（试构图）/ 12（定稿） |
| cfg | **1.5**（上游说 "no CFG"，实测 1.0 出伪影） |
| lora strength | 1.0（换 `lora_latest` 用 0.7） |

1264×1824 实测：8 步 36s、12 步 50s、16 步 63s，对比 50 步的 230s。代价是语义遵循度下降，细节多的场景建议 12 步起步。

**DMD 档的负面提示词基本不生效，这一条会直接毁掉参考图复刻。** CFG 1.5 低于 2，负向那一路起不到该有的作用。复刻时"把原角色的兽耳、尾巴、发色瞳色压进负面"是标准动作，但在 DMD 档上这套失效——原图轮廓里的猫耳、猫尾会直接留在成品上。要压住只能靠正向描述写死（"人族少女，没有兽耳与尾巴"）加角色 tag 的先验，可靠性明显低于 50 步档的 CFG 3。所以复刻流程固定为：**i2i + DMD 12 步快速定构图与姿势，定稿切回 50 步 t2i/i2i 补身份精度**。

图生图同样能接这个 LoRA（`VAEEncode → LoraLoaderModelOnly → KSampler`，denoise 0.9，12 步约 58s），**同耗时下 i2i 的姿态比 t2i 更贴参考图**，因为带进了原图的构图轮廓。复杂动作建议：i2i + 12 步先定构图，50 步 t2i 再补关节精度。完整对照见 `reference/workflows.md`。

## 提示词核心

顺序（MOSS 官方推荐，Danbooru 惯例）：Quality → Score → Meta → Year → Character → Series → Artist → General。

```
masterpiece, best quality, anime style, cel shading,
[角色tag], [作品tag], @[画师名],
[中文场景/动作/光线/材质描述]
```

四条必守：角色用 Danbooru 官方 tag 而非中文名；画师带 `@` 前缀；二次元风格必须显式锁 `anime style, cel shading, clean lineart`，否则往半写实漂；负面提示词中英混写都生效。

## 文件导航

按需读取，不要一次全看。

| 需要什么 | 读哪个 |
|---|---|
| 复杂度分级（L1/L2/L3）、维度清单、变量模板与词组库 | `reference/prompting.md` |
| 参考图复刻四步流程、问题修正对照表 | `reference/replication.md` |
| 四种工作流、性能与故障对照、配套节点 | `reference/workflows.md` |
| 实测完整提示词示例（单双人、变量替换） | `reference/examples.md` |
