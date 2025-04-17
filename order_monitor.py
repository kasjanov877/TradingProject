import time
from tinkoff.invest import Client
from tinkoff.invest.constants import INVEST_GRPC_API
from tinkoff_api import TOKEN
from utils import save_positions_to_json, POSITIONS_FILE
import logging

def monitor_order_completion(account_id, ticker, open_order_id, close_order_id, positions, log_trade_to_csv, exit_comment=None, exit_client_order_id=None, lock=None, broker_fee=None):
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        while True:
            close_state = client.orders.get_order_state(account_id=account_id, order_id=close_order_id)
            if close_state.lots_executed == close_state.lots_requested and close_state.execution_report_status == 1:
                exit_price = close_state.average_position_price.units + close_state.average_position_price.nano / 1_000_000_000
                open_state = client.orders.get_order_state(account_id=account_id, order_id=open_order_id)
                entry_price = open_state.average_position_price.units + open_state.average_position_price.nano / 1_000_000_000
                quantity = positions[ticker]["quantity"]
                direction = positions[ticker]["direction"]
                profit_gross = (exit_price - entry_price) * quantity if direction == "buy" else (entry_price - exit_price) * quantity
                entry_fee = positions[ticker].get("broker_fee", 0)
                exit_fee = broker_fee or 0
                trade_data = {
                    "ticker": ticker,
                    "figi": positions[ticker]["figi"],
                    "instrument_uid": positions[ticker]["instrument_uid"],
                    "open_datetime": positions[ticker]["open_datetime"],
                    "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "entry_broker_fee": entry_fee,
                    "exit_broker_fee": exit_fee,
                    "broker_fee": entry_fee + exit_fee,
                    "profit_gross": profit_gross,
                    "profit_net": profit_gross - (entry_fee + exit_fee),
                    "entry_client_order_id": positions[ticker]["client_order_id"],
                    "entry_exchange_order_id": open_order_id,
                    "exit_client_order_id": exit_client_order_id,
                    "exit_exchange_order_id": close_order_id,
                    "exitComment": exit_comment,
                    "stop_order_id": positions[ticker].get("stop_order_id", None)
                }
                try:
                    log_trade_to_csv(trade_data)
                except Exception as e:
                    logging.error(f"Failed to write to trades.csv: {str(e)}")
                with lock:
                    del positions[ticker]
                    save_positions_to_json(positions)
                break
            time.sleep(1)