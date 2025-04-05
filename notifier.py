import time

def notify_error(ticker, sum_value, error_type, error_message):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    badge = (
        "*** ALERT!!! ***\n"
        f"Ticker: {ticker}\n"
        f"Sum: {sum_value}\n"
        f"Time: {current_time}\n"
        f"Error: {error_type} - {error_message}\n"
        "****************"
    )
    print(badge)