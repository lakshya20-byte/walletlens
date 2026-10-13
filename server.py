import asyncio
import json
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from hypersync import enabled as hs_enabled, fetch_approvals_hs, HyperSyncError
from rules import assess_wallet, find_eoa_spenders
from api_v1 import build_router
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

RPC_URL = os.environ.get("MONAD_RPC_URL", "https://rpc1.monad.xyz")
KIMI_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "")
EXPLORER = os.environ.get("EXPLORER_TX_BASE", "https://monadvision.com/tx/")
CHUNK = int(os.environ.get("SCAN_CHUNK", "1000"))
MAX_CHUNKS = int(os.environ.get("SCAN_MAX_CHUNKS", "3"))
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "10"))

APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
UNLIMITED = 2**255
BASE = Path(__file__).parent

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

_hits = defaultdict(deque)
_cache = {}
CACHE_SECONDS = 300


class RpcError(Exception):
    pass


class Body(BaseModel):
    address: str


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def short(a: str) -> str:
    return a[:6] + "..." + a[-4:]


async def rpc(client, method, params):
    for attempt in range(3):
        try:
            response = await client.post(
                RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
            )
            response.raise_for_status()
            body = response.json()

            if "error" in body:
                error = body["error"]
                message = error.get("message", "RPC error")
                raise RpcError(str(message)[:200])

            if "result" not in body:
                raise RpcError("The data provider returned an invalid response.")

            return body["result"]

        except RpcError:
            # Preserve provider errors so range splitting can recognize them.
            raise
        except (httpx.HTTPError, ValueError) as exc:
            if attempt == 2:
                raise RpcError("The data provider did not respond.") from exc
            await asyncio.sleep(1.5)

async def fetch_approvals(client, owner):
    latest = int(await rpc(client, "eth_blockNumber", []), 16)
    owner_topic = "0x" + "0" * 24 + owner[2:].lower()
    sem = asyncio.Semaphore(2)

    # Scan the most recent blocks, using the configured chunk size.
    chunk_size = max(1, CHUNK)
    max_chunks = max(1, MAX_CHUNKS)
    n = min(max_chunks, latest // chunk_size + 1)

    async def get_logs(from_block, to_block):
        """Retry rejected block ranges by splitting them in half."""
        async with sem:
            try:
                return await rpc(
                    client,
                    "eth_getLogs",
                    [{
                        "fromBlock": hex(from_block),
                        "toBlock": hex(to_block),
                        "topics": [APPROVAL_TOPIC, owner_topic],
                    }],
                )
            except RpcError as exc:
                message = str(exc).lower()
                range_too_large = (
                    "block range too large" in message
                    or "range is too large" in message
                    or "query returned more than" in message
                    or "too many results" in message
                )

                if not range_too_large or from_block >= to_block:
                    raise

        # Do not hold the semaphore while recursively requesting subranges.
        midpoint = (from_block + to_block) // 2
        left, right = await asyncio.gather(
            get_logs(from_block, midpoint),
            get_logs(midpoint + 1, to_block),
        )
        return left + right

    async def one(i):
        to_block = latest - i * chunk_size
        from_block = max(0, to_block - chunk_size + 1)
        return await get_logs(from_block, to_block)

    parts = await asyncio.gather(*(one(i) for i in range(n)))
    logs = [log for part in parts for log in part]
    logs.sort(
        key=lambda log: (
            int(log["blockNumber"], 16),
            int(log["logIndex"], 16),
        )
    )

    latest_by_pair = {}
    for log in logs:
        if len(log.get("topics", [])) != 3 or len(log.get("data", "")) != 66:
            continue

        spender = "0x" + log["topics"][2][-40:]
        latest_by_pair[
            (log["address"].lower(), spender.lower())
        ] = {
            "token": log["address"],
            "spender": spender,
            "value": int(log["data"], 16),
            "tx_hash": log["transactionHash"],
        }

    active = [
        approval
        for approval in latest_by_pair.values()
        if approval["value"] > 0
    ]
    blocks_scanned = min(latest + 1, n * chunk_size)
    return latest, blocks_scanned, active


def run_rules(active):
    findings = []
    unlimited = [a for a in active if a["value"] >= UNLIMITED]
    for a in unlimited[:5]:
        findings.append({
            "severity": "high",
            "title": "Unlimited spending approval",
            "detail": f"Token {short(a['token'])} lets {short(a['spender'])} spend any amount of it.",
            "tx_hash": a["tx_hash"],
        })
    spenders = {a["spender"].lower() for a in active}
    if len(spenders) >= 5:
        findings.append({
            "severity": "medium",
            "title": "Many active approvals",
            "detail": f"{len(spenders)} different contracts can currently spend this wallet's tokens.",
            "tx_hash": active[-1]["tx_hash"],
        })
    level = "high" if any(f["severity"] == "high" for f in findings) else (
        "medium" if findings else "low")
    return level, findings


def fallback_summary(level, findings, blocks):
    if not findings:
        return (f"No risky token approvals were found in the last {blocks:,} blocks. "
                "This does not prove the wallet is safe. This is not financial advice.")
    return (f"{len(findings)} item(s) need attention (overall level: {level}). "
            "Review each finding and revoke approvals you do not recognise. "
            "This is not financial advice.")


async def explain(level, findings, blocks):
    if not (KIMI_KEY and KIMI_MODEL):
        return None
    facts = {"level": level, "scanned_blocks": blocks,
             "findings": [{k: f[k] for k in ("severity", "title", "detail")} for f in findings]}
    system = (
        "You explain wallet risk findings to a non-technical user. Use ONLY the facts in the "
        "JSON. Never invent addresses, tokens, amounts or transactions. Write under 120 words "
        "in plain English. If there are no findings, say nothing was found in the scanned "
        "window and that this does not prove the wallet is safe. End with: "
        "'This is not financial advice.'"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{KIMI_URL}/chat/completions",
                headers={"Authorization": f"Bearer {KIMI_KEY}"},
                json={"model": KIMI_MODEL, "temperature": 0.2, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(facts)}]},
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            return text[:900] or None
    except Exception:
        return None


@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
    )


@app.get("/llms.txt")
async def llms():
    return PlainTextResponse(
        "# WalletLens\n\n"
        "> Read-only scanner for token approvals on Monad. Paste a wallet "
        "address and see which addresses can spend its ERC-20 tokens, with "
        "a link to the transaction behind every finding.\n\n"
        "## What it checks\n"
        "- Active ERC-20 approvals, read from on-chain Approval events\n"
        "- Unlimited allowances, grouped by spender\n\n"
        "## What it does not check\n"
        "- NFT approvals, token reputation, known-malicious address lists, "
        "balances, transaction history\n\n"
        "## Notes\n"
        "- Read-only: never asks for keys, seed phrases or signatures\n"
        "- A result of no findings does not prove a wallet is safe\n"
        "- Data source: Envio HyperSync on Monad mainnet\n"
    )
@app.get("/")
async def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/developers")
async def developers():
    return FileResponse(BASE / "static" / "developers.html")    

@app.post("/api/analyze")
async def analyze(body: Body, request: Request):
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = fwd or (request.client.host if request.client else "unknown")
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return JSONResponse({"error": "Too many requests. Wait a minute and try again."}, 429)
    q.append(now)
    print("DEBUG: /api/analyze received request", flush=True)

    address = body.address.strip()
    if not ADDR_RE.match(address):
        return JSONResponse({"error": "Enter a valid address: 0x followed by 40 hex characters."}, 400)
    if not RPC_URL:
        return JSONResponse({"error": "The server is not configured yet."}, 500)

    key = address.lower()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]

  
    try:
        print("DEBUG: Starting chain-history scan", flush=True)

        if hs_enabled():
            print("DEBUG: Using HyperSync", flush=True)
            blocks, active = await asyncio.wait_for(
                fetch_approvals_hs(address),
                timeout=30,
            )
        else:
            print("DEBUG: Using Monad RPC", flush=True)
            async with httpx.AsyncClient(timeout=10) as client:
                _, blocks, active = await asyncio.wait_for(
                    fetch_approvals(client, address),
                    timeout=30,
                )

        print(
            f"DEBUG: Scan finished; blocks={blocks}, approvals={len(active)}",
            flush=True,
        )

    except asyncio.TimeoutError:
        print("DEBUG: Chain-history scan timed out", flush=True)
        return JSONResponse(
            {"error": "Chain scan timed out. Please try again shortly."},
            status_code=504,
        )
    except (RpcError, HyperSyncError) as e:
        print(f"DEBUG: Chain data error: {e}", flush=True)
        return JSONResponse(
            {"error": f"Could not read chain data: {e}"},
            status_code=502,
        )
    except Exception as e:
        print(f"DEBUG: Unexpected scan error: {type(e).__name__}: {e}", flush=True)
        return JSONResponse(
            {"error": "Something went wrong while scanning chain history."},
            status_code=500,
        )
   
    async with httpx.AsyncClient(timeout=10) as c:
        eoa = await find_eoa_spenders(c, active)

    level, findings = assess_wallet(active, eoa)
    ai_text = await explain(level, findings, blocks)

    result = {
        "address": address,
        "level": level,
        "findings": findings,
        "summary": ai_text or fallback_summary(level, findings, blocks),
        "ai": ai_text is not None,
        "scanned_blocks": blocks,
        "explorer_base": EXPLORER,
    }

    _cache[key] = (now, result)
    return result 

app.include_router(build_router(analyze, Body))
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=[])