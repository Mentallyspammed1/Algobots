const config = require('./config');
const { MultiSymbolOHLC } = require('./services/ohlc');
const bybit = require('./services/bybit');
const {
  sma, ema, superTrend, ehlersCyberCycle,
  calculateRSI, isImpulsiveCandle
} = require('./indicators');

async function displayIndicators() {
    console.log('Fetching live candle data and calculating indicators...');

    const multiOHLC = new MultiSymbolOHLC([config.SYMBOL], 100);

    let ws = null;
    const connectAndCollect = new Promise((resolve) => {
        ws = bybit.connect((msg) => {
            const klineData = msg.data[0];
            const symbol = msg.topic.split('.')[2];
            const candle = {
                timestamp: parseInt(klineData.start),
                open: parseFloat(klineData.open),
                high: parseFloat(klineData.high),
                low: parseFloat(klineData.low),
                close: parseFloat(klineData.close),
                volume: parseFloat(klineData.volume),
            };
            multiOHLC.updateCandle(symbol, candle);

            if (multiOHLC.getCandles(config.SYMBOL).length >= 50) {
                resolve();
            }
        });
    });

    await connectAndCollect;

    const candles = multiOHLC.getCandles(config.SYMBOL);
    const close = candles.map(c => c.close);
    const high = candles.map(c => c.high);
    const low = candles.map(c => c.low);
    const volume = candles.map(c => c.volume);
    const price = close[close.length - 1];
    const last = multiOHLC.getLatestCandle(config.SYMBOL);

    const emaShort = ema(close, 12);
    const emaLong = ema(close, 26);
    const trendUp = emaShort >= emaLong;

    const st = superTrend(candles);
    const ehlers = ehlersCyberCycle(close);
    const rsiVal = calculateRSI(close);
    const avgRange = sma(high.map((h, i) => h - low[i]), 20);
    const volSpike = volume[volume.length - 1] > sma(volume, 10) * 1.3;
    const { bullish: impBull, bearish: impBear } = isImpulsiveCandle(last, avgRange);

    const confluence = [
        trendUp, st.trend === 1, ehlers.bullish,
        rsiVal > 55, volSpike, impBull
    ].filter(Boolean).length;

    console.log('\n--- Current Market Snapshot ---');
    console.log(`Symbol: ${config.SYMBOL}`);
    console.log(`Current Price: ${price.toFixed(2)}`);
    console.log(`EMA (12): ${emaShort.toFixed(2)}`);
    console.log(`EMA (26): ${emaLong.toFixed(2)}`);
    console.log(`Trend Up (EMA Cross): ${trendUp}`);
    console.log(`SuperTrend (Trend): ${st.trend === 1 ? 'Bullish' : 'Bearish'}`);
    console.log(`Ehlers Cyber Cycle (Bullish): ${ehlers.bullish}`);
    console.log(`RSI: ${rsiVal.toFixed(2)}`);
    console.log(`Volume Spike: ${volSpike}`);
    console.log(`Impulsive Bullish Candle: ${impBull}`);
    console.log(`Impulsive Bearish Candle: ${impBear}`);
    console.log(`Confluence Score: ${confluence}/6`);
    console.log('-------------------------------\n');
    
    // Close the websocket connection after getting data
    if (ws) {
        ws.close();
    }
}

displayIndicators().catch(console.error);
