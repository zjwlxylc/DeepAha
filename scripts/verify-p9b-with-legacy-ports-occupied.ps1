param(
    [string]$ComposeProjectName,
    [string]$ExpectedCandidate
)

$ErrorActionPreference = "Stop"
$listeners = [System.Collections.Generic.List[System.Net.Sockets.TcpListener]]::new()
try {
    foreach ($port in @(55439, 55007)) {
        $occupied = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        if ($occupied.Count -eq 0) {
            $listener = [System.Net.Sockets.TcpListener]::new(
                [System.Net.IPAddress]::Loopback,
                $port
            )
            $listener.Start()
            $listeners.Add($listener)
        }
    }
    & (Join-Path $PSScriptRoot "verify-p9b.ps1") `
        -ComposeProjectName $ComposeProjectName `
        -ExpectedCandidate $ExpectedCandidate
}
finally {
    foreach ($listener in $listeners) { $listener.Stop() }
}
