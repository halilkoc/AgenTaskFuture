# Baslangic kontrolu: ayarlar, tarayici, hedef, MongoDB, model/S3 ayari. Sir yazdirmaz.
Set-Location $PSScriptRoot
& ".\.venv\Scripts\agentask.exe" --env-file .env --doctor
exit $LASTEXITCODE
