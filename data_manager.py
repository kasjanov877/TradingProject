# data_manager.py
import json
import os

JSON_FILE = "tokens_figi_uid.json"

def save_library_to_json(library):
    with open(JSON_FILE, 'w', encoding='utf-8') as json_file:
        json.dump(library, json_file, ensure_ascii=False, indent=4)

def initialize_libraries():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r', encoding='utf-8') as json_file:
            return json.load(json_file)
    return {}