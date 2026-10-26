# Monta a versão portátil do Sentinela para Windows (pasta + ZIP).
#
# Requisitos na máquina que MONTA (não na que vai usar): Windows 64 bits,
# Python 3.12 no PATH, PostgreSQL instalado (os binários são copiados dele) e,
# opcionalmente, MariaDB (clientes mariadb/mariadb-dump). É o que o GitHub
# Actions usa em .github/workflows/portatil.yml.
#
# Uso:  powershell -ExecutionPolicy Bypass -File portatil\montar.ps1 [-Saida dist\Sentinela]
param(
    [string]$Saida = "dist\Sentinela",
    [string]$PyVersion = "3.12.10"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$repo = (Resolve-Path "$PSScriptRoot\..").Path
if (Test-Path $Saida) { Remove-Item -Recurse -Force $Saida }
New-Item -ItemType Directory -Force "$Saida\python", "$Saida\app", "$Saida\ferramentas" | Out-Null
$Saida = (Resolve-Path $Saida).Path

# 1. Python embutido (oficial, assinado pela Python Software Foundation)
Write-Host "== Python $PyVersion embutido"
$zip = Join-Path $env:TEMP "python-$PyVersion-embed-amd64.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip "$Saida\python" -Force
$tag = ($PyVersion.Split('.')[0..1] -join '')
# python3XX._pth define o sys.path do Python embutido
@"
python$tag.zip
.
Lib\site-packages
..\app
import site
"@ | Set-Content -Encoding ASCII "$Saida\python\python$tag._pth"

# 2. Bibliotecas (rodas binárias para Windows/Python 3.12)
Write-Host "== Bibliotecas"
python -m pip install --disable-pip-version-check --only-binary=:all: `
    --target "$Saida\python\Lib\site-packages" -r "$repo\requirements.txt"
Remove-Item -Recurse -Force "$Saida\python\Lib\site-packages\bin" -ErrorAction SilentlyContinue

# 3. Aplicação
Write-Host "== Sentinela"
Copy-Item -Recurse "$repo\sentinela" "$Saida\app\sentinela"
Copy-Item "$repo\portatil\portatil.py", "$repo\portatil\demo.sql", "$repo\LICENSE", "$repo\README.md" "$Saida\app"
Copy-Item "$repo\portatil\Sentinela.bat", "$repo\portatil\Sentinela-Demo.bat", "$repo\portatil\Trocar-Senha.bat", "$repo\portatil\Descriptografar.bat", "$repo\portatil\Parar-Sentinela.bat", "$repo\portatil\LEIA-ME.txt" $Saida
Get-ChildItem $Saida -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# 4. PostgreSQL: clientes (pg_dump/psql) e servidor do banco de demonstração
Write-Host "== PostgreSQL"
$pgroot = if ($env:PGROOT) { $env:PGROOT } else {
    (Get-ChildItem "C:\Program Files\PostgreSQL\*" -Directory | Sort-Object { [int]($_.Name -replace '\D', '') } | Select-Object -Last 1).FullName }
if (-not $pgroot -or -not (Test-Path "$pgroot\bin\pg_dump.exe")) { throw "PostgreSQL não encontrado (defina PGROOT)" }
$pg = "$Saida\ferramentas\pgsql"
New-Item -ItemType Directory -Force $pg | Out-Null
Copy-Item -Recurse "$pgroot\bin", "$pgroot\lib", "$pgroot\share" $pg
# o que não é usado: ferramentas gráficas, símbolos de depuração, cabeçalhos e documentação
Get-ChildItem $pg -Recurse -Include *.pdb, *.lib, *.a | Remove-Item -Force
foreach ($d in "share\doc", "share\man", "lib\pgxs", "lib\pkgconfig", "bin\stackbuilder*", "bin\pgAdmin*") {
    Remove-Item -Recurse -Force (Join-Path $pg $d) -ErrorAction SilentlyContinue }
@"
Binários do PostgreSQL $((& "$pg\bin\pg_dump.exe" --version) -replace 'pg_dump \(PostgreSQL\) ', '')
Licença PostgreSQL (permissiva): https://www.postgresql.org/about/licence/
"@ | Set-Content -Encoding UTF8 "$pg\LEIA-ME-LICENCA.txt"

# 5. Clientes do MariaDB (opcional)
$mdb = Get-ChildItem "C:\Program Files\MariaDB*\bin" -Directory -ErrorAction SilentlyContinue |
       Sort-Object FullName | Select-Object -Last 1
if ($mdb) {
    Write-Host "== MariaDB ($($mdb.FullName))"
    $md = "$Saida\ferramentas\mariadb"
    New-Item -ItemType Directory -Force $md | Out-Null
    Copy-Item "$($mdb.FullName)\mariadb.exe", "$($mdb.FullName)\mariadb-dump.exe" $md
    # Plugins de autenticação do CLIENTE (caching_sha2_password é o padrão do MySQL 8+;
    # sem ele: "Plugin caching_sha2_password could not be loaded")
    $plugsrc = Join-Path (Split-Path $mdb.FullName) "lib\plugin"
    New-Item -ItemType Directory -Force "$md\plugin" | Out-Null
    foreach ($p in "caching_sha2_password", "sha256_password", "client_ed25519", "dialog",
                   "mysql_clear_password", "auth_gssapi_client", "parsec", "pvio_npipe", "pvio_shmem") {
        if (Test-Path "$plugsrc\$p.dll") { Copy-Item "$plugsrc\$p.dll" "$md\plugin" }
    }
    if (-not (Test-Path "$md\plugin\caching_sha2_password.dll")) { throw "Plugin caching_sha2_password.dll não encontrado em $plugsrc" }
    Write-Host ("   plugins: " + ((Get-ChildItem "$md\plugin").Name -join ", "))
    # DLLs de que os executáveis e os plugins dependem e que estão na pasta do MariaDB
    python -m pip install --disable-pip-version-check -q pefile
    python "$repo\portatil\dlls.py" "$md" "$($mdb.FullName)"
    "Clientes do MariaDB (GPLv2). Código-fonte: https://mariadb.org/download/" |
        Set-Content -Encoding UTF8 "$md\LEIA-ME-LICENCA.txt"
} else { Write-Host "== MariaDB não encontrado: pacote sem os clientes do MariaDB" }

# 6. Runtime do Visual C++ junto dos executáveis (PCs sem o "Visual C++ Redistributable")
foreach ($dir in @("$pg\bin", "$Saida\ferramentas\mariadb")) {
    if (-not (Test-Path $dir)) { continue }
    foreach ($dll in "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll",
                     "msvcp140_2.dll", "concrt140.dll") {
        $src = "$env:SystemRoot\System32\$dll"
        if ((Test-Path $src) -and -not (Test-Path "$dir\$dll")) { Copy-Item $src $dir }
    }
}

# 7. ZIP
Write-Host "== Compactando"
$destZip = Join-Path (Split-Path $Saida) "Sentinela-Portatil-Windows.zip"
if (Test-Path $destZip) { Remove-Item $destZip }
Push-Location (Split-Path $Saida)
& 7z a -tzip -mx=7 -bso0 -bsp0 $destZip (Split-Path $Saida -Leaf)
Pop-Location
$mb = [math]::Round((Get-Item $destZip).Length / 1MB, 1)
$total = [math]::Round(((Get-ChildItem $Saida -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
Write-Host "Pronto: $destZip ($mb MB; $total MB extraído)"
