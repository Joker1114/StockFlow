@echo off
setlocal
set "STOCKFLOW_ENV_FILE=%~dp0stockflow.env"

powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$path = $env:STOCKFLOW_ENV_FILE;" ^
    "if (Test-Path -LiteralPath $path) { Write-Host 'Using existing stockflow.env'; exit 0 };" ^
    "$securePassword = Read-Host 'Set the initial admin password (10 to 256 characters)' -AsSecureString;" ^
    "$password = [Net.NetworkCredential]::new('', $securePassword).Password;" ^
    "$length = [regex]::Matches($password, '[\uD800-\uDBFF][\uDC00-\uDFFF]|.').Count;" ^
    "if ($length -lt 10 -or $length -gt 256) { throw 'Password must be 10 to 256 characters' };" ^
    "$secret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N');" ^
    "$lines = @('STOCKFLOW_ADMIN_USERNAME=admin', ('STOCKFLOW_ADMIN_PASSWORD=' + $password), ('STOCKFLOW_JWT_SECRET=' + $secret), 'STOCKFLOW_TOKEN_HOURS=24');" ^
    "$file = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write);" ^
    "try { $bytes = [Text.Encoding]::UTF8.GetBytes(($lines -join [Environment]::NewLine) + [Environment]::NewLine); $file.Write($bytes, 0, $bytes.Length) } finally { $file.Dispose() };" ^
    "Write-Host 'Created stockflow.env'"

exit /b %errorlevel%
