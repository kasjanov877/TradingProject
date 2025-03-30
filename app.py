# main.py
import uuid
import threading
import time
from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentIdType
from tinkoff.invest.sandbox.client import SandboxClient
from order_monitor import monitor_order_completion
from utils import get_quantity, log_trade_to_csv, check_position_exists, check_direction, can_open_position
from data_manager import initialize_libraries, save_library_to_json
from tinkoff_api import initialize_sandbox_account, TOKEN

app = Flask(__name__)
account_id = None
ticker_to_figi_uid_library = None
current_positions = {}
MAX_TICKERS = 5

def place_order(client, ticker, figi, direction, expected_sum):
    if not check_position_exists(ticker, current_positions) and not can_open_position(current_positions, MAX_TICKERS):
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    if check_direction(ticker, direction, current_positions):
        return {"error": "Позиция уже открыта в этом направлении"}, 400

    if ticker in ticker_to_figi_uid_library and ticker_to_figi_uid_library[ticker]["figi"] == figi:
        instrument_data = ticker_to_figi_uid_library[ticker]
        instrument_uid = instrument_data["instrument_uid"]
        lot = instrument_data["lot"]
    else:
        try:
            instrument = client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
            ).instrument
            if not instrument:
                return {"error": f"Инструмент с FIGI {figi} не найден"}, 400
            instrument_uid = instrument.uid
            lot = instrument.lot
            ticker_to_figi_uid_library[ticker] = {
                "figi": figi,
                "instrument_uid": instrument_uid,
                "lot": lot
            }
            save_library_to_json(ticker_to_figi_uid_library)
        except Exception as e:
            return {"error": f"Ошибка при запросе инструмента: {str(e)}"}, 400

    quantity = get_quantity(expected_sum, lot)
    if quantity == 0:
        return {"error": "Количество лотов равно 0"}, 400

    client_order_id = str(uuid.uuid4())
    order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == "buy" else OrderDirection.ORDER_DIRECTION_SELL
    try:
        response = client.orders.post_order(
            instrument_id=instrument_uid,
            quantity=quantity,
            direction=order_direction,
            account_id=account_id,
            order_type=OrderType.ORDER_TYPE_MARKET,
            order_id=client_order_id
        )
    except Exception as e:
        return {"error": f"Ошибка при размещении ордера: {str(e)}"}, 400

    is_opening = not check_position_exists(ticker, current_positions)
    if is_opening:
        current_positions[ticker] = {
            "figi": figi,
            "instrument_uid": instrument_uid,
            "open_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "quantity": quantity,
            "client_order_id": client_order_id,
            "exchange_order_id": response.order_id,
            "direction": direction
        }
    else:
        open_order_id = current_positions[ticker]["exchange_order_id"]
        threading.Thread(target=monitor_order_completion, args=(account_id, ticker, open_order_id, response.order_id, current_positions, log_trade_to_csv)).start()

    return {"client_order_id": client_order_id, "exchange_order_id": response.order_id}, 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    expected_sum = data.get("expected_sum")

    if not all([ticker, figi, direction, expected_sum]):
        return jsonify({"error": "Недостаточно данных"}), 400

    expected_sum = int(expected_sum)
    with SandboxClient(TOKEN) as client:
        result, status = place_order(client, ticker, figi, direction, expected_sum)
        return jsonify(result), status

def main():
    global ticker_to_figi_uid_library, account_id
    ticker_to_figi_uid_library = initialize_libraries()
    with SandboxClient(TOKEN) as client:
        account_id = initialize_sandbox_account(client)
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()