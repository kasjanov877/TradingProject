# Импорт необходимых библиотек
import csv
import os
import json
import logging
from decimal import Decimal
from tinkoff.invest.utils import quotation_to_decimal
from tenacity import retry, stop_after_attempt, wait_fixed

# Определение путей к файлам
POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")
TOKENS_FIGI_UID_FILE = os.path.join(os.path.dirname(__file__), "tokens_figi_uid.json")


# Расчёт количества лотов для открытия позиции
def get_quantity(expected_sum, signal_price, lot):
    try:
        cost_per_lot = signal_price * lot
        quantity = int(expected_sum / cost_per_lot)
        return quantity if quantity > 0 else 0
    except Exception as e:
        logging.error(f"Ошибка при расчёте количества: {str(e)}")
        return 0


# Расчёт суммы позиции как процент от свободных средств
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def calculate_expected_sum(client, account_id, position_size_percent):
    """
    Рассчитывает сумму позиции на основе процента от свободных средств на счёте.

    Args:
        client: Клиент Tinkoff API.
        account_id: ID аккаунта.
        position_size_percent: Процент от выделенной суммы (определяет плечо).

    Returns:
        float: Рассчитанная сумма позиции (expected_sum).

    Raises:
        ValueError: Если свободные средства равны нулю, слишком много позиций или недостаточно средств.
        Exception: Если портфель недоступен.
    """
    try:
        portfolio = client.operations.get_portfolio(account_id=account_id)
        free_balance = float(quotation_to_decimal(portfolio.total_amount_currencies))
        logging.info(f"Free balance: {free_balance} RUB")

        if free_balance <= 0:
            raise ValueError("Свободные средства на счёте равны нулю")

        # Логирование всех позиций для диагностики
        logging.info(
            f"Portfolio positions: {[(pos.figi, pos.instrument_type) for pos in portfolio.positions]}"
        )

        # Подсчёт открытых позиций (только акции)
        num_positions = sum(
            1 for pos in portfolio.positions if pos.instrument_type == "share"
        )
        logging.info(f"Open positions: {num_positions}")

        if num_positions >= 3:
            raise ValueError("Слишком много открытых позиций")

        # Расчёт выделенной суммы (1/3, 1/2 или весь остаток)
        allocated_amount = free_balance / (3 - num_positions)
        logging.info(f"Allocated amount: {allocated_amount} RUB")

        # Проверка достаточности средств
        if free_balance < allocated_amount:
            raise ValueError(
                f"Недостаточно средств: {free_balance} RUB для выделенной суммы {allocated_amount} RUB"
            )

        # Расчёт суммы позиции с учётом position_size_percent
        expected_sum = allocated_amount * (position_size_percent / 100)
        logging.info(
            f"Calculated expected_sum: {expected_sum} for position_size_percent: {position_size_percent}"
        )
        return expected_sum
    except Exception as e:
        logging.error(f"Error retrieving portfolio: {str(e)}")
        raise Exception(f"Не удалось получить данные портфеля: {str(e)}")


# Запись данных о сделке в CSV-файл
def log_trade_to_csv(trade_data, csv_file="trades.csv"):
    fieldnames = [
        "ticker",
        "figi",
        "exitComment",
        "instrument_uid",
        "open_datetime",
        "close_datetime",
        "quantity",
        "entry_signal_price",
        "exit_signal_price",
        "entry_broker_fee",
        "exit_broker_fee",
        "broker_fee",
        "profit_gross",
        "profit_net",
        "entry_client_order_id",
        "entry_exchange_order_id",
        "exit_client_order_id",
        "exit_exchange_order_id",
    ]
    try:
        logging.info(
            f"Attempting to write trade data to {csv_file}:\n{json.dumps(trade_data, indent=2)}"
        )
        file_exists = os.path.exists(csv_file)
        with open(csv_file, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade_data)
        logging.info(f"Successfully wrote trade data to {csv_file}")
    except Exception as e:
        logging.error(f"Ошибка при записи в {csv_file}: {str(e)}")
        raise


# Функции для проверки состояния позиций
def check_position_exists(ticker, positions):
    return ticker in positions


def check_direction(ticker, direction, positions):
    return ticker in positions and positions[ticker]["direction"] == direction


def can_open_position(positions, max_tickers=5):
    return len(positions) < max_tickers


# Работа с файлом позиций (чтение и запись)
def load_positions_from_json(file_path=POSITIONS_FILE):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                positions = json.load(f)
                logging.info(
                    f"Loaded positions from {file_path}:\n{json.dumps(positions, indent=2)}"
                )
                return positions
        return {}
    except Exception as e:
        logging.error(f"Error loading positions from {file_path}: {str(e)}")
        return {}


def save_positions_to_json(positions, file_path=POSITIONS_FILE):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False, indent=4)
        logging.info(
            f"Saved positions to {file_path}:\n{json.dumps(positions, indent=2)}"
        )
    except Exception as e:
        logging.error(f"Error saving positions to {file_path}: {str(e)}")


# Преобразование данных Quotation в Decimal для работы с API
def quotation_to_decimal(quotation):
    return Decimal(quotation.units) + Decimal(quotation.nano) / Decimal(1_000_000_000)
