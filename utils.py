import csv
import os
import json
import logging

POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")

def get_quantity(expected_sum, price, lot):
    try:
        cost_per_lot = price * lot
        quantity = int(expected_sum / cost_per_lot)
        return quantity if quantity > 0 else 0
    except Exception as e:
        print(f"Ошибка при расчёте количества: {str(e)}")
        return 0

def log_trade_to_csv(trade_data, csv_file="trades.csv"):
    fieldnames = [
        "ticker", "figi", "instrument_uid", "open_datetime", "close_datetime",
        "entry_price", "exit_price", "quantity", "entry_broker_fee", "exit_broker_fee",
        "broker_fee", "profit_gross", "profit_net", "entry_client_order_id",
        "entry_exchange_order_id", "exit_client_order_id", "exit_exchange_order_id",
        "exitComment", "stop_order_id"
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

def load_positions_from_json(file_path=POSITIONS_FILE):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                positions = json.load(f)
                logging.info(f"Loaded positions from {file_path}: {positions}")
                return positions
        logging.info(f"No positions file found at {file_path}, returning empty positions")
        return {}
    except Exception as e:
        logging.error(f"Error loading positions from {file_path}: {str(e)}")
        return {}

def save_positions_to_json(positions, file_path=POSITIONS_FILE):
    try:
        logging.info(f"Attempting to save positions to {file_path}, cwd: {os.getcwd()}")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=4)
        logging.info(f"Saved positions to {file_path}: {positions}")
    except Exception as e:
        logging.error(f"Error saving positions to {file_path}: {str(e)}")