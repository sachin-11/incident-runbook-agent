"""Load and validate kb/chunking.yaml and turn it into the CFN chunking property."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from aws_cdk import aws_bedrock as bedrock
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "kb" / "chunking.yaml"

_Cfn = bedrock.CfnDataSource


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixedSize(_Strict):
    max_tokens: int = Field(gt=0, le=8192)
    overlap_percentage: int = Field(ge=1, le=99)


class Hierarchical(_Strict):
    parent_max_tokens: int = Field(gt=0, le=8192)
    child_max_tokens: int = Field(gt=0, le=8192)
    overlap_tokens: int = Field(gt=0)


class Semantic(_Strict):
    max_tokens: int = Field(gt=0, le=8192)
    buffer_size: int = Field(ge=0, le=1)
    breakpoint_percentile_threshold: int = Field(ge=50, le=99)


class ChunkingConfig(_Strict):
    version: int = Field(ge=1)
    strategy: Literal["FIXED_SIZE", "HIERARCHICAL", "SEMANTIC", "NONE"]
    fixed_size: FixedSize | None = None
    hierarchical: Hierarchical | None = None
    semantic: Semantic | None = None

    def to_cfn(self) -> _Cfn.ChunkingConfigurationProperty:
        match self.strategy:
            case "FIXED_SIZE":
                fs = _require(self.fixed_size, "fixed_size")
                return _Cfn.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=_Cfn.FixedSizeChunkingConfigurationProperty(
                        max_tokens=fs.max_tokens, overlap_percentage=fs.overlap_percentage
                    ),
                )
            case "HIERARCHICAL":
                h = _require(self.hierarchical, "hierarchical")
                return _Cfn.ChunkingConfigurationProperty(
                    chunking_strategy="HIERARCHICAL",
                    hierarchical_chunking_configuration=_Cfn.HierarchicalChunkingConfigurationProperty(
                        level_configurations=[
                            _Cfn.HierarchicalChunkingLevelConfigurationProperty(
                                max_tokens=h.parent_max_tokens
                            ),
                            _Cfn.HierarchicalChunkingLevelConfigurationProperty(
                                max_tokens=h.child_max_tokens
                            ),
                        ],
                        overlap_tokens=h.overlap_tokens,
                    ),
                )
            case "SEMANTIC":
                s = _require(self.semantic, "semantic")
                return _Cfn.ChunkingConfigurationProperty(
                    chunking_strategy="SEMANTIC",
                    semantic_chunking_configuration=_Cfn.SemanticChunkingConfigurationProperty(
                        max_tokens=s.max_tokens,
                        buffer_size=s.buffer_size,
                        breakpoint_percentile_threshold=s.breakpoint_percentile_threshold,
                    ),
                )
            case "NONE":
                return _Cfn.ChunkingConfigurationProperty(chunking_strategy="NONE")


def _require[T](section: T | None, name: str) -> T:
    if section is None:
        raise ValueError(f"chunking strategy needs a `{name}` section in chunking.yaml")
    return section


def load_chunking(path: Path = DEFAULT_PATH) -> ChunkingConfig:
    return ChunkingConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
