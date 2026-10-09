from typing import Any

import pytest
from pydantic import ValidationError

from stacks.chunking import DEFAULT_PATH, ChunkingConfig, load_chunking


def test_repo_chunking_yaml_is_valid():
    cfg = load_chunking(DEFAULT_PATH)
    assert cfg.version >= 1
    assert cfg.to_cfn().chunking_strategy == cfg.strategy


def test_fixed_size_maps_to_cfn():
    cfg = ChunkingConfig(
        version=1, strategy="FIXED_SIZE", fixed_size={"max_tokens": 300, "overlap_percentage": 15}
    )
    prop: Any = cfg.to_cfn()
    assert prop.fixed_size_chunking_configuration.max_tokens == 300
    assert prop.fixed_size_chunking_configuration.overlap_percentage == 15


def test_hierarchical_maps_parent_then_child():
    cfg = ChunkingConfig(
        version=2,
        strategy="HIERARCHICAL",
        hierarchical={"parent_max_tokens": 1500, "child_max_tokens": 300, "overlap_tokens": 60},
    )
    prop: Any = cfg.to_cfn()
    levels = prop.hierarchical_chunking_configuration.level_configurations
    assert [lvl.max_tokens for lvl in levels] == [1500, 300]


def test_strategy_without_its_section_fails():
    with pytest.raises(ValueError, match="semantic"):
        ChunkingConfig(version=1, strategy="SEMANTIC").to_cfn()


@pytest.mark.parametrize(
    "data",
    [
        {"version": 0, "strategy": "NONE"},
        {"version": 1, "strategy": "MAGIC"},
        {"version": 1, "strategy": "NONE", "typo_key": 1},
        {
            "version": 1,
            "strategy": "FIXED_SIZE",
            "fixed_size": {"max_tokens": 0, "overlap_percentage": 10},
        },
    ],
)
def test_rejects_invalid_config(data):
    with pytest.raises(ValidationError):
        ChunkingConfig.model_validate(data)
