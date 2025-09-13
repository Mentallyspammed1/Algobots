Okay, let's create a couple of `.html` "apps" for Bybit trend analysis using their public API. We'll use the Bybit V5 API, specifically the `GET /v5/market/kline` endpoint to fetch candlestick data.

For charting, we'll use a fantastic, lightweight, and open-source library called **Lightweight-Charts** by TradingView, which is perfect for financial data.

---

### App 1: Basic Candlestick Chart with Moving Averages

This app will allow you to select a symbol and interval, fetch its candlestick data, and display it along with two configurable Moving Averages (MA).

**Features:**
*   Symbol selection (e.g., BTCUSDT, ETHUSDT)
*   Interval selection (e.g., 1m, 1h, 1D)
*   Displays candlestick chart
*   Adds two Simple Moving Averages (SMA) to the chart
*   Volume chart below the main price chart
*   Basic error handling and loading indicators

**`bybit_trend_app_v1.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bybit Trend Analysis (Basic)</title>
    <!-- Lightweight-Charts by TradingView -->
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #1a1a2e; /* Dark background */
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        h1 {
            color: #0f3460;
            margin-bottom: 20px;
        }
        .controls {
            background-color: #2e2e4a;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .controls label {
            margin-right: 5px;
            font-weight: bold;
        }
        .controls select, .controls input[type="number"], .controls button {
            padding: 8px 12px;
            border: 1px solid #0f3460;
            border-radius: 5px;
            background-color: #3e3e6b;
            color: #e0e0e0;
            font-size: 1rem;
            min-width: 80px;
        }
        .controls button {
            background-color: #e94560;
            cursor: pointer;
            transition: background-color 0.3s ease;
            font-weight: bold;
        }
        .controls button:hover {
            background-color: #b73347;
        }
        #chart-container {
            width: 90%;
            max-width: 1200px;
            height: 600px;
            background-color: #2e2e4a;
            border-radius: 8px;
            overflow: hidden; /* Important for chart sizing */
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }
        #status {
            margin-top: 20px;
            font-size: 0.9em;
            color: #e94560;
            min-height: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>Bybit Trend Analysis (Candlesticks & MAs)</h1>

    <div class="controls">
        <div>
            <label for="symbol">Symbol:</label>
            <select id="symbol">
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="XRPUSDT">XRPUSDT</option>
                <option value="SOLUSDT">SOLUSDT</option>
                <option value="ADAUSDT">ADAUSDT</option>
            </select>
        </div>
        <div>
            <label for="interval">Interval:</label>
            <select id="interval">
                <option value="1">1m</option>
                <option value="5">5m</option>
                <option value="15">15m</option>
                <option value="30">30m</option>
                <option value="60">1h</option>
                <option value="240">4h</option>
                <option value="720">12h</option>
                <option value="D" selected>1D</option>
                <option value="W">1W</option>
            </select>
        </div>
        <div>
            <label for="limit">Limit:</label>
            <input type="number" id="limit" value="200" min="1" max="1000">
        </div>
        <div>
            <label for="ma1Period">MA1:</label>
            <input type="number" id="ma1Period" value="20" min="5" max="200">
        </div>
        <div>
            <label for="ma2Period">MA2:</label>
            <input type="number" id="ma2Period" value="50" min="5" max="200">
        </div>
        <button id="loadData">Load Data</button>
    </div>

    <div id="status"></div>
    <div id="chart-container"></div>

    <script>
        const API_BASE_URL = 'https://api.bybit.com';
        const chartContainer = document.getElementById('chart-container');
        const symbolSelect = document.getElementById('symbol');
        const intervalSelect = document.getElementById('interval');
        const limitInput = document.getElementById('limit');
        const ma1PeriodInput = document.getElementById('ma1Period');
        const ma2PeriodInput = document.getElementById('ma2Period');
        const loadDataButton = document.getElementById('loadData');
        const statusDiv = document.getElementById('status');

        // Initialize the chart
        const chart = LightweightCharts.createChart(chartContainer, {
            width: chartContainer.offsetWidth,
            height: chartContainer.offsetHeight,
            layout: {
                backgroundColor: '#2e2e4a',
                textColor: '#e0e0e0',
            },
            grid: {
                vertLines: { color: '#3f3f5a' },
                horzLines: { color: '#3f3f5a' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            rightPriceScale: {
                borderColor: '#4d4d73',
            },
            handleScale: {
                axisPressedMouseMove: true,
            },
            handleScroll: {
                vertTouchDrag: true,
            },
        });

        // Add candlestick series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // Add volume series (below main chart)
        const volumeSeries = chart.addHistogramSeries({
            color: '#8383a5',
            priceFormat: { type: 'volume' },
            overlay: true,
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        // MA series
        let ma1Series = null;
        let ma2Series = null;

        // Function to calculate Simple Moving Average (SMA)
        function calculateSMA(data, period) {
            const smaData = [];
            for (let i = 0; i < data.length; i++) {
                if (i >= period - 1) {
                    const sum = data.slice(i - period + 1, i + 1).reduce((acc, val) => acc + val.close, 0);
                    smaData.push({ time: data[i].time, value: sum / period });
                }
            }
            return smaData;
        }

        // Function to fetch and display data
        async function fetchData() {
            const symbol = symbolSelect.value;
            const interval = intervalSelect.value;
            const limit = limitInput.value;
            const ma1Period = parseInt(ma1PeriodInput.value);
            const ma2Period = parseInt(ma2PeriodInput.value);

            statusDiv.textContent = 'Loading data...';
            statusDiv.style.color = '#e0e0e0';

            try {
                // Bybit's API returns timestamps in milliseconds
                const url = `${API_BASE_URL}/v5/market/kline?category=spot&symbol=${symbol}&interval=${interval}&limit=${limit}`;
                const response = await fetch(url);
                const data = await response.json();

                if (data.retCode !== 0) {
                    throw new Error(data.retMsg || 'Failed to fetch data.');
                }

                if (!data.result || !data.result.list || data.result.list.length === 0) {
                    statusDiv.textContent = 'No data available for the selected symbol/interval.';
                    statusDiv.style.color = '#e94560';
                    candlestickSeries.setData([]);
                    volumeSeries.setData([]);
                    if (ma1Series) { ma1Series.setData([]); }
                    if (ma2Series) { ma2Series.setData([]); }
                    return;
                }

                const klineData = data.result.list.map(item => ({
                    time: parseInt(item[0]) / 1000, // Convert ms to seconds
                    open: parseFloat(item[1]),
                    high: parseFloat(item[2]),
                    low: parseFloat(item[3]),
                    close: parseFloat(item[4]),
                    volume: parseFloat(item[5])
                })).reverse(); // Reverse to have oldest data first

                candlestickSeries.setData(klineData);

                const volumeData = klineData.map(item => ({
                    time: item.time,
                    value: item.volume,
                    color: item.close >= item.open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)'
                }));
                volumeSeries.setData(volumeData);

                // Remove old MA series if they exist
                if (ma1Series) { chart.removeSeries(ma1Series); }
                if (ma2Series) { chart.removeSeries(ma2Series); }

                // Add new MA series
                const sma1Data = calculateSMA(klineData, ma1Period);
                ma1Series = chart.addLineSeries({ color: '#fdd835', lineWidth: 1, title: `MA${ma1Period}` }); // Yellow
                ma1Series.setData(sma1Data);

                const sma2Data = calculateSMA(klineData, ma2Period);
                ma2Series = chart.addLineSeries({ color: '#ab47bc', lineWidth: 1, title: `MA${ma2Period}` }); // Purple
                ma2Series.setData(sma2Data);

                statusDiv.textContent = `Data loaded for ${symbol} (${interval})`;
                statusDiv.style.color = '#26a69a';

            } catch (error) {
                console.error("Error fetching data:", error);
                statusDiv.textContent = `Error: ${error.message}. Please check console for details.`;
                statusDiv.style.color = '#e94560';
                candlestickSeries.setData([]);
                volumeSeries.setData([]);
                if (ma1Series) { ma1Series.setData([]); }
                if (ma2Series) { ma2Series.setData([]); }
            }
        }

        // Resize chart on window resize
        new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== chartContainer) {
                return;
            }
            const newRect = entries[0].contentRect;
            chart.applyOptions({ height: newRect.height, width: newRect.width });
        }).observe(chartContainer);

        // Event listeners
        loadDataButton.addEventListener('click', fetchData);
        symbolSelect.addEventListener('change', fetchData);
        intervalSelect.addEventListener('change', fetchData);
        ma1PeriodInput.addEventListener('change', fetchData);
        ma2PeriodInput.addEventListener('change', fetchData);

        // Initial data load
        fetchData();
    </script>
</body>
</html>
```

**How to use `bybit_trend_app_v1.html`:**
1.  Save the code above as `bybit_trend_app_v1.html` on your computer.
2.  Open the file in your web browser (e.g., Chrome, Firefox).
3.  Use the dropdowns and input fields to select your desired symbol, interval, data limit, and Moving Average periods.
4.  Click "Load Data" (or just change an input, it auto-loads) to fetch and display the chart.

---

### App 2: Price Action & Recent Volume Spike Detection

This app focuses on visualizing recent price action and implementing a simple "volume spike" detection. A volume spike is defined as when the current candle's volume is significantly higher than the average volume of the preceding candles.

**Features:**
*   Symbol and interval selection.
*   Candlestick chart.
*   Volume chart with highlighted volume spikes.
*   Table showing recent price data.
*   Configurable volume spike threshold.

**`bybit_trend_app_v2.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bybit Trend Analysis (Volume Spike)</title>
    <!-- Lightweight-Charts by TradingView -->
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #1a1a2e; /* Dark background */
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        h1 {
            color: #0f3460;
            margin-bottom: 20px;
        }
        .controls {
            background-color: #2e2e4a;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .controls label {
            margin-right: 5px;
            font-weight: bold;
        }
        .controls select, .controls input[type="number"], .controls button {
            padding: 8px 12px;
            border: 1px solid #0f3460;
            border-radius: 5px;
            background-color: #3e3e6b;
            color: #e0e0e0;
            font-size: 1rem;
            min-width: 80px;
        }
        .controls button {
            background-color: #e94560;
            cursor: pointer;
            transition: background-color 0.3s ease;
            font-weight: bold;
        }
        .controls button:hover {
            background-color: #b73347;
        }
        #chart-container {
            width: 90%;
            max-width: 1200px;
            height: 500px;
            background-color: #2e2e4a;
            border-radius: 8px;
            overflow: hidden; /* Important for chart sizing */
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            margin-bottom: 20px;
        }
        #status {
            margin-top: 10px;
            font-size: 0.9em;
            color: #e94560;
            min-height: 20px;
            text-align: center;
        }
        #dataTable {
            width: 90%;
            max-width: 1200px;
            background-color: #2e2e4a;
            border-collapse: collapse;
            margin-top: 20px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        }
        #dataTable th, #dataTable td {
            padding: 10px 15px;
            text-align: left;
            border-bottom: 1px solid #3e3e6b;
        }
        #dataTable th {
            background-color: #0f3460;
            color: #e0e0e0;
            font-weight: bold;
        }
        #dataTable tr:hover {
            background-color: #3e3e6b;
        }
        #dataTable tbody tr:last-child td {
            border-bottom: none;
        }
        .volume-spike-row {
            background-color: #4e0000 !important; /* Highlight spike rows */
            font-weight: bold;
            color: #fdd835;
        }
    </style>
</head>
<body>
    <h1>Bybit Trend Analysis (Volume Spike Detector)</h1>

    <div class="controls">
        <div>
            <label for="symbol">Symbol:</label>
            <select id="symbol">
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="XRPUSDT">XRPUSDT</option>
                <option value="SOLUSDT">SOLUSDT</option>
                <option value="ADAUSDT">ADAUSDT</option>
            </select>
        </div>
        <div>
            <label for="interval">Interval:</label>
            <select id="interval">
                <option value="1">1m</option>
                <option value="5">5m</option>
                <option value="15">15m</option>
                <option value="30">30m</option>
                <option value="60">1h</option>
                <option value="240">4h</option>
                <option value="720">12h</option>
                <option value="D" selected>1D</option>
                <option value="W">1W</option>
            </select>
        </div>
        <div>
            <label for="limit">Limit:</label>
            <input type="number" id="limit" value="100" min="10" max="500">
        </div>
        <div>
            <label for="avgPeriod">Vol Avg Period:</label>
            <input type="number" id="avgPeriod" value="20" min="5" max="50">
        </div>
        <div>
            <label for="spikeMultiplier">Spike Multiplier:</label>
            <input type="number" id="spikeMultiplier" value="2.0" step="0.1" min="1.5" max="5.0">
        </div>
        <button id="loadData">Load Data</button>
    </div>

    <div id="status"></div>
    <div id="chart-container"></div>

    <table id="dataTable">
        <thead>
            <tr>
                <th>Time</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Close</th>
                <th>Volume</th>
                <th>Spike?</th>
            </tr>
        </thead>
        <tbody>
            <!-- Data will be inserted here -->
        </tbody>
    </table>

    <script>
        const API_BASE_URL = 'https://api.bybit.com';
        const chartContainer = document.getElementById('chart-container');
        const symbolSelect = document.getElementById('symbol');
        const intervalSelect = document.getElementById('interval');
        const limitInput = document.getElementById('limit');
        const avgPeriodInput = document.getElementById('avgPeriod');
        const spikeMultiplierInput = document.getElementById('spikeMultiplier');
        const loadDataButton = document.getElementById('loadData');
        const statusDiv = document.getElementById('status');
        const dataTableBody = document.querySelector('#dataTable tbody');

        // Initialize the chart
        const chart = LightweightCharts.createChart(chartContainer, {
            width: chartContainer.offsetWidth,
            height: chartContainer.offsetHeight,
            layout: {
                backgroundColor: '#2e2e4a',
                textColor: '#e0e0e0',
            },
            grid: {
                vertLines: { color: '#3f3f5a' },
                horzLines: { color: '#3f3f5a' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            rightPriceScale: {
                borderColor: '#4d4d73',
            },
            handleScale: {
                axisPressedMouseMove: true,
            },
            handleScroll: {
                vertTouchDrag: true,
            },
        });

        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        const volumeSeries = chart.addHistogramSeries({
            color: '#8383a5', // Default volume color
            priceFormat: { type: 'volume' },
            overlay: true,
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        // Function to calculate average volume and detect spikes
        function detectVolumeSpikes(data, avgPeriod, spikeMultiplier) {
            const volumeDataWithSpikes = [];
            const volumes = data.map(d => d.volume);

            for (let i = 0; i < data.length; i++) {
                const currentVolume = volumes[i];
                let isSpike = false;
                let color = data[i].close >= data[i].open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)'; // Green/Red based on candle

                if (i >= avgPeriod) {
                    const avgVolume = volumes.slice(i - avgPeriod, i).reduce((sum, val) => sum + val, 0) / avgPeriod;
                    if (currentVolume > avgVolume * spikeMultiplier) {
                        isSpike = true;
                        color = '#fdd835'; // Yellow for volume spike
                    }
                }
                volumeDataWithSpikes.push({
                    time: data[i].time,
                    value: currentVolume,
                    color: color,
                    isSpike: isSpike
                });
            }
            return volumeDataWithSpikes;
        }

        // Function to populate the data table
        function populateDataTable(dataWithSpikes) {
            dataTableBody.innerHTML = ''; // Clear previous data

            dataWithSpikes.slice().reverse().forEach(item => { // Show most recent first in table
                const row = dataTableBody.insertRow();
                if (item.isSpike) {
                    row.classList.add('volume-spike-row');
                }
                const date = new Date(item.time * 1000); // Convert seconds to milliseconds for Date object
                row.insertCell().textContent = date.toLocaleString();
                row.insertCell().textContent = item.open.toFixed(2);
                row.insertCell().textContent = item.high.toFixed(2);
                row.insertCell().textContent = item.low.toFixed(2);
                row.insertCell().textContent = item.close.toFixed(2);
                row.insertCell().textContent = item.value.toFixed(0);
                row.insertCell().textContent = item.isSpike ? '⚡ Yes' : 'No';
            });
        }

        // Function to fetch and display data
        async function fetchData() {
            const symbol = symbolSelect.value;
            const interval = intervalSelect.value;
            const limit = limitInput.value;
            const avgPeriod = parseInt(avgPeriodInput.value);
            const spikeMultiplier = parseFloat(spikeMultiplierInput.value);

            statusDiv.textContent = 'Loading data...';
            statusDiv.style.color = '#e0e0e0';

            try {
                const url = `${API_BASE_URL}/v5/market/kline?category=spot&symbol=${symbol}&interval=${interval}&limit=${limit}`;
                const response = await fetch(url);
                const data = await response.json();

                if (data.retCode !== 0) {
                    throw new Error(data.retMsg || 'Failed to fetch data.');
                }

                if (!data.result || !data.result.list || data.result.list.length === 0) {
                    statusDiv.textContent = 'No data available for the selected symbol/interval.';
                    statusDiv.style.color = '#e94560';
                    candlestickSeries.setData([]);
                    volumeSeries.setData([]);
                    dataTableBody.innerHTML = '';
                    return;
                }

                const klineData = data.result.list.map(item => ({
                    time: parseInt(item[0]) / 1000, // Convert ms to seconds
                    open: parseFloat(item[1]),
                    high: parseFloat(item[2]),
                    low: parseFloat(item[3]),
                    close: parseFloat(item[4]),
                    volume: parseFloat(item[5])
                })).reverse(); // Reverse to have oldest data first

                candlestickSeries.setData(klineData);

                const volumeDataWithSpikes = detectVolumeSpikes(klineData, avgPeriod, spikeMultiplier);
                volumeSeries.setData(volumeDataWithSpikes);

                populateDataTable(volumeDataWithSpikes);

                statusDiv.textContent = `Data loaded for ${symbol} (${interval})`;
                statusDiv.style.color = '#26a69a';

            } catch (error) {
                console.error("Error fetching data:", error);
                statusDiv.textContent = `Error: ${error.message}. Please check console for details.`;
                statusDiv.style.color = '#e94560';
                candlestickSeries.setData([]);
                volumeSeries.setData([]);
                dataTableBody.innerHTML = '';
            }
        }

        // Resize chart on window resize
        new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== chartContainer) {
                return;
            }
            const newRect = entries[0].contentRect;
            chart.applyOptions({ height: newRect.height, width: newRect.width });
        }).observe(chartContainer);

        // Event listeners
        loadDataButton.addEventListener('click', fetchData);
        symbolSelect.addEventListener('change', fetchData);
        intervalSelect.addEventListener('change', fetchData);
        limitInput.addEventListener('change', fetchData);
        avgPeriodInput.addEventListener('change', fetchData);
        spikeMultiplierInput.addEventListener('change', fetchData);

        // Initial data load
        fetchData();
    </script>
</body>
</html>
```

**How to use `bybit_trend_app_v2.html`:**
1.  Save the code above as `bybit_trend_app_v2.html`.
2.  Open the file in your web browser.
3.  Select symbol, interval, data limit, volume average period, and the spike multiplier (e.g., a multiplier of 2 means volume must be 2x the average).
4.  Click "Load Data" (or change an input) to update the chart and the table.
5.  Look for yellow volume bars on the chart and "⚡ Yes" in the "Spike?" column of the table, highlighted in yellow, to identify periods of significant volume.

---

### Important Considerations:

1.  **CORS (Cross-Origin Resource Sharing):** Bybit's public API generally allows CORS for read-only endpoints, so you should be able to fetch data directly from your HTML file opened locally in a browser without issues. If you were to host this on a different domain, it would still work.
2.  **API Rate Limits:** Be mindful of Bybit's API rate limits. For public endpoints like `kline`, they are usually generous, but making too many rapid requests could lead to temporary blocks. These simple apps make a request only when controls are changed or on initial load, which should be fine.
3.  **Data Freshness:** These apps fetch historical data up to the current moment. For real-time data, you'd need to implement WebSocket connections, which is a more advanced topic not covered here.
4.  **Error Handling:** Basic error handling is included, displaying messages if the API fails or returns no data.
5.  **Bybit API Documentation:** Always refer to the official Bybit API documentation for the latest endpoints, parameters, and rate limits: [https://bybit-exchange.github.io/docs/v5/market/kline](https://bybit-exchange.github.io/docs/v5/market/kline)
6.  **Lightweight-Charts Documentation:** For more customization of the charts, check out: [https://tradingview.github.io/lightweight-charts/](https://tradingview.github.io/lightweight-charts/)

These two HTML applications provide a solid foundation for Bybit trend analysis directly in your browser!
