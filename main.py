"""A cautious, long-only trend entry for the make.fun bars replay."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars


FAST = 10
SLOW = 40
FILTER = 120
STOP_BPS = 300
TAKE_PROFIT_BPS = 50
COOLDOWN_BARS = 240
MAX_SLIPPAGE_BPS = 500

history = []
fast = None
slow = None
filter_ema = None
previous_gap = None
peak = 0
last_exit_seq = -COOLDOWN_BARS
completed_cycle = False


def on_batch(state, batch):
    global fast, slow, filter_ema, previous_gap, peak, last_exit_seq, completed_cycle

    bars = batch["bars"]
    if not bars:
        return []
    bar = bars[0]
    close = int(bar["c"])
    history.append(close)

    def update(value, span):
        alpha_num = 2
        if value is None:
            return sum(history[-span:]) / span if len(history) >= span else None
        return value + alpha_num / (span + 1) * (close - value)

    fast = update(fast, FAST)
    slow = update(slow, SLOW)
    filter_ema = update(filter_ema, FILTER)
    gap = fast - slow if fast is not None and slow is not None else None
    holding = state.positions.get(bar["symbol"])

    if holding:
        peak = max(peak, close)
        cost_basis = holding.cost
        worth = state.value(bar["symbol"], holding.qty)
        stop_hit = peak > 0 and close * 10_000 <= peak * (10_000 - STOP_BPS)
        take_profit = worth * 10_000 >= cost_basis * (10_000 + TAKE_PROFIT_BPS)
        weak_trend = gap is not None and gap < 0 and take_profit
        deep_loss = worth * 10_000 <= cost_basis * 9_000
        if stop_hit or weak_trend or deep_loss or state.seq >= 1438:
            previous_gap = gap
            last_exit_seq = state.seq
            completed_cycle = True
            return [{"side": "sell", "symbol": bar["symbol"], "qty": holding.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    elif (gap is not None and previous_gap is not None and gap > 0 >= previous_gap
          and filter_ema is not None and close > filter_ema
          and state.seq - last_exit_seq >= COOLDOWN_BARS and not completed_cycle):
        stake = min(state.cash, state.equity)
        if stake >= int(state.hello["fees"]["min_notional_quote_units"]):
            peak = close
            previous_gap = gap
            # Reply with the orders for this just-closed bar; fills arrive on the next bar.
            return [{"side": "buy", "symbol": bar["symbol"],
                     "notional_quote_units": stake, "max_slippage_bps": MAX_SLIPPAGE_BPS}]

    previous_gap = gap
    return []


makefun_bars.run(on_batch)
