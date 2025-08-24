import time
import requests
import hashlib
import hmac
from urllib.parse import urlencode
from decimal import Decimal
from dataclasses import dataclass


@dataclass
class Market:
    first: str
    second: str
    price_precision: Decimal
    amount_precision: Decimal
    min_base_order_size: Decimal
    min_quote_order_size: Decimal


def round_to_precision(n: Decimal, precision: Decimal, round_up: bool = False) -> Decimal:
    if round_up:
        result = ((n + precision - Decimal('1E-20')) // precision) * precision
    else:
        result = (n // precision) * precision
    return result.normalize()


class TabdealAPI:
    BASE_URL = "https://api-web.tabdeal.org"

    def __init__(self, api_key: str, secret_key: str, passphrase: str = None):
        super().__init__()

        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.session = None
        self.markets = self.get_markets()

    def get_signature(self, input_data):
        query_string = urlencode(input_data)
        signature = hmac.new(self.secret_key.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature

    def request(self, *args, **kwargs):
        headers = {"X-MBX-APIKEY": self.api_key}

        if "headers" in kwargs.keys():
            kwargs.get("headers").update(headers)
        else:
            headers = {"X-MBX-APIKEY": self.api_key}
            kwargs["headers"] = headers

        return requests.request(*args, **kwargs)

    def get(self, params, *args, **kwargs):
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self.get_signature(input_data=params)
        return self.request(params=params, method="GET", *args, **kwargs)

    def post(self, data, *args, **kwargs):
        data["timestamp"] = int(time.time() * 1000)
        data["signature"] = self.get_signature(input_data=data)
        return self.request(data=data, method="POST", *args, **kwargs)

    def delete(self, data, *args, **kwargs):
        data["timestamp"] = int(time.time() * 1000)
        data["signature"] = self.get_signature(input_data=data)
        return self.request(data=data, method="DELETE", *args, **kwargs)

    def get_markets(self):
        response = self.get(params={}, url=f"{self.BASE_URL}/r/api/v1/exchangeInfo")
        markets = {}

        if not response.status_code in [200, 201]:
            raise Exception(f"response text: {response.text}\n")

        for market_data in response.json():
            price_precision = None
            amount_precision = None
            min_base_order_size = None
            min_quote_order_size = None

            for filter in market_data["filters"]:
                if filter["filterType"] == "PRICE_FILTER":
                    price_precision = Decimal(filter["tickSize"])
                if filter["filterType"] == "LOT_SIZE":
                    amount_precision = Decimal(filter["stepSize"])
                    min_base_order_size = Decimal(filter["minQty"])
                if filter["filterType"] == "MIN_NOTIONAL":
                    min_quote_order_size = Decimal(filter["minNotional"])

            markets[market_data["baseAsset"]] = Market(
                first=market_data["baseAsset"],
                second=market_data["quoteAsset"],
                price_precision=price_precision,
                amount_precision=amount_precision,
                min_base_order_size=min_base_order_size,
                min_quote_order_size=min_quote_order_size,
            )

        return markets

    def get_price_usdt_ask(self, currency_symbol):
        response = self.get(params={"symbol": f"{currency_symbol}USDT"}, url=f"{self.BASE_URL}/r/api/v1/depth")
        if not response.status_code in [200, 201]:
            raise Exception(f"response text: {response.text}\n")

        asks = response.json()["asks"]
        ask_price = Decimal(asks[0][0])
        return ask_price

    def place_order(self, usdt_value, currency_symbol):
        market = self.markets.get(currency_symbol)

        if market is None:
            raise Exception(f"market {currency_symbol} not found in tabdeal :(")

        price = self.get_price_usdt_ask(currency_symbol)
        quantity = (Decimal(usdt_value) / price)
        quantity = round_to_precision(quantity, precision=market.amount_precision, round_up=True)

        data = {
            "side": "BUY",
            "type": "MARKET",
            "quantity": quantity,
            "symbol": f"{currency_symbol}USDT",
        }

        response = self.post(data=data, url=f"{self.BASE_URL}/api/v1/order")

        if not response.status_code in [200, 201]:
            raise Exception(f"response text: {response.text}\n")

        response = response.json()

        text = f"bought {currency_symbol}: amount: {response['executedQty']} value is {response['cummulativeQuoteQty']}"

        return text
