# 模型选型候选（网关共 1510 个，剔除视觉/批处理/免费/别名后 613 个文本模型）

- 网关：`http://127.0.0.1:8326/v1`（GET /v1/models，HTTP 200）
- 剔除规则：`-vision/`、`:batch`、`:free`、`-latest`、image/audio/lyria/tts/embedding/rerank 共 897 个

| 渠道前缀 | 文本模型数 | 代表型号 |
|---|---:|---|
| `cline` | 357 | `anthropic/claude-opus-4.1` |
| `trae` | 37 | `glm-5.3` |
| `modlens-cline` | 33 | `cline-pass/glm-5.3` |
| `lobsterai` | 30 | `glm-5.3` |
| `workbuddy` | 28 | `gpt-6-astra` |
| `our-free-model` | 19 | `z-ai/glm-5.3` |
| `buddy` | 17 | `glm-5.3` |
| `qoder` | 17 | `auto` |
| `qodercn` | 14 | `auto` |
| `modlens-trae` | 11 | `glm-5.3` |
| `loomy` | 10 | `GLM-5.3-Flash` |
| `codearts` | 8 | `glm-5.3-flash` |
| `modlens-lobsterai` | 6 | `glm-5.3` |
| `raccoon` | 6 | `sn-kimi-k3` |
| `modlens-codearts` | 5 | `deepseek-v4-pro` |
| `minimax` | 4 | `MiniMax-M3` |
| `deepseek-account` | 2 | `deepseek-v4-pro` |
| `deepseek-official` | 2 | `deepseek-v4-pro` |
| `zcode` | 2 | `GLM-5.3` |
| `deepseek-modlens` | 1 | `deepseek-v4-pro` |
| `modlens-deepseek-account` | 1 | `deepseek-v4-pro` |
| `modlens-loomy` | 1 | `deepseek-v4-flash-0731` |
| `modlens-our-free-model` | 1 | `z-ai/glm-5.3` |
| `modlens-zcode` | 1 | `GLM-5.3` |
