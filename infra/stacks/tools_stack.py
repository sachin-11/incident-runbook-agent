"""Tool Lambdas (one per tool), the restart audit table and the approval signing key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from tools.registry import TOOLS


def _pascal(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


class ToolsStack(Stack):
    def __init__(  # noqa: PLR0913 (construct signature + required config)
        self,
        scope: Construct,
        construct_id: str,
        *,
        code_dir: Path,
        stage: str,
        tool_timeout_s: float,
        sim_scenario_id: str,
        log_level: str = "INFO",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        prod = stage == "prod"
        removal = RemovalPolicy.RETAIN if prod else RemovalPolicy.DESTROY

        # Append-only audit trail for risky tools (see tools/common/audit.py).
        audit_table = dynamodb.Table(
            self,
            "AuditTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=prod
            ),
            removal_policy=removal,
        )

        # HMAC key for approval tokens. Only restart_service (verify) and humans (issue) read it.
        signing_key = secretsmanager.Secret(
            self,
            "ApprovalSigningKey",
            description="HMAC key for restart_service approval tokens.",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=64, exclude_punctuation=True
            ),
            removal_policy=removal,
        )

        code = lambda_.Code.from_asset(str(code_dir))
        self.functions: dict[str, lambda_.Function] = {}
        for tool in TOOLS:
            cid = _pascal(tool.name)
            log_group = logs.LogGroup(
                self,
                f"{cid}Logs",
                retention=logs.RetentionDays.TWO_WEEKS,
                removal_policy=RemovalPolicy.DESTROY,
            )
            # Own role per function: may only write to its own log group (no wildcard
            # logs:CreateLogGroup from the AWS managed basic execution policy).
            role = iam.Role(
                self,
                f"{cid}Role",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                description=f"Least-privilege role for the {tool.name} tool",
            )
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[log_group.log_group_arn, f"{log_group.log_group_arn}:*"],
                )
            )
            env = {
                "LOG_LEVEL": log_level,
                "STAGE": stage,
                "SIM_SCENARIO_ID": sim_scenario_id,
            }
            if tool.risky:
                env["AUDIT_TABLE"] = audit_table.table_name
                env["APPROVAL_SECRET_ARN"] = signing_key.secret_arn
                # Append-only: no UpdateItem/DeleteItem. Transact puts need PutItem.
                audit_table.grant(role, "dynamodb:PutItem", "dynamodb:GetItem")
                signing_key.grant_read(role)

            fn = lambda_.Function(
                self,
                cid,
                function_name=f"ira-{stage}-{tool.name.replace('_', '-')}",
                description=tool.description[:256],
                runtime=lambda_.Runtime.PYTHON_3_12,
                architecture=lambda_.Architecture.ARM_64,
                handler=tool.handler_path,
                code=code,
                role=role,
                memory_size=256,
                timeout=Duration.seconds(max(1, round(tool_timeout_s))),
                log_group=log_group,
                environment=env,
            )
            fn.node.add_dependency(role)
            self.functions[tool.name] = fn
            CfnOutput(self, f"{cid}FunctionName", value=fn.function_name)

        self.audit_table = audit_table
        self.signing_key = signing_key
        CfnOutput(self, "AuditTableName", value=audit_table.table_name)
        CfnOutput(self, "ApprovalSecretArn", value=signing_key.secret_arn)
