import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("TABLE_NAME", "serverless-notes-api-notes")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _parse_body(event):
    raw_body = event.get("body")
    if not raw_body:
        return None, "Request body is required."
    try:
        return json.loads(raw_body), None
    except json.JSONDecodeError:
        return None, "Request body must be valid JSON."


def handler(event, context):
    method = event.get("httpMethod")
    path = event.get("path", "")

    if method == "POST" and path.endswith("/notes"):
        body, error = _parse_body(event)
        if error:
            return _response(400, {"message": error})

        content = body.get("content")
        if not content:
            return _response(400, {"message": "content is required."})

        note_id = str(uuid.uuid4())
        item = {
            "note_id": note_id,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            table.put_item(Item=item)
        except ClientError:
            return _response(500, {"message": "Could not create note."})

        return _response(201, item)

    if method in ("GET", "DELETE") and "/notes/" in path:
        note_id = (event.get("pathParameters") or {}).get("note_id")
        if not note_id:
            return _response(400, {"message": "note_id is required."})

        if method == "GET":
            try:
                result = table.get_item(Key={"note_id": note_id})
            except ClientError:
                return _response(500, {"message": "Could not fetch note."})

            item = result.get("Item")
            if not item:
                return _response(404, {"message": "Note not found."})

            return _response(200, item)

        try:
            table.delete_item(Key={"note_id": note_id})
        except ClientError:
            return _response(500, {"message": "Could not delete note."})

        return _response(200, {"message": "Note deleted."})

    return _response(404, {"message": "Route not found."})
