@echo off
chcp 936 >nul
title 更新三角洲物价并发布到网上
setlocal

rem 带 /quiet 参数时不弹任何提示，适合计划任务在后台运行
if /i "%~1"=="/quiet" set "QUIET=1"

set "PY="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if not defined PY for /d %%D in ("%USERPROFILE%\.dsh\dsh-runtimes\*") do if exist "%%~fD\dependencies\python\python.exe" set "PY=%%~fD\dependencies\python\python.exe"

if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 set "PY=py"
)

if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY goto nopython

pushd "%~dp0"
if not defined QUIET echo.
if not defined QUIET echo   第 1 步：抓取最新物价...
"%PY%" scripts\fetch_data.py
if errorlevel 1 goto fetchfail
if not defined QUIET echo.
if not defined QUIET echo   第 2 步：发布到 GitHub...
"%PY%" scripts\publish.py
if errorlevel 1 goto pushfail
if not defined QUIET echo.
if not defined QUIET echo   完成！网站大约 1 分钟后自动更新：
if not defined QUIET echo   https://chengluo2008.github.io/delta-price-board/
if not defined QUIET pause
popd
exit /b 0

:fetchfail
if not defined QUIET echo.
if not defined QUIET echo   抓取失败：多半是数据站或网络暂时不通。
if not defined QUIET echo   没有发布任何东西，网上还是旧数据，稍后再双击一次就行。
if not defined QUIET pause
popd
exit /b 1

:pushfail
if not defined QUIET echo.
if not defined QUIET echo   发布失败：多半是连不上 GitHub。
if not defined QUIET echo   数据已经存在本地了，网络好一点再双击一次。
if not defined QUIET pause
popd
exit /b 1

:nopython
echo.
echo   [x] 没找到 Python，跑不起来。
echo       先打开一次 DeepSeek Harness 再双击本文件。
pause
exit /b 1
