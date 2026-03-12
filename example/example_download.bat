@echo off
echo [Diffinite] Starting download of example data (AOSP Android 9 vs 11 Core OS)...
echo.

:: 1. Set up folder structure
echo Creating folder structure...
if not exist "left" mkdir "left"
if not exist "right" mkdir "right"

:: 2. Download Android 9 (Pie) source code (left)
echo.
echo Downloading Android 9 source code (left)...
curl -L -o "left\Looper.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/pie-release/core/java/android/os/Looper.java"
curl -L -o "left\Handler.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/pie-release/core/java/android/os/Handler.java"
curl -L -o "left\Message.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/pie-release/core/java/android/os/Message.java"

:: 3. Download Android 11 source code (right)
echo.
echo Downloading Android 11 source code (right)...
curl -L -o "right\Looper.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android-11.0.0_r1/core/java/android/os/Looper.java"
curl -L -o "right\Handler.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android-11.0.0_r1/core/java/android/os/Handler.java"
curl -L -o "right\Message.java" "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android-11.0.0_r1/core/java/android/os/Message.java"

echo.
echo All downloads complete! Check the example folder.
pause