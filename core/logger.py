import os, json
from datetime import datetime

def log_trades(trades):
    """Dump the list of trade-dicts to logs/trades_<YYYYMMDD_HHMMSS>.json."""
    os.makedirs("logs", exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"logs/trades_{ts}.json"
    with open(path, "w") as f:
        json.dump(trades, f, indent=2)
    print(f"[logger] saved trades to {path}")
