# 模型明细（型号 × 渠道，跨渠道去重共 485 个型号）

- 来源：`http://127.0.0.1:8326/v1/models`（HTTP 200，原始 1510 项）
- 已剔除：`-vision/`、`:batch`、`:free`、`-latest`、image/audio/lyria/tts/embedding/rerank
- 「渠道」列为该型号可用的渠道前缀；写入 backend/.env 的 MODEL_DEFAULT 时用**完整 id**（`渠道/型号`）


## Anthropic（16）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `anthropic/claude-fable-5` | `cline` |
| `anthropic/claude-fable-5.1` | `cline` |
| `anthropic/claude-haiku-4.5` | `cline` |
| `anthropic/claude-haiku-5.5` | `cline` |
| `anthropic/claude-opus-4.1` | `cline` |
| `anthropic/claude-opus-4.5` | `cline` |
| `anthropic/claude-opus-4.6` | `cline` |
| `anthropic/claude-opus-4.7` | `cline` |
| `anthropic/claude-opus-4.8` | `cline` |
| `anthropic/claude-opus-5` | `cline` |
| `anthropic/claude-opus-5.5` | `cline` |
| `anthropic/claude-sonnet-4` | `cline` |
| `anthropic/claude-sonnet-4.5` | `cline` |
| `anthropic/claude-sonnet-4.6` | `cline` |
| `anthropic/claude-sonnet-5` | `cline` |
| `anthropic/claude-sonnet-5.5` | `cline` |

## OpenAI（69）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `gpt-5.3-codex` | `workbuddy` |
| `gpt-5.4` | `workbuddy` |
| `gpt-5.5` | `workbuddy` |
| `gpt-5.6-luna` | `workbuddy` |
| `gpt-5.6-sol` | `workbuddy` |
| `gpt-5.6-terra` | `workbuddy` |
| `gpt-6-astra` | `workbuddy` |
| `gpt-6-luna` | `workbuddy` |
| `gpt-6-sol` | `workbuddy` |
| `gpt-6.1-sol` | `workbuddy` |
| `openai/gpt-3.5-turbo` | `cline` |
| `openai/gpt-3.5-turbo-0613` | `cline` |
| `openai/gpt-3.5-turbo-16k` | `cline` |
| `openai/gpt-3.5-turbo-instruct` | `cline` |
| `openai/gpt-4` | `cline` |
| `openai/gpt-4-turbo` | `cline` |
| `openai/gpt-4.1` | `cline` |
| `openai/gpt-4.1-mini` | `cline` |
| `openai/gpt-4.1-nano` | `cline` |
| `openai/gpt-4o` | `cline` |
| `openai/gpt-4o-2024-05-13` | `cline` |
| `openai/gpt-4o-2024-08-06` | `cline` |
| `openai/gpt-4o-2024-11-20` | `cline` |
| `openai/gpt-4o-mini` | `cline` |
| `openai/gpt-4o-mini-2024-07-18` | `cline` |
| `openai/gpt-5` | `cline` |
| `openai/gpt-5-mini` | `cline` |
| `openai/gpt-5-nano` | `cline` |
| `openai/gpt-5-pro` | `cline` |
| `openai/gpt-5.1` | `cline` |
| `openai/gpt-5.1-codex` | `cline` |
| `openai/gpt-5.1-codex-max` | `cline` |
| `openai/gpt-5.1-codex-mini` | `cline` |
| `openai/gpt-5.2` | `cline` |
| `openai/gpt-5.2-chat` | `cline` |
| `openai/gpt-5.2-codex` | `cline` |
| `openai/gpt-5.2-pro` | `cline` |
| `openai/gpt-5.3-codex` | `cline` |
| `openai/gpt-5.4` | `cline` |
| `openai/gpt-5.4-mini` | `cline` |
| `openai/gpt-5.4-nano` | `cline` |
| `openai/gpt-5.4-pro` | `cline` |
| `openai/gpt-5.5` | `cline` |
| `openai/gpt-5.5-pro` | `cline` |
| `openai/gpt-5.6-luna` | `cline` |
| `openai/gpt-5.6-luna-pro` | `cline` |
| `openai/gpt-5.6-sol` | `cline` |
| `openai/gpt-5.6-sol-pro` | `cline` |
| `openai/gpt-5.6-terra` | `cline` |
| `openai/gpt-5.6-terra-pro` | `cline` |
| `openai/gpt-6-astra` | `cline` |
| `openai/gpt-6-astra-pro` | `cline` |
| `openai/gpt-6-luna` | `cline` |
| `openai/gpt-6-luna-pro` | `cline` |
| `openai/gpt-6-sol` | `cline` |
| `openai/gpt-6-sol-pro` | `cline` |
| `openai/gpt-6.1-sol` | `cline` |
| `openai/gpt-6.1-sol-pro` | `cline` |
| `openai/gpt-oss-120b` | `cline` |
| `openai/gpt-oss-20b` | `cline`, `our-free-model` |
| `openai/gpt-oss-safeguard-20b` | `cline` |
| `openai/o1` | `cline` |
| `openai/o1-pro` | `cline` |
| `openai/o3` | `cline` |
| `openai/o3-mini` | `cline` |
| `openai/o3-mini-high` | `cline` |
| `openai/o3-pro` | `cline` |
| `openai/o4-mini` | `cline` |
| `openai/o4-mini-high` | `cline` |

## Google（22）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `gemini-3.5-flash` | `workbuddy` |
| `google/gemini-2.5-flash` | `cline` |
| `google/gemini-2.5-flash-lite` | `cline` |
| `google/gemini-2.5-pro` | `cline` |
| `google/gemini-2.5-pro-preview` | `cline` |
| `google/gemini-3-flash-preview` | `cline` |
| `google/gemini-3.1-flash-lite` | `cline` |
| `google/gemini-3.1-flash-lite-preview` | `cline` |
| `google/gemini-3.1-pro-preview` | `cline` |
| `google/gemini-3.1-pro-preview-customtools` | `cline` |
| `google/gemini-3.5-flash` | `cline` |
| `google/gemini-3.5-flash-lite` | `cline` |
| `google/gemini-3.6-flash` | `cline` |
| `google/gemini-3.7-flash` | `cline` |
| `google/gemini-3.8-flash` | `cline` |
| `google/gemini-nano-banana-2.1` | `cline` |
| `google/gemma-2-27b-it` | `cline` |
| `google/gemma-3-12b-it` | `cline` |
| `google/gemma-3-27b-it` | `cline` |
| `google/gemma-3-4b-it` | `cline` |
| `google/gemma-4-26b-a4b-it` | `cline` |
| `google/gemma-4-31b-it` | `cline` |

## DeepSeek（33）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `DeepSeek-V4-Flash` | `modlens-trae`, `trae` |
| `DeepSeek-V4-Flash-Official` | `modlens-trae`, `trae` |
| `DeepSeek-V4-Pro` | `modlens-trae`, `trae` |
| `DeepSeek-V4-Pro-Official` | `modlens-trae`, `trae` |
| `DeepSeek-V4.1-Flash` | `loomy` |
| `cline-pass/deepseek-v4-flash` | `cline`, `modlens-cline` |
| `cline-pass/deepseek-v4-pro` | `cline`, `modlens-cline` |
| `cline-pass/deepseek-v4.1-flash` | `cline` |
| `deepseek-V3` | `modlens-trae`, `trae` |
| `deepseek-V3.1` | `modlens-trae`, `trae` |
| `deepseek-ai/deepseek-v4.1-flash` | `our-free-model` |
| `deepseek-flash` | `deepseek-account`, `deepseek-official`, `lobsterai` |
| `deepseek-v4-flash` | `buddy`, `codearts`, `lobsterai`, `modlens-codearts`, `modlens-lobsterai` |
| `deepseek-v4-flash-0731` | `loomy`, `modlens-loomy` |
| `deepseek-v4-flash-vision-exp` | `lobsterai` |
| `deepseek-v4-pro` | `buddy`, `codearts`, `deepseek-account`, `deepseek-modlens`, `deepseek-official`, `lobsterai`, `modlens-codearts`, `modlens-deepseek-account`, `modlens-lobsterai` |
| `deepseek-v4.1-flash` | `buddy`, `codearts`, `modlens-codearts`, `trae`, `workbuddy` |
| `deepseek-v4.1-flash-sg` | `workbuddy` |
| `deepseek/deepseek-chat` | `cline`, `modlens-cline` |
| `deepseek/deepseek-chat-v3-0324` | `cline`, `modlens-cline` |
| `deepseek/deepseek-chat-v3.1` | `cline`, `modlens-cline` |
| `deepseek/deepseek-r1` | `cline`, `modlens-cline` |
| `deepseek/deepseek-r1-0528` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v3.1-terminus` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v3.2` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v3.2-exp` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v4-flash` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v4-flash-0731` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v4-flash-vision-exp` | `cline` |
| `deepseek/deepseek-v4-pro` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v4-pro-0813` | `cline`, `modlens-cline` |
| `deepseek/deepseek-v4.1-flash` | `cline`, `modlens-cline` |
| `sn-deepseek-v4-1-flash` | `raccoon` |

## Qwen（56）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `cline-pass/qwen3.7-max` | `cline` |
| `cline-pass/qwen3.7-plus` | `cline` |
| `cline-pass/qwen3.8-max` | `cline` |
| `qwen-3.5` | `trae` |
| `qwen-3.6-plus` | `trae` |
| `qwen-3.7-plus` | `trae` |
| `qwen-3.8-max` | `loomy` |
| `qwen/qwen-2.5-72b-instruct` | `cline` |
| `qwen/qwen-2.5-7b-instruct` | `cline` |
| `qwen/qwen-2.5-coder-32b-instruct` | `cline` |
| `qwen/qwen-plus` | `cline` |
| `qwen/qwen2.5-vl-72b-instruct` | `cline` |
| `qwen/qwen3-14b` | `cline` |
| `qwen/qwen3-235b-a22b-2507` | `cline` |
| `qwen/qwen3-235b-a22b-thinking-2507` | `cline` |
| `qwen/qwen3-30b-a3b` | `cline` |
| `qwen/qwen3-30b-a3b-instruct-2507` | `cline` |
| `qwen/qwen3-32b` | `cline` |
| `qwen/qwen3-coder` | `cline` |
| `qwen/qwen3-coder-30b-a3b-instruct` | `cline` |
| `qwen/qwen3-coder-flash` | `cline` |
| `qwen/qwen3-coder-next` | `cline` |
| `qwen/qwen3-next-80b-a3b-instruct` | `cline` |
| `qwen/qwen3-next-80b-a3b-thinking` | `cline` |
| `qwen/qwen3-vl-235b-a22b-instruct` | `cline` |
| `qwen/qwen3-vl-30b-a3b-instruct` | `cline` |
| `qwen/qwen3-vl-30b-a3b-thinking` | `cline` |
| `qwen/qwen3-vl-8b-instruct` | `cline` |
| `qwen/qwen3.5-122b-a10b` | `cline` |
| `qwen/qwen3.5-27b` | `cline` |
| `qwen/qwen3.5-35b-a3b` | `cline` |
| `qwen/qwen3.5-397b-a17b` | `cline` |
| `qwen/qwen3.5-9b` | `cline` |
| `qwen/qwen3.5-flash-02-23` | `cline` |
| `qwen/qwen3.5-plus-02-15` | `cline` |
| `qwen/qwen3.5-plus-20260420` | `cline` |
| `qwen/qwen3.6-27b` | `cline` |
| `qwen/qwen3.6-35b-a3b` | `cline` |
| `qwen/qwen3.6-flash` | `cline` |
| `qwen/qwen3.6-plus` | `cline` |
| `qwen/qwen3.7-flash` | `cline` |
| `qwen/qwen3.7-max` | `cline` |
| `qwen/qwen3.7-plus` | `cline` |
| `qwen/qwen3.8-2.4t-a95b` | `cline` |
| `qwen/qwen3.8-27b` | `cline` |
| `qwen/qwen3.8-flash` | `cline` |
| `qwen/qwen3.8-max-0902` | `cline` |
| `qwen/qwen3.8-max-prime` | `cline` |
| `qwen/qwen3.8-omni-flash` | `cline` |
| `qwen3.5-plus-2026-04-20` | `lobsterai` |
| `qwen3.6-plus` | `lobsterai` |
| `qwen3.7-max` | `lobsterai` |
| `qwen3.7-plus` | `lobsterai` |
| `qwen3.8-flash` | `lobsterai`, `loomy`, `trae` |
| `qwen3.8-max` | `lobsterai`, `trae` |
| `qwen3.8-omni-flash` | `lobsterai` |

## GLM（33）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `GLM-5.2` | `codearts`, `modlens-codearts` |
| `GLM-5.3` | `modlens-zcode`, `zcode` |
| `GLM-5.3-Flash` | `loomy`, `zcode` |
| `cline-pass/glm-5.2` | `cline`, `modlens-cline` |
| `cline-pass/glm-5.3` | `cline`, `modlens-cline` |
| `cline-pass/glm-5.3-flash` | `cline` |
| `glm-4.7` | `modlens-trae`, `trae` |
| `glm-5` | `lobsterai`, `modlens-lobsterai`, `modlens-trae`, `trae` |
| `glm-5.1` | `buddy`, `lobsterai`, `modlens-lobsterai`, `modlens-trae`, `trae` |
| `glm-5.2` | `buddy`, `lobsterai`, `modlens-lobsterai`, `modlens-trae`, `trae`, `workbuddy` |
| `glm-5.2-sft-harmony` | `codearts`, `modlens-codearts` |
| `glm-5.3` | `buddy`, `lobsterai`, `modlens-lobsterai`, `modlens-trae`, `trae`, `workbuddy` |
| `glm-5.3-flash` | `buddy`, `codearts`, `lobsterai`, `trae`, `workbuddy` |
| `glm-5.3-flashx` | `lobsterai`, `trae` |
| `glm-5v-turbo` | `buddy`, `lobsterai`, `trae` |
| `sn-glm-5-3` | `raccoon` |
| `sn-glm-5-3-flash` | `raccoon` |
| `z-ai/glm-4.5` | `cline`, `modlens-cline` |
| `z-ai/glm-4.5-air` | `cline`, `modlens-cline` |
| `z-ai/glm-4.5v` | `cline` |
| `z-ai/glm-4.6` | `cline`, `modlens-cline` |
| `z-ai/glm-4.6v` | `cline` |
| `z-ai/glm-4.7` | `cline`, `modlens-cline` |
| `z-ai/glm-4.7-flash` | `cline`, `modlens-cline` |
| `z-ai/glm-5` | `cline`, `modlens-cline` |
| `z-ai/glm-5-turbo` | `cline`, `modlens-cline` |
| `z-ai/glm-5.1` | `cline`, `modlens-cline` |
| `z-ai/glm-5.2` | `cline`, `modlens-cline` |
| `z-ai/glm-5.3` | `cline`, `modlens-cline`, `modlens-our-free-model`, `our-free-model` |
| `z-ai/glm-5.3-flash` | `cline`, `our-free-model` |
| `z-ai/glm-5.3-flashx` | `cline`, `modlens-cline` |
| `z-ai/glm-5.3-prime` | `cline`, `modlens-cline` |
| `z-ai/glm-5v-turbo` | `cline` |

## Kimi（20）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `Kimi-k2.6` | `loomy` |
| `cline-pass/kimi-k2.6` | `cline` |
| `cline-pass/kimi-k2.7-code` | `cline` |
| `cline-pass/kimi-k3` | `cline` |
| `kimi-k2.5` | `lobsterai`, `trae` |
| `kimi-k2.6` | `buddy`, `lobsterai`, `trae`, `workbuddy` |
| `kimi-k2.7` | `buddy` |
| `kimi-k2.7-code` | `lobsterai`, `trae` |
| `kimi-k2.7-code-highspeed` | `lobsterai` |
| `kimi-k2.8-preview` | `buddy`, `lobsterai`, `trae`, `workbuddy` |
| `kimi-k3` | `lobsterai`, `trae`, `workbuddy` |
| `kimi-k3-1` | `buddy` |
| `moonshotai/kimi-k2` | `cline` |
| `moonshotai/kimi-k2-0905` | `cline` |
| `moonshotai/kimi-k2-thinking` | `cline` |
| `moonshotai/kimi-k2.5` | `cline` |
| `moonshotai/kimi-k2.6` | `cline`, `our-free-model` |
| `moonshotai/kimi-k2.7-code` | `cline` |
| `moonshotai/kimi-k3` | `cline`, `our-free-model` |
| `sn-kimi-k3` | `raccoon` |

## Meta（17）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `aion-labs/aion-rp-llama-3.1-8b` | `cline` |
| `meta-llama/llama-3.1-70b-instruct` | `cline` |
| `meta-llama/llama-3.1-8b-instruct` | `cline` |
| `meta-llama/llama-3.2-1b-instruct` | `cline` |
| `meta-llama/llama-3.2-3b-instruct` | `cline` |
| `meta-llama/llama-3.3-70b-instruct` | `cline` |
| `meta-llama/llama-4-maverick` | `cline` |
| `meta-llama/llama-4-scout` | `cline` |
| `meta-llama/llama-guard-4-12b` | `cline` |
| `meta/muse-glimmer-30b` | `cline` |
| `meta/muse-spark-1.1` | `cline` |
| `meta/muse-spark-1.2` | `cline` |
| `meta/muse-spark-1.2-contributor` | `cline` |
| `meta/muse-spark-1.3` | `cline` |
| `meta/muse-spark-1.3-contributor` | `cline` |
| `nousresearch/hermes-3-llama-3.1-405b` | `cline` |
| `nousresearch/hermes-3-llama-3.1-70b` | `cline` |

## Mistral（21）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `cognitivecomputations/dolphin-mistral-24b-venice-edition` | `cline` |
| `mistralai/codestral-2508` | `cline` |
| `mistralai/devstral-2512` | `cline` |
| `mistralai/ministral-14b-2512` | `cline` |
| `mistralai/ministral-3b-2512` | `cline` |
| `mistralai/ministral-8b-2512` | `cline` |
| `mistralai/mistral-large` | `cline` |
| `mistralai/mistral-large-2407` | `cline` |
| `mistralai/mistral-large-2512` | `cline` |
| `mistralai/mistral-large-4-0` | `cline` |
| `mistralai/mistral-medium-3` | `cline` |
| `mistralai/mistral-medium-3-5` | `cline` |
| `mistralai/mistral-medium-3.1` | `cline` |
| `mistralai/mistral-nemo` | `cline` |
| `mistralai/mistral-saba` | `cline` |
| `mistralai/mistral-small-24b-instruct-2501` | `cline` |
| `mistralai/mistral-small-2603` | `cline` |
| `mistralai/mistral-small-3.1-24b-instruct` | `cline` |
| `mistralai/mistral-small-3.2-24b-instruct` | `cline` |
| `mistralai/mixtral-8x22b-instruct` | `cline` |
| `mistralai/voxtral-small-24b-2507` | `cline` |

## MiniMax（15）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `MiniMax-M2.7` | `lobsterai`, `minimax` |
| `MiniMax-M2.7-highspeed` | `minimax` |
| `MiniMax-M3` | `lobsterai`, `loomy`, `minimax` |
| `MiniMax-M3.1-Flash-Preview` | `lobsterai`, `minimax` |
| `cline-pass/minimax-m3` | `cline` |
| `minimax-m2.7` | `trae` |
| `minimax-m3` | `buddy`, `trae` |
| `minimax/minimax-01` | `cline` |
| `minimax/minimax-m1` | `cline` |
| `minimax/minimax-m2` | `cline` |
| `minimax/minimax-m2-her` | `cline` |
| `minimax/minimax-m2.1` | `cline` |
| `minimax/minimax-m2.5` | `cline` |
| `minimax/minimax-m2.7` | `cline` |
| `minimax/minimax-m3` | `cline` |

## Grok（8）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `grok-4.7` | `workbuddy` |
| `x-ai/grok-4.20` | `cline` |
| `x-ai/grok-4.20-multi-agent` | `cline` |
| `x-ai/grok-4.3` | `cline` |
| `x-ai/grok-4.5` | `cline` |
| `x-ai/grok-4.6` | `cline` |
| `x-ai/grok-4.7` | `cline` |
| `x-ai/grok-build-0.1` | `cline` |

## Cohere（5）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `cohere/command-a` | `cline` |
| `cohere/command-a-plus` | `cline` |
| `cohere/command-r-08-2024` | `cline` |
| `cohere/command-r-plus-08-2024` | `cline` |
| `cohere/command-r7b-12-2024` | `cline` |

## Amazon（7）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `amazon/nova-2-lite-v1` | `cline` |
| `amazon/nova-lite-v1` | `cline` |
| `amazon/nova-micro-v1` | `cline` |
| `amazon/nova-premier-v1` | `cline` |
| `amazon/nova-pro-v1` | `cline` |
| `sn-sensenova-6-8-flash` | `raccoon` |
| `sn-sensenova-6-8-flash-lite` | `raccoon` |

## ByteDance（15）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `Doubao-Seed-2.0-Code` | `trae` |
| `Doubao-Seed-2.1-Pro` | `trae` |
| `Doubao-Seed-2.1-Turbo` | `trae` |
| `Doubao-Seed-Code` | `trae` |
| `Doubao-Seed-Evolving` | `trae` |
| `bytedance-seed/seed-1.6` | `cline` |
| `bytedance-seed/seed-1.6-flash` | `cline` |
| `bytedance-seed/seed-2-1-turbo` | `cline` |
| `bytedance-seed/seed-2.0-code` | `cline` |
| `bytedance-seed/seed-2.0-lite` | `cline` |
| `bytedance-seed/seed-2.0-mini` | `cline` |
| `bytedance/ui-tars-1.5-7b` | `cline` |
| `doubao-seed-2-0-code-preview-260215` | `lobsterai` |
| `doubao-seed-2-1-pro-260915` | `lobsterai` |
| `doubao-seed-2-1-turbo-260628` | `lobsterai` |

## Tencent（11）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `hy3` | `buddy`, `workbuddy` |
| `hy3-x` | `buddy` |
| `hy4-preview` | `buddy`, `workbuddy` |
| `hy4-preview-f` | `workbuddy` |
| `tencent/hunyuan-a13b-instruct` | `cline` |
| `tencent/hy-mt2-1.8b` | `cline` |
| `tencent/hy-mt2-30b-a3b` | `cline` |
| `tencent/hy-mt2-7b` | `cline` |
| `tencent/hy3` | `cline` |
| `tencent/hy3-preview` | `cline` |
| `tencent/hy4-preview` | `cline` |

## Xiaomi（14）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `cline-free/mimo-v2.6-flash` | `cline` |
| `cline-pass/mimo-v2.5` | `cline` |
| `cline-pass/mimo-v2.5-pro` | `cline`, `modlens-cline` |
| `cline-pass/mimo-v2.6-flash` | `cline` |
| `cline-pass/mimo-v2.6-pro` | `cline` |
| `mimo-v2.5` | `loomy` |
| `mimo-v2.6-flash` | `trae` |
| `mimo-v2.6-flash-free` | `our-free-model` |
| `mimo-v2.6-pro` | `trae` |
| `xiaomi/mimo-v2.5` | `cline` |
| `xiaomi/mimo-v2.5-pro` | `cline`, `modlens-cline` |
| `xiaomi/mimo-v2.6-flash` | `cline` |
| `xiaomi/mimo-v2.6-pro` | `cline`, `modlens-cline` |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | `cline`, `modlens-cline` |

## StepFun（7）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `cline-free/step-5-preview` | `cline` |
| `step-5-preview` | `trae` |
| `step-5-preview-free` | `our-free-model` |
| `stepfun/step-3.5-flash` | `cline` |
| `stepfun/step-3.7-flash` | `cline` |
| `stepfun/step-5-preview` | `cline` |
| `stepfun/step-5-preview-free` | `our-free-model` |

## 其他（116）

| 型号 | 可用渠道（完整 id = 渠道/型号） |
|---|---|
| `aion-labs/aion-2.0` | `cline` |
| `aion-labs/aion-3.0` | `cline` |
| `aion-labs/aion-3.0-mini` | `cline` |
| `aion-labs/aion-3.5` | `cline` |
| `aion-labs/aion-3.5-mini` | `cline` |
| `anthracite-org/magnum-v4-72b` | `cline` |
| `arcee-ai/trinity-large-thinking` | `cline` |
| `auto` | `loomy`, `qoder`, `qodercn` |
| `balanced-model` | `workbuddy` |
| `cline-free/muse-spark-1.3-contributor` | `cline` |
| `cline-free/solar-mini4` | `cline` |
| `cline-pass/muse-spark-1.3-contributor` | `cline` |
| `cmodel` | `qoder` |
| `code-review-judge` | `trae` |
| `deep-model` | `workbuddy` |
| `default-model` | `workbuddy` |
| `dfmodel` | `qoder`, `qodercn` |
| `dmodel` | `qoder`, `qodercn` |
| `doubao-2.0-mini` | `trae` |
| `efficient` | `qoder` |
| `exo-free` | `our-free-model` |
| `fast-model` | `workbuddy` |
| `fireworks/ember-1` | `cline` |
| `gfmodel` | `qoder`, `qodercn` |
| `gm51model` | `qodercn` |
| `gmodel` | `qoder`, `qodercn` |
| `gryphe/mythomax-l2-13b` | `cline` |
| `ibm-granite/granite-4.0-h-micro` | `cline` |
| `ibm-granite/granite-4.2-8b` | `cline` |
| `inception/mercury-2` | `cline` |
| `inception/mercury-2.5` | `cline` |
| `inclusionai/ling-3.0-flash` | `cline` |
| `inclusionai/ling-3.0-flash-fin` | `cline` |
| `inclusionai/ling-3.0-flash-sante` | `cline` |
| `inclusionai/ling-3.0-flash-vl` | `cline` |
| `inclusionai/ling-3.1-flash` | `cline`, `our-free-model` |
| `inference-net/schematron-v2-small` | `cline` |
| `inference-net/schematron-v2-turbo` | `cline` |
| `kilo-auto/free` | `our-free-model` |
| `kmodel` | `qoder`, `qodercn` |
| `kmodel_latest` | `qoder`, `qodercn` |
| `ling-3.1-flash-free` | `our-free-model` |
| `longcat-2.5-preview-free` | `our-free-model` |
| `mancer/weaver` | `cline` |
| `meituan/longcat-2.0` | `cline` |
| `microsoft/phi-4` | `cline` |
| `microsoft/wizardlm-2-8x22b` | `cline` |
| `mmodel` | `qoder`, `qodercn` |
| `morph/morph-v3-fast` | `cline` |
| `morph/morph-v3-large` | `cline` |
| `nemotron-3-ultra-free` | `our-free-model` |
| `nemotron-3.5-lightning-free` | `our-free-model` |
| `nex-agi/nex-n2.5-mini` | `cline` |
| `nex-agi/nex-n2.5-pro` | `cline` |
| `nousresearch/hermes-4-405b` | `cline` |
| `nvidia/nemotron-3-nano-30b-a3b` | `cline` |
| `nvidia/nemotron-3-super-120b-a12b` | `cline` |
| `nvidia/nemotron-3-ultra-550b-a55b` | `cline` |
| `nvidia/nemotron-3.5-content-safety` | `cline` |
| `nvidia/nemotron-3.5-lightning` | `cline` |
| `nvidia/switchyard` | `cline` |
| `openpangu-2.0-flash` | `codearts` |
| `openpangu-2.0-pro` | `codearts` |
| `openrouter/auto` | `cline` |
| `openrouter/auto-beta` | `cline` |
| `openrouter/bodybuilder` | `cline` |
| `openrouter/free` | `cline`, `our-free-model` |
| `openrouter/fusion` | `cline` |
| `openrouter/pareto-code` | `cline` |
| `perceptron/perceptron-mk1` | `cline` |
| `perceptron/perceptron-mk1.5` | `cline` |
| `performance` | `qoder` |
| `perplexity/sonar` | `cline` |
| `perplexity/sonar-deep-research` | `cline` |
| `perplexity/sonar-pro` | `cline` |
| `perplexity/sonar-pro-search` | `cline` |
| `perplexity/sonar-reasoning-pro` | `cline` |
| `poolside/laguna-s-2.1` | `cline` |
| `poolside/laguna-xs-2.1` | `cline` |
| `primary-model` | `workbuddy` |
| `prism-ml/ternary-bonsai-2-27b` | `cline` |
| `q37fmodel` | `qodercn` |
| `qfmodel` | `qoder`, `qodercn` |
| `qmodel` | `qoder`, `qodercn` |
| `qmodel_38max` | `qoder`, `qodercn` |
| `qmodel_latest` | `qoder`, `qodercn` |
| `rekaai/reka-edge` | `cline` |
| `rekaai/reka-flash-3` | `cline` |
| `relace/relace-apply-3` | `cline` |
| `relace/relace-search` | `cline` |
| `sakana/fugu-max` | `cline` |
| `sakana/fugu-ultra` | `cline` |
| `sakana/fugu-ultra-v2` | `cline` |
| `sakana/sakana-namazu` | `cline` |
| `sao10k/l3-lunaris-8b` | `cline` |
| `sao10k/l3.1-euryale-70b` | `cline` |
| `sao10k/l3.3-euryale-70b` | `cline` |
| `smodel` | `qoder` |
| `space-bunny` | `buddy` |
| `space-bunny-free` | `our-free-model` |
| `spark-x` | `loomy` |
| `stealth/glyph-cluster` | `our-free-model` |
| `thedrummer/cydonia-24b-v4.1` | `cline` |
| `thedrummer/skyfall-36b-v2` | `cline` |
| `thedrummer/unslopnemo-12b` | `cline` |
| `thinkingmachines/inkling` | `cline` |
| `thinkingmachines/inkling-small` | `cline` |
| `typesafe/jev-router` | `cline` |
| `ultimate` | `qoder` |
| `unbiased/pareto` | `cline` |
| `unbiased/pareto-26.10-preview` | `cline` |
| `undi95/remm-slerp-l2-13b` | `cline` |
| `upstage/solar-mini4` | `cline` |
| `upstage/solar-pro-3` | `cline` |
| `upstage/solar-pro4` | `cline` |
| `writer/palmyra-x5` | `cline` |
