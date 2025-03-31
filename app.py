# main.py
import uuid
import threading
import time
import os
import json
from notifier import notify_error
from validator import validate_webhook_data  # Новая библиотека
from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentIdType
from tinkoff.invest.sandbox.client import SandboxClient
from order_monitor import monitor_order_completion
from utils import get_quantity, log_trade_to_csv, check_position_exists, check_direction, can_open_position
from tinkoff_api import initialize_sandbox_account, TOKEN

app = Flask(__name__)
account_id = None
current_positions = {}
MAX_TICKERS = 5

def place_order(client, ticker, figi, direction, expected_sum):
    if not check_position_exists(ticker, current_positions) and not can_open_position(current_positions, MAX_TICKERS):
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    if check_direction(ticker, direction, current_positions):
        return {"error": "Позиция уже открыта в этом направлении"}, 400

    # Читаем tokens_figi_uid.json напрямую
    json_file_path = "tokens_figi_uid.json"
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            instrument_data = json.load(json_file)
    else:
        instrument_data = {}
    # Проверяем figi в данных из JSON
    if figi in instrument_data:
        instrument_uid = instrument_data[figi]["instrument_uid"]
        lot = instrument_data[figi]["lot"]
    else:
        try:
            instrument = client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
            ).instrument
            if not instrument:
                return {"error": f"Инструмент с FIGI {figi} не найден"}, 400
            instrument_uid = instrument.uid
            lot = instrument.lot
            # Добавляем новую запись в данные и сохраняем в JSON
            instrument_data[figi] = {
                "ticker": ticker,
                "instrument_uid": instrument_uid,
                "lot": lot
            }
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
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
    print("Received webhook data:", data)  # Логирование входящих данных
    
    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    expected_sum = data.get("expected_sum")

    # Валидация данных
    is_valid, result = validate_webhook_data(ticker, figi, direction, expected_sum)
    if not is_valid:
        return jsonify({"error": result}), 400

    # Если валидация прошла, result — это преобразованное expected_sum
    expected_sum = result

    # Вызов place_order с обработкой исключений
    try:
        with SandboxClient(TOKEN, timeout=5) as client:
            result, status = place_order(client, ticker, figi, direction, expected_sum)
            if status != 200:
                notify_error(ticker, expected_sum, "OrderError", result.get("error", "Неизвестная ошибка"))
            return jsonify(result), status
    except Exception as e:
        notify_error(ticker, expected_sum, type(e).__name__, str(e))
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

def main():
    global account_id
    with SandboxClient(TOKEN) as client:
        account_id = initialize_sandbox_account(client)
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()