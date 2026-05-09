$repoRoot = "D:\code2026\sentinel-ai"
$workerDir = Join-Path $repoRoot "worker"
$envFile = Join-Path $repoRoot ".env.local"
$python = Join-Path $workerDir ".venv\Scripts\python.exe"
$logFile = Join-Path $workerDir "worker.log"

Set-Location $workerDir

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n========== $ts worker starting =========="

# Use cmd-level redirection to bypass PowerShell 5.1's NativeCommandError wrapping
# of uvicorn's stderr (which would otherwise crash the process).
$cmdLine = "`"$python`" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file `"$envFile`" >> `"$logFile`" 2>&1"
& cmd.exe /c $cmdLine
