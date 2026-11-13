# Gecici admin parolasi icin hash uretir. Parola ekrana ve gecmise yazilmaz; ciktiyi .env ADMIN_PASSWORD_HASH satirina koyun.
Set-Location $PSScriptRoot
& ".\.venv\Scripts\agentask.exe" --hash-admin-password
exit $LASTEXITCODE
