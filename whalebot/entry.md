⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading⡿  Loading⣟  Loading⣯  Loading⣷  Loading⣾  Loading⣽  Loading⣻  Loading⢿  Loading          
Certainly! Here are three example entry conditions and their corresponding signal code snippets that can be integrated into the existing logic_loop or _evaluate_entry_signals method flow in the BybitApex class.  
I provide the snippets and how to tie them in your system, preserving your style and architecture.

---

### 1. Entry Condition: RSI Divergence Confirmation  
**Description:** Confirm entry only when RSI shows bullish/bearish divergence vs price trend, improving signal reliability.

```python
def _rsi_divergence_confirmed(self, direction: str) -> bool:
    s = self.state
    if len(s.ohlc) < 14:
        return False
    closes = np.array([c[3] for c in s.ohlc])
    rsi_values = []
    cfg = self.cfg
    period = 14

    # Calculate RSI for last period (simple version)
    def compute_rsi(data):
        deltas = np.diff(data)
        up = np.sum(deltas[deltas > 0])
        down = -np.sum(deltas[deltas < 0])
        rs = up / (down + 1e-9)
        return 100 - (100 / (1 + rs))

    for i in range(len(closes) - period, len(closes)):
        window = closes[max(i - period + 1, 0) : i + 1]
        if len(window) == period:
            rsi_values.append(compute_rsi(window))

    if len(rsi_values) < 2:
        return False

    # Bullish divergence: price lows decreasing but RSI lows increasing (for LONG)
    if direction == "LONG":
        price_lows = np.min(closes[-period :])
        prev_low = np.min(closes[-2 * period : -period])
        rsi_low = min(rsi_values[-1], rsi_values[-2])
        prev_rsi_low = min(rsi_values[:-2]) if len(rsi_values) > 2 else rsi_values[-2]
        return price_lows < prev_low and rsi_low > prev_rsi_low

    # Bearish divergence: price highs increasing but RSI highs decreasing (for SHORT)
    if direction == "SHORT":
        price_highs = np.max(closes[-period :])
        prev_high = np.max(closes[-2 * period : -period])
        rsi_high = max(rsi_values[-1], rsi_values[-2])
        prev_rsi_high = max(rsi_values[:-2]) if len(rsi_values) > 2 else rsi_values[-2]
        return price_highs > prev_high and rsi_high < prev_rsi_high

    return False
```

**Tie-in:** Call _rsi_divergence_confirmed inside _evaluate_entry_signals alongside your other confirmation checks.  
Example snippet inside _evaluate_entry_signals before execution:

```python
if not self._rsi_divergence_confirmed(direction):
    s.log(f"RSI divergence not confirmed for {direction} entry.", "warn")
    return
```

---

### 2. Entry Condition: Volume Spike Confirmation  
**Description:** Require a minimum volume spike relative to recent average volume to validate strength of the move before entry.

```python
def _recent_volume_spike(self, multiplier: float = 1.5) -> bool:
    s = self.state
    if len(s.ohlc) < 20:
        return False
    volumes = np.array([c[4] for c in s.ohlc])
    recent_vol = volumes[-1]
    avg_vol = np.mean(volumes[-20:-1])
    return recent_vol >= multiplier * avg_vol
```

**Tie-in:** Use this in _evaluate_entry_signals:

```python
if not self._recent_volume_spike():
    s.log("Volume spike condition not met; entry aborted.", "warn")
    return
```

You can adjust the multiplier parameter or make it configurable.

---

### 3. Entry Condition: EMA Crossover Filter  
**Description:** Require short-term EMA crossing above/below long-term EMA in the direction of the intended trade.

```python
def _ema_crossover_filter(self, direction: str) -> bool:
    s = self.state
    if len(s.ohlc) < 10:
        return False
    closes = np.array([c[3] for c in s.ohlc])
    short_period = 5
    long_period = 20
    short_ema = np.mean(closes[-short_period:])
    long_ema = np.mean(closes[-long_period:])

    if direction == "LONG":
        return short_ema > long_ema
    elif direction == "SHORT":
        return short_ema < long_ema
    return False
```

**Tie-in:** Integrate into _evaluate_entry_signals, for example:

```python
if not self._ema_crossover_filter(direction):
    s.log("EMA crossover does not confirm entry direction.", "warn")
    return
```

---

### How to Tie Conditions Together in _evaluate_entry_signals

Incorporate these calls into your existing method, for example:

```python
async def _evaluate_entry_signals(self) -> None:
    s, cfg = self.state, self.cfg
    if await self._check_entry_cooldown():
        return
    if self._check_entry_guards():
        return
    if not self._check_bollinger_filter():
        return

    direction, strength = self._compute_signal_components()
    if direction == "NONE":
        s.signal_confirmed_candles = 0
        s.last_signal_direction = "NONE"
        s.signal_strength = 0
        return

    s.signal_strength = int(strength)
    if self._check_ema_alignment(strength):
        return
    if not self._check_signal_confirmation(direction, strength):
        return

    # --- Add new entry conditions here ---
    if not self._rsi_divergence_confirmed(direction):
        s.log(f"RSI divergence not confirmed for {direction} entry.", "warn")
        return

    if not self._recent_volume_spike():
        s.log("Recent volume spike condition not met; entry aborted.", "warn")
        return

    if not self._ema_crossover_filter(direction):
        s.log("EMA crossover does not validate entry direction.", "warn")
        return

    # Proceed with entry execution if all conditions met
    await self._execute_entry_with_aggression(direction, strength)
    s.last_trade_ts = time.time()
```

---

If you want me to provide the full updated class methods with these integrated, or if you want additional custom tuning, just ask!

