# Face-Fit Test All Script
Write-Host "Running Backend Tests..."
Set-Location "$PSScriptRoot\..\backend"
if (Test-Path "mvnw.cmd") {
    .\mvnw.cmd test
}

Write-Host "All tests executed."
