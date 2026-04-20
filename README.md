# Capitol Trades Mirror Bot (Alpaca Paper Trading)

This project schedules an automated **paper-trading** bot that:

1. Pulls recent stock trades from Capitol Trades.
2. Scores members by trailing realized performance (from copied trades in your local ledger).
3. Selects the "highest-return" traders in your configured lookback window.
4. Mirrors their newest disclosed trades into your Alpaca **paper** account.

> ⚠️ This is educational code, **not investment advice**. Congressional disclosures are delayed and may be incomplete.

## Features

- Scheduled jobs (cron or interval).
- Capitol Trades client with paging.
- Alpaca paper order placement.
- Local SQLite ledger for dedupe + historical copy-performance scoring.
- Risk controls:
  - max total notional per run
  - max positions per run
  - optional allowlist/blocklist

## Quick start

### 1) Create environment + install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure `.env`

```bash
cp .env.example .env
```

Set:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- optional strategy settings

### 3) Run once

```bash
python -m bot.main --once
```

### 4) Run scheduler

```bash
python -m bot.main
```

## Configuration

See `.env.example` for all options.

Key fields:

- `SCHEDULE_CRON`: cron schedule (UTC), default `*/30 * * * *`
- `LOOKBACK_DAYS`: performance window for ranking members
- `TOP_N_MEMBERS`: number of members to mirror
- `MAX_NOTIONAL_PER_RUN`: run budget cap
- `NOTIONAL_PER_TRADE`: target notional each copied trade

## How "highest-return" is computed

Each mirrored trade is stored in `state/trades.db`. When a SELL closes prior copied BUY quantity, PnL is realized (FIFO by date). A member score is:

`realized_pnl / invested_capital` over the trailing lookback window.

Members with insufficient history are ignored until they have closed trades in the window.

## Security note

If API credentials were ever shared publicly, revoke and rotate them immediately.

## Caveats

- Capitol Trades may change response format or rate limits.
- Congressional trade disclosures are delayed by law.
- This bot intentionally defaults to paper trading endpoint.
