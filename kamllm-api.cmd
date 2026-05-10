@echo off
cd /d "%~dp0backend"
python -m kamllm.api_main %*
