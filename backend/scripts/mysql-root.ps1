# mysql-root.ps1 — 带凭据的 mysql.exe 包装器
# 用途：my.ini 的 [client] 段没有 user/password，Windows 上 mysql.exe 不带 -u 时
#       会以 'ODBC' 用户连接并报 ERROR 1045。本脚本从 backend\.env 的 DATABASE_URL
#       解析 root 密码后透传所有参数给 mysql.exe，无需在命令行手输密码。
# 用法（参数原样透传给 mysql.exe，无需手输密码）：
#   .\backend\scripts\mysql-root.ps1 sfb_test -e "SELECT COUNT(*) FROM drill_marker;"
#   .\backend\scripts\mysql-root.ps1 -e "SHOW DATABASES;"

$ErrorActionPreference = 'Stop'

$backendDir = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $backendDir '.env'
if (-not (Test-Path $envFile)) { throw ".env not found: $envFile" }

$dbLine = (Get-Content $envFile) | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $dbLine) { throw "DATABASE_URL not found in $envFile" }
$inner = $dbLine -replace '^DATABASE_URL=mysql\+pymysql://', ''
$userPwd = (($inner -split '@', 2)[0]) -split ':', 2
$dbPwd = [uri]::UnescapeDataString($userPwd[1])

$mysql = 'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe'
if (-not (Test-Path $mysql)) { throw "mysql.exe not found: $mysql" }

& $mysql -u root "-p$dbPwd" --default-character-set=utf8mb4 @args
exit $LASTEXITCODE
