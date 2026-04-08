import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "serverless-notes-api-notes"
ROLE_NAME = "serverless-notes-api-role"
ROLE_POLICY_NAME = "serverless-notes-api-dynamodb"
LAMBDA_NAME = "serverless-notes-api"
API_NAME = "serverless-notes-api"


def _delete_api(apigw):
    apis = apigw.get_rest_apis(limit=500)["items"]
    for api in apis:
        if api["name"] == API_NAME:
            apigw.delete_rest_api(restApiId=api["id"])
            return True
    return False


def _delete_lambda(lambda_client):
    try:
        lambda_client.delete_function(FunctionName=LAMBDA_NAME)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    return False


def _delete_role(iam):
    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=ROLE_POLICY_NAME)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise

    try:
        iam.detach_role_policy(
            RoleName=ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise

    try:
        iam.delete_role(RoleName=ROLE_NAME)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
    return False


def _delete_table(dynamodb):
    try:
        dynamodb.meta.client.delete_table(TableName=TABLE_NAME)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    return False


def main():
    session = boto3.session.Session()
    apigw = session.client("apigateway")
    lambda_client = session.client("lambda")
    iam = session.client("iam")
    dynamodb = session.resource("dynamodb")

    deleted_api = _delete_api(apigw)
    deleted_lambda = _delete_lambda(lambda_client)
    deleted_role = _delete_role(iam)
    deleted_table = _delete_table(dynamodb)

    print("Deleted API:", deleted_api)
    print("Deleted Lambda:", deleted_lambda)
    print("Deleted IAM role:", deleted_role)
    print("Deleted table:", deleted_table)


if __name__ == "__main__":
    main()
