while ($true) {
    try {
        python mist-guests-stats.py
    } catch {
        Write-Host "Le script Python a échoué: $_"
    }
    Start-Sleep -Seconds 5
}