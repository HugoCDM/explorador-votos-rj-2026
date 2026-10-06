FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=10000 \
    DB_PATH=/app/data/votos_cloud.sqlite

# URL do banco enxuto (release asset do GitHub, ~377 MB).
# Sobrescreva com: docker build --build-arg DB_URL=... 
ARG DB_URL=https://github.com/HugoCDM/explorador-votos-rj-2026/releases/latest/download/votos_cloud.sqlite

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY server.py .
COPY web web

RUN mkdir -p data \
    && curl -fL "$DB_URL" -o data/votos_cloud.sqlite \
    && ls -lh data/votos_cloud.sqlite

EXPOSE 10000

CMD ["python", "server.py", "--host", "0.0.0.0"]