@echo off
echo.
echo Global Healthy and Sustainable City Indicators -- R vs Python cycling comparison
for /f "usebackq tokens=2 delims==" %%x in (`findstr "^GHSCI_RELEASE=" "%CD%\.env"`) do set GHSCI_RELEASE=%%x
set GHSCI_RELEASE=%GHSCI_RELEASE:"=%
echo %GHSCI_RELEASE%
echo.
echo This launcher also mounts the R cycling outputs read-only at /home/ghsci/r_output
echo (via docker-compose-cycling-comparison.yml) for compare_cycling_r_python.py.
echo.

(
:: launch the compose image with the cycling-comparison overlay merged in
    docker compose -f docker-compose.yml -f docker-compose-cycling-comparison.yml up -d  && docker attach ghsci
) || (
:: catch
    echo "Please ensure that Docker Desktop is installed and running (https://www.docker.com/products/docker-desktop/). Docker Desktop includes Docker Compose, which is required to run this software."
)
