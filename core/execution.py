import logging
from .strategy import filter_underlying, filter_options, score_options, select_options
from .logger import log_trades  # JSON logging helper
from models.contract import Contract
import numpy as np
from datetime import datetime, date
from alpaca.common.exceptions import APIError

logger = logging.getLogger(f"strategy.{__name__}")

def sell_puts(client, allowed_symbols, buying_power, strat_logger=None):
    """
    Scan allowed symbols and sell short puts up to the buying power limit.
    """
    trades = []
    try:
        if not allowed_symbols or buying_power <= 0:
            return

        logger.info("Searching for put options...")
        filtered_symbols = filter_underlying(client, allowed_symbols, buying_power)
        if strat_logger:
            strat_logger.set_filtered_symbols(filtered_symbols)

        if not filtered_symbols:
            logger.info("No symbols found with sufficient buying power.")
            return

        # Fetch and filter put options
        option_contracts = client.get_options_contracts(filtered_symbols, 'put')
        snapshots = client.get_option_snapshot([c.symbol for c in option_contracts])
        put_options = filter_options([
            Contract.from_contract_snapshot(contract, snapshots.get(contract.symbol, None))
            for contract in option_contracts
            if snapshots.get(contract.symbol, None)
        ])
        if strat_logger:
            strat_logger.log_put_options([p.to_dict() for p in put_options])

        if put_options:
            logger.info("Scoring put options...")
            scores = score_options(put_options)
            selected = select_options(put_options, scores)

            for p in selected:
                cost = 100 * p.strike
                if buying_power < cost:
                    break
                buying_power -= cost
                logger.info(f"Selling put: {p.symbol}")
                try:
                    order = client.market_sell(p.symbol)
                except APIError as e:
                    msg = str(e)
                    if '"code":40310000' in msg:
                        logger.warning(f"Skipping {p.symbol}: insufficient options buying power")
                        break
                    else:
                        raise

                # Format expiration date as string
                exp_val = getattr(p, 'expiration_date', None)
                if isinstance(exp_val, date):
                    exp_str = exp_val.strftime('%Y-%m-%d')
                else:
                    exp_str = str(exp_val) if exp_val else ''

                trade = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "ticker": p.underlying,
                    "type": "PUT",
                    "strike": p.strike,
                    "expiration": exp_str,
                    "premium": p.bid_price * 100,
                    "action": "SELL_TO_OPEN",
                    "status": getattr(order, 'status', 'UNKNOWN')
                }
                trades.append(trade)

                if strat_logger:
                    strat_logger.log_sold_puts([p.to_dict()])
        else:
            logger.info("No put options found with sufficient criteria.")
    except Exception as exc:
        logger.exception(f"Error in sell_puts: {exc}")
    finally:
        if trades:
            log_trades(trades)


def sell_calls(client, symbol, purchase_price, stock_qty, strat_logger=None):
    """
    Select and sell covered calls.
    """
    trades = []
    try:
        if stock_qty < 100:
            msg = (
                f"Not enough shares of {symbol} to cover short calls! "
                f"Only {stock_qty} shares held (need at least 100)."
            )
            logger.error(msg)
            raise ValueError(msg)

        logger.info(f"Searching for call options on {symbol}...")
        call_options = filter_options([
            Contract.from_contract(option, client)
            for option in client.get_options_contracts([symbol], 'call')
        ], purchase_price)
        if strat_logger:
            strat_logger.log_call_options([c.to_dict() for c in call_options])

        if call_options:
            scores = score_options(call_options)
            contract = call_options[np.argmax(scores)]
            logger.info(f"Selling call option: {contract.symbol}")
            try:
                order = client.market_sell(contract.symbol)
            except APIError as e:
                msg = str(e)
                if '"code":40310000' in msg:
                    logger.warning(f"Skipping {contract.symbol}: insufficient options buying power")
                else:
                    raise
                return

            # Format expiration date as string
            exp_val = getattr(contract, 'expiration_date', None)
            if isinstance(exp_val, date):
                exp_str = exp_val.strftime('%Y-%m-%d')
            else:
                exp_str = str(exp_val) if exp_val else ''

            trade = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "ticker": contract.underlying,
                "type": "CALL",
                "strike": contract.strike,
                "expiration": exp_str,
                "premium": contract.bid_price * 100,
                "action": "SELL_TO_OPEN",
                "status": getattr(order, 'status', 'UNKNOWN')
            }
            trades.append(trade)

            if strat_logger:
                strat_logger.log_sold_calls(contract.to_dict())
        else:
            logger.info(f"No viable call options found for {symbol}.")
    except Exception as exc:
        logger.exception(f"Error in sell_calls: {exc}")
    finally:
        if trades:
            log_trades(trades)
