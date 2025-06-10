from pathlib import Path
from core.broker_client import BrokerClient
from core.execution import sell_puts, sell_calls
from core.state_manager import update_state, calculate_risk
from config.credentials import ALPACA_API_KEY, ALPACA_SECRET_KEY, IS_PAPER
from logging.strategy_logger import StrategyLogger
from logging.logger_setup import setup_logger
from core.cli_args import parse_args


def main():
    args = parse_args()
    
    # Initialize loggers
    strat_logger = StrategyLogger(enabled=args.strat_log)
    logger = setup_logger(level=args.log_level, to_file=args.log_to_file)

    strat_logger.set_fresh_start(args.fresh_start)

    # Load symbols to trade
    SYMBOLS_FILE = Path(__file__).parent.parent / "config" / "symbol_list.txt"
    with open(SYMBOLS_FILE, 'r') as f:
        SYMBOLS = [line.strip() for line in f if line.strip()]

    # Initialize Alpaca client
    client = BrokerClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=IS_PAPER)

    # Fetch your actual cash balance (not margin buying power)
    # Fetch your Alpaca account details
    account = client.trade_client.get_account()
    # Cash balance and options buying power
    cash_balance = float(account.cash)
    options_bp = float(getattr(account, 'options_buying_power', 0))
    logger.info(f"[Cash balance: ${cash_balance}, Options buying power: ${options_bp}]")

    if args.fresh_start:
        logger.info("Running in fresh start mode — liquidating all positions.")
        client.liquidate_all_positions()
        allowed_symbols = SYMBOLS
        # On fresh start, limit by both cash and options buying power
        buying_power = min(cash_balance, options_bp)
    else:
        # Track existing positions
        positions = client.get_positions()
        strat_logger.add_current_positions(positions)

        # Calculate current deployed risk in cash-equivalent terms
        current_risk = calculate_risk(positions)

        # Update state and potentially sell covered calls
        states = update_state(positions)
        strat_logger.add_state_dict(states)

        for symbol, state in states.items():
            if state["type"] == "long_shares":
                sell_calls(client, symbol, state["price"], state["qty"], strat_logger)

        # Determine which symbols are available for new puts
        allowed_symbols = list(set(SYMBOLS) - set(states.keys()))
        # Limit by free cash after risk and by options buying power
        buying_power = min(cash_balance - current_risk, options_bp)

    strat_logger.set_buying_power(buying_power)
    strat_logger.set_allowed_symbols(allowed_symbols)

    logger.info(f"[Effective buying power is ${buying_power}]")
    sell_puts(client, allowed_symbols, buying_power, strat_logger)

    # Persist any strategy logs
    strat_logger.save()


if __name__ == "__main__":
    main()
