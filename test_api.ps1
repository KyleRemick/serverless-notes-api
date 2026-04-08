$apiUrl = $args[0]
if (-not $apiUrl) {
    Write-Host "Usage: .\test_api.ps1 <API_URL>"
    exit 1
}

$body = @{ content = "Test note from script" } | ConvertTo-Json
$create = Invoke-RestMethod -Method Post -Uri "$apiUrl/notes" -Body $body -ContentType "application/json"
Write-Host ("Created: " + ($create | ConvertTo-Json -Compress))

$noteId = $create.note_id
if (-not $noteId) {
    Write-Host "No note_id returned."
    exit 1
}

$get = Invoke-RestMethod -Method Get -Uri "$apiUrl/notes/$noteId"
Write-Host ("Fetched: " + ($get | ConvertTo-Json -Compress))

$delete = Invoke-RestMethod -Method Delete -Uri "$apiUrl/notes/$noteId"
Write-Host ("Deleted: " + ($delete | ConvertTo-Json -Compress))
