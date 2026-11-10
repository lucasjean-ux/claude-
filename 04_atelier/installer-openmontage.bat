@echo off
REM Installe OpenMontage (montage vidéo IA open source, licence AGPL-3.0) dans 04_atelier\OpenMontage
REM Il faut : Git, Python 3.10+, Node.js 18+ et FFmpeg (installer.bat de l'usine installe FFmpeg).
cd /d "%~dp0"
where git >nul 2>nul || winget install --id Git.Git -e
where node >nul 2>nul || winget install --id OpenJS.NodeJS.LTS -e
python --version || (echo Installe Python depuis python.org en cochant "Add to PATH" & pause & exit /b)
if not exist OpenMontage git clone --depth 1 https://github.com/OpenMontageInc/OpenMontage.git
cd OpenMontage
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install "pip>=26.2.2"
python -m pip install -r requirements.txt
python -m pip install piper-tts
cd remotion-composer
call npm install || call npx --yes npm install
cd ..
if not exist .env copy .env.example .env
echo.
echo OpenMontage est installe. Ouvre Claude Code dans 04_atelier\OpenMontage et decris ta video.
echo Test sans cle API : .venv\Scripts\python render_demo.py
pause
