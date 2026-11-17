@echo off
chcp 65001 >nul
title Instalar notificacoes de Licitacoes INPAV
echo.
echo  ===============================================
echo    Notificacoes de Licitacoes INPAV no Windows
echo  ===============================================
echo.

set "DEST=%LOCALAPPDATA%\LicitacoesINPAV"
if not exist "%DEST%" mkdir "%DEST%"

copy /Y "%~dp0notificador.ps1" "%DEST%\" >nul || goto erro
copy /Y "%~dp0avisar.vbs" "%DEST%\" >nul || goto erro
copy /Y "%~dp0desinstalar.bat" "%DEST%\" >nul

rem confere a cada hora (o painel atualiza as 06h e as 15h)
schtasks /Create /F /TN "Licitacoes INPAV" /SC HOURLY /MO 1 /TR "wscript.exe \"%DEST%\avisar.vbs\"" >nul || goto erro
rem confere tambem ao ligar o computador
schtasks /Create /F /TN "Licitacoes INPAV - ao entrar" /SC ONLOGON /DELAY 0002:00 /TR "wscript.exe \"%DEST%\avisar.vbs\"" >nul 2>nul

echo  Enviando notificacao de teste...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DEST%\notificador.ps1" -Teste
timeout /t 3 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DEST%\notificador.ps1"

echo.
echo  PRONTO! Duas notificacoes devem ter aparecido no canto da tela.
echo  O computador vai conferir licitacoes novas de hora em hora.
echo.
echo  Se nao apareceu nada: Configuracoes ^> Sistema ^> Notificacoes
echo  e confira se as notificacoes estao ligadas (e o "Nao perturbe" desligado).
echo.
pause
exit /b 0

:erro
echo.
echo  Algo deu errado na instalacao. Tire um print desta tela e envie.
pause
exit /b 1
