# Импорт необходимых библиотек и модулей
import logging
from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType
from tinkoff.invest.constants import INVEST_GRPC_API
from order_monitor import monitor_order_completion
from tinkoff_api import initialize_account, TOKEN
from notifier import notify_error
from validator import validate_webhook_data
from instrument_manager import get_instrument_data
import uuid
import threading
import time
import os
from utils import (
    get_quantity,
    log_trade_to_csv,
    check_position_exists,
    check_direction,
    can_open_position,
    load_positions_from_json,
    save_positions_to_json,
    calculate_expected_sum,
    POSITIONS_FILE,
)
import json
from decimal import Decimal, ROUND_DOWN

# Настройка логирования для отслеживания событий и ошибок
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# Инициализация Flask-приложения и глобальных переменных
app = Flask(__name__)
account_id = None
lock = threading.Lock()
MAX_TICKERS = 5  # Максимальное количество одновременных тикеров


# Функция для размещения ордеров (открытие и закрытие позиций)
def place_order(
    client,
    ticker,
    figi,
    direction,
    position_size_percent,
    exit_comment,
    signal_price,
    positions,
    leverage,
):
    # Логирование входных параметров ордера
    logging.info(
        f"Entering place_order:\n"
        f"ticker={ticker},\n"
        f"figi={figi},\n"
        f"direction={direction},\n"
        f"position_size_percent={position_size_percent},\n"
        f"exit_comment={exit_comment},\n"
        f"signal_price={signal_price},\n"
        f"leverage={leverage}"
    )

    # Проверка лимита тикеров перед открытием новой позиции
    if not check_position_exists(ticker, positions) and not can_open_position(
        positions, MAX_TICKERS
    ):
        logging.error(f"Exceeded max tickers limit: {MAX_TICKERS}")
        notify_error(
            ticker,
            position_size_percent or "N/A",
            "MaxTickers",
            f"Превышен лимит одновременных тикеров ({MAX_TICKERS})",
        )
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    # Получение данных об инструменте из API
    instrument_uid, lot, min_price_increment = get_instrument_data(client, figi, ticker)
    if instrument_uid is None or lot is None or min_price_increment is None:
        logging.error(f"Failed to get instrument data for FIGI: {figi}")
        notify_error(
            ticker,
            position_size_percent or "N/A",
            "InstrumentData",
            f"Не удалось получить данные инструмента для FIGI {figi}",
        )
        return {"error": f"Не удалось получить данные инструмента для FIGI {figi}"}, 400

    # Округление signal_price до шага цены инструмента
    if signal_price is not None:
        try:
            signal_price = Decimal(str(signal_price))
            signal_price = (signal_price / min_price_increment).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            ) * min_price_increment
            signal_price = float(signal_price)
            logging.info(f"Rounded signal_price to {signal_price}")
        except ValueError as e:
            logging.error(f"Invalid signal_price format: {str(e)}")
            notify_error(
                ticker,
                position_size_percent or "N/A",
                "PriceError",
                f"Неверный формат signal_price: {str(e)}",
            )
            return {"error": f"Неверный формат signal_price: {str(e)}"}, 400

    # Расчёт количества лотов в зависимости от типа операции
    expected_sum = None
    if exit_comment in ["LongStop", "ShortStop", "LongTrTake", "ShortTrTake"]:
        if not check_position_exists(ticker, positions):
            logging.error(
                f"Attempt to close non-existent position for ticker: {ticker}"
            )
            notify_error(
                ticker,
                position_size_percent or "N/A",
                "NoPosition",
                "Попытка закрыть несуществующую позицию",
            )
            return {"error": "Попытка закрыть несуществующую позицию"}, 400
        quantity = positions[ticker]["quantity"]
        logging.info(f"Closing position: ticker={ticker}, quantity={quantity}")
    else:
        if check_position_exists(ticker, positions):
            logging.error(f"Position already open for ticker: {ticker}")
            notify_error(
                ticker,
                position_size_percent or "N/A",
                "PositionExists",
                "Позиция уже открыта",
            )
            return {"error": "Позиция уже открыта"}, 400
        # Расчёт суммы позиции как процент от свободных средств
        try:
            expected_sum = calculate_expected_sum(
                client, account_id, position_size_percent, leverage
            )
            logging.info(
                f"Calculated expected_sum: {expected_sum} for position_size_percent: {position_size_percent}, leverage: {leverage}"
            )
        except Exception as e:
            logging.error(f"Error calculating expected_sum: {str(e)}")
            notify_error(
                ticker,
                position_size_percent or "N/A",
                "BalanceError",
                f"Ошибка при расчёте суммы позиции: {str(e)}",
            )
            return {"error": f"Ошибка при расчёте суммы позиции: {str(e)}"}, 400
        quantity = get_quantity(expected_sum, signal_price, lot)
        logging.info(
            f"Calculated quantity: {quantity} for expected_sum={expected_sum}, signal_price={signal_price}, lot={lot}"
        )
        if quantity == 0:
            logging.error("Quantity is 0")
            notify_error(
                ticker,
                position_size_percent or "N/A",
                "InvalidQuantity",
                "Количество лотов равно 0",
            )
            return {"error": "Количество лотов равно 0"}, 400

    # Подготовка параметров ордера
    if not isinstance(quantity, int):
        logging.error(f"Invalid quantity type: expected int, got {type(quantity)}")
        notify_error(
            ticker,
            position_size_percent or "N/A",
            "InvalidQuantity",
            f"Неверный тип quantity: ожидается int, получено {type(quantity)}",
        )
        return {
            "error": f"Неверный тип quantity: ожидается int, получено {type(quantity)}"
        }, 400

    client_order_id = str(uuid.uuid4())
    order_direction = (
        OrderDirection.ORDER_DIRECTION_BUY
        if direction == "buy"
        else OrderDirection.ORDER_DIRECTION_SELL
    )

    if not isinstance(account_id, str):
        logging.error(f"Invalid account_id type: expected str, got {type(account_id)}")
        notify_error(
            ticker,
            position_size_percent or "N/A",
            "InvalidAccount",
            f"Неверный тип account_id: ожидается строка, получено {type(account_id)}",
        )
        return {
            "error": f"Неверный тип account_id: ожидается строка, получено {type(account_id)}"
        }, 400

    logging.info(
        f"Preparing to place order:\n"
        f"instrument_uid={instrument_uid},\n"
        f"quantity={quantity},\n"
        f"direction={order_direction},\n"
        f"account_id={account_id},\n"
        f"client_order_id={client_order_id}"
    )

    # Размещение рыночного ордера через API
    try:
        response = client.orders.post_order(
            instrument_id=instrument_uid,
            quantity=quantity,
            direction=order_direction,
            account_id=account_id,
            order_type=OrderType.ORDER_TYPE_MARKET,
            order_id=client_order_id,
        )
        logging.info(f"Order placed successfully: order_id={response.order_id}")
    except Exception as e:
        logging.error(f"Error placing order: {str(e)}")
        notify_error(
            ticker,
            position_size_percent or "N/A",
            "OrderError",
            f"Ошибка при размещении ордера: {str(e)}",
        )
        return {"error": f"Ошибка при размещении ордера: {str(e)}"}, 400

    # Обработка результата: обновление позиций или запуск мониторинга закрытия
    is_opening = exit_comment in ["OpenLong", "OpenShort"]
    if is_opening:
        with lock:
            positions[ticker] = {
                "figi": figi,
                "instrument_uid": instrument_uid,
                "open_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "quantity": quantity,
                "client_order_id": client_order_id,
                "exchange_order_id": response.order_id,
                "direction": direction,
                "signal_price": signal_price,
                "exitComment": exit_comment,
            }
            save_positions_to_json(positions)
        logging.info(
            f"Opened position:\n"
            f"ticker={ticker},\n"
            f"quantity={quantity},\n"
            f"direction={direction},\n"
            f"signal_price={signal_price},\n"
            f"exitComment={exit_comment}"
        )
    else:
        open_order_id = positions[ticker]["exchange_order_id"]
        logging.info(
            f"Starting monitor for closing order:\n"
            f"ticker={ticker},\n"
            f"open_order_id={open_order_id},\n"
            f"close_order_id={response.order_id}"
        )
        threading.Thread(
            target=monitor_order_completion,
            args=(
                account_id,
                ticker,
                open_order_id,
                response.order_id,
                positions,
                log_trade_to_csv,
                exit_comment,
                client_order_id,
                lock,
                signal_price,
            ),
        ).start()

    return {
        "client_order_id": client_order_id,
        "exchange_order_id": response.order_id,
    }, 200


# Маршрут для обработки вебхуков от TradingView
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    logging.info(f"Received webhook data:\n{json.dumps(data, indent=2)}")

    # Извлечение данных из вебхука
    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    position_size_percent = data.get("position_size_percent")
    signal_price = data.get("price")
    exit_comment = data.get("exitComment")
    leverage = data.get("leverage")

    if position_size_percent == "null":
        position_size_percent = None
    if signal_price == "null":
        signal_price = None
    if leverage == "null":
        leverage = None

    logging.info(
        f"Parsed webhook:\n"
        f"ticker={ticker},\n"
        f"figi={figi},\n"
        f"direction={direction},\n"
        f"position_size_percent={position_size_percent},\n"
        f"signal_price={signal_price},\n"
        f"leverage={leverage},\n"
        f"exit_comment={exit_comment}"
    )

    # Валидация полученных данных
    is_valid, result = validate_webhook_data(
        ticker,
        figi,
        direction,
        position_size_percent,
        exit_comment,
        signal_price,
        leverage,
    )
    if not is_valid:
        logging.error(f"Validation failed: {result}")
        return jsonify({"error": result}), 400

    position_size_percent, exit_comment, signal_price, leverage = result

    logging.info(
        f"Validated data:\n"
        f"position_size_percent={position_size_percent},\n"
        f"exit_comment={exit_comment},\n"
        f"signal_price={signal_price},\n"
        f"leverage={leverage}"
    )

    # Выполнение ордера с использованием Tinkoff API
    try:
        with Client(TOKEN, target=INVEST_GRPC_API) as client:
            logging.info("Initialized Tinkoff client")
            positions = load_positions_from_json()
            logging.info(f"Loaded positions:\n{json.dumps(positions, indent=2)}")
            result, status = place_order(
                client,
                ticker,
                figi,
                direction,
                position_size_percent,
                exit_comment,
                signal_price,
                positions,
                leverage,
            )
            logging.info(f"place_order result: {result}, status: {status}")
            return jsonify(result), status
    except Exception as e:
        logging.error(f"Error in webhook processing: {str(e)}")
        notify_error(ticker or "Unknown", "N/A", "WebhookError", str(e))
        return jsonify({"error": f"Ошибка при обработке ордера: {str(e)}"}), 500


# Основная функция для запуска приложения
def main():
    global account_id
    logging.info("Starting account initialization")
    account = initialize_account(TOKEN)
    account_id = account[0].id if account else None
    if account_id is None:
        logging.error("Failed to initialize account")
        print("Не удалось инициализировать аккаунт, приложение не будет запущено.")
        return False
    logging.info(f"Starting application with account_id: {account_id}")
    print(f"Запуск приложения с аккаунтом: {account_id}")
    if not os.path.exists(POSITIONS_FILE):
        logging.info(f"Creating empty positions file at {POSITIONS_FILE}")
        save_positions_to_json({})
    return True


if not main():
    exit(1)
