# Uygulamayi baslatir (Ctrl+C ile durur). Once ayarlar ve baglantilar kontrol edilir; loglar bu konsola yazilir.
Set-Location $PSScriptRoot
& ".\.venv\Scripts\agentask.exe" --env-file .env --doctor
if ($LASTEXITCODE -ne 0) { Write-Host "Kontrol basarisiz; uygulama baslatilmadi."; exit $LASTEXITCODE }
& ".\.venv\Scripts\agentask.exe" --env-file .env
exit $LASTEXITCODE
