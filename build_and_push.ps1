param(
    [Parameter(Mandatory = $true)]
    [string]$DockerUser,
    [string]$ImageName = "explorador-votos-rj-2026",
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "data\votos_cloud.sqlite")) {
    Write-Host "data\votos_cloud.sqlite nao encontrado. Rode: python build_cloud_db.py"
    exit 1
}

Write-Host "==> Build da imagem: $DockerUser/$ImageName`:$Tag"
docker build -t "$DockerUser/$ImageName`:$Tag" .

Write-Host "==> Login no Docker Hub (use seu usuario/senha, ou token)"
docker login

Write-Host "==> Push: $DockerUser/$ImageName`:$Tag"
docker push "$DockerUser/$ImageName`:$Tag"

Write-Host ""
Write-Host "Pronto! No Render, crie um Web Service com a imagem:"
Write-Host "    docker.io/$DockerUser/$ImageName`:$Tag"
Write-Host "plano Free, e deixe a porta como PORT (10000)."