$childPID = Get-Process -ProcessName testserver | Select-Object -Expand Id
Stop-Process $childPID