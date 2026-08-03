import json
import os
import subprocess
import sys
from pathlib import Path


CLAUDE_HELP = """Usage: claude [options] [command] [prompt]

Options:
  --model <model>  Model for the current session. Provide an alias for the latest
                   model (e.g. 'fable', 'opus', or 'sonnet') or a full name.
  --output-format <format>  Output format.
"""

AGY_LINES = "gemini-x-flash-high\ngemini-x-flash-low\nclaude-sonnet-x\n"


def write_fake_cli(bin_dir: Path, name: str, body: str) -> None:
    """A fake reviewer CLI: /bin/sh script using only absolute-path commands
    and shell builtins, so it works even when tests restrict PATH."""
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def write_fake_cli_printing(bin_dir: Path, name: str, payload: str) -> None:
    data = bin_dir / f"{name}-output.txt"
    data.write_text(payload)
    write_fake_cli(bin_dir, name, f"/bin/cat '{data}'")


def run_models_available(script_path: Path, cwd: Path, bin_dir: Path,
                         restrict_path: bool = False, timeout: str = None):
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) if restrict_path else f"{bin_dir}:{env['PATH']}"
    if timeout is not None:
        env["THREEP_MODELS_CLI_TIMEOUT"] = timeout
    return subprocess.run(
        [sys.executable, str(script_path), "models", "available"],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


def make_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    return bin_dir


def test_happy_path_filters_and_annotates(script_path, tmp_path):
    bin_dir = make_bin(tmp_path)
    write_fake_cli_printing(bin_dir, "claude", CLAUDE_HELP)
    write_fake_cli_printing(bin_dir, "agy", AGY_LINES)
    result = run_models_available(script_path, tmp_path, bin_dir)
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)

    claude = doc["reviewers"]["claude"]
    assert claude["status"] == "ok"
    assert [m["id"] for m in claude["models"]] == ["fable", "opus", "sonnet"]
    assert claude["models"][0]["displayName"] == "Fable"
    assert claude["models"][0]["reasoningLevels"] == []
    assert claude["models"][0]["warning"] is None

    agy = doc["reviewers"]["antigravity"]
    assert agy["status"] == "ok"
    ids = [m["id"] for m in agy["models"]]
    assert ids == ["gemini-x-flash-high", "gemini-x-flash-low", "claude-sonnet-x"]
    warnings = {m["id"]: m["warning"] for m in agy["models"]}
    assert warnings["gemini-x-flash-high"] is None
    assert warnings["gemini-x-flash-low"] is None
    assert "diversity" in warnings["claude-sonnet-x"]

    # Current config rides along for comparison (defaults in a fresh dir).
    assert doc["current"]["claude"]["high"]["reasoning"] == "opus"
    assert doc["current"]["antigravity"]["low"]["code"] == "gemini-3.6-flash-low"


def test_one_cli_failing_is_soft(script_path, tmp_path):
    bin_dir = make_bin(tmp_path)
    write_fake_cli_printing(bin_dir, "claude", CLAUDE_HELP)
    write_fake_cli(bin_dir, "agy", "echo boom >&2\nexit 3")
    result = run_models_available(script_path, tmp_path, bin_dir)
    assert result.returncode == 0
    doc = json.loads(result.stdout)
    assert doc["reviewers"]["claude"]["status"] == "ok"
    agy = doc["reviewers"]["antigravity"]
    assert agy["status"] == "error"
    assert "exit 3" in agy["error"]
    assert agy["models"] == []


def test_both_failing_exits_nonzero(script_path, tmp_path):
    bin_dir = make_bin(tmp_path)
    # No claude at all (restricted PATH -> command not found); agy fails.
    write_fake_cli(bin_dir, "agy", "exit 3")
    result = run_models_available(script_path, tmp_path, bin_dir,
                                  restrict_path=True)
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert doc["reviewers"]["claude"]["status"] == "error"
    assert "not found" in doc["reviewers"]["claude"]["error"]
    assert doc["reviewers"]["antigravity"]["status"] == "error"


def test_hung_cli_times_out(script_path, tmp_path):
    bin_dir = make_bin(tmp_path)
    write_fake_cli(bin_dir, "claude", "/bin/sleep 20")
    write_fake_cli_printing(bin_dir, "agy", AGY_LINES)
    result = run_models_available(script_path, tmp_path, bin_dir, timeout="1")
    assert result.returncode == 0
    doc = json.loads(result.stdout)
    claude = doc["reviewers"]["claude"]
    assert claude["status"] == "error"
    assert "timed out" in claude["error"]
    assert doc["reviewers"]["antigravity"]["status"] == "ok"


def test_unparseable_claude_output_is_soft(script_path, tmp_path):
    bin_dir = make_bin(tmp_path)
    write_fake_cli_printing(bin_dir, "claude", "this is not json")
    write_fake_cli_printing(bin_dir, "agy", AGY_LINES)
    result = run_models_available(script_path, tmp_path, bin_dir)
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    doc = json.loads(result.stdout)
    claude = doc["reviewers"]["claude"]
    assert claude["status"] == "error"
    assert "unparseable" in claude["error"]
