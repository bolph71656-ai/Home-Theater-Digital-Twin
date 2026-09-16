param(
    [string]$RewBaseUrl = 'http://127.0.0.1:4735',
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'

function Get-RewJson {
    param([string]$Path)
    try {
        return Invoke-RestMethod -Uri ($RewBaseUrl.TrimEnd('/') + $Path) -Method Get -TimeoutSec 3
    }
    catch {
        return [pscustomobject]@{ error = $_.Exception.Message }
    }
}

$computer = Get-CimInstance Win32_ComputerSystem
$video = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [pscustomobject]@{
        name = $_.Name
        driverVersion = $_.DriverVersion
    }
})

$audioEndpoints = @(Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{
        status = [string]$_.Status
        name = [string]$_.FriendlyName
    }
})
$rewOutputDevices = Get-RewJson '/audio/java/output-devices'
$rewInputDevices = Get-RewJson '/audio/java/input-devices'
$rewMeasurements = Get-RewJson '/measurements'

$result = [ordered]@{
    collectedAt = (Get-Date).ToUniversalTime().ToString('o')
    computer = [ordered]@{
        manufacturer = $computer.Manufacturer
        model = $computer.Model
    }
    video = $video
    windowsAudioEndpoints = $audioEndpoints
    yamahaEndpointPresent = [bool]($audioEndpoints | Where-Object { $_.name -match 'Yamaha|RX-A4A' })
    rew = [ordered]@{
        baseUrl = $RewBaseUrl
        audioStatus = Get-RewJson '/audio/status'
        driver = Get-RewJson '/audio/driver'
        sampleRate = Get-RewJson '/audio/samplerate'
        outputDevice = Get-RewJson '/audio/java/output-device'
        outputDevices = $rewOutputDevices
        inputDevice = Get-RewJson '/audio/java/input-device'
        inputDevices = $rewInputDevices
        outputDeviceChannels = Get-RewJson '/audio/java/num-output-device-channels'
        outputChannels = Get-RewJson '/audio/java/output-channels'
        outputChannelMapping = Get-RewJson '/audio/java/output-channel-mapping'
        measurements = $rewMeasurements
    }
}
$exclusiveCandidates = @()
if ($rewOutputDevices -is [System.Array]) {
    $exclusiveCandidates = @($rewOutputDevices | Where-Object { [string]$_ -like 'EXCL:*' })
}
$result.rew['exclusiveMultichannelCandidates'] = $exclusiveCandidates

$json = $result | ConvertTo-Json -Depth 12
if ($OutputPath) {
    $resolved = [System.IO.Path]::GetFullPath($OutputPath)
    $parent = Split-Path -Parent $resolved
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [System.IO.File]::WriteAllText($resolved, $json, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Saved: $resolved"
}

Write-Host "Yamaha/RX-A4A endpoint present: $($result.yamahaEndpointPresent)"
Write-Host "REW Java output hardware channels: $($result.rew.outputDeviceChannels)"
if ($exclusiveCandidates.Count -gt 0) {
    Write-Host 'REW WASAPI-exclusive candidates:'
    $exclusiveCandidates | ForEach-Object { Write-Host "  $_" }
}
else {
    Write-Host 'No REW WASAPI-exclusive output candidate is currently visible.'
}

$json