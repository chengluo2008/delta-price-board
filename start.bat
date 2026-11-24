@echo off
chcp 936 >nul
title 三角洲行动 · 变卖物行情
setlocal

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
echo.
echo   正在启动本地服务，浏览器会自动打开，请稍等几秒...
echo   关闭这个黑窗口 = 停止服务。
echo.
"%PY%" server.py
set "CODE=%ERRORLEVEL%"
popd
if not "%CODE%"=="0" (
  echo.
  echo   服务异常退出，请把上面的报错发给我看看。
  pause
)
exit /b 0

:nopython
echo.
echo   [x] 没找到 Python，网页起不来。
echo.
echo       办法一：先打开一次 DeepSeek Harness，再双击本文件。
echo       办法二：去 https://www.python.org/downloads/ 安装 Python，
echo              安装时记得勾选 Add Python to PATH。
echo.
pause
exit /b 1
