import logging
import time
import uuid
from decimal import Decimal
from tinkoff.invest import (
    Client,
    StopOrderDirection,
    StopOrderType,
    StopOrderExpirationType,
)
from tinkoff.invest.utils import decimal_to_quotation
from notifier import notify_error


def place_stop_loss(
    client: Client,
    account_id: str,
    instrument_uid: str,
    quantity: int,
    stop_loss_price,
    direction: str,
):
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
        stop_direction = (
            StopOrderDirection.STOP_ORDER_DIRECTION_SELL
            if direction == "buy"
            else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        )

        response = client.stop_orders.post_stop_order(
            account_id=account_id,
            instrument_id=instrument_uid,
            quantity=quantity,
            stop_price=stop_price,
            direction=stop_direction,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
            order_id=stop_order_id,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
        )
        logging.info(
            f"Placed stop-loss order: instrument_ui={instrument_uid}, id={response.stop_order_id}, price={stop_loss_price}"
        )
        return response.stop_order_id

    except Exception as e:
        logging.error(f"Error placing stop-loss order: {str(e)}")
        return None


def handle_stop_close(
    client: Client,
    account_id: str,
    ticker: str,
    figi: str,
    positions: dict,
    exit_comment: str,
):
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
        notify_error(
            ticker,
            "N/A",
            "StopOrderError",
            f"No stop_order_id for {ticker}. Check Tinkoff terminal.",
        )
        return False, None

    # Проверить, открыта ли еще позиция с несколькими попытками
    max_attempts = 3
    attempt = 0
    is_position_open = True  # По умолчанию предполагаем, что позиция открыта
    while attempt < max_attempts:
        try:
            portfolio = client.operations.get_portfolio(account_id=account_id)
            is_position_open = any(pos.figi == figi for pos in portfolio.positions)
            break  # Успешный запрос, выходим из цикла
        except Exception as e:
            logging.error(
                f"Error checking portfolio for {ticker}: {str(e)}, attempt {attempt + 1}"
            )
            attempt += 1
            if attempt < max_attempts:
                time.sleep(1)
            continue

    # После всех попыток
    if attempt >= max_attempts:
        logging.error(
            f"Failed to check portfolio for {ticker} after {max_attempts} attempts"
        )
        notify_error(
            ticker,
            "N/A",
            "StopOrderError",
            f"Failed to check portfolio for {ticker}. Check Tinkoff terminal.",
        )
        return False, None

    if is_position_open:
        # Позиция все еще открыта, стоп-приказ не исполнен
        logging.error(f"Position {ticker} still open, stop order not executed")
        notify_error(
            ticker,
            "N/A",
            "StopOrderError",
            f"Position {ticker} still open, stop order not executed",
        )
        return False, None
    else:
        # Позиция закрыта, предполагаем, что стоп-приказ был исполнен
        logging.info(f"Position {ticker} closed, assuming stop order was executed")
        # Формируем trade_data
        entry_signal_price = positions[ticker].get("signal_price", 0)
        exit_signal_price = positions[ticker][
            "stop_loss_price"
        ]  # Используем stop_loss_price как цену исполнения для стоп-лосса
        quantity = positions[ticker]["quantity"]
        lot_size = positions[ticker].get(
            "lot_size", 1
        )  # По умолчанию 1, если не указано
        total_shares = quantity * lot_size
        entry_broker_fee = positions[ticker].get("entry_broker_fee", 0)
        exit_broker_fee = (
            0.0005 * exit_signal_price * total_shares
        )  # Комиссия 0.05% от размера позиции при закрытии
        broker_fee = entry_broker_fee + exit_broker_fee
        profit_gross = (
            exit_signal_price - entry_signal_price
        ) * total_shares  # Валовая прибыль
        profit_net = profit_gross - broker_fee  # Чистая прибыль с вычетом комиссий
        trade_data = {
            "ticker": ticker,
            "figi": positions[ticker]["figi"],
            "exitComment": exit_comment,
            "instrument_uid": positions[ticker]["instrument_uid"],
            "open_datetime": positions[ticker]["open_datetime"],
            "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "quantity": quantity,
            "entry_signal_price": entry_signal_price,
            "exit_signal_price": exit_signal_price,
            "entry_broker_fee": entry_broker_fee,
            "exit_broker_fee": exit_broker_fee,
            "broker_fee": broker_fee,
            "profit_gross": profit_gross,
            "profit_net": profit_net,
            "entry_client_order_id": positions[ticker]["client_order_id"],
            "entry_exchange_order_id": positions[ticker]["exchange_order_id"],
            "exit_client_order_id": stop_order_id,
            "exit_exchange_order_id": positions[ticker].get(
                "exchange_order_id", None
            ),  # Предполагаем, что это ордер закрытия
        }
        return True, trade_data
