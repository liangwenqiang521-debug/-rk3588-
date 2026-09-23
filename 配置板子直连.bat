@echo off
chcp 65001 >nul
title 配置 PC <-> RK3588 网线直连

REM ==== 按需修改：PC 侧地址与板子地址（须同网段）====
set PC_IP=192.168.1.100
set BOARD_IP=192.168.1.20

net session >nul 2>&1
if errorlevel 1 (
    echo [错误] 需要管理员权限。
    echo        请右键本文件 -^> 以管理员身份运行。
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   配置 PC  USB 网口 为 %PC_IP%/24
echo   板子 eth0 已配置为 %BOARD_IP%/24
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$n = Get-NetAdapter -Physical | Where-Object { $_.InterfaceDescription -like '*AX88179*' -or $_.Name -like '以太网 2' } | Select-Object -First 1;" ^
  "if (-not $n) { Write-Host '[错误] 未找到 USB 网卡 (ASIX AX88179)' -ForegroundColor Red; exit 1 }" ^
  "Write-Host ('目标网卡: ' + $n.Name + '  (ifIndex=' + $n.ifIndex + ')')" ^
  "Write-Host ('状态    : ' + $n.Status + '  ' + $n.LinkSpeed)" ^
  "$i = $n.ifIndex;" ^
  "Get-NetIPAddress -InterfaceIndex $i -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "New-NetIPAddress -InterfaceIndex $i -IPAddress %PC_IP% -PrefixLength 24 | Out-Null;" ^
  "Write-Host '已配置静态 IP: %PC_IP%/24' -ForegroundColor Green;" ^
  "Start-Sleep -Seconds 2;" ^
  "Get-NetIPAddress -InterfaceIndex $i -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength | Format-Table | Out-String | Write-Host"

echo.
echo --- 测试连通性 (ping %BOARD_IP%) ---
ping -n 3 -w 1000 %BOARD_IP%

echo.
echo --- 测试 SSH 端口 22 ---
powershell -NoProfile -Command "Test-NetConnection -ComputerName %BOARD_IP% -Port 22 -InformationLevel Quiet | ForEach-Object { if ($_) { Write-Host 'SSH 22  端口: 可达' -ForegroundColor Green } else { Write-Host 'SSH 22  端口: 不可达' -ForegroundColor Red } }"

echo.
echo --- 测试推理端口 9000 ---
powershell -NoProfile -Command "Test-NetConnection -ComputerName %BOARD_IP% -Port 9000 -InformationLevel Quiet | ForEach-Object { if ($_) { Write-Host 'TCP 9000 端口: 可达' -ForegroundColor Green } else { Write-Host 'TCP 9000 端口: 不可达 (服务可能未启动)' -ForegroundColor Yellow } }"

echo.
pause
