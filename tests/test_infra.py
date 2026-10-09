import json
import tempfile
from pathlib import Path

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template

from agent.config import InfraSettings
from app import build_app
from stacks.chunking import load_chunking

SETTINGS = InfraSettings(
    aws_region="us-east-1",
    embedding_model_id="amazon.titan-embed-text-v2:0",
    embedding_dimensions=1024,
)


def _make_bundle() -> Path:
    """A stand-in for build/lambda so infra tests do not need the real bundle."""
    path = Path(tempfile.mkdtemp(prefix="ira-bundle-"))
    (path / "tools").mkdir()
    (path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    return path


BUNDLE = _make_bundle()


def _app(**context: str) -> App:
    return build_app(App(context=context), SETTINGS, BUNDLE)


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


def test_missing_lambda_bundle_fails_with_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"build_lambda\.py"):
        build_app(App(), SETTINGS, tmp_path / "nope")


def _tools_template() -> Template:
    return Template.from_stack(_app().node.find_child("Ira-dev-Tools"))  # type: ignore[arg-type]


def test_tools_stack_has_one_arm64_function_per_tool():
    t = _tools_template()
    t.resource_count_is("AWS::Lambda::Function", 5)
    for name in ("get-logs", "get-service-health", "get-recent-deploys", "get-metrics"):
        t.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": f"ira-dev-{name}",
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
                "Timeout": 10,
                "Environment": {
                    "Variables": Match.not_(Match.object_like({"AUDIT_TABLE": Match.any_value()}))
                },
            },
        )
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "ira-dev-restart-service",
            "Handler": "tools.restart_service.handler.handler",
            "Environment": {
                "Variables": Match.object_like(
                    {"AUDIT_TABLE": Match.any_value(), "APPROVAL_SECRET_ARN": Match.any_value()}
                )
            },
        },
    )


def test_tools_have_log_retention_and_audit_table():
    t = _tools_template()
    t.resource_count_is("AWS::Logs::LogGroup", 5)
    t.all_resources_properties("AWS::Logs::LogGroup", {"RetentionInDays": 14})
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_only_restart_service_can_touch_audit_table_and_secret():
    t = _tools_template()
    policies = t.find_resources("AWS::IAM::Policy")
    dynamo = [p for p in policies.values() if "dynamodb" in json.dumps(p)]
    secrets = [p for p in policies.values() if "secretsmanager" in json.dumps(p)]
    assert len(dynamo) == len(secrets) == 1
    assert dynamo[0] is secrets[0]
    statements = json.dumps(dynamo[0])
    for forbidden in ("dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Scan", "dynamodb:*"):
        assert forbidden not in statements
    # No role gets the wildcard managed basic-execution policy.
    for role in t.find_resources("AWS::IAM::Role").values():
        assert "ManagedPolicyArns" not in role["Properties"]


def test_every_log_policy_is_scoped_to_its_own_log_group():
    for policy in _tools_template().find_resources("AWS::IAM::Policy").values():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            if "logs:PutLogEvents" in stmt["Action"]:
                assert "*" not in json.dumps(stmt["Resource"]).replace(":*", "")
