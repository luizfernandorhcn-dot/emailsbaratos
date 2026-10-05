@echo off
title DIGITAL STORE - Servidor de Vendas
chcp 65001 >nul
cls

echo ==============================================================
echo              DIGITAL STORE - SISTEMA SEGURO
echo ==============================================================
echo.
echo  [1/2] Verificando dependencias...
python -m pip install -r "%~dp0requirements.txt" --quiet

echo  [2/2] Iniciando o servidor...
echo.
echo  -------------------------------------------------------------
echo   Loja Publica:            http://localhost:5000
echo   Painel Secreto:          http://localhost:5000/painel-gestao-77x
echo   Senha de Acesso:         Z8#mK9!vP2@wL5$qF7
echo  -------------------------------------------------------------
echo.
echo  Pressione CTRL+C nesta janela para parar o servidor.
echo.

start http://localhost:5000

python "%~dp0app.py"

pause
