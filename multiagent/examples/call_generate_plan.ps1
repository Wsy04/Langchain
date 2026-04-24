$baseUrl = if ($env:APP_BASE_URL) { $env:APP_BASE_URL } else { "http://127.0.0.1:18010" }
$requestPath = Join-Path $PSScriptRoot "demo_request.json"
$body = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8

$response = Invoke-RestMethod `
    -Uri "$baseUrl/api/v1/plan/generate" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $body

$response | ConvertTo-Json -Depth 20
