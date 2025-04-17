import logging
import time
import uuid
from decimal import Decimal
from tinkoff.invest import Client, StopOrderDirection, StopOrderType, StopOrderExpirationType, OrderExecutionReportStatus
from tinkoff.invest.utils import decimal_to_quotation

def place_stop_loss(client: Client, account_id: str, instrument_uid: str, quantity: int, stop_loss_price, direction: str):
    """
    Размещает стоп-лосс для позиции.

    Args:
        client: Клиент Tinkoff API.
        account_id: ID аккаунта.
        instrument_uid: UID инструмента.
        quantity: Количество лотов.
        stop_loss_price: Цена стоп-лосса (за акцию).
        direction: Направление позиции ("buy" или "sell").

    Returns:
        str: ID стоп-приказа или None при ошибке.
    """
    try:
        # Проверка типа stop_loss_price
        stop_price = decimal_to_quotation(Decimal(str(stop_loss_price)))
    except (ValueError, TypeError) as e:
        logging.error(f"Invalid stop_loss_price format: {str(e)}")
        return None

    try:
        stop_order_id = str(uuid.uuid4())
        stop_direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL if direction == "buy" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY

        response = client.stop_orders.post_stop_order(
            account_id=account_id,
            instrument_id=instrument_uid,
            quantity=quantity,
            stop_price=stop_price,
            direction=stop_direction,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
            order_id=stop_order_id,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL
        )
        logging.info(f"Placed stop-loss order: ticker={instrument_uid}, id={response.stop_order_id}, price={stop_loss_price}")
        return response.stop_order_id

    except Exception as e:
        logging.error(f"Error placing stop-loss order: {str(e)}")
        return None

def handle_stop_close(client: Client, account_id: str, ticker: str, figi: str, positions: dict, exit_comment: str):
    """
    Обрабатывает закрытие позиции по стоп-лоссу.

    Args:
        client: Клиент Tinkoff API.
        account_id: ID аккаунта.
        ticker: Тикер инструмента.
        figi: FIGI инструмента.
        positions: Словарь текущих позиций.
        exit_comment: Комментарий закрытия ("LongStop" или "ShortStop").

    Returns:
        tuple: (is_executed, trade_data)
            - is_executed: True (ордер исполнен), False (не исполнен или ошибка).
            - trade_data: Данные для trades.csv (если исполнен).
    """
    stop_order_id = positions[ticker].get("stop_order_id")
    if not stop_order_id:
        logging.error(f"No stop_order_id found for ticker {ticker}")
        notify_error(ticker, "N/A", "StopOrderError", f"No stop_order_id for {ticker}. Check Tinkoff terminal.")
        return False, None

    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        try:
            stop_state = client.orders.get_order_state(account_id=account_id, order_id=stop_order_id)
            if stop_state.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
                logging.info(f"Position {ticker} closed by broker: exitComment={exit_comment}, stop_order_id={stop_order_id}")
                exit_price = stop_state.average_position_price.units + stop_state.average_position_price.nano / 1_000_000_000
                exit_broker_fee = stop_state.executed_commission.units + stop_state.executed_commission.nano / 1_000_000_000
                trade_data = {
                    "ticker": ticker,
                    "figi": positions[ticker]["figi"],
                    "instrument_uid": positions[ticker]["instrument_uid"],
                    "open_datetime": positions[ticker]["open_datetime"],
                    "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "entry_price": positions[ticker].get("entry_price", 0),
                    "exit_price": exit_price,
                    "quantity": positions[ticker]["quantity"],
                    "entry_broker_fee": positions[ticker].get("broker_fee", 0),
                    "exit_broker_fee": exit_broker_fee,
                    "broker_fee": positions[ticker].get("broker_fee", 0) + exit_broker_fee,
                    "profit_gross": 0,  # Требует уточнения
                    "profit_net": 0,
                    "entry_client_order_id": positions[ticker]["client_order_id"],
                    "entry_exchange_order_id": positions[ticker]["exchange_order_id"],
                    "exit_client_order_id": None,
                    "exit_exchange_order_id": stop_order_id,
                    "exitComment": exit_comment,
                    "stop_order_id": stop_order_id
                }
                return True, trade_data
            else:
                logging.info(f"Stop-order {stop_order_id} for {ticker} not executed, status: {stop_state.execution_report_status}, attempt {attempt + 1}")
                attempt += 1
                if attempt < max_attempts:
                    time.sleep(1)
                continue
        except Exception as e:
            logging.error(f"Error checking stop-order {stop_order_id} for {ticker}: {str(e)}, attempt {attempt + 1}")
            attempt += 1
            if attempt < max_attempts:
                time.sleep(1)
            continue

    # После всех попыток
    notify_error(ticker, "N/A", "StopOrderError", f"Stop-order for {ticker} not executed. Stop-order ID: {stop_order_id}, Status: Unknown or Error. Check Tinkoff terminal.")
    return False, None