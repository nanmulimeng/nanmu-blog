"""CLI 入口冒烟(修复轮 I3):main() 是 systemd timer 挂载点(Task 25
前置),须可执行——配置错误退出 2;完整链(锁→config→migrate→run_once)
在替身目录走到 E2 退出 3。零真实网络零付费(上游文件不存在→E2)。"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SRC = ENGINE_ROOT / "src"


def _run_cli(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nanmu_engine.run", "--root", str(root)],
        capture_output=True, text=True, timeout=120, env=None, cwd=str(root))


@pytest.fixture
def env_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", str(SRC))
    return tmp_path


def test_cli_config_error_exits_2(env_path):
    result = _run_cli(env_path)               # 空目录:无 config.toml
    assert result.returncode == 2, result.stderr[-500:]
    assert (env_path / "run.lock").exists()   # 锁文件已建


def test_cli_full_chain_reaches_run_once_exits_3(env_path):
    shutil.copytree(ENGINE_ROOT / "config", env_path / "config")
    shutil.copytree(ENGINE_ROOT / "resources", env_path / "resources")
    result = _run_cli(env_path)               # 上游 db 不存在 → E2
    assert result.returncode == 3, result.stderr[-500:]
    assert (env_path / "engine.db").exists()  # migrate 已建表


def test_cli_info_level_events_reach_stderr(env_path):
    """Task 25 观测性:main 须配置日志 handler——INFO 级 stage=/event=
    行(收尾 run_end)要进 stderr→systemd journal,runbook 的结构化
    日志承诺依赖 INFO 可见,而不仅 WARNING+ 经 lastResort 兜底。"""
    shutil.copytree(ENGINE_ROOT / "config", env_path / "config")
    shutil.copytree(ENGINE_ROOT / "resources", env_path / "resources")
    result = _run_cli(env_path)               # 上游 db 不存在 → E2 exit 3
    assert result.returncode == 3, result.stderr[-500:]
    assert "stage=run event=run_end exit=3" in result.stderr
