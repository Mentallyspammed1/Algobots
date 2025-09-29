from backend_app import app
from fastapi.testclient import TestClient

client = TestClient(app)


# Test for GET /klines endpoint
def test_get_klines():
    response = client.get("/klines?symbol=BTCUSDT&interval=15&limit=10")
    assert response.status_code == 200
    klines = response.json()
    assert isinstance(klines, list)
    assert len(klines) == 10
    for kline in klines:
        assert "timestamp" in kline
        assert "open" in kline
        assert "high" in kline
        assert "low" in kline
        assert "close" in kline
        assert "volume" in kline
        assert isinstance(kline["timestamp"], int)
        assert isinstance(kline["open"], float)


# Test for POST /indicators endpoint
def test_post_indicators_ema_rsi():
    # Create mock kline data for the request
    mock_klines_data = [
        {
            "timestamp": 1678886400000,
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1000.0,
        },
        {
            "timestamp": 1678886460000,
            "open": 102.0,
            "high": 108.0,
            "low": 101.0,
            "close": 106.0,
            "volume": 1200.0,
        },
        {
            "timestamp": 1678886520000,
            "open": 106.0,
            "high": 107.0,
            "low": 103.0,
            "close": 104.0,
            "volume": 1100.0,
        },
        {
            "timestamp": 1678886580000,
            "open": 104.0,
            "high": 110.0,
            "low": 103.0,
            "close": 109.0,
            "volume": 1500.0,
        },
        {
            "timestamp": 1678886640000,
            "open": 109.0,
            "high": 112.0,
            "low": 107.0,
            "close": 111.0,
            "volume": 1300.0,
        },
        {
            "timestamp": 1678886700000,
            "open": 111.0,
            "high": 115.0,
            "low": 109.0,
            "close": 113.0,
            "volume": 1400.0,
        },
        {
            "timestamp": 1678886760000,
            "open": 113.0,
            "high": 114.0,
            "low": 110.0,
            "close": 112.0,
            "volume": 1000.0,
        },
        {
            "timestamp": 1678886820000,
            "open": 112.0,
            "high": 116.0,
            "low": 111.0,
            "close": 115.0,
            "volume": 1600.0,
        },
        {
            "timestamp": 1678886880000,
            "open": 115.0,
            "high": 118.0,
            "low": 114.0,
            "close": 117.0,
            "volume": 1700.0,
        },
        {
            "timestamp": 1678886940000,
            "open": 117.0,
            "high": 120.0,
            "low": 116.0,
            "close": 119.0,
            "volume": 1800.0,
        },
    ]

    request_payload = {"klines": mock_klines_data, "ema_period": 3, "rsi_period": 3}

    response = client.post("/indicators", json=request_payload)
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["status"] == "success"
    data = response_json["data"]
    assert isinstance(data, list)
    assert len(data) == len(mock_klines_data)

    # Check if EMA and RSI columns are added
    for item in data:
        assert "ema_3" in item
        assert "rsi_3" in item
        # Ensure some values are not None (i.e., calculated)
        if item["timestamp"] == mock_klines_data[2]["timestamp"]:
            assert item["ema_3"] is not None  # First EMA value should be here
        if item["timestamp"] == mock_klines_data[3]["timestamp"]:
            assert item["rsi_3"] is not None  # First RSI value should be here


def test_post_indicators_supertrend():
    mock_klines_data = [
        {
            "timestamp": 1678886400000,
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1000.0,
        },
        {
            "timestamp": 1678886460000,
            "open": 102.0,
            "high": 108.0,
            "low": 101.0,
            "close": 106.0,
            "volume": 1200.0,
        },
        {
            "timestamp": 1678886520000,
            "open": 106.0,
            "high": 107.0,
            "low": 103.0,
            "close": 104.0,
            "volume": 1100.0,
        },
        {
            "timestamp": 1678886580000,
            "open": 104.0,
            "high": 110.0,
            "low": 103.0,
            "close": 109.0,
            "volume": 1500.0,
        },
        {
            "timestamp": 1678886640000,
            "open": 109.0,
            "high": 112.0,
            "low": 107.0,
            "close": 111.0,
            "volume": 1300.0,
        },
        {
            "timestamp": 1678886700000,
            "open": 111.0,
            "high": 115.0,
            "low": 109.0,
            "close": 113.0,
            "volume": 1400.0,
        },
        {
            "timestamp": 1678886760000,
            "open": 113.0,
            "high": 114.0,
            "low": 110.0,
            "close": 112.0,
            "volume": 1000.0,
        },
        {
            "timestamp": 1678886820000,
            "open": 112.0,
            "high": 116.0,
            "low": 111.0,
            "close": 115.0,
            "volume": 1600.0,
        },
        {
            "timestamp": 1678886880000,
            "open": 115.0,
            "high": 118.0,
            "low": 114.0,
            "close": 117.0,
            "volume": 1700.0,
        },
        {
            "timestamp": 1678886940000,
            "open": 117.0,
            "high": 120.0,
            "low": 116.0,
            "close": 119.0,
            "volume": 1800.0,
        },
    ]

    request_payload = {
        "klines": mock_klines_data,
        "supertrend_period": 7,
        "supertrend_multiplier": 3.0,
    }

    response = client.post("/indicators", json=request_payload)
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["status"] == "success"
    data = response_json["data"]
    assert isinstance(data, list)
    assert len(data) == len(mock_klines_data)

    # Check if Supertrend columns are added
    for item in data:
        assert "supertrend" in item
        assert "supertrend_direction" in item
        # Ensure some values are not None (i.e., calculated)
        if item["timestamp"] == mock_klines_data[6]["timestamp"]:
            assert item["supertrend"] is not None
            assert item["supertrend_direction"] is not None


def test_post_indicators_no_klines():
    request_payload = {"klines": [], "ema_period": 3}
    response = client.post("/indicators", json=request_payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "No kline data provided."


def test_post_indicators_invalid_kline_data():
    request_payload = {
        "klines": [
            {
                "timestamp": 1678886400000,
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": "invalid",
            }  # Invalid volume type
        ],
        "ema_period": 3,
    }
    response = client.post("/indicators", json=request_payload)
    assert response.status_code == 422  # Unprocessable Entity for validation errors
