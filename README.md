# serverless-notes-api

Small serverless API for creating, fetching, and deleting notes using API Gateway, Lambda, and DynamoDB.

## Architecture
- API Gateway REST API
- Lambda (Python)
- DynamoDB table

## Setup
1. Install dependencies:
   - `python -m pip install -r requirements.txt`
2. Configure AWS credentials (e.g. `aws configure`).
3. Deploy:
   - `python deploy.py`

The deploy script prints the API base URL.

## Example requests
Replace `API_URL` with the base URL from deploy (for example: `https://abc123.execute-api.us-east-1.amazonaws.com/dev`).

- Create a note:
  - `curl -X POST "$API_URL/notes" -H "Content-Type: application/json" -d "{\"content\":\"Buy milk\"}"`
- Get a note:
  - `curl "$API_URL/notes/NOTE_ID"`
- Delete a note:
  - `curl -X DELETE "$API_URL/notes/NOTE_ID"`

## Cleanup
- `python cleanup.py`
