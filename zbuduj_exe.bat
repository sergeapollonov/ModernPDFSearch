@echo off
echo ====================================================
echo Budowanie pliku .exe dla aplikacji ModernPDFSearch...
echo ====================================================
echo.

pyinstaller --noconfirm ModernPDFSearch.spec

echo.
echo ====================================================
echo ZAKONCZONO! 
echo Twoj nowy plik aplikacji ModernPDFSearch.exe znajdziesz
echo wewnatrz folderu "dist", ktory wlasnie sie utworzyl.
echo ====================================================
pause
