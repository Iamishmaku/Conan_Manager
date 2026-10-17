@echo off
powershell.exe -NoProfile -WindowStyle Hidden -Command "$listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; foreach ($listener in $listeners) { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue }"
exit /b 0
