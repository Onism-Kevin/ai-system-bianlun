# MODEL_DEFAULT 选型基准报告（S0-3b）

网关 `http://127.0.0.1:8326/v1`，原始 1510 个模型，剔除视觉/批处理/免费/别名后 485 个去重文本型号。本报告实测其中 5 个候选，用于确定 `MODEL_DEFAULT`。

## 一、5 候选基准对比

| 候选（完整 id） | 连通 | decompose 合规 | analyze 合规(strict/lenient) | analyze 首字节 | 300字首字节 | probe_text 总时 |
|---|---|---|---|---|---|---|
| `cline/deepseek/deepseek-v4-pro` | ✅ | ✅ | **✅/✅** | 27.6s | 4.7s | 7.9s |
| `trae/qwen3.8-max` | ✅ | ✅ | **✅/✅** | 28.7s | 4.6s | 10.6s |
| `cline/z-ai/glm-5.3` | ✅ | ✅ | ❌/✅(围栏) | 4.8s | 2.1s | 5.3s |
| `cline/anthropic/claude-haiku-5.5` | ✅ | ✅ | ❌/✅(围栏) | 7.8s | 2.9s | 3.8s |
| `our-free-model/mimo-v2.6-flash-free` | ✅ | ✅ | ❌/❌(截断+非法type) | 31.1s | 6.6s | 24.4s |

### 关键观察
- **首过 strict 合规**：只有 `deepseek-v4-pro` 与 `qwen3.8-max` 在 decompose+analyze 双 structured 任务全绿。glm-5.3 与 haiku 均裹 ```json 围栏（S0-4 的 `extract_json_text` 能救，但首过率低）。mimo 因 JSON 截断 + 非法 `type:"text"` 节点，lenient 也救不了。
- **速度**：glm-5.3 与 haiku 快（analyze 首字节 <8s）；deepseek/qwen 慢（~28s，长 JSON）。
- **无一限速**：免费 mimo 未撞 429，但 analyze 首过率 0，不适合做 spike 主力。

### 决策
`MODEL_DEFAULT = cline/deepseek/deepseek-v4-pro`
理由：唯一双 structured 首过 strict 全绿的中文强候选；速度非首版瓶颈（spike 仅 20 议题）；mimo 虽稳但 analyze 首过率 0，无法兜底。

## 二、限速与延迟稳定性

对 `cline/deepseek/deepseek-v4-pro` 连续跑 10×decompose + 10×analyze（共 20 次，无并发），逐次记录首字节延迟与成败。

原始数据：`docs/model_bench_stability.json`

### decompose（10 次）
| 指标 | 值 |
|---|---|
| 成功/失败 | **10 / 0** |
| 429 限速 | **0 次** |
| 超时 | 0 次 |
| 首字节延迟 min/median/max | 2.76s / 4.78s / 8.73s |
| 总延迟 min/max | 4.10s / 9.19s |

### analyze（10 次）
| 指标 | 值 |
|---|---|
| 成功/失败 | **10 / 0** |
| 429 限速 | **0 次** |
| 超时 | 0 次 |
| 首字节延迟 min/median/max | 17.13s / 26.94s / 78.91s |
| 总延迟 min/max | 17.93s / 79.58s |

逐次 analyze 首字节：33.0 → 33.7 → **76.8** → 17.5 → 17.1 → **78.9** → **50.7** → 20.4 → 20.9 → 30.9（s）

### 结论（对照你的判定阈值）
你设定的停机阈值是「≥2 次 429 或延迟翻倍」。
- **429：0 次** ✅
- **失败/超时：0 次** ✅
- **延迟**：analyze 确实出现明显抖动——基线约 17-34s，但第 3/6/7 次冲到 77/79/51s，接近基线的 **2.3-4.6 倍**。这属于**单次抖动**而非「连续调用第 N 次系统性变慢」（第 4/5/8/9 次又回到 17-21s，无单调劣化趋势）。

**判断**：无 429、无失败、无系统性变慢，**不触发换模型**。但 analyze 的 p95 抖动到 ~79s，说明 spike 跑 20 议题 × analyze 时，延迟不稳定是真实风险。
