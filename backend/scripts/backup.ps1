param(
  [string]$Database = "sfb_test",
  [string]$OutDir   = ""
)
# S0-10 备份脚本：mysqldump 逻辑备份，默认只备份 sfb_test（不动 sfb_dev）。
# 输出：<OutDir>\<db>_<yyyyMMdd_HHmmss>.dump
# 密码取自 backend/.env 的 DATABASE_URL（percent-decode 后使用），不回显、不写进任何提交物。
# 库名唯一来源 = 显式 -Database 参数（默认 sfb_test），绝不从 URL 覆盖。

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # backend/scripts -> repo root
if (-not $OutDir) { $OutDir = Join-Path $repoRoot "backend\scripts\backups" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- 读取 DATABASE_URL 并拆解 ---
$dbLine = (Get-Content (Join-Path $repoRoot "backend\.env")) |
  Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $dbLine) { throw "backend/.env 里没有 DATABASE_URL" }
$inner = $dbLine -replace '^DATABASE_URL=mysql\+pymysql://', ''
$userinfo = ($inner -split '@', 2)[0]
$rest     = ($inner -split '@', 2)[1]
$dbUser = ($userinfo -split ':', 2)[0]
$dbPwd  = [uri]::UnescapeDataString((($userinfo -split ':', 2)[1]))
$dbHost = ($rest -split ':', 2)[0]
$dbPort = (($rest -split ':', 2)[1] -split '/', 2)[0]
$charset = 'utf8mb4'
if ($inner -match 'charset=([a-z0-9_]+)') { $charset = $Matches[1] }

$mysqldump = "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"
$stamp  = Get-Date -Format 'yyyyMMdd_HHmmss'
$target = $Database   # 唯一来源 = 显式参数
$outFile = Join-Path $OutDir ("{0}_{1}.dump" -f $target, $stamp)

Write-Output "=== 备份目标 ==="
Write-Output ("  database : {0}" -f $target)
Write-Output ("  server   : {0}:{1}" -f $dbHost, $dbPort)
Write-Output ("  output   : {0}" -f $outFile)
Write-Output ("  charset  : {0}" -f $charset)
Write-Output ""

# --- mysqldump：不加 --databases，dump 只含该库的表结构+数据，不含 DROP/CREATE/USE ---
& $mysqldump `
  --host=$dbHost --port=$dbPort --user=$dbUser `
  --password=$dbPwd `
  --default-character-set=$charset `
  --single-transaction --routines --triggers --events `
  --no-tablespaces `
  $target `
  --result-file=$outFile

if ($LASTEXITCODE -ne 0) { throw "mysqldump 失败，exit=$LASTEXITCODE" }

$size = (Get-Item $outFile).Length
$lines = (Get-Content $outFile | Measure-Object -Line).Lines
Write-Output ""
Write-Output "=== 备份完成 ==="
Write-Output ("  file     : {0}" -f $outFile)
Write-Output ("  size     : {0} bytes" -f $size)
Write-Output ("  lines    : {0}" -f $lines)
Write-Output ""
Write-Output "下一步：恢复演练用 restore.ps1 -DumpFile `"$outFile`" -TargetDatabase sfb_test"
