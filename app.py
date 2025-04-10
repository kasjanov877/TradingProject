# main.py

from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentIdType
from order_monitor import monitor_order_completion  # Импортируем monitor_order_completion
from tinkoff_api import initialize_account, TOKEN  # Импортируем функцию инициализации аккаунта и токен
from notifier import notify_error  # Импортируем функцию для уведомлений об ошибках
from validator import validate_webhook_data  # Импортируем функцию для валидации данных вебхука
import uuid
import threading
import time
import os
import json
from utils import get_quantity, log_trade_to_csv, check_position_exists, check_direction, can_open_position

app = Flask(__name__)
account_id = None
current_positions = {}
MAX_TICKERS = 5

def place_order(client, ticker, figi, direction, expected_sum, exit_comment, price):
    """
    Размещает рыночный ордер на покупку или продажу инструмента через API Тинькофф.
    
    Аргументы:
        client: Экземпляр Client для взаимодействия с API.
        ticker (str): Тикер инструмента (например, "SBER").
        figi (str): Уникальный идентификатор инструмента в системе Тинькофф (например, "BBG004730N88").
        direction (str): Направление ордера ("buy" или "sell").
        expected_sum (int or None): Сумма в валюте для расчёта количества лотов при открытии позиции.
        exit_comment (str or None): Комментарий выхода (например, "LongTrTake"), указывает на закрытие позиции.
        price (float): Цена одной единицы инструмента из вебхука, используется для расчёта quantity при открытии.
    
    Возвращает:
        tuple: (результат в формате JSON, HTTP-статус).
    """
    if not check_position_exists(ticker, current_positions) and not can_open_position(current_positions, MAX_TICKERS):
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    json_file_path = "tokens_figi_uid.json"
    
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            instrument_data = json.load(json_file)
    else:
        instrument_data = {}
    
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
            instrument_data[figi] = {
                "ticker": ticker,
                "instrument_uid": instrument_uid,
                "lot": lot
            }
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            return {"error": f"Ошибка при запросе инструмента: {str(e)}"}, 400

    if exit_comment:
        if not check_position_exists(ticker, current_positions):
            return {"error": "Попытка закрыть несуществующую позицию"}, 400
        quantity = current_positions[ticker]["quantity"]
    else:
        if check_position_exists(ticker, current_positions):
            return {"error": "Позиция уже открыта"}, 400
        quantity = get_quantity(expected_sum, price, lot)
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
    is_opening = not exit_comment
    
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
        threading.Thread(target=monitor_order_completion, args=(
            client, account_id, ticker, open_order_id, response.order_id, current_positions, log_trade_to_csv, exit_comment, client_order_id
        )).start()

    return {"client_order_id": client_order_id, "exchange_order_id": response.order_id}, 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Received webhook data:", data)
    
    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    expected_sum = data.get("expected_sum")
    price = data.get("price") 
    exit_comment = data.get("exitComment")

    is_valid, result = validate_webhook_data(ticker, figi, direction, expected_sum, exit_comment, price)
    if not is_valid:
        return jsonify({"error": result}), 400

    expected_sum, exit_comment, price = result  

    try:
        with Client(TOKEN, timeout=5) as client:  
            result, status = place_order(client, ticker, figi, direction, expected_sum, exit_comment, price) 
            if status == 200:
                return jsonify(result), 200
            else:
                return jsonify(result), status
    except Exception as e:
        notify_error(str(e))  # Добавляем уведомление об ошибке
        return jsonify({"error": f"Ошибка при обработке ордера: {str(e)}"}), 500

def main():
    global account_id
    account_id = initialize_account(TOKEN)
    app.run(debug=True, host="0.0.0.0", port=5000)

if __name__ == '__main__':
    main()
