"""Read-only chain data from Blockscout (no API key needed)."""

import httpx

BLOCKSCOUT = {
    "base": "https://base.blockscout.com/api/v2",
    "ethereum": "https://eth.blockscout.com/api/v2",
    "arbitrum-one": "https://arbitrum.blockscout.com/api/v2",
}


def _get(network: str, path: str, params: dict | None = None) -> dict | list:
    base = BLOCKSCOUT.get(network)
    if not base:
        raise ValueError(f"unsupported network {network!r}; use one of {list(BLOCKSCOUT)}")
    r = httpx.get(f"{base}{path}", params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0 dustpan/0.1"})
    r.raise_for_status()
    return r.json()


def token_balances(network: str, address: str) -> list[dict]:
    """ERC-20 tokens held by address, with Blockscout metadata."""
    out = []
    for row in _get(network, f"/addresses/{address}/token-balances"):
        t = row.get("token") or {}
        if t.get("type") != "ERC-20":
            continue
        out.append({
            "contractAddress": t.get("address_hash") or t.get("address"),
            "name": t.get("name") or "",
            "symbol": t.get("symbol") or "",
            "decimals": int(t.get("decimals") or 0),
            "rawAmount": row.get("value") or "0",
            "holders": int(t.get("holders_count") or t.get("holders") or 0),
            "usdRate": t.get("exchange_rate"),  # display only; the Tangem quote is the true value
            "reputation": t.get("reputation"),
        })
    return out


def counterparties(network: str, address: str, pages: int = 3) -> list[dict]:
    """Addresses seen in history (native txs + token transfers), with direction."""
    me = address.lower()
    seen: dict[str, dict] = {}

    def add(addr: str | None, direction: str, kind: str, tx: str | None):
        if not addr or addr.lower() == me:
            return
        e = seen.setdefault(addr.lower(), {"address": addr, "sent": 0, "received": 0, "kinds": set(), "txs": []})
        e[direction] += 1
        e["kinds"].add(kind)
        if tx and len(e["txs"]) < 3:
            e["txs"].append(tx)

    for path, kind in (("/transactions", "tx"), ("/internal-transactions", "internal"), ("/token-transfers", "token")):
        params: dict | None = None
        for _ in range(pages):
            data = _get(network, f"/addresses/{address}{path}", params)
            for it in data.get("items", []):
                frm = (it.get("from") or {}).get("hash")
                to = (it.get("to") or {}).get("hash")
                tx = it.get("hash") or it.get("transaction_hash")
                if frm and frm.lower() == me:
                    add(to, "sent", kind, tx)
                else:
                    add(frm, "received", kind, tx)
            params = data.get("next_page_params")
            if not params:
                break

    for e in seen.values():
        e["kinds"] = sorted(e["kinds"])
    return list(seen.values())


# --- Etherscan V2 backend (one free key for every chain). Used when ETHERSCAN_API_KEY is set. ---
import os

CHAIN_IDS = {"ethereum": 1, "base": 8453, "arbitrum-one": 42161}


def _es(network: str, **params) -> list[dict]:
    key = os.environ.get("ETHERSCAN_API_KEY")
    if not key:
        raise RuntimeError("set ETHERSCAN_API_KEY (free at etherscan.io/apis)")
    import time
    for attempt in range(5):
        r = httpx.get("https://api.etherscan.io/v2/api",
                      params={"chainid": CHAIN_IDS[network], "apikey": key, **params}, timeout=20)
        r.raise_for_status()
        body = r.json()
        res = body.get("result")
        if isinstance(res, list):
            return res
        # Free tier allows 3 calls/sec and one scan makes 4 calls: back off and retry.
        if isinstance(res, str) and "rate limit" in res.lower():
            time.sleep(0.5 * (attempt + 1))
            continue
        break
    # Etherscan returns a string result on errors (rate limit, bad key, unsupported chain).
    # Fail loudly: an empty scan would look like a clean wallet.
    raise RuntimeError(f"Etherscan could not read {network} history: {body.get('message')} - {res}")


def es_tokens(network: str, address: str) -> list[dict]:
    """Tokens ever transferred to/from address. Balances come from Tangem get_balances."""
    toks: dict[str, dict] = {}
    for t in _es(network, module="account", action="tokentx", address=address, sort="desc", offset=200, page=1):
        toks.setdefault(t["contractAddress"].lower(), {
            "contractAddress": t["contractAddress"], "name": t.get("tokenName", ""),
            "symbol": t.get("tokenSymbol", ""), "decimals": int(t.get("tokenDecimal") or 0)})
    return list(toks.values())


def es_counterparties(network: str, address: str) -> list[dict]:
    me = address.lower()
    seen: dict[str, dict] = {}
    signed: set[str] = set()  # tx hashes this wallet actually signed
    for action, kind in (("txlist", "tx"), ("txlistinternal", "internal"), ("tokentx", "token")):
        for it in _es(network, module="account", action=action, address=address, sort="desc", offset=200, page=1):
            frm, to = (it.get("from") or "").lower(), (it.get("to") or "").lower()
            if action == "txlist" and frm == me:
                signed.add((it.get("hash") or "").lower())
            other, d = (to, "sent") if frm == me else (frm, "received")
            # Fake tokens can emit a Transfer "from" us that we never signed (address poisoning).
            # Such an entry must not make the recipient trusted.
            if kind == "token" and d == "sent" and (it.get("hash") or "").lower() not in signed:
                d, kind = "received", "forged-transfer"
            if not other or other == me:
                continue
            e = seen.setdefault(other, {"address": it["to"] if frm == me else it["from"],
                                        "sent": 0, "received": 0, "kinds": set(), "txs": []})
            e[d] += 1
            e["kinds"].add(kind)
            if len(e["txs"]) < 3:
                e["txs"].append(it.get("hash"))
    for e in seen.values():
        e["kinds"] = sorted(e["kinds"])
    return list(seen.values())
