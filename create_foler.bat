@echo off
setlocal enabledelayedexpansion

set /p api_id=Enter api_id:
set /p api_hash=Enter api_hash:
set /p phone=Enter phone number:

xcopy /E /I /Y "userbottest" "userbot%phone%"

(
echo api_id = %api_id%
echo api_hash = "%api_hash%"
) > "userbot%phone%\config.py"

echo Done! Created folder userbot%phone% with file config.py.
pause
