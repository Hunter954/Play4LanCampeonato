@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
if not exist agent\config.json copy agent\config.example.json agent\config.json
echo Instalacao concluida.
