# tinkoff_api.py
from tinkoff.invest import Client, MoneyValue

TOKEN = "t.Gk6qrpcVv87MYW8ZPgUOO7dKVV-GLQKtKAeymLEmZaGA6UTi9LseC0zvkCZ4GrgRdnrNFxfuwTgjT1V4xV-oJA"

def initialize_sandbox_account(client):
    accounts = client.sandbox.get_sandbox_accounts()
    if accounts.accounts:
        account_id = accounts.accounts[0].id
        print(f"Подключено к существующему счету: {account_id}")
        return account_id
    else:
        sandbox_account = client.sandbox.open_sandbox_account()
        account_id = sandbox_account.account_id
        client.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount=MoneyValue(units=200000, nano=0, currency="rub")
        )
        print(f"Создан новый счет: {account_id}")
        return account_id