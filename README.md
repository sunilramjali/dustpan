# Dustpan

> Tangem makes sure a human approves. Dustpan makes sure the human knows what they're approving.

A wallet-hygiene agent that runs next to the [Tangem MCP](https://mcp.tangem.org/). Ask it to "clean my wallet" and it sorts every token into three buckets:

1. **Recover:** dust worth swapping, ranked by the real Tangem swap quote (value after slippage and gas).
2. **Ignore:** dust that costs more in gas than it's worth.
3. **Quarantine:** spam tokens, plus **address-poisoning lookalikes** found in history (same first 4 and last 4 characters as an address you trust). They go on a blocklist, and a send guard refuses future sends to them.

Every swap and send is still signed by tapping your Tangem card. Dustpan itself only reads public chain data and never signs anything.

## Use it with your Tangem

**You need:** the Tangem app (6.8.1 or later) with your card, [Claude Code](https://claude.com/claude-code), [uv](https://docs.astral.sh/uv/), and a free [Etherscan API key](https://etherscan.io/apis).

1. **Get the code**
   ```bash
   git clone <this repo> dustpan && cd dustpan
   uv sync
   ```
2. **Register both MCP servers** (run inside the `dustpan` folder):
   ```bash
   claude mcp add --scope local -e ETHERSCAN_API_KEY=<your key> dustpan -- uv run --directory "$PWD" dustpan
   claude mcp add --transport http --scope local tangem https://mcp.tangem.org/mcp
   ```
3. **Connect your wallet:** start `claude`, type `/mcp`, pick **tangem**, choose Authenticate, then approve in the Tangem app.
   In the app, add the networks you use (e.g. Arbitrum One) and turn off dynamic addresses.
4. **Save the people you pay** so Dustpan can spot lookalikes of them:
   > Save Alice as a contact: 0x…
5. **Try it:**
   - `Clean my wallet` shows the three buckets and a 0-100 hygiene score.
   - `Recover the <token>` creates the swap; you approve it on your card.
   - `Pay 0.01 ETH to 0x…` runs the send guard first and refuses known lookalikes.

Dustpan tells Claude how to chain its tools with Tangem's, so this works from any folder.

**Networks:** Ethereum and Arbitrum One work with a free Etherscan key. Base needs a paid Etherscan plan; without a key Dustpan falls back to Blockscout, which can be flaky.

Your contacts (`data/contacts.json`) and blocklist (`data/blocklist.json`) stay on your machine and are gitignored.

## Tools

| Tool | What it does |
|---|---|
| `scan_wallet(address, network)` | Finds ERC-20s and poisoned lookalikes in recent history (via Etherscan V2; Blockscout fallback without a key) |
| `classify(tokens, gas_cost_native_wei)` | Sorts into recover / ignore / quarantine, with a 0-100 hygiene score |
| `gas_price(network)` | Current gas price, to cost a swap from the Tangem quote |
| `check_recipient(to_address)` | Send guard: ALLOW or BLOCK, called before every Tangem send |
| `add_contact(name, address)` | Saves a trusted contact |

Idea credit: the dust-recovery idea came from a fellow hacker at the Encode x Tangem MCP hackathon.

## License

MIT. See [LICENSE](LICENSE). Dustpan is a hackathon project: review it before trusting it with real funds.
