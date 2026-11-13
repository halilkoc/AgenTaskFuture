# AgenTask sirket testi kurulumu (Windows PowerShell). Internet varsaymaz; paket icindeki wheels klasorunu kullanir.
# Calistirma: powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) { $exe = "py"; $pre = @("-3.12") } else { $exe = "python"; $pre = @() }
$version = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($version -ne "3.12") { throw "Python 3.12 gerekli (bulunan: $version). Kurum yazilim merkezinden kurun." }

if (-not (Test-Path ".venv")) { & $exe @pre -m venv .venv }
$pip = ".\.venv\Scripts\python.exe"
& $pip -m pip install --no-index --find-links wheels --require-hashes -r requirements-windows.lock
if ($LASTEXITCODE -ne 0) { throw "Bagimlilik kurulumu basarisiz (cikis $LASTEXITCODE)." }
$wheel = Get-ChildItem "app\agentask-*.whl" | Select-Object -First 1
& $pip -m pip install --no-index --no-deps $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "Uygulama kurulumu basarisiz (cikis $LASTEXITCODE)." }

if (-not (Test-Path ".env")) {
    $key = & $pip -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content ".env.company.example" -Encoding UTF8) -replace "^SESSION_SIGNING_KEY=.*", "SESSION_SIGNING_KEY=$key" | Set-Content ".env" -Encoding UTF8
    Write-Host ".env olusturuldu. Sonra: admin hash uretin, hedef adresleri ve MongoDB ayarlarini girin (INSTALL.md)."
} else {
    Write-Host ".env zaten var; degistirilmedi."
}
Write-Host "Kurulum tamam. Tarayici adimi icin INSTALL.md bolum 3'e bakin."
