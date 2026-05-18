import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from ta.momentum import RSIIndicator

# Download TSLA data for 5 years
symbol = 'TSLA'
start = pd.Timestamp.today() - pd.DateOffset(years=5)
end = pd.Timestamp.today()

# yfinance will handle date string
data = yf.download(symbol, start=start, end=end)

data.dropna(inplace=True)

# Calculate moving averages
data['MA6'] = data['Close'].rolling(window=6).mean()
data['MA18'] = data['Close'].rolling(window=18).mean()

# Calculate RSI
rsi_period = 14
rsi_indicator = RSIIndicator(close=data['Close'], window=rsi_period)
data['RSI'] = rsi_indicator.rsi()

# Detect bullish and bearish engulfing patterns
bullish = (
    (data['Close'].shift(1) < data['Open'].shift(1)) &
    (data['Open'] < data['Close']) &
    (data['Open'] <= data['Close'].shift(1)) &
    (data['Close'] >= data['Open'].shift(1))
)

bearish = (
    (data['Close'].shift(1) > data['Open'].shift(1)) &
    (data['Open'] > data['Close']) &
    (data['Open'] >= data['Close'].shift(1)) &
    (data['Close'] <= data['Open'].shift(1))
)

# Generate signals
signals = pd.DataFrame(index=data.index)
signals['signal'] = 0

long_condition = (
    (data['MA6'] > data['MA18']) &
    (data['MA6'].shift(1) <= data['MA18'].shift(1)) &
    (data['RSI'] > 50) &
    bullish
)

exit_condition = (
    (data['MA6'] < data['MA18']) |
    (data['RSI'] < 50) |
    bearish
)

signals.loc[long_condition, 'signal'] = 1
signals.loc[exit_condition, 'signal'] = 0
signals['signal'] = signals['signal'].ffill().fillna(0)

# Position sizing and backtest
initial_capital = 10000.0
cash = initial_capital
shares = 0
portfolio_values = []
trade_returns = []
trade_outcomes = []
entry_price = 0

for i in range(len(data)):
    if i == 0:
        portfolio_values.append(cash)
        continue
    # entry
    if signals['signal'].iloc[i] == 1 and signals['signal'].iloc[i-1] == 0:
        risk_per_trade = 0.01 * cash
        stop_price = data['Low'].iloc[i-1]
        risk_per_share = data['Close'].iloc[i] - stop_price
        if risk_per_share <= 0:
            portfolio_values.append(cash + shares * data['Close'].iloc[i])
            continue
        size = max(int(risk_per_trade / risk_per_share), 1)
        cost = size * data['Close'].iloc[i]
        if cost > cash:
            size = int(cash / data['Close'].iloc[i])
            cost = size * data['Close'].iloc[i]
        shares += size
        cash -= cost
        entry_price = data['Close'].iloc[i]
    # exit
    elif signals['signal'].iloc[i] == 0 and signals['signal'].iloc[i-1] == 1 and shares > 0:
        proceeds = shares * data['Close'].iloc[i]
        cash += proceeds
        tr = (data['Close'].iloc[i] - entry_price) / entry_price
        trade_returns.append(tr)
        trade_outcomes.append(tr > 0)
        shares = 0
    portfolio_values.append(cash + shares * data['Close'].iloc[i])

# Close any open position at end
if shares > 0:
    final_price = data['Close'].iloc[-1]
    cash += shares * final_price
    tr = (final_price - entry_price) / entry_price
    trade_returns.append(tr)
    trade_outcomes.append(tr > 0)
    shares = 0
portfolio_values[-1] = cash

portfolio_series = pd.Series(portfolio_values, index=data.index)

# Metrics
returns = portfolio_series.pct_change().dropna()
if returns.std() != 0:
    sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std()
else:
    sharpe_ratio = 0
win_rate = np.mean(trade_outcomes) if trade_outcomes else 0
cumulative_return = (portfolio_series.iloc[-1] - initial_capital) / initial_capital
rolling_max = portfolio_series.cummax()
drawdown = (portfolio_series - rolling_max) / rolling_max
max_drawdown = drawdown.min()

# Buy and hold curve
buy_hold = (data['Close'] / data['Close'].iloc[0]) * initial_capital

# Plot
plt.figure(figsize=(12, 6))
plt.plot(portfolio_series, label='Strategy')
plt.plot(buy_hold, label='Buy & Hold')
plt.legend()
plt.title('Equity Curve: Strategy vs Buy & Hold')
plt.tight_layout()
plt.savefig('equity_curve.png')

print(f"Final Portfolio Value: {portfolio_series.iloc[-1]:.2f}")
print(f"Cumulative Return: {cumulative_return:.2%}")
print(f"Win Rate: {win_rate:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
print(f"Max Drawdown: {max_drawdown:.2%}")
