import csv
import os

def get_quantity(expected_sum, price, lot):
    try:
        cost_per_lot = price * lot  # Стоимость одного лота
        quantity = int(expected_sum / cost_per_lot)  # Количество лотов
        return quantity if quantity > 0 else 0
    except Exception as e:
        print(f"Ошибка при расчёте количества: {str(e)}")
        return 0

def log_trade_to_csv(trade_data, csv_file="trades.csv"):
    fieldnames = [
        "ticker", "figi", "instrument_uid", "open_datetime", "close_datetime",
        "entry_price", "exit_price", "quantity", "broker_fee", "profit_gross",
        "profit_net", "entry_client_order_id", "entry_exchange_order_id",
        "exit_client_order_id", "exit_exchange_order_id", "exitComment"
    ]
    file_exists = os.path.exists(csv_file)
    with open(csv_file, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_data)

def check_position_exists(ticker, positions):
    return ticker in positions

def check_direction(ticker, direction, positions):
    return ticker in positions and positions[ticker]["direction"] == direction

def can_open_position(positions, max_tickers=5):
    return len(positions) < max_tickers