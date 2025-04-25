import time
from tinkoff.invest import Client
from tinkoff.invest.constants import INVEST_GRPC_API
from tinkoff_api import TOKEN
from utils import save_positions_to_json, POSITIONS_FILE
import logging

def monitor_order_completion(account_id, ticker, open_order_id, close_order_id, positions, log_trade_to_csv, exit_comment=None, exit_client_order_id=None, lock=None, exit_signal_price=None):
    if exit_signal_price is None:
        logging.error(f"Missing exit_signal_price for ticker {ticker}")
        return

    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        while True:
            try:
                close_state = client.orders.get_order_state(account_id=account_id, order_id=close_order_id)
            except Exception as e:
                logging.error(f"Failed to get order state for {close_order_id}: {str(e)}")
                time.sleep(5)
                continue
            if close_state.lots_executed == close_state.lots_requested and close_state.execution_report_status == 1:
                entry_signal_price = positions[ticker]["signal_price"]
                quantity = positions[ticker]["quantity"]
                direction = positions[ticker]["direction"]
                lot = positions[ticker].get("lot", 1)  # Assuming lot is available in positions, default to 1 if not present
                
                # Calculate commissions
                 = entry_signal_price * quantity * 0.0005  # Example commission rate of 0.05%
                exit_broker_fee = exit_signal_price * quantity * 0.0005   # Example commission rate of 0.05%
                broker_fee =  + exit_broker_fee
                
                # Calculate profit
                profit_gross = (exit_signal_price - entry_signal_price) * quantity * lot if direction == "buy" else (entry_signal_price - exit_signal_price) * quantity * lot
                profit_net = profit_gross - broker_fee

                trade_data = {
                    "ticker": ticker,
                    "figi": positions[ticker]["figi"],
                    "exitComment": exit_comment,
                    "instrument_uid": positions[ticker]["instrument_uid"],
                    "open_datetime": positions[ticker]["open_datetime"],
                    "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "entry_signal_price": entry_signal_price,
                    "exit_signal_price": exit_signal_price,
                    "quantity": quantity,
                    "": ,
                    "exit_broker_fee": exit_broker_fee,
                    "broker_fee": broker_fee,
                    "profit_gross": profit_gross,
                    "profit_net": profit_net,
                    "entry_client_order_id": positions[ticker]["client_order_id"],
                    "entry_exchange_order_id": open_order_id,
                    "exit_client_order_id": exit_client_order_id,
                    "exit_exchange_order_id": close_order_id
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