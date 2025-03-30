# order_monitor.py
import time
from tinkoff.invest import SandboxClient

TOKEN = "t.Gk6qrpcVv87MYW8ZPgUOO7dKVV-GLQKtKAeymLEmZaGA6UTi9LseC0zvkCZ4GrgRdnrNFxfuwTgjT1V4xV-oJA"

def monitor_order_completion(account_id, ticker, open_order_id, close_order_id, current_positions, log_trade_to_csv):
    with SandboxClient(TOKEN) as client:
        while True:
            close_state = client.orders.get_order_state(account_id=account_id, order_id=close_order_id)
            if close_state.lots_executed == close_state.lots_requested and close_state.execution_report_status == "FILL":
                exit_price = close_state.executed_order_price.units + close_state.executed_order_price.nano / 1_000_000_000
                open_state = client.orders.get_order_state(account_id=account_id, order_id=open_order_id)
                entry_price = open_state.executed_order_price.units + open_state.executed_order_price.nano / 1_000_000_000
                quantity = current_positions[ticker]["quantity"]
                direction = current_positions[ticker]["direction"]
                profit_gross = (exit_price - entry_price) * quantity if direction == "buy" else (entry_price - exit_price) * quantity
                broker_fee = profit_gross * 0.0005
                trade_data = {
                    "ticker": ticker,
                    "figi": current_positions[ticker]["figi"],
                    "instrument_uid": current_positions[ticker]["instrument_uid"],
                    "open_datetime": current_positions[ticker]["open_datetime"],
                    "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "broker_fee": broker_fee,
                    "profit_gross": profit_gross,
                    "profit_net": profit_gross - broker_fee,
                    "entry_client_order_id": current_positions[ticker]["client_order_id"],
                    "entry_exchange_order_id": open_order_id,
                    "exit_client_order_id": close_state.order_id,
                    "exit_exchange_order_id": close_order_id
                }
                log_trade_to_csv(trade_data)
                del current_positions[ticker]
                break
            time.sleep(1)