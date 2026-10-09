#!/usr/bin/env bash
# Destroy the KnowledgeBase stack (docs bucket, vector bucket + index, KB, data source, role).
#
#   scripts/teardown.sh [stage]        # stage defaults to $IRA_STAGE, then dev
#
# Only this stack is destroyed (--exclusively). prod needs CONFIRM_PROD=yes.
set -euo pipefail

STAGE="${1:-${IRA_STAGE:-dev}}"
STACK="Ira-${STAGE}-KnowledgeBase"
REGION="${IRA_AWS_REGION:-$(aws configure get region)}"

if [[ "$STAGE" == "prod" && "${CONFIRM_PROD:-}" != "yes" ]]; then
  echo "Refusing to destroy $STACK without CONFIRM_PROD=yes" >&2
  exit 1
fi

cd "$(dirname "$0")/../infra"
echo "Destroying $STACK in $REGION ..."
npx --yes aws-cdk@2 destroy "$STACK" --exclusively --force -c stage="$STAGE"

# Verify nothing billable is left behind.
if aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" >/dev/null 2>&1; then
  echo "WARNING: $STACK still exists; check the CloudFormation console." >&2
  exit 1
fi
echo "Remaining S3 vector buckets in $REGION:"
aws s3vectors list-vector-buckets --region "$REGION" --query "vectorBuckets[].vectorBucketName" --output text || true
echo "Done."
