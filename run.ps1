# run.ps1 - launches the FastAPI backend (uv run archivenetwork, :8000) and the
# SvelteKit dev server (npm run dev, :5173) together in one console.
#
# Stop BOTH with:
#   * typing  exit  <Enter>
#
# On stop we kill each child's whole process tree (uv->python, npm->node/vite)
# and, as a backstop, free the two dev ports.

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$procs = @()
$nullFile = $null

function Get-FreePort {
    param([int]$StartingPort)
    $port = $StartingPort
    while ($true) {
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $listener.Start()
            $listener.Stop()
            return $port
        } catch {
            $port++
        }
    }
}

$backendPort = Get-FreePort -StartingPort 8000
$frontendPort = Get-FreePort -StartingPort 5173

$ports = @($backendPort, $frontendPort)

# Resolve paths to npm-cli.js and npx-cli.js to run npm/npx commands using node directly,
# avoiding cmd.exe's "Terminate batch job (Y/N)?" prompt.
$npmPath = (Get-Command npm -ErrorAction SilentlyContinue).Source
$npmCli = $null
$npxCli = $null
if ($npmPath) {
    if ($npmPath -like '*.ps1') {
        $npmCli = $npmPath -replace '\.ps1$', '\node_modules\npm\bin\npm-cli.js'
    } elseif ($npmPath -like '*.cmd') {
        $npmCli = $npmPath -replace '\.cmd$', '\node_modules\npm\bin\npm-cli.js'
    }
    if ($npmCli -and (Test-Path $npmCli)) {
        $npxCli = $npmCli -replace 'npm-cli\.js$', 'npx-cli.js'
    } else {
        $npmCli = $null
    }
}

function Stop-All {
    Write-Host "`nShutting down..." -ForegroundColor Yellow
    foreach ($p in $script:procs) {
        if ($p -and -not $p.HasExited) {
            # /T kills the whole tree, /F forces it.
            taskkill /PID $p.Id /T /F *> $null
        }
    }
    # Backstop: anything still holding a dev port (orphaned node/python).
    foreach ($port in $script:ports) {
        if ($script:npxCli) {
            node $script:npxCli --yes kill-port $port *> $null
        } else {
            npx --yes kill-port $port *> $null
        }
    }
    Write-Host "Stopped backend + frontend." -ForegroundColor Yellow
}

try {
    $env:UV_LINK_MODE = 'copy'

    # Pass the dynamically selected ports to the backend and frontend
    $env:ARCHIVENETWORK_PORT = $backendPort
    $env:VITE_API_BASE = "http://127.0.0.1:$backendPort"

    # Create an empty temp file to redirect stdin for both child processes.
    # Without it, vite (npm run dev) opens the shared console's stdin for its shortcut keys and
    # competes with our ReadKey loop for keystrokes -- so Ctrl+C gets swallowed by
    # vite and the parent never sees it (the classic "Ctrl+C does nothing" hang).
    $nullFile = New-TemporaryFile

    Write-Host "Starting backend  (uv run archivenetwork -> http://127.0.0.1:$backendPort)" -ForegroundColor Green
    $procs += Start-Process -FilePath 'uv' `
        -ArgumentList 'run', 'archivenetwork' `
        -WorkingDirectory $root -NoNewWindow -PassThru `
        -RedirectStandardInput $nullFile.FullName
 
    Write-Host "Starting frontend (npm run dev     -> http://localhost:$frontendPort)" -ForegroundColor Green
    if ($npmCli) {
        $procs += Start-Process -FilePath 'node' `
            -ArgumentList "`"$npmCli`"", 'run', 'dev', '--', '--port', "$frontendPort", '--strictPort' `
            -WorkingDirectory (Join-Path $root 'frontend') -NoNewWindow -PassThru `
            -RedirectStandardInput $nullFile.FullName
    } else {
        $procs += Start-Process -FilePath 'cmd.exe' `
            -ArgumentList '/c', "npm run dev -- --port $frontendPort --strictPort < NUL" `
            -WorkingDirectory (Join-Path $root 'frontend') -NoNewWindow -PassThru
    }

    Write-Host "`nBoth running. Type 'exit' to stop both.`n" -ForegroundColor Cyan

    # Read keys ourselves so we can catch Ctrl+C AND a typed "exit" line,
    # while also noticing if either child dies on its own.
    [Console]::TreatControlCAsInput = $true
    $line = ''
    while ($true) {
        if ($procs | Where-Object { $_.HasExited }) {
            Write-Host "`nA process exited on its own." -ForegroundColor Yellow
            break
        }
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if (($key.Modifiers -band [ConsoleModifiers]::Control) -and $key.Key -eq 'C') {
                # Ignore Ctrl+C completely to prevent termination
                continue
            }
            switch ($key.Key) {
                'Enter' {
                    if ($line.Trim() -ieq 'exit') { $line = 'EXIT'; break }
                    $line = ''; Write-Host ''
                }
                'Backspace' {
                    if ($line.Length -gt 0) {
                        $line = $line.Substring(0, $line.Length - 1)
                        Write-Host "`b `b" -NoNewline
                    }
                }
                default {
                    if ($key.KeyChar) { $line += $key.KeyChar; Write-Host $key.KeyChar -NoNewline }
                }
            }
            if ($line -eq 'EXIT') { break }
        }
        else {
            Start-Sleep -Milliseconds 150
        }
    }
}
finally {
    try { [Console]::TreatControlCAsInput = $false } catch {}
    Stop-All
    if ($nullFile -and (Test-Path $nullFile.FullName)) {
        Remove-Item $nullFile.FullName -Force -ErrorAction SilentlyContinue
    }
}
