param([string]$ProjectDir = "$env:USERPROFILE\eda\ThermoBridge")
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir 'rtl\thermobridge_top.sv'))) {
    throw "Existing ThermoBridge checkout not found at $ProjectDir. No clone was attempted."
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir 'scripts\container.py'))) {
    throw 'Existing scripts/container.py missing: refusing to recreate or alter Docker tools.'
}
$docker = Get-Command docker -ErrorAction Stop
$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue
if ($python) { $pythonExe = $python.Source; $prefix=@() }
elseif ($py) { $pythonExe = $py.Source; $prefix=@('-3') }
else { throw 'A working Windows Python 3 executable is required for existing scripts/container.py.' }
Push-Location -LiteralPath $ProjectDir
try {
    $running = & $docker.Source inspect -f '{{.State.Running}}' iic-osic-tools
    if (($LASTEXITCODE -ne 0) -or (($running | Out-String).Trim() -ne 'true')) { throw 'The existing iic-osic-tools container is not running.' }
    Write-Host 'Syncing existing source and additive release files. No image download.'
    & $pythonExe @prefix scripts/container.py sync rtl tb tests src configs scripts flow release requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Sync failed; original files were not deleted.' }
    Write-Host 'Running thermal validation, RTL tests, experiments, plots, and real SKY130A GDS flow.'
    & $pythonExe @prefix scripts/container.py run python3 -m release.runner
    $runExit = $LASTEXITCODE
    Write-Host "Container runner exit code: $runExit (ZIP will still contain partial evidence if nonzero)."
    & $pythonExe @prefix scripts/container.py fetch release_out
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Could not retrieve release_out, check docker logs.' }
    # If physics model had to regenerate raw evidence, retrieve it as well.
    try {
        & $pythonExe @prefix scripts/container.py fetch outputs/physics
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Raw physics exports could not be refreshed.' }
    } catch { Write-Warning 'Could not fetch physics outputs; retaining any existing local copy.' }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $stage = Join-Path $env:TEMP "ThermoBridge_export_$stamp"
    $zip = Join-Path $ProjectDir "ThermoBridge_complete_$stamp.zip"
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $paths=@('rtl','src','tb','tests','configs','scripts','release','flow','docs',
             'release_out','reports','results','analog','README.md','AGENTS.md','START_HERE.md','requirements.txt',
             '.gitignore')
    foreach ($relative in $paths) {
        $src=Join-Path $ProjectDir $relative
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination $stage -Recurse -Force
        }
    }
    $physics=Join-Path $ProjectDir 'outputs\physics'
    if (Test-Path -LiteralPath $physics) {
        New-Item -ItemType Directory -Force -Path (Join-Path $stage 'outputs') | Out-Null
        Copy-Item -LiteralPath $physics -Destination (Join-Path $stage 'outputs') -Recurse -Force
    }
    Get-ChildItem -LiteralPath $stage -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('__pycache__','.pytest_cache','.venv') } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal -Force
    Remove-Item -LiteralPath $stage -Recurse -Force
    Write-Host "FINAL ZIP: $zip"
    Write-Host "RUN STATUS: $(Join-Path $ProjectDir 'release_out\RELEASE_STATUS.md')"
    if ($runExit -ne 0) {
        Write-Warning 'Some gates failed or are incomplete. Results were packaged honestly; consult the manifest/logs.'
    }
} finally { Pop-Location }
