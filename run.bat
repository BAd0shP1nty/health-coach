@echo off
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -r requirements.txt -r requirements-extra.txt -r requirements-desktop.txt
if not exist .env copy .env.example .env
streamlit run app.py
