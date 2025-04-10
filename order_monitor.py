import time
from tinkoff.invest import Client
from tinkoff_api import TOKEN

def monitor_order_completion(account_id, ticker, open_order_id, close_order_id, current_positions, log_trade_to_csv, exit_comment=None, exit_client_order_id=None, lock=None):
    """
    Мониторит выполнение ордера закрытия позиции и записывает данные о сделке в CSV.
    
    Аргументы:
        account_id (str): ID аккаунта.
        ticker (str): Тикер инструмента.
        open_order_id (str): Биржевой ID ордера открытия.
        close_order_id (str): Биржевой ID ордера закрытия.
        current_positions (dict): Словарь текущих открытых позиций.
        log_trade_to_csv (callable): Функция для записи данных о сделке в CSV.
        exit_comment (str or None): Комментарий выхода (например, "LongTrTake").
        exit_client_order_id (str or None): Клиентский ID ордера закрытия.
    """
    with Client(TOKEN, timeout=10) as client:  # Создаём новый клиент внутри функции
        while True:
            # Получаем состояние ордера закрытия
            close_state = client.orders.get_order_state(account_id=account_id, order_id=close_order_id)
            
            # Проверяем, полностью ли исполнен ордер (lots_executed == lots_requested) и его статус (FILL = 1)
            if close_state.lots_executed == close_state.lots_requested and close_state.execution_report_status == 1:  # Исполнена (FILL)
                # Рассчитываем цену закрытия в рублях (units + nano/10^9)
                exit_price = close_state.executed_order_price.units + close_state.executed_order_price.nano / 1_000_000_000
                # Получаем состояние ордера открытия
                open_state = client.orders.get_order_state(account_id=account_id, order_id=open_order_id)
                # Рассчитываем цену открытия в рублях
                entry_price = open_state.executed_order_price.units + open_state.executed_order_price.nano / 1_000_000_000
                # Извлекаем количество лотов и направление из текущей позиции
                quantity = current_positions[ticker]["quantity"]
                direction = current_positions[ticker]["direction"]
                # Рассчитываем валовую прибыль в зависимости от направления (buy или sell)
                profit_gross = (exit_price - entry_price) * quantity if direction == "buy" else (entry_price - exit_price) * quantity
                # Рассчитываем комиссию брокера (0.05% от валовой прибыли)
                broker_fee = profit_gross * 0.0005
                # Формируем данные о сделке для записи
                trade_data = {
                    "ticker": ticker,
                    "figi": current_positions[ticker]["figi"],
                    "instrument_uid": current_positions[ticker]["instrument_uid"],
                    "open_datetime": current_positions[ticker]["open_datetime"],
                    "close_datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "broker_fee": broker_fee,
                    "profit_gross": profit_gross,
                    "profit_net": profit_gross - broker_fee,
                    "entry_client_order_id": current_positions[ticker]["client_order_id"],
                    "entry_exchange_order_id": open_order_id,
                    "exit_client_order_id": exit_client_order_id,
                    "exit_exchange_order_id": close_order_id,
                    "exitComment": exit_comment
                }
                # Записываем данные о сделке в CSV
                log_trade_to_csv(trade_data)
                # Удаляем закрытую позицию из current_positions
                with lock:
                    del current_positions[ticker]
                break
            # Ждем 1 секунду перед следующей проверкой состояния ордера
            time.sleep(1)