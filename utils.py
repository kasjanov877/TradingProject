# Импорт необходимых библиотек
import csv
import os
import json
import logging
from decimal import Decimal
from tinkoff.invest.utils import quotation_to_decimal

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
def calculate_expected_sum(client, account_id, position_size_percent):
    """
    Рассчитывает сумму позиции на основе процента от свободных средств на счёте.

    Args:
        client: Клиент Tinkoff API.
        account_id: ID аккаунта.
        position_size_percent: Процент от свободных средств.

    Returns:
        float: Рассчитанная сумма позиции (expected_sum).

    Raises:
        Exception: Если портфель недоступен или свободные средства равны нулю.
    """
    try:
        portfolio = client.operations.get_portfolio(account_id=account_id)
        free_balance = float(quotation_to_decimal(portfolio.total_amount_currencies))
        logging.info(f"Free balance: {free_balance} RUB")
        if free_balance <= 0:
            raise ValueError("Свободные средства на счёте равны нулю")
        expected_sum = free_balance * (position_size_percent / 100)
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
