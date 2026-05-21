# ERNIE Image

本文件提供简体中文说明。英文文档请参见上级目录的 `README.md`。

基于百度飞桨星河社区（AI Studio）OpenAI 兼容接口的文生图工具，支持
**ERNIE Image** 与 **ERNIE Image Turbo** 两个模型。

## 模型

| 模型 | 说明 |
|------|------|
| `ernie-image-turbo` | 速度更快，适合草图与快速迭代。 |
| `ernie-image` | 画质更佳，细节更丰富。 |

## 配置

1. 登录 <https://aistudio.baidu.com>，在「个人中心 → 访问令牌」中创建访问令牌。
2. 在 Dify 中安装本插件并填入该令牌完成授权。

## 参数

- `prompt`（必填）：图像的文字描述。
- `model`：`ernie-image-turbo`（默认）或 `ernie-image`。
- `size`：`WxH`，例如 `1024x1024`、`1024x768`、`768x1024`、`1280x720`、
  `1792x1024`，默认 `1024x1024`。
- `n`：生成图像数量，1–4，默认 `1`。
- `seed`：可选随机种子，用于复现结果。
- `watermark`：是否在输出中添加模型水印，默认 `false`。

输出：每张生成的图像都会以二进制 blob 返回，同时附带一段 JSON
（包含原始 URL 与 `revised_prompt`）。

## 隐私

详见同目录下的 `PRIVACY.md`。
