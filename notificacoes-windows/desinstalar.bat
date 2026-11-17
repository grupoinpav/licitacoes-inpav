@echo off
chcp 65001 >nul
schtasks /Delete /F /TN "Licitacoes INPAV" >nul 2>nul
schtasks /Delete /F /TN "Licitacoes INPAV - ao entrar" >nul 2>nul
echo Notificacoes de Licitacoes INPAV desligadas.
echo (Os arquivos ficam em %LOCALAPPDATA%\LicitacoesINPAV e podem ser apagados.)
pause
