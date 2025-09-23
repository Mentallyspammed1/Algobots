exchange_options = {
        'apiKey': AK, 'secret': AS, 'enableRateLimit': True,
        'options': {'defaultType': 'linear', 'adjustForTimeDifference': True,
                    'fetchTickerTimeout': 10000, 'fetchBalanceTimeout': 15000,
                    'createOrderTimeout': 20000, 'cancelOrderTimeout': 15000,
                    'fetchPositionsTimeout': 15000, 'fetchOHLCVTimeout': 15000,
                    'recvWindow': 10000} # Explicitly set recvWindow to 10000ms
    }