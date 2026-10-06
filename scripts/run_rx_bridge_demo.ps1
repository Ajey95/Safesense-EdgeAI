param(
    [Parameter(Mandatory = $true)]
    [string]$RestoreWifiProfile
)

$restoreProfileLiteral = "'" + $RestoreWifiProfile.Replace("'", "''") + "'"
$restoreCommand = "Start-Sleep -Seconds 90; netsh wlan connect name=$restoreProfileLiteral"
$encodedRestoreCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($restoreCommand))
$restore = Start-Process -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-EncodedCommand', $encodedRestoreCommand) `
    -WindowStyle Hidden -PassThru
try {
    netsh wlan connect name=SafeSense-RX-V1 interface='Wi-Fi'
    Start-Sleep -Seconds 7
    $pending = Invoke-RestMethod 'http://192.168.4.1/api/v1/pending' -TimeoutSec 8
    [pscustomobject]@{
        event_id = $pending.event_id
        persisted = $pending.rx.queue_persisted
        csi_frames = $pending.rx.csi_frames
        csi_windows = $pending.rx.csi_windows
        csi_raw_callbacks = $pending.rx.csi_raw_callbacks
        first_word_invalid = $pending.rx.csi_invalid_first_word
        measured_carriers = $pending.rx.csi_min_measured_subcarriers
        csi_rssi_dbm = $pending.rx.csi_rssi_dbm
        seen_age_ms = $pending.rx.seen_age_ms
    } | Format-List
    & (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe') -c 'from scripts.rx_http_bridge import forward_once; [forward_once("http://192.168.4.1", "http://127.0.0.1:8000") for _ in range(22)]'
} finally {
    netsh wlan connect name="$RestoreWifiProfile"
}
