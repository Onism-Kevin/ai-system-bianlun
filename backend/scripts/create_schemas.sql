-- S0-9：dev / test / demo 三 schema 建库脚本（幂等，可重复执行）
-- 规则：utf8mb4 + utf8mb4_unicode_ci，与 restore.ps1 重建目标库的规则一致。
-- 执行示例：
--   .\backend\scripts\mysql-root.ps1 < backend\scripts\create_schemas.sql
-- 或：
--   powershell -ExecutionPolicy Bypass -File backend\scripts\mysql-root.ps1 -e "source backend\scripts\create_schemas.sql"

CREATE DATABASE IF NOT EXISTS sfb_dev  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS sfb_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS sfb_demo DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 核对：
SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME LIKE 'sfb_%'
ORDER BY SCHEMA_NAME;
