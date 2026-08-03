# Face-Fit Setup Script
Write-Host "Setting up Face-Fit development environment..."

# Check .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host "Environment setup complete."
