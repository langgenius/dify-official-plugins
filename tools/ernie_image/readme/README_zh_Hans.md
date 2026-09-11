# ERNIE Image

本文件提供简体中文说明。英文文档请参见上级目录的 `README.md`。

基于百度飞桨星河社区（AI Studio）OpenAI 兼容 Images API 的文生图工具，
支持 **ERNIE Image** 与 **ERNIE Image Turbo** 两个模型。

## 模型

| 模型 | 官方模型说明 |
|------|--------------|
| `ernie-image-turbo` | 面向速度与美感优化的蒸馏模型，通常使用 8 个推理步骤；为插件默认模型。 |
| `ernie-image` | 强调通用能力和指令遵循的 SFT 模型，通常使用 50 个推理步骤。 |

推理参数由托管 API 控制，上述步骤数仅说明官方模型版本，并非插件参数。

## 配置

1. 登录 <https://aistudio.baidu.com>，在「个人中心 → 访问令牌」中创建访问令牌。
2. 在 Dify 中安装本插件并填入该令牌完成授权。

## 参数

- `prompt`（必填）：图像的文字描述，最长 2048 个字符。
- `model`：`ernie-image-turbo`（默认）或 `ernie-image`。
- `size`：当前官方分辨率之一：`1024x1024`、`848x1264`、`768x1376`、
  `896x1200`、`1264x848`、`1376x768` 或 `1200x896`。默认
  `1024x1024`，百度推荐 `1376x768`。运行时继续接受旧版插件已公开的尺寸，
  以兼容已有 Dify 工作流。
- `n`：生成图像数量，1–4，默认 `1`。
- `seed`：可选随机种子，用于复现结果。
- `watermark`：是否在输出中添加模型水印，默认 `false`。

`n` 与 `seed` 是 AI Studio endpoint 的兼容扩展；当前公开的千帆请求文档列出
`prompt`、`model`、`size` 与 `watermark`。

输出：每张成功下载的图像都会以 PNG blob 返回，同时附带一段 JSON，包含
响应 `id`、`created`、AI Studio `trace_id`、原始 URL 与 `revised_prompt`。
百度文档说明生成 URL 的有效期为 24 小时，持久化工作流结果应使用 blob。

## 兼容性与校验

- 请求前校验模型、尺寸、提示词长度、生成数量及整数种子。
- 同时支持 AI Studio（`errorCode` / `errorMsg`）和当前 OpenAI 兼容
  （`code` / `message` / `type`）错误格式。
- 单张图片下载失败只跳过该图片，不影响其他图片与 JSON 摘要。

## 官方资料

- [ERNIE-Image 官方模型卡](https://aistudio.baidu.com/modelsdetail/46031)
- [ERNIE-Image-Turbo 官方模型卡](https://aistudio.baidu.com/modelsdetail/46030/intro)
- [ERNIE-Image-Turbo API 文档](https://cloud.baidu.com/doc/qianfan-api/s/Imo9g5a6a)

## 隐私

详见同目录下的 `PRIVACY.md`。
