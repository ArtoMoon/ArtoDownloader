# ArtoDownloader derleme: exe'ler + kurulum dosyası (dist\ArtoDownloader-Setup.exe)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what başarısız (kod $LASTEXITCODE)" } }

$icon = Join-Path $PSScriptRoot "assets\icon.ico"

python make_icon.py; Check "İkon"

# Eklenti paketi
Compress-Archive -Path .\extension\manifest.json, .\extension\background.js -DestinationPath .\artodownloader.zip -Force
Copy-Item .\artodownloader.zip .\artodownloader.xpi -Force

# Arayüz uygulaması (pencereli)
python -m PyInstaller --noconfirm --clean --onedir --windowed --name ArtoDownloader `
    --icon $icon --paths host --hidden-import ui --add-data "$icon;assets" `
    --distpath build\dist --workpath build\work --specpath build host\app.py
Check "ArtoDownloader derlemesi"

# Native host (konsol: stdin/stdout gerekli), küçük tutmak için tkinter yok
python -m PyInstaller --noconfirm --clean --onedir --console --name ArtoHost `
    --icon $icon --exclude-module tkinter `
    --distpath build\dist --workpath build\work --specpath build host\host.py
Check "ArtoHost derlemesi"

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 bulunamadı: winget install JRSoftware.InnoSetup" }
& $iscc setup.iss
Check "Kurulum paketi"
Write-Host "Hazır: dist\ArtoDownloader-Setup.exe"


