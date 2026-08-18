import os
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

print("TESTANDO TELEGRAM...")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

r = requests.post(
    url,
    json={
        "chat_id": CHAT_ID,
        "text": "✅ TESTE OK — Monitoramento Eleitoral RJ 2026"
    },
    timeout=30
)

print("HTTP:", r.status_code)
print(r.text)

r.raise_for_status()

print("TELEGRAM FUNCIONANDO!")
