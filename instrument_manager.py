import json
import os
import logging
from decimal import Decimal
from tinkoff.invest import Client, InstrumentIdType
from utils import quotation_to_decimal

def get_instrument_data(client: Client, figi: str, ticker: str):
    """
    Получает данные об инструменте (instrument_uid, lot) из кэша или API.

    Args:
        client: Клиент Tinkoff API.
        figi: FIGI инструмента.
        ticker: Тикер инструмента.

    Returns:
        tuple: (instrument_uid, lot) или (None, None) при ошибке.
    """
    json_file_path = "tokens_figi_uid.json"
    instrument_data = {}

    try:
        # Загрузка кэша
        if os.path.exists(json_file_path):
            with open(json_file_path, 'r', encoding='utf-8') as json_file:
                instrument_data = json.load(json_file)
            logging.info(f"Loaded instrument data from {json_file_path}")
        else:
            logging.info(f"No instrument data file found at {json_file_path}, starting with empty data")

        # Проверка кэша
        if figi in instrument_data:
            instrument_uid = instrument_data[figi]["instrument_uid"]
            lot = instrument_data[figi]["lot"]
            min_price_increment = Decimal(instrument_data[figi]["min_price_increment"])
            logging.info(f"Found instrument in cache: figi={figi}, uid={instrument_uid}, lot={lot}, min_price_increment={min_price_increment}")
            return instrument_uid, lot, min_price_increment

        # Запрос к API
        instrument = client.instruments.get_instrument_by(
            id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
        ).instrument
        if not instrument:
            logging.error(f"Instrument not found for FIGI: {figi}")
            return None, None

        instrument_uid = instrument.uid
        lot = instrument.lot
        min_price_increment = quotation_to_decimal(instrument.min_price_increment)
        if min_price_increment is None:
            logging.error(f"min_price_increment is None for FIGI: {figi}")
            return {"error": f"Не удалось получить min_price_increment для FIGI {figi}"}, 400
        instrument_data[figi] = {
            "ticker": ticker,
            "instrument_uid": instrument_uid,
            "lot": lot,
            "min_price_increment": str(min_price_increment)  # Сохраняем как строку для JSON
        }

        # Сохранение кэша
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
        logging.info(f"Saved new instrument data: figi={figi}, uid={instrument_uid}, lot={lot}, min_price_increment={min_price_increment}")

        return instrument_uid, lot, min_price_increment

    except Exception as e:
        logging.error(f"Error fetching instrument data for FIGI {figi}: {str(e)}")
        return None, None, None