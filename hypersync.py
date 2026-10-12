import os

import httpx
from dotenv import load_dotenv

load_dotenv()

HS_URL = os.environ.get("HYPERSYNC_URL", "https://monad.hypersync.xyz")
TOKEN = os.environ.get("ENVIO_API_TOKEN", "")
MAX_PAGES = int(os.environ.get("HS_MAX_PAGES", "20"))
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
FIELDS = ["block_number", "log_index", "transaction_hash", "address",
          "data", "topic0", "topic1", "topic2", "topic3"]


class HyperSyncError(Exception):
    pass


def enabled() -> bool:
    return bool(TOKEN)


def _int(v):
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    return int(v, 16) if str(v).startswith("0x") else int(v)


async def fetch_approvals_hs(owner: str):
    """Return (blocks_covered, active_approvals) using full chain history."""
    owner_topic = "0x" + "0" * 24 + owner[2:].lower()
    headers = {"Authorization": f"Bearer {TOKEN}"}
    from_block, height, logs = 0, None, []

    async with httpx.AsyncClient(timeout=20) as client:
        for _ in range(MAX_PAGES):
            body = {
                "from_block": from_block,
                "logs": [{"topics": [[APPROVAL_TOPIC], [owner_topic]]}],
                "field_selection": {"log": FIELDS},
            }
            try:
                r = await client.post(f"{HS_URL}/query", json=body, headers=headers)
            except httpx.HTTPError:
                raise HyperSyncError("The indexer did not respond.")
            if r.status_code in (401, 403):
                raise HyperSyncError("The indexer rejected the API token.")
            if r.status_code >= 400:
                raise HyperSyncError(f"The indexer returned an error ({r.status_code}).")
            try:
                res = r.json()
            except ValueError:
                raise HyperSyncError("The indexer sent an unreadable response.")

            for page in res.get("data", []):
                logs.extend(page.get("logs", []))
            height = res.get("archive_height", height)
            nxt = res.get("next_block")
            if nxt is None or nxt <= from_block or (height is not None and nxt > height):
                break
            from_block = nxt

    logs.sort(key=lambda l: (_int(l.get("block_number")), _int(l.get("log_index"))))
    latest = {}
    for l in logs:
        data = l.get("data") or ""
        if l.get("topic3") or len(data) != 66 or not l.get("topic2"):
            continue  # keep ERC-20 Approval only (skips NFT approvals)
        spender = "0x" + l["topic2"][-40:]
        latest[(l["address"].lower(), spender.lower())] = {
            "token": l["address"], "spender": spender,
            "value": int(data, 16), "tx_hash": l["transaction_hash"],
        }
    active = [a for a in latest.values() if a["value"] > 0]
    return (height or 0), active
