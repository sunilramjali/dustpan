"""Pure logic: bucket tokens and spot address-poisoning lookalikes."""

import re

SPAM_PATTERNS = [
    r"https?://", r"www\.", r"\.(com|io|org|net|xyz|app|site|top|claims?)\b",
    r"\bclaim", r"\breward", r"\bairdrop", r"\bvisit\b", r"\bvoucher", r"\$\s?\d",
]


INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def spam_reasons(token: dict) -> list[str]:
    text = f"{token.get('name', '')} {token.get('symbol', '')}"
    reasons = []
    if INVISIBLE.search(text):
        reasons.append("name hides invisible characters")
    if any(ch.isalpha() and not ch.isascii() for ch in text):
        reasons.append("name uses lookalike letters from other alphabets (fake ticker)")
    for p in SPAM_PATTERNS:
        if re.search(p, text, re.I):
            reasons.append(f"name matches spam pattern '{p}'")
            break
    if token.get("reputation") in ("scam", "spam"):
        reasons.append("flagged by explorer")
    return reasons


def classify(tokens: list[dict], gas_cost_native_wei: int, min_profit_ratio: float = 3.0) -> dict:
    """Bucket tokens.

    Each token may carry `quoteToNativeWei` (from the Tangem exchange_quote, null if no route).
    Worth recovering only if the quote beats gas by min_profit_ratio (token swaps need approve + swap, plus a card tap).
    """
    buckets = {"recover": [], "ignore": [], "quarantine": []}
    for t in tokens:
        item = {k: t.get(k) for k in ("symbol", "name", "contractAddress", "rawAmount", "decimals")}
        spam = spam_reasons(t)
        q = t.get("quoteToNativeWei")
        if spam:
            item["reason"] = "Never approve or swap: " + "; ".join(spam)
            buckets["quarantine"].append(item)
        elif q is None:
            item["reason"] = "No swap route from Tangem providers; leave it alone"
            buckets["ignore"].append(item)
        elif int(q) < gas_cost_native_wei * min_profit_ratio:
            item["reason"] = (f"Worth only {int(q)/1e18:.6f} ETH; approve + swap costs ~{2*gas_cost_native_wei/1e18:.6f} ETH in gas "
                              f"plus a card tap. Not worth it, leave it")
            buckets["ignore"].append(item)
        else:
            net = int(q) - gas_cost_native_wei
            item["netNativeWei"] = str(net)
            item["reason"] = f"Recovers ~{net/1e18:.6f} ETH after gas"
            buckets["recover"].append(item)
    buckets["recover"].sort(key=lambda i: -int(i["netNativeWei"]))
    return buckets


def _fingerprint(addr: str) -> tuple[str, str]:
    a = addr.lower().removeprefix("0x")
    return a[:4], a[-4:]


def find_lookalikes(trusted: list[str], candidates: list[str]) -> list[dict]:
    """Candidates whose first4/last4 match a trusted address but which differ from it."""
    hits = []
    fp = {_fingerprint(t): t for t in trusted}
    trusted_l = {t.lower() for t in trusted}
    for c in candidates:
        if c.lower() in trusted_l:
            continue
        t = fp.get(_fingerprint(c))
        if t:
            hits.append({"lookalike": c, "imitates": t})
    return hits


def score(buckets: dict, poisoned: int) -> int:
    s = 100 - 15 * len(buckets["quarantine"]) - 5 * len(buckets["recover"]) - 2 * len(buckets["ignore"]) - 25 * poisoned
    return max(0, min(100, s))
