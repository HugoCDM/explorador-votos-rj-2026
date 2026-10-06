import datetime
import os
import sys
import urllib.request

URL = os.environ.get(
    "RENDER_URL",
    "https://explorador-votos-rj-2026.onrender.com/api/health",
)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keepalive.log")

try:
    with urllib.request.urlopen(URL, timeout=30) as r:
        body = r.read(200).decode("utf-8", "replace")
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {r.status} {body}"
except Exception as e:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] ERRO: {e!r}"

with open(LOG, "a", encoding="utf-8") as f:
    f.write(line + "\n")

print(line)
sys.exit(0)