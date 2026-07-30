# Face-Fit Local Run Script
Write-Host "Starting Face-Fit Local Services..."

Set-Location "$PSScriptRoot\..\backend"
if (Test-Path "mvnw.cmd") {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\mvnw.cmd spring-boot:run"
}

Write-Host "Backend service started in background process."
