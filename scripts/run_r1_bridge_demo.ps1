$ErrorActionPreference = 'Stop'

$profileLine = netsh wlan show interfaces |
    Select-String -Pattern '^\s*Profile\s*:\s*(.+)$' |
    Select-Object -First 1
if (-not $profileLine) {
    throw 'No connected Wi-Fi profile found to restore after the RX bridge demo.'
}
$previousProfile = $profileLine.Matches[0].Groups[1].Value.Trim()
$eventIdPath = Join-Path $env:TEMP 'safesense-r1-event-id.txt'
Set-Content -LiteralPath $eventIdPath -Value ''

$health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 5
if ($health.status -ne 'ok') {
    throw 'Start the local FastAPI server before forwarding RX records.'
}

try {
    netsh wlan disconnect interface='Wi-Fi'
    Start-Sleep -Seconds 2
    netsh wlan connect name='SafeSense-RX-V1' interface='Wi-Fi'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not connect to the RX access point.'
    }
    Start-Sleep -Seconds 7

    $pending = Invoke-RestMethod 'http://192.168.4.1/api/v1/pending' -TimeoutSec 8
    if ($null -ne $pending) {
        [pscustomobject]@{
            event_id = $pending.event_id
            rx_persisted = $pending.rx.queue_persisted
            csi_frames = $pending.rx.csi_frames
            csi_windows = $pending.rx.csi_windows
            measured_carriers = $pending.rx.csi_min_measured_subcarriers
            csi_rssi_dbm = $pending.rx.csi_rssi_dbm
        } | Format-List
    }

    $bridgeLines = & 'D:\SafeSense\.venv\Scripts\python.exe' -c @'
import time
from scripts.rx_http_bridge import forward_once

empty = 0
for _ in range(64):
    result = forward_once('http://192.168.4.1', 'http://127.0.0.1:8000')
    if result == 'empty':
        empty += 1
        if empty >= 6:
            break
    else:
        empty = 0
    time.sleep(0.5)
'@ | Tee-Object -FilePath (Join-Path $env:TEMP 'safesense-r1-bridge.log')
    if ($LASTEXITCODE -ne 0) {
        throw 'The RX-to-API bridge exited with an error.'
    }
    $bridgeLines | Select-Object -Last 10
    $lastForwarded = $bridgeLines |
        Select-String -Pattern '^forwarded event=(\S+)' |
        Select-Object -Last 1
    if ($lastForwarded) {
        $eventId = $lastForwarded.Matches[0].Groups[1].Value
        Set-Content -LiteralPath $eventIdPath -Value $eventId
        Write-Host "Latest forwarded event ID: $eventId"
    } else {
        Write-Warning 'No event was forwarded in this run. Do not use a previous event as live proof.'
    }
}
finally {
    netsh wlan connect name="$previousProfile" interface='Wi-Fi'
}
