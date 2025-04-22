# main.py
import logging
from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType
from tinkoff.invest.constants import INVEST_GRPC_API
from order_monitor import monitor_order_completion
from tinkoff_api import initialize_account, TOKEN
from notifier import notify_error
from validator import validate_webhook_data
from instrument_manager import get_instrument_data
from stop_order_manager import place_stop_loss, handle_stop_close
import uuid
import threading
import time
import os
from utils import get_quantity, log_trade_to_csv, check_position_exists, check_direction, can_open_position, load_positions_from_json, save_positions_to_json, POSITIONS_FILE

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
account_id = None
lock = threading.Lock()
MAX_TICKERS = 5

def place_order(client, ticker, figi, direction, expected_sum, exit_comment, price, stop_loss_price, positions):
    logging.info(f"Entering place_order: ticker={ticker}, figi={figi}, direction={direction}, "
                 f"expected_sum={expected_sum}, exit_comment={exit_comment}, price={price}, stop_loss_price={stop_loss_price}")

    if not check_position_exists(ticker, positions) and not can_open_position(positions, MAX_TICKERS):
        logging.error(f"Exceeded max tickers limit: {MAX_TICKERS}")
        return {"error": f"Превышен лимит одновременных тикеров ({MAX_TICKERS})"}, 400

    instrument_uid, lot = get_instrument_data(client, figi, ticker)
    if instrument_uid is None or lot is None:
        logging.error(f"Failed to get instrument data for FIGI: {figi}")
        return {"error": f"Не удалось получить данные инструмента для FIGI {figi}"}, 400

    if exit_comment in ["LongStop", "ShortStop", "LongTrTake", "ShortTrTake"]:
        if not check_position_exists(ticker, positions):
            logging.error(f"Attempt to close non-existent position for ticker: {ticker}")
            return {"error": "Попытка закрыть несуществующую позицию"}, 400
        quantity = positions[ticker]["quantity"]
        logging.info(f"Closing position: ticker={ticker}, quantity={quantity}")

        if exit_comment in ["LongStop", "ShortStop"]:
            is_executed, trade_data = handle_stop_close(client, account_id, ticker, figi, positions, exit_comment)
            if is_executed:
                try:
                    log_trade_to_csv(trade_data)
                except Exception as e:
                    logging.error(f"Failed to write to trades.csv: {str(e)}")
                with lock:
                    del positions[ticker]
                    save_positions_to_json(positions)
                logging.info(f"Closed position by stop: ticker={ticker}, exitComment={exit_comment}")
                return {"message": f"Position {ticker} closed by broker"}, 200
            else:
                return {"error": "Stop-order not executed, alert sent. Check Tinkoff terminal."}, 400
    else:
        if check_position_exists(ticker, positions):
            logging.error(f"Position already open for ticker: {ticker}")
            return {"error": "Позиция уже открыта"}, 400
        quantity = get_quantity(expected_sum, price, lot)
        logging.info(f"Calculated quantity: {quantity} for expected_sum={expected_sum}, price={price}, lot={lot}")
        if quantity == 0:
            logging.error("Quantity is 0")
            return {"error": "Количество лотов равно 0"}, 400

    if not isinstance(quantity, int):
        logging.error(f"Invalid quantity type: expected int, got {type(quantity)}")
        return {"error": f"Неверный тип quantity: ожидается int, получено {type(quantity)}"}, 400

    client_order_id = str(uuid.uuid4())
    order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == "buy" else OrderDirection.ORDER_DIRECTION_SELL

    if not isinstance(account_id, str):
        logging.error(f"Invalid account_id type: expected str, got {type(account_id)}")
        return {"error": f"Неверный тип account_id: ожидается строка, получено {type(account_id)}"}, 400

    logging.info(f"Preparing to place order: instrument_uid={instrument_uid} ({type(instrument_uid)}), "
                 f"quantity={quantity} ({type(quantity)}), "
                 f"direction={order_direction} ({type(order_direction)}), "
                 f"account_id={account_id} ({type(account_id)}), "
                 f"client_order_id={client_order_id} ({type(client_order_id)})")

    try:
        response = client.orders.post_order(
            instrument_id=instrument_uid,
            quantity=quantity,
            direction=order_direction,
            account_id=account_id,
            order_type=OrderType.ORDER_TYPE_MARKET,
            order_id=client_order_id
        )
        logging.info(f"Order placed successfully: order_id={response.order_id}")
        broker_fee = response.executed_commission.units + response.executed_commission.nano / 1_000_000_000
        logging.info(f"Broker fee for order {response.order_id}: {broker_fee}")
    except Exception as e:
        logging.error(f"Error placing order: {str(e)}")
        return {"error": f"Ошибка при размещении ордера: {str(e)}"}, 400

    is_opening = exit_comment in [None, "OpenLong", "OpenShort"]
    if is_opening:
        stop_order_id = None
        if stop_loss_price is not None:
            stop_order_id = place_stop_loss(client, account_id, instrument_uid, quantity, stop_loss_price, direction)
            if stop_order_id is None:
                logging.error(f"Failed to place stop-loss for ticker: {ticker}")
                return {"error": f"Не удалось установить стоп-лосс для {ticker}"}, 400

        with lock:
            positions[ticker] = {
                "figi": figi,
                "instrument_uid": instrument_uid,
                "open_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "quantity": quantity,
                "client_order_id": client_order_id,
                "exchange_order_id": response.order_id,
                "direction": direction,
                "broker_fee": broker_fee,
                "stop_loss_price": stop_loss_price,
                "stop_order_id": stop_order_id,
                "exitComment": exit_comment
            }
            save_positions_to_json(positions)
        logging.info(f"Opened position: ticker={ticker}, quantity={quantity}, direction={direction}, broker_fee={broker_fee}, stop_order_id={stop_order_id}, exitComment={exit_comment}")
    else:
        open_order_id = positions[ticker]["exchange_order_id"]
        logging.info(f"Starting monitor for closing order: ticker={ticker}, open_order_id={open_order_id}")
        threading.Thread(target=monitor_order_completion, args=(
            account_id, ticker, open_order_id, response.order_id, positions, 
            log_trade_to_csv, exit_comment, client_order_id, lock, broker_fee
        )).start()

    return {"client_order_id": client_order_id, "exchange_order_id": response.order_id, "broker_fee": broker_fee}, 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    logging.info(f"Received webhook data: {data}")

    ticker = data.get("ticker")
    figi = data.get("figi")
    direction = data.get("direction")
    expected_sum = data.get("expected_sum")
    price = data.get("price")
    stop_loss_price = data.get("stop_loss_price")
    exit_comment = data.get("exitComment")

    logging.info(f"Parsed webhook: ticker={ticker}, figi={figi}, direction={direction}, "
                 f"expected_sum={expected_sum}, price={price}, stop_loss_price={stop_loss_price}, exit_comment={exit_comment}")

    is_valid, result = validate_webhook_data(ticker, figi, direction, expected_sum, exit_comment, price, stop_loss_price)
    if not is_valid:
        logging.error(f"Validation failed: {result}")
        return jsonify({"error": result}), 400

    expected_sum, exit_comment, price, stop_loss_price = result
    logging.info(f"Validated data: expected_sum={expected_sum}, exit_comment={exit_comment}, price={price}, stop_loss_price={stop_loss_price}")

    try:
        with Client(TOKEN, target=INVEST_GRPC_API) as client:
            logging.info("Initialized Tinkoff client")
            positions = load_positions_from_json()
            logging.info(f"Loaded positions: {positions}")
            result, status = place_order(client, ticker, figi, direction, expected_sum, exit_comment, price, stop_loss_price, positions)
            logging.info(f"place_order result: {result}, status: {status}")
            return jsonify(result), status
    except Exception as e:
        logging.error(f"Error in webhook processing: {str(e)}")
        notify_error(ticker or "Unknown", "N/A", "WebhookError", str(e))
        return jsonify({"error": f"Ошибка при обработке ордера: {str(e)}"}), 500

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