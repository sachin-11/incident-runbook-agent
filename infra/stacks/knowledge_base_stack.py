"""Bedrock Knowledge Base over the runbooks and postmortems in kb/docs/, stored in S3 Vectors."""

from __future__ import annotations

from typing import Any

from aws_cdk import Aws, CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

from stacks.chunking import ChunkingConfig

# S3 prefix the data source reads; scripts/ingest_kb.py uploads kb/docs/ here.
DOCS_PREFIX = "docs/"

# Bedrock stores the chunk text and its own metadata under these keys. They are large, so they
# must be non-filterable: S3 Vectors caps filterable metadata at 2 KB per vector.
NON_FILTERABLE_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]


class KnowledgeBaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        embedding_model_id: str,
        embedding_dimensions: int,
        chunking: ChunkingConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dev-friendly lifecycle: the docs are rebuilt from git, so nothing here is precious.
        docs_bucket = s3.Bucket(
            self,
            "DocsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucket")
        index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            data_type="float32",
            dimension=embedding_dimensions,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=NON_FILTERABLE_KEYS
            ),
        )

        embedding_model_arn = self.format_arn(
            service="bedrock",
            account="",
            resource="foundation-model",
            resource_name=embedding_model_id,
        )

        role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {
                        "aws:SourceArn": self.format_arn(
                            service="bedrock", resource="knowledge-base", resource_name="*"
                        )
                    },
                },
            ),
        )
        role.add_to_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn])
        )
        docs_bucket.grant_read(role)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3vectors:GetIndex",
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:ListVectors",
                ],
                resources=[index.attr_index_arn],
            )
        )

        kb = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"{self.stack_name}-runbooks",
            description="Runbooks and postmortems for the incident runbook agent.",
            role_arn=role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn,
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=embedding_dimensions, embedding_data_type="FLOAT32"
                        )
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=index.attr_index_arn
                ),
            ),
        )
        # Bedrock validates the role's permissions at create time, so the policy must exist first.
        kb.node.add_dependency(role)

        # The version is part of the name: a chunking change replaces the data source cleanly.
        data_source = bedrock.CfnDataSource(
            self,
            "DocsDataSource",
            knowledge_base_id=kb.attr_knowledge_base_id,
            name=f"docs-chunking-v{chunking.version}",
            data_deletion_policy="DELETE",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=docs_bucket.bucket_arn, inclusion_prefixes=[DOCS_PREFIX]
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=chunking.to_cfn()
            ),
        )

        self.knowledge_base_id = kb.attr_knowledge_base_id
        self.knowledge_base_arn = kb.attr_knowledge_base_arn

        CfnOutput(self, "KnowledgeBaseId", value=kb.attr_knowledge_base_id)
        CfnOutput(self, "DataSourceId", value=data_source.attr_data_source_id)
        CfnOutput(self, "DocsBucketName", value=docs_bucket.bucket_name)
        CfnOutput(self, "DocsPrefix", value=DOCS_PREFIX)
        CfnOutput(self, "VectorIndexArn", value=index.attr_index_arn)
        CfnOutput(self, "EmbeddingModelId", value=embedding_model_id)
        CfnOutput(self, "ChunkingVersion", value=str(chunking.version))
