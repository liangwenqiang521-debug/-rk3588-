@echo off
chcp 65001 >nul
cd /d "%~dp0"
title RK3588 板端模拟器（协议级替身）

echo ================================================================
echo   RK3588 板端模拟器
echo   作用：没有真实板子时，用本机 TCP 服务顶替 board_infer.py，
echo        让上位机走完全真实的收发链路（真 socket - 真 JSON）。
echo        真板子到位后，只需把上位机里的 IP 换成板子 IP。
echo ================================================================
echo.
echo   启动后保持本窗口开着，然后去上位机：
echo     - NPU 监控页 - 数据来源「板端TCP」- 127.0.0.1:9000 - 连接
echo     - 检测页     - 边缘模式「网络(TCP)」- 同上        - 启动
echo.
echo   停止：按 Ctrl+C 或直接关窗口
echo ================================================================
echo.

"C:\Users\21191\.workbuddy\binaries\python\envs\default\Scripts\python.exe" "板端模拟器.py" --port 9000 --fps 10 --ng-rate 0.35

pause
