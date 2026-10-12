import pytest
from fastapi.testclient import TestClient

import server
from rules import assess_wallet


VALID_ADDRESS = "0x" + "1" * 40
TX_HASH = "0x" + "a" * 64
CONTRACT = "0x" + "2" * 40
WALLET = "0x" + "3" * 40
UNLIMITED = 2**255


def approval(spender, value=UNLIMITED, token="0x" + "4" * 40, tx_hash=TX_HASH):
    return {"spender": spender, "value": value, "token": token, "tx_hash": tx_hash}


@pytest.mark.parametrize(
    "address",
    [
        VALID_ADDRESS,
        "0x" + "a" * 40,
    ],
)
def test_address_validation_accepts_valid_addresses(address):
    assert server.ADDR_RE.fullmatch(address)


@pytest.mark.parametrize(
    "address",
    [
        "",
        "0x" + "1" * 39,
        "1" + "0" * 40,
        "0x" + "g" * 40,
        "0x" + "1" * 39 + "' OR '1'='1",
        "0x" + "1" * 40 + "; DROP TABLE approvals;",
    ],
)
def test_address_validation_rejects_bad_addresses(address):
    assert not server.ADDR_RE.fullmatch(address)


def test_assess_wallet_returns_metadata_and_medium_contract_finding():
    _, findings = assess_wallet([approval(CONTRACT)])

    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "medium"
    assert finding["evidence"] == TX_HASH
    assert finding["tx_hash"] == TX_HASH
    assert finding["detail"] == finding["description"]
    assert finding["source"] == "On-chain ERC-20 Approval logs via Envio HyperSync"
    assert finding["confidence"] == "high"
    assert "heuristic" in finding["limitations"]
    assert set(
        ("id", "severity", "title", "description", "evidence", "source",
         "confidence", "limitations", "detail", "tx_hash")
    ).issubset(finding)


def test_assess_wallet_marks_plain_wallet_high():
    level, findings = assess_wallet([approval(WALLET)], {WALLET})

    assert level == "high"
    assert findings[0]["severity"] == "high"
    assert findings[0]["title"] == "Unlimited approval to a plain wallet"


def test_assess_wallet_ignores_limited_only_approvals():
    level, findings = assess_wallet([approval(CONTRACT, value=UNLIMITED - 1)])

    assert level == "low"
    assert findings == []


def test_assess_wallet_groups_findings_by_spender():
    approvals = [
        approval(CONTRACT, token="0x" + "4" * 40),
        approval(CONTRACT, token="0x" + "5" * 40),
        approval(WALLET, token="0x" + "6" * 40),
    ]

    _, findings = assess_wallet(approvals, {WALLET})

    assert len(findings) == 2
    assert {finding["severity"] for finding in findings} == {"medium", "high"}


@pytest.mark.parametrize(
    "address",
    ["", "0x" + "1" * 39, "1" + "0" * 40, "0x" + "z" * 40],
)
def test_analyze_rejects_bad_input_without_network_calls(monkeypatch, address):
    async def unexpected_network_call(*args, **kwargs):
        raise AssertionError("network call should not occur for invalid input")

    monkeypatch.setattr(server, "fetch_approvals_hs", unexpected_network_call)
    monkeypatch.setattr(server, "fetch_approvals", unexpected_network_call)
    monkeypatch.setattr(server, "find_eoa_spenders", unexpected_network_call)

    with TestClient(server.app) as client:
        response = client.post("/api/analyze", json={"address": address})

    assert response.status_code == 400
    assert "valid address" in response.json()["error"]
