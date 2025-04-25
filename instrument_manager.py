import json
import os
import logging
from decimal import Decimal
from tinkoff.invest import Client, InstrumentIdType
from utils import quotation_to_decimal, TOKENS_FIGI_UID_FILE

def get_instrument_data(client: Client, figi: str, ticker: str):
    """
    Получает данные об инструменте (instrument_uid, lot, min_price_increment) из кэша или API.

    Args:
        client: Клиент Tinkoff API.
        figi: FIGI инструмента.
        ticker: Тикер инструмента.

    Returns:
        tuple: (instrument_uid, lot, min_price_increment) или (None, None, None) при ошибке.
    """
    instrument_data = {}
    try:
        if os.path.exists(TOKENS_FIGI_UID_FILE):
            with open(TOKENS_FIGI_UID_FILE, 'r', encoding='utf-8') as json_file:
                instrument_data = json.load(json_file)
            logging.info(f"Loaded instrument data from {TOKENS_FIGI_UID_FILE}")
        else:
            logging.info(f"No instrument data file found at {TOKENS_FIGI_UID_FILE}, starting with empty data")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in {TOKENS_FIGI_UID_FILE}: {str(e)}")
        instrument_data = {}
    except Exception as e:
        logging.error(f"Error loading instrument data: {str(e)}")
        instrument_data = {}

    # Проверка кэша
    if figi in instrument_data:
        instrument_uid = instrument_data[figi]["instrument_uid"]
        lot = instrument_data[figi]["lot"]
        min_price_increment = Decimal(instrument_data[figi]["min_price_increment"])
        logging.info(f"Found instrument in cache: figi={figi}, uid={instrument_uid}, lot={lot}, min_price_increment={min_price_increment}")
        return instrument_uid, lot, min_price_increment

    # Запрос к API
    try:
        instrument = client.instruments.get_instrument_by(
            id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
        ).instrument
        if not instrument:
            logging.error(f"Instrument not found for FIGI: {figi}")
            return None, None, None

        instrument_uid = instrument.uid
        lot = instrument.lot
        min_price_increment = quotation_to_decimal(instrument.min_price_increment)
        instrument_data[figi] = {
            "ticker": ticker,
            "instrument_uid": instrument_uid,
            "lot": lot,
            "min_price_increment": str(min_price_increment)
        }

        # Сохранение кэша
        with open(TOKENS_FIGI_UID_FILE, 'w', encoding='utf-8') as json_file:
            json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
        logging.info(f"Saved new instrument data: figi={figi}, uid={instrument_uid}, lot={lot}, min_price_increment={min_price_increment}")

        return instrument_uid, lot, min_price_increment

    except Exception as e:
        logging.error(f"Error fetching instrument data for FIGI {figi}: {str(e)}")
        return None, None, None