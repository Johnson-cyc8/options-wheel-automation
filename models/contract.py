from typing import Optional
from dataclasses import dataclass, field
import datetime
from core.broker_client import BrokerClient
from core.utils import get_ny_timestamp
import json

@dataclass
class Contract:
    underlying: str
    symbol: str
    contract_type: str
    expiration_date: datetime.date  # Expiration date from Alpaca API

    dte: Optional[float] = None  # Days to expiration
    strike: Optional[float] = None
    delta: Optional[float] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    last_price: Optional[float] = None
    oi: Optional[int] = None  # Open interest
    underlying_price: Optional[float] = None
    client: Optional[BrokerClient] = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.client:
            self.update()

    @classmethod
    def from_contract(cls, contract, client=None) -> "Contract":
        """
        Create a Contract object from a raw OptionsContract.
        """
        return cls(
            underlying=contract.underlying_symbol,
            symbol=contract.symbol,
            contract_type=contract.type.title().lower(),
            expiration_date=contract.expiration_date,
            oi=float(contract.open_interest) if contract.open_interest is not None else None,
            dte=(contract.expiration_date - datetime.date.today()).days,
            strike=contract.strike_price,
            client=client
        )
    
    @classmethod
    def from_contract_snapshot(cls, contract, snapshot) -> "Contract":
        """
        Create a Contract object from a raw OptionContract and OptionSnapshot
        """
        if not snapshot:
            raise ValueError(f"Snapshot data is required for symbol {contract.symbol}.")
        return cls(
            underlying=contract.underlying_symbol,
            symbol=contract.symbol,
            contract_type=contract.type.title().lower(),
            expiration_date=contract.expiration_date,
            oi=float(contract.open_interest) if contract.open_interest is not None else None,
            dte=(contract.expiration_date - datetime.date.today()).days,
            strike=contract.strike_price,
            delta=snapshot.greeks.delta if getattr(snapshot, 'greeks', None) else None,
            bid_price=snapshot.latest_quote.bid_price if getattr(snapshot, 'latest_quote', None) else None,
            ask_price=snapshot.latest_quote.ask_price if getattr(snapshot, 'latest_quote', None) else None,
            last_price=snapshot.latest_trade.price if getattr(snapshot, 'latest_trade', None) else None
        )
    
    @classmethod
    def from_dict(cls, data: dict) -> "Contract":
        return cls(**data)
    
    def update(self):
        """
        Fetch and update the contract's market data using its client.
        """
        if not self.client:
            raise ValueError("Cannot update Contract without a client.")
        snapshot = self.client.get_option_snapshot(self.symbol)
        data = snapshot.get(self.symbol) if isinstance(snapshot, dict) else None
        if data and getattr(data, 'greeks', None):
            self.delta = data.greeks.delta
        if data and getattr(data, 'latest_quote', None):
            self.bid_price = data.latest_quote.bid_price
            self.ask_price = data.latest_quote.ask_price
        if data and getattr(data, 'latest_trade', None):
            self.last_price = data.latest_trade.price

    def to_dict(self):
        return {
            "underlying": self.underlying,
            "symbol": self.symbol,
            "contract_type": self.contract_type,
            "expiration_date": self.expiration_date.isoformat(),
            "dte": self.dte,
            "strike": self.strike,
            "delta": self.delta,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "last_price": self.last_price,
            "oi": self.oi,
            "underlying_price": self.underlying_price,
        }
    
    @staticmethod
    def save_to_json(contracts: list["Contract"], filepath: str):
        payload = {
            "timestamp": get_ny_timestamp(),
            "contracts": [c.to_dict() for c in contracts]
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
    
    @staticmethod
    def load_from_json(filepath: str):
        with open(filepath, "r") as f:
            payload = json.load(f)
        return [Contract.from_dict(d) for d in payload["contracts"]]
