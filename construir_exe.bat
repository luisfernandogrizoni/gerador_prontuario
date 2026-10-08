@echo off
rem Gera o programa para abrir com um clique:  dist\SistemaProntuarios\SistemaProntuarios.exe
rem Pode rodar de novo sempre que o sistema mudar. Precisa do Python instalado (comando "py").
rem Os DADOS dos internos nao entram no programa: ficam em AppData\Local\SistemaProntuarios.
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Nao encontrei o Python ^(comando "py"^). Instale em https://www.python.org/downloads/
  goto fim
)

if not exist ".venv-exe\Scripts\python.exe" (
  echo Criando o ambiente de construcao...
  py -m venv .venv-exe || goto erro
)
echo Instalando as dependencias...
".venv-exe\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements-exe.txt || goto erro

echo Construindo o programa ^(leva alguns minutos^)...
".venv-exe\Scripts\python.exe" -m PyInstaller --noconfirm --clean --name SistemaProntuarios --console ^
  --add-data "templates;templates" --add-data "static;static" --add-data "modelo;modelo" iniciar.py || goto erro

echo.
echo Pronto! Abra: dist\SistemaProntuarios\SistemaProntuarios.exe
goto fim

:erro
echo.
echo A construcao falhou. Leia as mensagens acima.

:fim
if not defined SEM_PAUSA pause
