@echo off
REM 启动雷达系统（允许音频自动播放）
REM --user-data-dir 强制启动独立 Chrome 实例，使 --autoplay-policy 生效
REM （如果 Chrome 已在运行，不加此参数则新标签页会加入旧进程，忽略启动参数）
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --autoplay-policy=no-user-gesture-required --user-data-dir="%TEMP%\radar_chrome_profile" http://localhost:5173/index.html
