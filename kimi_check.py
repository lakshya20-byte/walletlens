import os

import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ.get("KIMI_API_KEY", "")
MODEL = os.environ.get("KIMI_MODEL", "")
BASE = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1")

if not KEY:
    raise SystemExit("KIMI_API_KEY is empty in .env")
if not MODEL:
    raise SystemExit("KIMI_MODEL is empty in .env (try kimi-k2-turbo-preview)")

facts = ('{"level": "medium", "scanned_blocks": 1000, "findings": [{"severity": "medium", '
         '"title": "Unlimited approval to a contract", "detail": "The contract 0x0000...10e2 '
         'can spend any amount of 5 tokens."}]}')
system = ("You explain wallet risk findings to a non-technical user. Use ONLY the facts in the "
          "JSON. Never invent addresses, tokens, amounts or transactions. Under 120 words. "
          "End with: 'This is not financial advice.'")

r = httpx.post(
    f"{BASE}/chat/completions", timeout=30,
    headers={"Authorization": f"Bearer {KEY}"},
    json={"model": MODEL, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": facts}]},
)
print("model:", MODEL)
print("status:", r.status_code)
if r.status_code == 200:
    print("reply:", r.json()["choices"][0]["message"]["content"][:400])
else:
    print("error body:", r.text[:300])
