import os
from tinkoff.invest import Client
from tinkoff_api import TOKEN


def main():
    with Client(TOKEN) as client:
        # Используем dir() для получения списка доступных атрибутов и методов
        print(dir(client))

if __name__ == "__main__":
    main()