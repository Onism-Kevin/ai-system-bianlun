# 项目三：AI 辩论系统

基于 Tkinter 桌面界面的 AI 辩论系统。由 Ollama 本地大模型驱动，支持正反双方自动辩论与人机对话辩论，并提供 AI 头像生成、词云、文生图等配套能力。

## 功能列表

- **AI vs AI 自动辩论**：正方、反方、裁判三个模型自动完成立论、反驳、总结的完整流程。
- **人 vs AI 对话辩论**：人类选手选择一方，与 AI 对手逐轮交锋。
- **暂停 / 继续**：辩论过程中可随时暂停，再继续后续流程。
- **一键加速**：调节发言节奏，快速跑完整场辩论。
- **双击编辑头像提示词**：在界面上双击头像即可编辑该角色的生成提示词。
- **AI 头像生成（ComfyUI）**：调用本地 ComfyUI 工作流，为辩论角色生成头像。
- **词云**：根据辩论内容生成词云图。
- **文生图**：根据文本描述生成配图。
- **辩论存档 / 读档**：辩论记录保存到 `history/`，可随时回放。

## 环境要求

- Python 3.10 及以上。
- [Ollama](https://ollama.com) 已安装并启动，且已拉取以下模型：

  ```bash
  ollama pull llama3.2
  ollama pull gemma3:1b
  ollama pull qwen3.5:4b
  ```

- （可选）[ComfyUI](https://github.com/comfyanonymous/ComfyUI) 本地运行，并导入项目根目录的 `workflow_api.json` 工作流，用于 AI 头像生成与文生图。

> 注：不安装 ComfyUI 时，辩论主流程仍可正常使用，仅头像生成与文生图不可用。

## 安装

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境（Windows）
venv\Scripts\activate
#    Linux / macOS
#    source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
```

`requirements.txt` 内容：`requests`、`jieba`、`wordcloud`、`Pillow`。`tkinter` 为 Python 标准库，无需单独安装。

## 启动

```bash
python debate_ui.py
```

## 目录结构

```
AISystemBianlunn/
├── debate_ui.py        # 界面与流程入口（正式入口）
├── debate_engine.py    # 辩论流程纯逻辑（可独立测试）
├── debate_logic.py     # Ollama 流式调用
├── debate_config.py    # 角色 / 模型 / 阶段配置
├── debate_utils.py     # 词云与文生图工具
├── workflow_api.json   # ComfyUI 工作流
├── requirements.txt    # Python 依赖
├── history/            # 辩论存档
├── output/             # 生成的图片（词云、头像、文生图）
├── docs/               # 项目文档
└── venv/               # 虚拟环境（不纳入版本控制）
```
