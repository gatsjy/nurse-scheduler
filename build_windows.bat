@echo off
echo === 간호사 스케줄러 Windows 빌드 ===
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo Python 3.10 이상을 설치하세요: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 패키지 설치 중...
pip install PyQt5 openpyxl ortools pyinstaller

echo.
echo [2/3] 빌드 중... (수분 소요)
pyinstaller schedule.spec --clean

echo.
echo [3/3] 완료!
echo 실행 파일 위치: dist\NurseScheduler\NurseScheduler.exe
echo.
pause
