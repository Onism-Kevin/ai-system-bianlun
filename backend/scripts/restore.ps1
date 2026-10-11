param(
  [Parameter(Mandatory=$true)][string]$DumpFile,
  [string]$TargetDatabase = "sfb_test"
)
# S0-10 恢复脚本：把 backup.ps1 产出的 .dump 恢复到 $TargetDatabase（默认 sfb_test，不动 sfb_dev）。
# 说明：backup.ps1 不带 --databases，dump 只含表结构+数据，不含 CREATE DATABASE / USE。
#       因此本脚本负责：DROP 后重建目标库（utf8mb4），再把 dump 导入选中的库。
# 判据：恢复后 SELECT COUNT(*) 与备份前一致（由调用方备份前后各跑一次对比）。

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

if (-not (Test-Path $DumpFile)) { throw "找不到 dump 文件: $DumpFile" }

# --- 读取 DATABASE_URL ---
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

$mysql = "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"

# 公共参数（数组 splat，避免引号/反引号陷阱）
$myArgs = @(
  "--host=$dbHost", "--port=$dbPort", "--user=$dbUser",
  "--password=$dbPwd", "--default-character-set=$charset"
)

Write-Output "=== 恢复演练 ==="
Write-Output ("  dump file : {0}" -f $DumpFile)
Write-Output ("  target db : {0}" -f $TargetDatabase)
Write-Output ("  server    : {0}:{1}" -f $dbHost, $dbPort)
Write-Output ""

# 步骤 1：DROP 后重建目标库（utf8mb4，与 S0-9 建库规则一致）
$createSql = "DROP DATABASE IF EXISTS ``" + $TargetDatabase + "``; CREATE DATABASE ``" + $TargetDatabase + "`` DEFAULT CHARACTER SET " + $charset + " COLLATE " + $charset + "_unicode_ci;"
Write-Output ">> 步骤 1/3：重建目标库 $TargetDatabase"
& $mysql @myArgs -e $createSql
if ($LASTEXITCODE -ne 0) { throw "重建目标库失败 exit=$LASTEXITCODE" }

# 步骤 2：导入 dump（先选定目标库，再 source；避免 dump 无 USE 时报 "No database selected"）
Write-Output ">> 步骤 2/3：导入 dump"
$src = "source " + $DumpFile
& $mysql @myArgs $TargetDatabase -e $src
if ($LASTEXITCODE -ne 0) { throw "导入 dump 失败 exit=$LASTEXITCODE" }

# 步骤 3：核对
Write-Output ">> 步骤 3/3：核对表行数"
$chk = "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA='" + $TargetDatabase + "' ORDER BY TABLE_NAME;"
& $mysql @myArgs -e $chk
if ($LASTEXITCODE -ne 0) { throw "核对失败 exit=$LASTEXITCODE" }

Write-Output ""
Write-Output "=== 恢复完成 ==="
Write-Output "请把备份前后的 SELECT COUNT(*) 贴给我对比，一致即 S0-10 通过。"
