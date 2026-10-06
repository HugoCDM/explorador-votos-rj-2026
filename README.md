---
title: Explorador de Votos RJ 2026
emoji: 🗳️
colorFrom: blue
colorTo: blue
sdk: docker
app_port: 10000
pinned: false
---

# Explorador de Votos RJ 2026

Aplicacao para consultar os votos por cargo, candidato, municipio, bairro, local de votacao, zona e secao — feito para o CSV grande sem carregar milhoes de linhas direto no navegador. Os dados sao importados para SQLite e a interface consulta por uma API Python.

## Uso local

1. Importe o CSV para SQLite:

   ```powershell
   python import_data.py
   ```

2. Inicie o servidor:

   ```powershell
   python server.py --db data/votos_cloud.sqlite
   ```

3. Abra no navegador:

   ```text
   http://127.0.0.1:8000
   ```

## Publicar gratuitamente no Render

O banco enxuto (`data/votos_cloud.sqlite`, ~380 MB) contem apenas os cargos de Governador e Presidente. Para gerá-lo a partir do banco completo:

```powershell
python build_cloud_db.py
```

A forma mais simples é subir a imagem Docker para o Docker Hub e criar um Web Service no Render (plano Free, sem cartao). O Render injeta a variavel `PORT` e o servidor já a usa.

1. Crie uma conta gratuita no Docker Hub (sem cartao) em <https://hub.docker.com>.
2. Suba a imagem (precisa do Docker instalado e logado):

   ```powershell
   .\build_and_push.ps1 -DockerUser SEU_USUARIO_DOCKER_HUB
   ```

3. Crie uma conta gratuita no Render (sem cartao) em <https://render.com>.
4. Em **Dashboard → New → Web Service**, use **Deploy an existing image from a registry** e informe:

   ```text
   docker.io/SEU_USUARIO_DOCKER_HUB/explorador-votos-rj-2026:latest
   ```

5. Escolha o plano **Free** (dorme apos ~15 min sem visitas e acorda em ~1 min com a primeira visita).
6. Deploy conclui em ~2 min. O link publico fica em:

   ```text
   https://SEU_NOME-render.onrender.com
   ```

Observações:
- No plano Free o Render dorme quando não há visitas (evita consumo) e acorda sob demanda; 750 h de instancia por mes sao suficiente para um servico 24/7 com visitas.
- Se preferir manter Cloud complementar, ha tambem o banco completo local (`data/votos.sqlite`, ~5 GB) com todos os cargos.

## ENDPOINTS disponíveis

- `/api/health` — status do servidor
- `/api/options` — cargos, municipios, bairros, candidatos e tipos de voto
- `/api/overview` — totais e lideres
- `/api/summary?group={candidato|municipio|bairro|local|secao|tipo}` — ranking
- `/api/rows` — linhas detalhadas com paginacao
- `/api/map` — locais georreferenciados para o mapa
- `/api/location` — detalhe de um local de votacao

Todos os endpoints aceitam `cargo=Governador`/`cargo=Presidente`, `municipio`, `bairro`, `candidato` (numero), `tipo`, `zona`, `secao` e `q` (busca textual via FTS).

## Filtros e busca

- Cargos exibidos: Governador e Presidente (os dados de deputados/senador ficam fora do banco enxuto).
- A busca `q` procura por prefixo de token (escola *brizola*, candidato *paes*, etc.) usando FTS5 com remoção de acentos.

## Arquivos esperados (importacao completa)

```text
Eleições 2026 completas.csv
consulta_cand_2026_BRASIL.csv
```

Tambem e possivel informar caminhos manualmente:

```powershell
python import_data.py --votes "D:\Downloads\eleicoes_2026\Eleições 2026 completas.csv" --candidates "D:\Downloads\eleicoes_2026\consulta_cand_2026_BRASIL.csv"
```

## Observacoes

- O banco completo fica em `data/votos.sqlite` (~5 GB, por isso nao vai para o git).
- O banco enxuto fica em `data/votos_cloud.sqlite` (~380 MB) e usa apenas Governador e Presidente.
- A importacao completa pode demorar alguns minutos porque o CSV tem milhoes de linhas.