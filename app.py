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
#from tinkoff.invest.sandbox.client import Client
from order_monitor import monitor_order_completion
from utils import get_quantity, log_trade_to_csv, check_position_exists, check_direction, can_open_position
from tinkoff_api import initialize_sandbox_account, TOKEN

app = Flask(__name__)
account_id = None
current_positions = {}
MAX_TICKERS = 5

def place_order(client, ticker, figi, direction, expected_sum, exit_comment, price):
    """
    Размещает рыночный ордер на покупку или продажу инструмента через API Тинькофф.
    
    Аргументы:
        client: Экземпляр SandboxClient для взаимодействия с API.
        ticker (str): Тикер инструмента (например, "SBER").
        figi (str): Уникальный идентификатор инструмента в системе Тинькофф (например, "BBG004730N88").
        direction (str): Направление ордера ("buy" или "sell").
        expected_sum (int or None): Сумма в валюте для расчёта количества лотов при открытии позиции.
        exit_comment (str or None): Комментарий выхода (например, "LongTrTake"), указывает на закрытие позиции.
        price (float): Цена одной единицы инструмента из вебхука, используется для расчёта quantity при открытии.
    
    Возвращает:
        tuple: (результат в формате JSON, HTTP-статус).
    """
    
    # Проверяем, не превышен ли лимит одновременно открытых позиций (MAX_TICKERS).
    # Если позиция по тикеру ещё не открыта и лимит достигнут, возвращаем ошибку.
    if not check_position_exists(ticker, current_positions) and not can_open_position(current_positions, MAX_TICKERS):
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    # Указываем путь к файлу с данными об инструментах (токены, UID, лотность).
    json_file_path = "tokens_figi_uid.json"
    
    # Проверяем, существует ли файл с данными об инструментах.
    # Если да, загружаем его содержимое для быстрого доступа к информации.
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            instrument_data = json.load(json_file)
    else:
        # Если файла нет, создаём пустой словарь для хранения данных об инструментах.
        instrument_data = {}
    
    # Проверяем, есть ли данные об инструменте по его FIGI в загруженном словаре.
    if figi in instrument_data:
        # Если данные есть, извлекаем UID инструмента и его лотность.
        instrument_uid = instrument_data[figi]["instrument_uid"]
        lot = instrument_data[figi]["lot"]
    else:
        # Если данных нет, запрашиваем информацию об инструменте через API.
        try:
            instrument = client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
            ).instrument
            if not instrument:
                # Если инструмент не найден, возвращаем ошибку.
                return {"error": f"Инструмент с FIGI {figi} не найден"}, 400
            # Извлекаем UID и лотность из ответа API.
            instrument_uid = instrument.uid
            lot = instrument.lot
            # Сохраняем полученные данные в словарь для будущих запросов.
            instrument_data[figi] = {
                "ticker": ticker,
                "instrument_uid": instrument_uid,
                "lot": lot
            }
            # Записываем обновлённый словарь в файл.
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            # Если произошла ошибка при запросе, возвращаем её описание.
            return {"error": f"Ошибка при запросе инструмента: {str(e)}"}, 400

    # Определяем количество лотов (quantity) в зависимости от типа операции.
    if exit_comment:            # Если есть exit_comment, это закрытие позиции.
                                # Проверяем, существует ли открытая позиция по тикеру.
        if not check_position_exists(ticker, current_positions):
            return {"error": "Попытка закрыть несуществующую позицию"}, 400
        # Берём количество лотов из текущей открытой позиции, price не используется.
        quantity = current_positions[ticker]["quantity"]
    else:   # Если exit_comment нет, это открытие новой позиции.
        if check_position_exists(ticker, current_positions):
            return {"error": "Позиция уже открыта"}, 400
        quantity = get_quantity(expected_sum, price, lot) # Рассчитываем количество лотов на основе суммы, цены и лотности.
        if quantity == 0:
            return {"error": "Количество лотов равно 0"}, 400

    # Генерируем уникальный клиентский ID для ордера (UUID).
    client_order_id = str(uuid.uuid4())
    
    # Преобразуем направление из строки ("buy"/"sell") в формат API Тинькофф.
    order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == "buy" else OrderDirection.ORDER_DIRECTION_SELL
    
    # Отправляем рыночный ордер через API.
    try:
        response = client.orders.post_order(
            instrument_id=instrument_uid,  # UID инструмента для API.
            quantity=quantity,            # Количество лотов для покупки/продажи.
            direction=order_direction,    # Направление ордера (покупка/продажа).
            account_id=account_id,        # ID аккаунта, заданный глобально.
            order_type=OrderType.ORDER_TYPE_MARKET,  # Тип ордера — рыночный.
            order_id=client_order_id      # Клиентский ID ордера.
        )
    except Exception as e:
        return {"error": f"Ошибка при размещении ордера: {str(e)}"}, 400 
    is_opening = not exit_comment # Определяем, является ли операция открытием позиции.
    
    if is_opening:  # Если это открытие позиции.
        # Сохраняем данные о новой позиции в current_positions.
        current_positions[ticker] = {
            "figi": figi,                      # FIGI инструмента.
            "instrument_uid": instrument_uid,  # UID инструмента.
            "open_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),  # Время открытия.
            "quantity": quantity,             # Количество лотов.
            "client_order_id": client_order_id,  # Клиентский ID ордера открытия.
            "exchange_order_id": response.order_id,  # Биржевой ID ордера.
            "direction": direction            # Направление (buy/sell).
        }
    else:  # Если это закрытие позиции.
        # Извлекаем биржевой ID ордера открытия для мониторинга.
        open_order_id = current_positions[ticker]["exchange_order_id"]
        # Запускаем мониторинг выполнения ордеров в отдельном потоке.
        # Передаём client_order_id закрытия для записи в статистику.
        threading.Thread(target=monitor_order_completion, args=(
            account_id, ticker, open_order_id, response.order_id, current_positions, log_trade_to_csv, exit_comment, client_order_id
        )).start()

    # Возвращаем успешный результат с клиентским и биржевым ID ордера.
    return {"client_order_id": client_order_id, "exchange_order_id": response.order_id}, 200
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Received webhook data:", data)
    
    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    expected_sum = data.get("expected_sum")
    price = data.get("price")  # Добавляем извлечение price
    exit_comment = data.get("exitComment")

    is_valid, result = validate_webhook_data(ticker, figi, direction, expected_sum, exit_comment, price)  # Передаем price
    if not is_valid:
        return jsonify({"error": result}), 400

    expected_sum, exit_comment, price = result  # Распаковываем price

    try:
        with Client(token=TOKEN, sandbox=True, timeout=5) as client:
            result, status = place_order(client, ticker, figi, direction, expected_sum, exit_comment, price)  # Передаем price
            if status != 200:
                notify_error(ticker, expected_sum or "N/A", "OrderError", result.get("error", "Неизвестная ошибка"))
            return jsonify(result), status
    except Exception as e:
        notify_error(ticker, expected_sum or "N/A", type(e).__name__, str(e))
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500

def main():
    global account_id
    with Client(token=TOKEN, sandbox=True) as client:
        account_id = initialize_sandbox_account(client)
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()