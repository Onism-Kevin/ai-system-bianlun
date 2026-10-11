# debate_engine.py
"""辩论流程纯逻辑模块（不依赖 Tkinter），可独立单元测试。"""
from debate_config import ROLES


def build_debate_sequence(max_turns):
    """按轮数生成完整辩论流程：开场陈词 -> N轮辩论阶段 -> 总结陈词。

    Returns:
        list[tuple[str, str]]: [(role, phase), ...]
    """
    if max_turns < 0:
        raise ValueError(f"max_turns 不能为负数: {max_turns}")
    sequence = [("正方", "开场陈词"), ("反方", "开场陈词")]
    for i in range(max_turns):
        sequence.append(("正方", f"辩论阶段{i + 1}"))
        sequence.append(("反方", f"辩论阶段{i + 1}"))
    sequence.append(("正方", "总结陈词"))
    sequence.append(("反方", "总结陈词"))
    return sequence


def resolve_role_params(role, temp_override=None, model_override=None):
    """基于 debate_config.ROLES 解析角色的 (temperature, model)。

    override 为 None 时使用角色默认配置；传入值优先（供 UI 独立调节）。
    """
    cfg = ROLES[role]
    temp = cfg["temperature"] if temp_override is None else temp_override
    model = cfg["model"] if model_override is None else model_override
    return temp, model


def is_debate_round(phase):
    """判断阶段是否为辩论阶段（用于轮次统计，排除开场/总结陈词）。"""
    return "辩论阶段" in phase
