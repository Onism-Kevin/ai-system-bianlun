"""pytest 配置：沙箱拒写 %TEMP%（WinError 5），把 tmp_path 重定向到工作区。

仅覆盖 tmp_path 工厂，返回工作区内 .pytest_tmp 目录，测试无需 danger-full-access。

2026-10-13 S1-10 修正（用户指示）：实测本机 workspace-write 沙箱**只放行工作区
根目录的写入**，backend/ 等子目录一律 PermissionError(Errno 13)——tmp_path
必须落在仓库根 .pytest_tmp/（.gitignore 已忽略），而非 backend/tests/.pytest_tmp/。
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def _workspace_root() -> Path:
    """仓库根（向上找含 .git 的目录）；找不到则退回 backend/tests 上两级。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return Path(__file__).resolve().parents[2]


_WORKSPACE_TMP = _workspace_root() / ".pytest_tmp"


@pytest.fixture()
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """替代 pytest 内建 tmp_path，落在工作区根 .pytest_tmp 而非系统 %TEMP%。"""
    name = request.node.name.replace("[", "_").replace("]", "_").replace("/", "_")
    target = _WORKSPACE_TMP / name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    return target
