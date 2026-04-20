"""
BTCUSDT / ETHUSDT Stat-Arb Backtest (Binance USDⓈ-M Perps)
15m, Aug 2025
Kalman/RLS hedge ratio + RSI filter
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import ccxt
from dataclasses import dataclass

TIMEFRAME = "15m"
START = "2025-08-01 00:00:00"
END = "2025-09-01 00:00:00"

SYMBOL_Y = "BTC/USDT:USDT"
SYMBOL_X = "ETH/USDT:USDT"

INITIAL_EQUITY = 28000.0
RISK_PER_TRADE = 0.02
TP_MULT_R = 2.0

MAKER_FEE = 0.0002
TAKER_FEE = 0.0005
USE_TAKER = True

Z_ENTRY = 2.0
Z_EXIT = 0.3
RSI_LEN = 14
RSI_LO = 30
RSI_HI = 70

SPREAD_VOL_WIN = 96
STOP_MULT_SIGMA = 1.0

DELTA = 1e-4
R_MEAS = 1e-3


def to_ms(dt_str: str) -> int:
    return int(pd.Timestamp(dt_str, tz="UTC").timestamp() * 1000)


def fetch_ohlcv_binance_usdm(symbol, timeframe, start_ms, end_ms, limit=1500):
    ex = ccxt.binanceusdm({"enableRateLimit": True})
    all_rows = []
    since = start_ms
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        if not batch:
            break
        dfb = pd.DataFrame(batch, columns=["ts", "open", "high", "low", "close", "vol"])
        all_rows.append(dfb)
        last_ts = int(dfb["ts"].iloc[-1])
        since = last_ts + 1
        if last_ts >= end_ms:
            break
    df = pd.concat(all_rows, ignore_index=True).drop_duplicates("ts")
    df = df[(df["ts"] >= start_ms) & (df["ts"] < end_ms)].copy()
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("time", inplace=True)
    return df


def rsi(series: pd.Series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / length, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / length, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))


def kalman_rls_beta(y, x, delta=1e-4, r_meas=1e-3):
    n = len(y)
    theta = np.zeros((n, 2))
    P = np.eye(2) * 1.0
    Q = np.eye(2) * delta
    R = r_meas
    th = np.array([0.0, 1.0], dtype=float)

    for t in range(n):
        H = np.array([1.0, x[t]], dtype=float).reshape(1, 2)
        P = P + Q
        yhat = float(H @ th.reshape(2, 1))
        e = y[t] - yhat
        S = float(H @ P @ H.T + R)
        K = (P @ H.T) / S
        th = th + (K.flatten() * e)
        P = P - (K @ H @ P)
        theta[t] = th

    return theta[:, 0], theta[:, 1]


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    beta_entry: float
    btc_entry: float
    eth_entry: float
    btc_qty: float
    eth_qty: float
    entry_spread: float
    exit_spread: float
    entry_z: float
    exit_z: float
    stop_dist: float
    tp_dist: float
    fees_paid: float
    pnl_net: float
    r_multiple: float
    duration_bars: int


def max_drawdown(equity_series: pd.Series):
    peak = equity_series.cummax()
    dd = equity_series / peak - 1.0
    return float(dd.min()), dd


def sharpe_ratio_bar(equity_series: pd.Series, bars_per_day=96):
    rets = equity_series.pct_change().fillna(0.0)
    if rets.std() < 1e-12:
        return 0.0
    ann = np.sqrt(bars_per_day * 365)
    return float(rets.mean() / rets.std() * ann)


def main():
    start_ms, end_ms = to_ms(START), to_ms(END)

    btc = fetch_ohlcv_binance_usdm(SYMBOL_Y, TIMEFRAME, start_ms, end_ms)
    eth = fetch_ohlcv_binance_usdm(SYMBOL_X, TIMEFRAME, start_ms, end_ms)

    df = pd.DataFrame(index=btc.index.union(eth.index)).sort_index()
    df["btc"] = btc["close"]
    df["eth"] = eth["close"]
    df = df.dropna()

    df["y"] = np.log(df["btc"].values)
    df["x"] = np.log(df["eth"].values)

    alpha, beta = kalman_rls_beta(df["y"].values, df["x"].values, delta=DELTA, r_meas=R_MEAS)
    df["alpha"] = alpha
    df["beta"] = beta

    df["spread"] = df["y"] - (df["alpha"] + df["beta"] * df["x"])
    df["spread_mu"] = df["spread"].rolling(SPREAD_VOL_WIN).mean()
    df["spread_sig"] = df["spread"].rolling(SPREAD_VOL_WIN).std()
    df["z"] = (df["spread"] - df["spread_mu"]) / (df["spread_sig"] + 1e-12)
    df["rsi_spread"] = rsi(df["spread"], RSI_LEN)

    df = df.dropna()

    fee_rate = TAKER_FEE if USE_TAKER else MAKER_FEE

    equity = INITIAL_EQUITY
    equity_curve = []
    trades = []

    in_pos = False
    side = None
    entry_i = None

    entry_spread = entry_z = None
    entry_beta = None
    entry_btc = entry_eth = None
    btc_qty = eth_qty = None
    stop_dist = tp_dist = None
    risk_dollars = None
    fees_paid_entry = 0.0

    for i, (ts, row) in enumerate(df.iterrows()):
        btc_px = float(row["btc"])
        eth_px = float(row["eth"])
        sp = float(row["spread"])
        z = float(row["z"])
        sig = float(row["spread_sig"])
        b = float(row["beta"])
        rsi_s = float(row["rsi_spread"])

        equity_curve.append((ts, equity))

        if not in_pos:
            stop_dist = STOP_MULT_SIGMA * sig
            if stop_dist <= 0:
                continue
            tp_dist = TP_MULT_R * stop_dist

            enter_short = (z >= Z_ENTRY) and (rsi_s >= RSI_HI)
            enter_long = (z <= -Z_ENTRY) and (rsi_s <= RSI_LO)

            if enter_short or enter_long:
                side = "short_spread" if enter_short else "long_spread"
                in_pos = True
                entry_i = i

                entry_spread = sp
                entry_z = z
                entry_beta = b
                entry_btc = btc_px
                entry_eth = eth_px

                risk_dollars = equity * RISK_PER_TRADE
                btc_qty = risk_dollars / (entry_btc * stop_dist + 1e-12)
                eth_qty = entry_beta * (entry_btc / entry_eth) * btc_qty

                notional_btc = abs(btc_qty) * entry_btc
                notional_eth = abs(eth_qty) * entry_eth
                fees_paid_entry = fee_rate * (notional_btc + notional_eth)

                equity -= fees_paid_entry
                continue

        if in_pos:
            dspread = sp - entry_spread

            if side == "long_spread":
                pnl_gross = (btc_qty * btc_px - btc_qty * entry_btc) + (-eth_qty * eth_px + eth_qty * entry_eth)
                stop_hit = dspread <= -stop_dist
                tp_hit = dspread >= +tp_dist
            else:
                pnl_gross = (-btc_qty * btc_px + btc_qty * entry_btc) + (eth_qty * eth_px - eth_qty * entry_eth)
                stop_hit = dspread >= +stop_dist
                tp_hit = dspread <= -tp_dist

            mr_exit = abs(z) <= Z_EXIT

            if stop_hit or tp_hit or mr_exit:
                notional_btc_exit = abs(btc_qty) * btc_px
                notional_eth_exit = abs(eth_qty) * eth_px
                fees_exit = fee_rate * (notional_btc_exit + notional_eth_exit)

                pnl_net = pnl_gross - fees_exit
                equity += pnl_net

                fees_total = fees_paid_entry + fees_exit
                r_mult = pnl_net / (risk_dollars + 1e-12)

                trades.append(
                    Trade(
                        entry_time=df.index[entry_i],
                        exit_time=ts,
                        side=side,
                        beta_entry=entry_beta,
                        btc_entry=entry_btc,
                        eth_entry=entry_eth,
                        btc_qty=btc_qty if side == "long_spread" else -btc_qty,
                        eth_qty=-eth_qty if side == "long_spread" else eth_qty,
                        entry_spread=entry_spread,
                        exit_spread=sp,
                        entry_z=entry_z,
                        exit_z=z,
                        stop_dist=stop_dist,
                        tp_dist=tp_dist,
                        fees_paid=fees_total,
                        pnl_net=pnl_net,
                        r_multiple=r_mult,
                        duration_bars=i - entry_i,
                    )
                )

                in_pos = False
                side = None
                entry_i = None

    equity_curve = pd.DataFrame(equity_curve, columns=["time", "equity"]).set_index("time")
    trade_df = pd.DataFrame([t.__dict__ for t in trades])

    final_equity = float(equity_curve["equity"].iloc[-1])
    net_pnl = final_equity - INITIAL_EQUITY
    ret_pct = net_pnl / INITIAL_EQUITY

    mdd, dd_series = max_drawdown(equity_curve["equity"])
    sharpe = sharpe_ratio_bar(equity_curve["equity"])

    num_trades = len(trade_df)
    win_rate = float((trade_df["pnl_net"] > 0).mean()) if num_trades else 0.0
    avg_r = float(trade_df["r_multiple"].mean()) if num_trades else 0.0
    profit_factor = (
        trade_df.loc[trade_df["pnl_net"] > 0, "pnl_net"].sum()
        / (-trade_df.loc[trade_df["pnl_net"] < 0, "pnl_net"].sum() + 1e-12)
        if num_trades
        else 0.0
    )
    avg_duration_hours = float(trade_df["duration_bars"].mean() * 0.25) if num_trades else 0.0
    fees_sum = float(trade_df["fees_paid"].sum()) if num_trades else 0.0

    print("========== BINANCE USDⓈ-M STAT-ARB (Aug 2025, 15m) ==========")
    print(f"Initial Equity: ${INITIAL_EQUITY:,.2f}")
    print(f"Final Equity:   ${final_equity:,.2f}")
    print(f"Net P&L:        ${net_pnl:,.2f}  ({ret_pct*100:.2f}%)")
    print(f"Max Drawdown:   {mdd*100:.2f}%")
    print(f"Sharpe (ann.):  {sharpe:.2f}")
    print(f"Trades:         {num_trades}")
    print(f"Win rate:       {win_rate*100:.1f}%")
    print(f"Avg R-multiple: {avg_r:.2f}R")
    print(f"Profit Factor:  {profit_factor:.2f}")
    print(f"Avg Duration:   {avg_duration_hours:.2f} hours")
    print(f"Total Fees:     ${fees_sum:,.2f}")
    print("=============================================================")

    plt.figure(figsize=(12, 5))
    plt.plot(equity_curve.index, equity_curve["equity"])
    plt.title("Equity Curve - BTCUSDT/ETHUSDT Stat-Arb (USDⓈ-M, 15m, Aug 2025)")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Equity ($)")
    plt.grid(True)
    plt.show()

    plt.figure(figsize=(12, 4))
    plt.plot(dd_series.index, dd_series.values)
    plt.title("Drawdown")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Drawdown")
    plt.grid(True)
    plt.show()

    equity_curve.to_csv("equity_curve_aug2025_usdm.csv")
    trade_df.to_csv("trades_aug2025_usdm.csv", index=False)

    print("Saved: equity_curve_aug2025_usdm.csv, trades_aug2025_usdm.csv")
    if num_trades:
        print(trade_df.tail(10))


if __name__ == "__main__":
    main()
