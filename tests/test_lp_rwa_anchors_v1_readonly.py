"""Mock contracts for the three free, keyless, read-only RWA anchors."""

from datetime import datetime, timezone

import pytest

from scripts.lp_rwa_anchors_v1_readonly import (
    AnchorUnavailable,
    BybitAnchorClient,
    RobinhoodAnchorClient,
    XStocksAnchorClient,
)


class FakeClock:
    def __init__(self, value=1_786_118_400.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        for needle, response in self.responses.items():
            if needle in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")


def test_xstocks_parses_mocked_official_contract_to_nine_fields():
    transport = FakeTransport({
        "/token?type=xstocks": {"nodes": [{"id": "id1", "symbol": "AAPLx", "underlyingSymbol": "AAPL", "isTradingHalted": False}]},
        "/token/AAPLx/multiplier": {"currentMultiplier": 0.5, "newMultiplier": 0, "activationDateTime": 0},
        "/quotes/assets/AAPLx": {"symbol": "AAPLx", "currency": "USD", "bid": 49.9, "ask": 50.1,
                                    "isTradingHalted": False, "canQuote": True, "sourceTimestamp": "2026-08-07T15:00:00Z"},
    })
    quote = XStocksAnchorClient(transport=transport, clock=FakeClock()).quote("AAPLx", market_session="REGULAR")
    assert quote.instrument.issuer == "Backed"
    assert quote.instrument.underlying_ticker == "AAPL"
    assert str(quote.instrument.multiplier) == "0.5"
    assert str(quote.price) == "50.0"
    assert len(quote.instrument.to_mapping()) == 9


def test_xstocks_realistic_weekend_null_price_fails_closed_explainably():
    transport = FakeTransport({
        "/token?type=xstocks": {"nodes": [{"id": "id1", "symbol": "AAPLx", "underlyingSymbol": "AAPL", "isTradingHalted": False}]},
        "/token/AAPLx/multiplier": {"currentMultiplier": 1},
        "/quotes/assets/AAPLx": {"symbol": "AAPLx", "currency": "USD", "bid": None, "ask": None,
                                    "isTradingHalted": False, "canQuote": False},
    })
    with pytest.raises(AnchorUnavailable, match="xstocks_official.*bid/ask"):
        XStocksAnchorClient(transport=transport, clock=FakeClock()).quote("AAPLx", market_session="PRIMARY_CLOSED")


def test_xstocks_missing_timestamp_fails_closed_even_with_prices():
    transport = FakeTransport({
        "/token?type=xstocks": {"nodes": [{"id": "id1", "symbol": "AAPLx", "underlyingSymbol": "AAPL", "isTradingHalted": False}]},
        "/token/AAPLx/multiplier": {"currentMultiplier": 1},
        "/quotes/assets/AAPLx": {"symbol": "AAPLx", "currency": "USD", "bid": 100, "ask": 101,
                                    "isTradingHalted": False, "canQuote": True},
    })
    with pytest.raises(AnchorUnavailable, match="xstocks_official.*timestamp"):
        XStocksAnchorClient(transport=transport, clock=FakeClock()).quote("AAPLx", market_session="REGULAR")


def test_bybit_parses_public_spot_ticker_and_server_timestamp():
    transport = FakeTransport({"/v5/market/tickers": {
        "retCode": 0, "retMsg": "OK", "time": 1786114800000,
        "result": {"category": "spot", "list": [{"symbol": "AAPLXUSDT", "bid1Price": "99.9", "ask1Price": "100.1"}]},
    }})
    quote = BybitAnchorClient(transport=transport, clock=FakeClock()).quote("AAPLXUSDT", market_session="REGULAR")
    assert quote.source_name == "bybit_public_spot"
    assert quote.instrument.instrument_id == "backed:AAPLx"
    assert quote.instrument.quote_currency == "USDT"
    assert str(quote.price) == "100.0"


def test_robinhood_combines_public_price_and_multiplier_without_losing_semantics():
    transport = FakeTransport({
        "/rhj/prices/AAPL": {"quotes": [{"tokenSymbol": "AAPL", "bid": "199", "ask": "201", "currency": "USD",
                                           "isTradingHalt": False, "generatedAt": "2026-08-07T15:00:00Z"}]},
        "/rhj/assets": {"assets": [{"id": "rh1", "tokenSymbol": "AAPL", "currentMultiplier": "0.5",
                                      "pendingMultiplier": "", "status": "ASSET_STATUS_ACTIVE"}]},
    })
    quote = RobinhoodAnchorClient(transport=transport, clock=FakeClock()).quote("AAPL", market_session="REGULAR")
    assert quote.instrument.issuer == "Robinhood"
    assert quote.instrument.multiplier == pytest.approx(0.5)
    assert str(quote.price) == "100.0"  # token-equivalent price; normalization returns $200/share
    assert quote.instrument.redemption_status == "OPEN"


@pytest.mark.parametrize("client_factory,symbol,responses", [
    (BybitAnchorClient, "AAPLXUSDT", {"/v5/market/tickers": {"retCode": 0, "time": 1786114800000, "result": {"list": []}}}),
    (RobinhoodAnchorClient, "AAPL", {"/rhj/prices/AAPL": {"quotes": []}, "/rhj/assets": {"assets": []}}),
])
def test_malformed_or_empty_public_responses_fail_closed(client_factory, symbol, responses):
    with pytest.raises(AnchorUnavailable):
        client_factory(transport=FakeTransport(responses), clock=FakeClock()).quote(symbol, market_session="REGULAR")


def test_15_second_cache_prevents_duplicate_robinhood_requests():
    clock = FakeClock()
    transport = FakeTransport({
        "/rhj/prices/AAPL": {"quotes": [{"tokenSymbol": "AAPL", "bid": "199", "ask": "201", "currency": "USD",
                                           "isTradingHalt": False, "generatedAt": "2026-08-07T15:00:00Z"}]},
        "/rhj/assets": {"assets": [{"id": "rh1", "tokenSymbol": "AAPL", "currentMultiplier": "1",
                                      "pendingMultiplier": "", "status": "ASSET_STATUS_ACTIVE"}]},
    })
    client = RobinhoodAnchorClient(transport=transport, clock=clock)
    first = client.quote("AAPL", market_session="REGULAR")
    clock.value += 14.9
    second = client.quote("AAPL", market_session="REGULAR")
    assert first is second
    assert len(transport.calls) == 2


def test_cache_expiry_refreshes_and_robinhood_rate_limit_is_explicit():
    clock = FakeClock()
    transport = FakeTransport({
        "/rhj/prices/AAPL": {"quotes": [{"tokenSymbol": "AAPL", "bid": "199", "ask": "201", "currency": "USD",
                                           "isTradingHalt": False, "generatedAt": "2026-08-07T15:00:00Z"}]},
        "/rhj/assets": {"assets": [{"id": "rh1", "tokenSymbol": "AAPL", "currentMultiplier": "1",
                                      "pendingMultiplier": "", "status": "ASSET_STATUS_ACTIVE"}]},
    })
    client = RobinhoodAnchorClient(transport=transport, clock=clock)
    assert client.cache_ttl_seconds == 15
    assert client.max_requests_per_second == 60
    client.quote("AAPL", market_session="REGULAR")
    clock.value += 15.1
    client.quote("AAPL", market_session="REGULAR")
    assert len(transport.calls) == 4


def test_no_client_accepts_or_stores_api_credentials():
    for cls in (XStocksAnchorClient, BybitAnchorClient, RobinhoodAnchorClient):
        assert "api_key" not in cls.__init__.__annotations__
        with pytest.raises(TypeError):
            cls(transport=FakeTransport({}), clock=FakeClock(), api_key="forbidden")

