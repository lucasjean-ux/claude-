@echo off
echo Installation de l'Usine a TikTok...
python --version || (echo Installe Python depuis python.org en cochant "Add to PATH" & pause & exit /b)
python -m pip install --upgrade edge-tts pillow numpy
where ffmpeg >nul 2>nul || winget install --id Gyan.FFmpeg -e
echo.
echo Test : python 04_atelier\render\render_countryball.py 05_references\exemple\pack-singapour.json 05_references\exemple\images 05_references\exemple\test.mp4
pause
