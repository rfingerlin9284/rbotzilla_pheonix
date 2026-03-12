# 📟 RBOTZILLA PHOENIX: Operations Guide

This guide provides the core agent and human commands required to operate the trading system in its current **Professional Compounding** state.

## 🚀 Core Command: `rbot_ctl.sh`
The primary control interface is the `rbot_ctl.sh` script located in the `scripts/` directory.

### 1. Starting the Bot
To start the bot in the current **Practice** mode (Paper Trading):
```bash
./scripts/rbot_ctl.sh start
```

To start the bot in **Live** mode (Real Capital):
> [!WARNING]
> Ensure `RICK_PIN=841921` is set in your `.env` file before running live.
```bash
./scripts/rbot_ctl.sh start-live
```

### 2. Monitoring Performance
To see a live-refreshing dashboard of all open positions, P&L, and technical details:
```bash
./scripts/rbot_ctl.sh monitor
```

To view the raw logic narration (what the bot is thinking):
```bash
tail -f narration.jsonl
```

### 3. Restart & Update
Whenever you change configuration variables or need to reload the logic:
```bash
./scripts/rbot_ctl.sh restart
```

### 4. Stopping Operations
To gracefully shut down the engine and all background monitoring agents:
```bash
./scripts/rbot_ctl.sh stop
```

---

## 🛠️ Management Commands

### Mode Switching
If you need to flip between Practice and Live without starting the bot:
```bash
python scripts/switch_mode.py practice # Switch to Practice
python scripts/switch_mode.py live     # Switch to Live (requires PIN)
```

### Quality Control Tests
To run the Stop-Loss verification suite (checks if SL logic is active):
```bash
python scripts/qc_sl_test.py --verbose
```

### Account Status
For a quick snapshot of your balance, NAV, and margin usage:
```bash
python scripts/check_positions.py
```

---

## 🛡️ Operational Parameters
The current behavior is driven by these environment variables (configured in `rbot_ctl.sh`):

| Variable | Current Value | Purpose |
| :--- | :--- | :--- |
| `RBOT_MIN_SIGNAL_CONFIDENCE` | `0.72` | Minimum floor to even consider a trade (72%). |
| `RBOT_BE_TRIGGER_R` | `0.85` | Move Stop-Loss to Break-Even when trade reaches 0.85x Risk. |
| `RBOT_TRAIL_TRIGGER_R` | `1.50` | Start Trailing Stop after 1.5x Risk profit. |
| `RBOT_TRAIL_DISTANCE_R` | `0.35` | Distance to trail behind price (0.35x Risk). |
| `RBOT_AUTO_RESIZE_POSITIONS` | `1` | **ACTIVE**: Resizes old small trades to the new larger compounding size. |
| `RBOT_TP_COOLDOWN_MINUTES` | `3` | Wait only 3 minutes before retaking a pair after hitting TP. |
| `RBOT_GREEN_LOCK_MIN_PROFIT` | `10.0` | **AGGRESSIVE**: Move to Break-Even at 10 pips (~$80 profit). |
