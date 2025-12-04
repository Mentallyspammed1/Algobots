# tests/test_app.py
import pytest
from app import app as flask_app  # Import the Flask app instance from app.py


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Configure the app for testing
    flask_app.config.update(
        {
            "TESTING": True,
        },
    )

    # Other setup can go here.
    # For example, setting up a test database.

    return flask_app  # provide the app instance


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


def test_health_check(client):
    """Test the root endpoint for a successful response."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Bybit Trading Terminal Backend is running!" in response.data


# --- Tests for /analyze endpoint ---


def test_analyze_success(client):
    """Test a successful request to the /analyze endpoint."""
    # Sample data mimicking frontend payload
    sample_data = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "klines": [
            [1678886400000, 25000.00, 25500.00, 24800.00, 25200.00, 1000.00],
            [1678890000000, 25200.00, 25800.00, 25100.00, 25600.00, 1200.00],
            [1678893600000, 25600.00, 26000.00, 25500.00, 25900.00, 1100.00],
            [1678897200000, 25900.00, 26200.00, 25700.00, 26100.00, 1300.00],
            [1678900800000, 26100.00, 26500.00, 26000.00, 26400.00, 1600.00],
        ],
        "indicators": {
            "sma": [25200.00, 25300.00, 25400.00, 25500.00, 25600.00],
            "rsi": [55.0, 58.0, 60.0, 62.0, 64.0],
            "supertrend": {
                "line": [24800.00, 25100.00, 25500.00, 25700.00, 26000.00],
                "trend": [true, true, true, true, true],
            },
        },
        "signals": [
            {
                "type": "Supertrend",
                "strength": 80,
                "direction": "buy",
                "price": 25200.00,
                "time": 1678886400000,
            },
        ],
    }
    response = client.post("/analyze", json=sample_data)
    assert response.status_code == 200
    data = response.get_json()
    assert "analysis" in data
    assert isinstance(data["analysis"], str)
    assert len(data["analysis"]) > 0


def test_analyze_missing_symbol(client):
    """Test /analyze endpoint with missing required parameter 'symbol'."""
    sample_data = {
        # "symbol": "BTCUSDT", # Symbol is missing
        "interval": "1h",
        "klines": [[1678886400000, 25000.00, 25500.00, 24800.00, 25200.00, 1000.00]],
        "indicators": {},
        "signals": [],
    }
    response = client.post("/analyze", json=sample_data)
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "Missing required data: symbol" in data["error"]


def test_analyze_invalid_json(client):
    """Test /analyze endpoint with invalid JSON payload."""
    response = client.post(
        "/analyze", data="This is not JSON",
    )  # Sending raw string instead of JSON
    assert response.status_code == 400  # Flask typically returns 400 for invalid JSON
    data = response.get_json()
    assert "error" in data
    assert "Invalid JSON payload" in data["error"]


# Note: Testing the Gemini API call itself would require mocking or a dedicated test API.
# These tests focus on the Flask endpoint's handling of requests and data validation.
