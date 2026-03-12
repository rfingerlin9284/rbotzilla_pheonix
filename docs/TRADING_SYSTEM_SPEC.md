# 🏗️ RBOTZILLA PHOENIX: Technical System Specification

This document details the internal architecture and logic flow that results in the current "Professional Compounding" trading behavior.

## 1. The Compounding Engine (`util/margin_maximizer.py`)
This is the core mathematical model that replaced the old static sizing.

*   **Risk Profile**: Standardized at **2.0% Risk per Trade**. This means every trade is sized so that a Stop-Loss hit equals exactly 2.0% of the current account NAV.
*   **Leverage Sizing**: Operates on a **Max 8.0x Leverage per Symbol**. On a $6,800 account, this allows for up to ~$54,000 notional per trade, a significant increase from the previous $15,000 cap.
*   **Drawdown Protection**: If account drawdown exceeds **5%**, the system automatically cuts position sizes by **50%** until recovery.
*   **Dynamic Notional**:
    ```python
    target_notional = risk_amount / (sl_pips * pip_value)
    # Limited by leverage cap
    final_notional = min(target_notional, account_balance * 8.0)
    ```

## 2. Quality Selection Logic (`oanda_trading_engine.py`)
This "December Quality" logic ensures we don't just trade frequently, but trade *optimally*.

*   **Power-Curve Scaling**:
    *   Sizing uses an exponential curve: `scale = (conf - floor) ** 1.8`.
    *   A 72% confidence trade (the floor) sits at minimum size.
    *   An 88%+ confidence trade (the "Home Run") triggers a **25% size bonus** and hits the full 8x leverage cap.
*   **Hive Consensus Filter**:
    *   Before trade entry, the engine queries the **Rick Hive Mind**.
    *   If the technical strategy says `SELL` but the Hive Mind consensus is `BUY`, the trade is rejected as a `hive_conflict`.
    *   *Rationale*: Prevents spread bleed from entering positions that the multi-agent system would likely close early.

## 3. Guardian Safety Gates (`foundation/margin_correlation_gate.py`)
Hard-coded safety limits that prevent systemic account failure.

*   **Margin Cap**: Increased from 35% to **75%**. This provides the "headroom" necessary for aggressive compounding while still keeping a 25% reserve for volatility.
*   **Correlation Buckets**: Increased to **65,000 units**.
    *   Allows the bot to stack multiple trades in the same currency (e.g., selling `EUR_AUD` and buying `AUD_JPY` simultaneously) because it recognizes the higher conviction in the AUD trend.
*   **Trailing Efficiency**: Stop-losses are "loosened" to trigger Break-Even at **0.85R**, giving the trade 30% more breathing room to survive initial pullbacks.

## 4. Multi-Agent Coordination
The system operates as a "Hive" of specialized agents:

1.  **Technical Analysis Agent**: Scans the FX universe for EMA stacks, Fibonacci levels, and EMA200 scalping entries.
2.  **Risk Management Agent**: Enforces the 2.0% compounding risk and leverage caps.
3.  **Audit & Compliance Agent**: Validates all trades against the Charter rules (3.2:1 RR minimum) before execution.
4.  **Portfolio Orchestrator (`util/portfolio_orchestrator.py`)**:
    *   **Universal Position Registry**: Tracks all automated and manual (LLM) trades in one place.
    *   **5-Second Aggressive Monitor**: Closes any position that enters a "Red Alert" state (deep loss) within 5 seconds.
    *   **Net Positive Capital Engine**: Reallocates capital from stagnant or losing positions into high-performers every 120 seconds.

## 5. Auto-Resize & Self-Correction
*   **`RBOT_AUTO_RESIZE_POSITIONS`**: A self-healing loop that runs on startup. It calculates what the "ideal" size should be for every current open trade given the new $6.8k balance and 2.0% risk. If a trade is significantly undersized, it closes and re-opens it to lock in the compounding growth.
