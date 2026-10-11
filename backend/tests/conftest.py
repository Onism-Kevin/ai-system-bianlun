"""pytest 配置：沙箱拒写 %TEMP%（WinError 5），把 tmp_path 重定向到工作区。

仅覆盖 tmp_path 工厂，返回工作区内 .pytest_tmp 目录，测试无需 danger-full-access。
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_WORKSPACE_TMP = Path(__file__).resolve().parent / ".pytest_tmp"


@pytest.fixture()
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """替代 pytest 内建 tmp_path，落在工作区而非系统 %TEMP%。"""
    name = request.node.name.replace("[", "_").replace("]", "_").replace("/", "_")
    target = _WORKSPACE_TMP / name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    return target
