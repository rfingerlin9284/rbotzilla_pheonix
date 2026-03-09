---
description: Universal Restart
---

This workflow will safely shut down all trading systems, clear the environment, and turn the engine back on cleanly.

// turbo-all
1. Restart the trading engine
```bash
cd /home/rfing/RBOTZILLA_PHOENIX
./turn_off.sh
echo "CONFIRM LIVE" | ./start_trading.sh live
```
