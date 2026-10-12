import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.environ.get("MONAD_RPC_URL", "https://rpc1.monad.xyz")
UNLIMITED = 2**255
SYSTEM_RANGE = 0x10000  # very low addresses are protocol/system contracts: never flag


def short(a: str) -> str:
    return a[:6] + "..." + a[-4:]


async def find_eoa_spenders(client, active, limit=10):
    """Return spenders (with unlimited approvals) that have no contract code."""
    spenders = sorted({a["spender"].lower() for a in active if a["value"] >= UNLIMITED})[:limit]

    async def check(s):
        if int(s, 16) < SYSTEM_RANGE:
            return None
        try:
            r = await client.post(RPC_URL, json={
                "jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": [s, "latest"]})
            return s if r.json().get("result") == "0x" else None
        except Exception:
            return None  # on any failure, do not flag

    results = await asyncio.gather(*(check(s) for s in spenders))
    return {s for s in results if s}


def assess_wallet(active, eoa=frozenset()):
    findings = []
    by_spender = {}
    for a in active:
        if a["value"] >= UNLIMITED:
            by_spender.setdefault(a["spender"].lower(), []).append(a)

    for spender, items in list(by_spender.items())[:5]:
        n = len(items)
        tokens = f"{n} token{'s' if n != 1 else ''}"
        if spender in eoa:
            findings.append({
                "id": f"unlimited-approval-{spender}",
                "severity": "high",
                "title": "Unlimited approval to a plain wallet",
                "description": (f"{short(spender)} is a regular wallet, not a contract, and can spend "
                                f"any amount of {tokens}. Real apps use contracts, so this is a strong "
                                "warning sign."),
                "detail": (f"{short(spender)} is a regular wallet, not a contract, and can spend "
                           f"any amount of {tokens}. Real apps use contracts, so this is a strong "
                           "warning sign."),
                "evidence": items[-1]["tx_hash"],
                "source": "On-chain ERC-20 Approval logs via Envio HyperSync",
                "confidence": "high",
                "limitations": "The approval is verified on-chain, but the risk judgement is a heuristic.",
                "tx_hash": items[-1]["tx_hash"],
            })
        else:
            findings.append({
                "id": f"unlimited-approval-{spender}",
                "severity": "medium",
                "title": "Unlimited approval to a contract",
                "description": (f"The contract {short(spender)} can spend any amount of {tokens}. "
                                "Trading apps often ask for this. Revoke it if you no longer use that app."),
                "detail": (f"The contract {short(spender)} can spend any amount of {tokens}. "
                           "Trading apps often ask for this. Revoke it if you no longer use that app."),
                "evidence": items[-1]["tx_hash"],
                "source": "On-chain ERC-20 Approval logs via Envio HyperSync",
                "confidence": "high",
                "limitations": "The approval is verified on-chain, but the risk judgement is a heuristic.",
                "tx_hash": items[-1]["tx_hash"],
            })

    spenders = {a["spender"].lower() for a in active}
    if len(spenders) >= 5:
        findings.append({
            "id": "many-active-approvals",
            "severity": "medium",
            "title": "Many active approvals",
            "description": f"{len(spenders)} different addresses can currently spend this wallet's tokens.",
            "detail": f"{len(spenders)} different addresses can currently spend this wallet's tokens.",
            "evidence": active[-1]["tx_hash"],
            "source": "On-chain ERC-20 Approval logs via Envio HyperSync",
            "confidence": "high",
            "limitations": "The approvals are verified on-chain, but the risk judgement is a heuristic.",
            "tx_hash": active[-1]["tx_hash"],
        })

    level = ("high" if any(f["severity"] == "high" for f in findings)
             else "medium" if findings else "low")
    return level, findings
