while ($true) {
    try {
        python mist-guest-logger.py
    } catch {
        Write-Host "Le script Python a échoué: $_"
    }
    Start-Sleep -Seconds 5
}