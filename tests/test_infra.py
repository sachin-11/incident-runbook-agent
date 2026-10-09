import json

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template

from agent.config import KbSettings
from app import build_app
from stacks.chunking import load_chunking

SETTINGS = KbSettings(
    aws_region="us-east-1",
    embedding_model_id="amazon.titan-embed-text-v2:0",
    embedding_dimensions=1024,
)


def _app(**context: str) -> App:
    return build_app(App(context=context), SETTINGS)


def _stack_names(app: App) -> set[str]:
    return {s.stack_name for s in app.synth().stacks}


def _kb_template() -> Template:
    stack = _app().node.find_child("Ira-dev-KnowledgeBase")
    return Template.from_stack(stack)  # type: ignore[arg-type]


def test_synthesizes_four_stacks_for_default_stage():
    assert _stack_names(_app()) == {
        "Ira-dev-KnowledgeBase",
        "Ira-dev-Tools",
        "Ira-dev-Agent",
        "Ira-dev-Observability",
    }


def test_stage_from_context_prefixes_stacks():
    names = _stack_names(_app(stage="prod"))
    assert names == {f"Ira-prod-{n}" for n in ("KnowledgeBase", "Tools", "Agent", "Observability")}


def test_agent_depends_on_kb_and_tools():
    agent = _app().synth().get_stack_by_name("Ira-dev-Agent")
    assert {d.id for d in agent.dependencies} >= {"Ira-dev-KnowledgeBase", "Ira-dev-Tools"}


def test_rejects_unknown_stage():
    with pytest.raises(ValueError, match="stage must be one of"):
        _app(stage="qa")


def test_kb_uses_s3_vectors_with_configured_embedding_model():
    t = _kb_template()
    t.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    t.has_resource_properties(
        "AWS::S3Vectors::Index",
        {
            "Dimension": 1024,
            "DistanceMetric": "cosine",
            "DataType": "float32",
            "MetadataConfiguration": {
                "NonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
            },
        },
    )
    t.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {
            "StorageConfiguration": {"Type": "S3_VECTORS"},
            "KnowledgeBaseConfiguration": {
                "VectorKnowledgeBaseConfiguration": {
                    "EmbeddingModelConfiguration": {
                        "BedrockEmbeddingModelConfiguration": {"Dimensions": 1024}
                    },
                }
            },
        },
    )


def test_kb_embedding_model_arn_comes_from_settings():
    kb = next(iter(_kb_template().find_resources("AWS::Bedrock::KnowledgeBase").values()))
    arn = json.dumps(
        kb["Properties"]["KnowledgeBaseConfiguration"]["VectorKnowledgeBaseConfiguration"][
            "EmbeddingModelArn"
        ]
    )
    assert ":bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0" in arn


def test_data_source_name_and_chunking_follow_yaml():
    cfg = load_chunking()
    _kb_template().has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "Name": f"docs-chunking-v{cfg.version}",
            "DataSourceConfiguration": {
                "S3Configuration": {"InclusionPrefixes": ["docs/"]},
            },
            "VectorIngestionConfiguration": {
                "ChunkingConfiguration": {"ChunkingStrategy": cfg.strategy}
            },
        },
    )


def test_kb_role_is_scoped_to_model_and_index():
    t = _kb_template()
    t.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like({"Action": "bedrock:InvokeModel", "Effect": "Allow"}),
                        Match.object_like(
                            {
                                "Action": Match.array_with(["s3vectors:QueryVectors"]),
                                "Resource": {"Fn::GetAtt": [Match.any_value(), "IndexArn"]},
                            }
                        ),
                    ]
                )
            }
        },
    )


def test_kb_outputs_for_scripts():
    outputs = _kb_template().find_outputs("*")
    assert {"KnowledgeBaseId", "DataSourceId", "DocsBucketName", "DocsPrefix"} <= set(outputs)
