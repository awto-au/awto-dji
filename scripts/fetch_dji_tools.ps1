<#
Download the DJI Phantom 3 Professional PC tool, firmware and docs into source/.

Uses awto-playwrong (headed Chrome, Cloudflare-cleared session) for the transfers.
Files land in <repo>/source/ (untracked: do not commit the binaries).
Source pages:
  https://www.dji.com/au/downloads/softwares/assistant-dji-2-for-phantom
  https://www.dji.com/au/downloads/products/phantom-3-pro

Usage: pwsh scripts/fetch_dji_tools.ps1 [-Playwrong C:\git\awto-playwrong]
#>
param(
    [string]$Playwrong = 'C:\git\awto-playwrong',
    [string]$Out = (Join-Path $PSScriptRoot '..\source')
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$py = Join-Path $Playwrong '.venv\Scripts\python.exe'

$files = @(
    @('https://dl.djicdn.com/downloads/dji_assistant/20200721/DJI+Assistant+2+For+Phantom+2.0.10.exe', 'DJI_Assistant_2_For_Phantom_2.0.10.exe'),
    @('https://dl.djicdn.com/downloads/dji_assistant/20200721/DJI+Assistant+2+For+Phantom+2.0.10.zip', 'DJI_Assistant_2_For_Phantom_2.0.10.zip'),
    @('https://dl.djicdn.com/downloads/dji_assistant/20200721/DJI+Assistant+2+For+Phantom+Release+Notes(2.0.10).pdf', 'Assistant_2_Release_Notes_2.0.10.pdf'),
    @('https://dl.djicdn.com/downloads/phantom_3/20170706/P3P_FW_V01.11.0020.bin.zip', 'P3P_FW_V01.11.0020.bin.zip'),
    @('https://dl.djicdn.com/downloads/phantom_3/User%20Manual/Phantom_3_Professional_User_Manual_v1.8_en.pdf', 'Phantom_3_Professional_User_Manual_v1.8.pdf'),
    @('https://dl.djicdn.com/downloads/phantom_3/20170706/Phantom+3+Professional+Release+Notes_.pdf', 'P3P_Release_Notes_20170706.pdf'),
    @('https://dl.djicdn.com/downloads/phantom_3/en/Firmware_Update_Guide_en_v1.4.pdf', 'P3_Firmware_Update_Guide_v1.4.pdf')
)

Push-Location $Playwrong
try {
    foreach ($f in $files) {
        $dest = Join-Path $Out $f[1]
        if (Test-Path $dest) { Write-Host "have  $($f[1])"; continue }
        Write-Host "fetch $($f[1])"
        # --pdf downloads any file through the cleared session; its "not a PDF" /
        # "pdftotext missing" warnings are expected for non-PDFs and can be ignored.
        & $py -m engine.cli --pdf $f[0] -o $dest 2>&1 | Out-Null
    }
} finally { Pop-Location }

Get-ChildItem $Out -File | ForEach-Object {
    '{0}  {1,12:N0}  {2}' -f (Get-FileHash $_.FullName).Hash.Substring(0, 16), $_.Length, $_.Name
}
Get-ChildItem $Out -Filter *.exe | ForEach-Object {
    $s = Get-AuthenticodeSignature $_.FullName
    "{0}: {1} ({2})" -f $_.Name, $s.Status, $s.SignerCertificate.Subject
}
