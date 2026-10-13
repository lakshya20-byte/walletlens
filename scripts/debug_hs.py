import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ.get("ENVIO_API_TOKEN", "")
RPC = os.environ.get("MONAD_RPC_URL", "https://rpc1.monad.xyz")
HS = os.environ.get("HYPERSYNC_URL", "https://monad.hypersync.xyz")
TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

if not TOKEN:
    raise SystemExit("ENVIO_API_TOKEN is missing from .env")

height = int(httpx.post(
    RPC, timeout=15,
    json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
).json()["result"], 16)
print("chain height:", height)

body = {
    "from_block": height - 50000,
    "to_block": height,
    "logs": [{"topics": [[TOPIC]]}],
    "field_selection": {"log": [
        "block_number", "log_index", "transaction_hash", "address",
        "data", "topic0", "topic1", "topic2", "topic3"]},
}
r = httpx.post(f"{HS}/query", json=body, timeout=30,
               headers={"Authorization": f"Bearer {TOKEN}"})
print("status:", r.status_code)
res = r.json()
print("top-level keys:", list(res.keys()))

logs = [l for page in res.get("data", []) for l in page.get("logs", [])]
print("approval logs returned:", len(logs))
if logs:
    print("first log:", json.dumps(logs[0], indent=2))
else:
    print("raw response (trimmed):", json.dumps(res)[:600])

found = {}
for l in logs:
    d = l.get("data") or ""
    if l.get("topic3") or len(d) != 66 or not l.get("topic1"):
        continue
    if int(d, 16) >= 2**255:
        found["0x" + l["topic1"][-40:]] = l.get("transaction_hash")

print("\nwallets with an unlimited approval in the last 50,000 blocks:")
for owner, tx in list(found.items())[:5]:
    print(owner, tx)
if not found:
    print("(none found in this window)")