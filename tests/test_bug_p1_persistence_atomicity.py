import shutil

import yaml
import pytest

import 运行程序.interactive_backtest_app as app


CONFIG = "1_策略配置"
FORMAL_FILES = (
    "参数配置.yaml",
    "模块开关配置.yaml",
    "核心模块配置.yaml",
)


def _formal_bytes(config_dir):
    return {
        name: (config_dir / name).read_bytes()
        for name in FORMAL_FILES
    }


def _prepare_config(tmp_path):
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG, config_dir)
    return config_dir


def test_formal_timing_save_failure_on_second_write_is_atomic(monkeypatch, tmp_path):
    config_dir = _prepare_config(tmp_path)
    before = _formal_bytes(config_dir)
    real_write_yaml = app.写入_yaml
    calls = []

    def fail_on_second_write(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("injected second-write failure")
        return real_write_yaml(path, data)

    monkeypatch.setattr(app, "正式配置目录", str(config_dir))
    monkeypatch.setattr(app, "写入_yaml", fail_on_second_write)

    with pytest.raises(OSError, match="injected second-write failure"):
        app.保存入场时序到正式配置({
            "entry_timing": "same_bar_entry",
            "grid_entry_timing": "precomputed_stop_entry",
        })

    assert len(calls) == 2
    assert _formal_bytes(config_dir) == before
    assert list(config_dir.glob("*.tmp")) == []


def test_formal_timing_save_success_updates_all_three_files(tmp_path, monkeypatch):
    config_dir = _prepare_config(tmp_path)
    before = _formal_bytes(config_dir)
    monkeypatch.setattr(app, "正式配置目录", str(config_dir))

    app.保存入场时序到正式配置({
        "entry_timing": "same_bar_entry",
        "grid_entry_timing": "precomputed_stop_entry",
    })

    after = _formal_bytes(config_dir)
    assert after != before
    parameters = yaml.safe_load((config_dir / "参数配置.yaml").read_text(encoding="utf-8"))
    switches = yaml.safe_load((config_dir / "模块开关配置.yaml").read_text(encoding="utf-8"))
    core = yaml.safe_load((config_dir / "核心模块配置.yaml").read_text(encoding="utf-8"))
    assert parameters["买入参数"]["买入时机模式"] == "same_bar_entry"
    assert switches["模块类别"]["核心模块"]["same_bar_entry"]["启用"] is True
    assert core["核心模块"]["本根形成立即成交"]["启用"] is True
    assert list(config_dir.glob("*.tmp")) == []
