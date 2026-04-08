import json
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PROJECT_NAME = "serverless-notes-api"
TABLE_NAME = "serverless-notes-api-notes"
ROLE_NAME = "serverless-notes-api-role"
ROLE_POLICY_NAME = "serverless-notes-api-dynamodb"
LAMBDA_NAME = "serverless-notes-api"
API_NAME = "serverless-notes-api"
STAGE_NAME = "dev"

ROOT = Path(__file__).parent
ZIP_PATH = ROOT / "lambda_package.zip"


def _build_lambda_zip():
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w") as zipf:
        zipf.write(ROOT / "lambda_function.py", "lambda_function.py")


def _ensure_table(dynamodb):
    existing_tables = dynamodb.meta.client.list_tables()["TableNames"]
    if TABLE_NAME in existing_tables:
        return

    dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "note_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "note_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    waiter = dynamodb.meta.client.get_waiter("table_exists")
    waiter.wait(TableName=TABLE_NAME)


def _ensure_role(iam, table_arn):
    try:
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise

        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )["Role"]

    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=ROLE_POLICY_NAME,
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"],
                        "Resource": table_arn,
                    }
                ],
            }
        ),
    )

    for _ in range(10):
        try:
            iam.get_role(RoleName=ROLE_NAME)
            return role["Arn"]
        except ClientError:
            time.sleep(2)

    return role["Arn"]


def _ensure_lambda(lambda_client, role_arn):
    _build_lambda_zip()

    with ZIP_PATH.open("rb") as handle:
        zip_bytes = handle.read()

    try:
        lambda_client.get_function(FunctionName=LAMBDA_NAME)
        lambda_client.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
        lambda_client.update_function_configuration(
            FunctionName=LAMBDA_NAME,
            Runtime="python3.12",
            Handler="lambda_function.handler",
            Role=role_arn,
            Environment={"Variables": {"TABLE_NAME": TABLE_NAME}},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

        for attempt in range(6):
            try:
                lambda_client.create_function(
                    FunctionName=LAMBDA_NAME,
                    Runtime="python3.12",
                    Handler="lambda_function.handler",
                    Role=role_arn,
                    Code={"ZipFile": zip_bytes},
                    Timeout=10,
                    Environment={"Variables": {"TABLE_NAME": TABLE_NAME}},
                )
                return
            except ClientError as create_exc:
                message = create_exc.response["Error"].get("Message", "")
                if "cannot be assumed" not in message or attempt == 5:
                    raise
                time.sleep(5)


def _get_or_create_api(apigw):
    apis = apigw.get_rest_apis(limit=500)["items"]
    for api in apis:
        if api["name"] == API_NAME:
            return api["id"]

    return apigw.create_rest_api(name=API_NAME)["id"]


def _get_resource_by_path(resources, path):
    for resource in resources:
        if resource.get("path") == path:
            return resource["id"]
    return None


def _setup_routes(apigw, rest_api_id, lambda_arn, region, account_id):
    resources = apigw.get_resources(restApiId=rest_api_id)["items"]
    root_id = _get_resource_by_path(resources, "/")

    notes_id = _get_resource_by_path(resources, "/notes")
    if not notes_id:
        notes_id = apigw.create_resource(
            restApiId=rest_api_id, parentId=root_id, pathPart="notes"
        )["id"]

    note_id_id = _get_resource_by_path(resources, "/notes/{note_id}")
    if not note_id_id:
        note_id_id = apigw.create_resource(
            restApiId=rest_api_id, parentId=notes_id, pathPart="{note_id}"
        )["id"]

    lambda_uri = (
        f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/"
        f"{lambda_arn}/invocations"
    )

    for method, resource_id in [
        ("POST", notes_id),
        ("GET", note_id_id),
        ("DELETE", note_id_id),
    ]:
        try:
            apigw.put_method(
                restApiId=rest_api_id,
                resourceId=resource_id,
                httpMethod=method,
                authorizationType="NONE",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConflictException":
                raise

        apigw.put_integration(
            restApiId=rest_api_id,
            resourceId=resource_id,
            httpMethod=method,
            type="AWS_PROXY",
            integrationHttpMethod="POST",
            uri=lambda_uri,
        )

    source_arn = f"arn:aws:execute-api:{region}:{account_id}:{rest_api_id}/*/*/*"
    statement_id = f"{PROJECT_NAME}-{rest_api_id}"
    try:
        boto3.client("lambda").add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId=statement_id,
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=source_arn,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise


def _deploy_api(apigw, rest_api_id):
    apigw.create_deployment(restApiId=rest_api_id, stageName=STAGE_NAME)


def main():
    session = boto3.session.Session()
    region = session.region_name or "us-east-1"

    dynamodb = session.resource("dynamodb")
    iam = session.client("iam")
    lambda_client = session.client("lambda")
    apigw = session.client("apigateway")
    sts = session.client("sts")

    _ensure_table(dynamodb)
    table_arn = dynamodb.Table(TABLE_NAME).table_arn

    role_arn = _ensure_role(iam, table_arn)
    _ensure_lambda(lambda_client, role_arn)

    account_id = sts.get_caller_identity()["Account"]
    rest_api_id = _get_or_create_api(apigw)
    _setup_routes(apigw, rest_api_id, lambda_client.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"], region, account_id)
    _deploy_api(apigw, rest_api_id)

    endpoint = f"https://{rest_api_id}.execute-api.{region}.amazonaws.com/{STAGE_NAME}"
    print("API deployed:", endpoint)


if __name__ == "__main__":
    main()
