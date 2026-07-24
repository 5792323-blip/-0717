import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


neutral = importlib.import_module("8_过滤因子.rsi_neutral_zone_filter")
alignment = importlib.import_module("8_过滤因子.rsi_band_alignment_filter")


def test_neutral_zone_filter_blocks_middle_band():
    result = neutral.检查(
        "RSI上穿30",
        {"RSI_14": 50},
        {},
        {"中性下限": 42, "中性上限": 58},
    )
    assert result["通过"] is False
    assert "中性区" in result["原因"]


def test_alignment_filter_allows_low_signal_in_low_band():
    result = alignment.检查(
        "RSI上穿30",
        {"RSI_14": 35},
        {},
        {"中性下限": 42, "中性上限": 58},
    )
    assert result["通过"] is True


def test_alignment_filter_blocks_low_signal_in_middle_band():
    result = alignment.检查(
        "RSI上穿30",
        {"RSI_14": 50},
        {},
        {"中性下限": 42, "中性上限": 58},
    )
    assert result["通过"] is False
    assert "中性区" in result["原因"]
