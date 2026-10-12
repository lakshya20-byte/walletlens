import os
import re
import time
from collections import defaultdict, deque

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

load_dotenv()

RPC_URL = os.environ.get("MONAD_RPC_URL", "https://rpc1.monad.xyz")
LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "10"))
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
SYSTEM_RANGE = 0x10000  # very low addresses are protocol/system contracts

SOURCE = "On-chain ERC-20 Approval event logs (Envio HyperSync, RPC fallback)"
LIMITATIONS = ("Heuristic. Covers ERC-20 approvals only. Does not check token reputation, "
               "known-malicious address lists, NFT approvals or transaction history. "
               "No findings does not mean a wallet is safe.")

_hits = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")


def _limited(request: Request) -> bool:
    now, q = time.time(), _hits[_client_ip(request)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= LIMIT:
        return True
    q.append(now)
    return False


def to_v1(res: dict) -> dict:
    findings = []
    for i, f in enumerate(res["findings"], start=1):
        findings.append({
            "id": f"wl-{i}",
            "severity": f["severity"],
            "title": f["title"],
            "description": f["detail"],
            "evidence": {
                "tx_hash": f["tx_hash"],
                "explorer_url": res["explorer_base"] + f["tx_hash"],
            },
            "source": SOURCE,
            "confidence": {"approval_exists": "high", "risk_judgement": "heuristic"},
            "limitations": LIMITATIONS,
        })
    return {
        "version": "1",
        "chain": "monad-mainnet",
        "address": res["address"],
        "risk_level": res["level"],
        "scanned_blocks": res["scanned_blocks"],
        "findings": findings,
        "summary": res["summary"],
        "summary_written_by": "ai" if res.get("ai") else "rules",
        "limitations": LIMITATIONS,
    }


async def get_code(address: str):
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": [address, "latest"]})
        return r.json().get("result")


def build_router(analyze_fn, body_model) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/scan/{address}")
    async def scan(address: str, request: Request):
        res = await analyze_fn(body_model(address=address), request)
        if isinstance(res, JSONResponse):
            return res
        return to_v1(res)

    @router.get("/check")
    async def check(spender: str, request: Request, unlimited: bool = False):
        if _limited(request):
            return JSONResponse({"error": "Too many requests. Wait a minute and try again."}, 429)
        if not ADDR_RE.match(spender):
            return JSONResponse({"error": "spender must be 0x followed by 40 hex characters."}, 400)
        if int(spender, 16) < SYSTEM_RANGE:
            verdict = "unclassified"
            reason = "Very low address: a protocol or system contract. WalletLens cannot classify it."
        else:
            try:
                code = await get_code(spender)
            except Exception:
                return JSONResponse({"error": "Could not read chain data."}, 502)
            if not isinstance(code, str):
                return JSONResponse({"error": "Could not read chain data."}, 502)
            if code == "0x":
                verdict = "warn"
                reason = ("This address is a regular wallet, not a contract. "
                          "Real apps request approvals through contracts.")
            elif unlimited:
                verdict = "review"
                reason = ("A contract is asking for an unlimited allowance. Common with trading "
                          "apps; continue only if you trust the app.")
            else:
                verdict = "no_flag"
                reason = ("A contract with a limited allowance. No flag from WalletLens's checks; "
                          "this is not proof of safety.")
        return {"version": "1", "spender": spender, "verdict": verdict, "reason": reason,
                "checked": ["whether the spender address has contract code"],
                "limitations": LIMITATIONS}

    return router
