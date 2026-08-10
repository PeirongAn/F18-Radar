$ErrorActionPreference = 'SilentlyContinue'
$url = 'http://127.0.0.1:8080/'
$deadline = [DateTime]::UtcNow.AddSeconds(60)

while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process $url
            exit 0
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

exit 1
