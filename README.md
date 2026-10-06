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

## Publicar gratuitamente no Render (sem Docker Hub, sem cartao)

O banco enxuto (`data/votos_cloud.sqlite`, ~380 MB) contem apenas os cargos de Governador e Presidente. Para gerá-lo a partir do banco completo:

```powershell
python build_cloud_db.py
```

O repositorio publicado em <https://github.com/HugoCDM/explorador-votos-rj-2026> já tem tudo pronto:

- O banco **nao** fica no git (377 MB): ele é distribuido como **release asset** (`votos_cloud.sqlite` em <https://github.com/HugoCDM/explorador-votos-rj-2026/releases>) e o `Dockerfile` o baixa com `curl` na hora do build. Assim o repositório fica leve e sem custo de LFS.
- O `Dockerfile` já escuta na porta do Render (`PORT` injetada como env, default `10000`, host `0.0.0.0`).

Para publicar:

1. Crie uma conta gratuita em <https://render.com> (login pode ser com o GitHub, sem cartao).
2. Em **Dashboard → New → Web Service** escolha **Public Git Repository** e cole a URL:

   ```text
   https://github.com/HugoCDM/explorador-votos-rj-2026
   ```

3. **Language/Runtime:** Docker (o Render detecta o Dockerfile).
4. Escolha o plano **Free** e clique em **Create Web Service**.
5. O build baixa o banco (~380 MB, ~2–3 min) e sobe. O link publico fica em:

   ```text
   https://SEU_NOME.onrender.com
   ```

Observações:
- No plano Free o Render dorme apos ~15 min sem visitas e acorda em ~1 min na primeira visita (750 h/mes cobrem 24/7).
- Para atualizar o banco depois, suba um novo release asset com o mesmo nome e redeploy no Render.
- Fluxo alternativo via imagem Docker Hub: `.\build_and_push.ps1 -DockerUser SEU_USUARIO` e no Render use **Deploy an existing image from a registry** com `docker.io/SEU_USUARIO/explorador-votos-rj-2026:latest`.

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