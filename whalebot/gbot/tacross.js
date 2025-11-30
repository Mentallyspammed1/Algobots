// scalptrader-final.js — SuperTrend + Ehlers + Gemini + SMS (Termux)
require('dotenv').config();
const { GoogleGenerativeAI } = require("@google/generative-ai");
const fetch = require('node-fetch');
const { execSync } = require('child_process');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const PHONE_NUMBER = process.env.PHONE_NUMBER;
const SYMBOL = "BTCUSDT";
const TIMEFRAME = "3";

if (!GEMINI_API_KEY || !PHONE_NUMBER) {
    console.log("Set GEMINI_API_KEY and PHONE_NUMBER in .env");
    process.exit(1);
}

const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });

// === SMS ===
function sendSMS(text) {
    try {
        execSync(`termux-sms-send -n "${PHONE_NUMBER}" "${text}"`, { stdio: 'ignore' });
        console.log(`SMS Sent (${text.length} chars)`);
    } catch (e) {
        console.log("SMS failed");
    }
}

// === BYBIT DATA ===
async function getCandles() {
    const now = Math.floor(Date.now() / 1000);
    const from = now - 86400 * 14;
    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${SYMBOL}&interval=${TIMEFRAME}&start=${from * 1000}&limit=500`;
    const res = await fetch(url);
    const json = await res.json();
    if (json.retCode !== 0) throw new Error(json.retMsg);
    return json.result.list.map(c => ({
        ts: +c[0], open: +c[1], high: +c[2], low: +c[3], close: +c[4], volume: +c[5]
    })).reverse();
}

// === INDICATORS ===
const sma = (arr, len) => arr.slice(-len).reduce((a,b) => a+b, 0) / len;
const ema = (arr, len) => {
    const k = 2/(len+1);
    let val = sma(arr.slice(0,len), len);
    for (let i = len; i < arr.length; i++) val = arr[i]*k + val*(1-k);
    return val;
};
const atr = (candles, len = 10) => {
    const tr = [];
    for (let i = 1; i < candles.length; i++) {
        const h = candles[i].high, l = candles[i].low, pc = candles[i-1].close;
        tr.push(Math.max(h-l, Math.abs(h-pc), Math.abs(l-pc)));
    }
    return sma(tr.slice(-len), len);
};

// SuperTrend (accurate port)
function superTrend(candles, period = 10, mult = 3) {
    const atrVal = atr(candles, period);
    const hl2 = (candles[candles.length-1].high + candles[candles.length-1].low) / 2;
    let up = hl2 - (mult * atrVal);
    let down = hl2 + (mult * atrVal);
    const prev = candles[candles.length-2];
    const prevUp = (prev.high + prev.low)/2 - mult * atr(candles.slice(0,-1), period);
    const prevDown = (prev.high + prev.low)/2 + mult * atr(candles.slice(0,-1), period);
    up = prev.close > prevUp ? Math.max(up, prevUp) : up;
    down = prev.close < prevDown ? Math.min(down, prevDown) : down;
    const trend = candles[candles.length-1].close > up ? 1 : -1;
    return { up, down, trend };
}

// Ehlers Cyber Cycle
function ehlersCyberCycle(src) {
    const smooth = [];
    const trigger = [];
    const cycle = [];
    const alpha = 0.07;
    for (let i = 6; i < src.length; i++) {
        smooth[i] = (src[i] + 2*src[i-1] + 2*src[i-2] + src[i-3]) / 6;
        cycle[i] = (1 - alpha/2)**2 * (smooth[i] - 2*smooth[i-1] + smooth[i-2]) +
                   2*(1-alpha)* (cycle[i-1] || 0) - (1-alpha)**2 * (cycle[i-2] || 0);
        trigger[i] = cycle[i-1] || 0;
    }
    const lastCycle = cycle[cycle.length-1] || 0;
    const lastTrigger = trigger[trigger.length-1] || 0;
    return { cycle: lastCycle, trigger: lastTrigger, bullish: lastCycle > lastTrigger };
}

// === MAIN LOOP ===
(async () => {
    console.clear();
    console.log(`\n Ultimate Scalp Pro + SuperTrend + Ehlers + SMS\nWatching ${SYMBOL} ${TIMEFRAME}m...\n`);

    let lastSignalTime = 0;

    while (true) {
        try {
            const candles = await getCandles();
            const close = candles.map(c => c.close);
            const high = candles.map(c => c.high);
            const low = candles.map(c => c.low);
            const volume = candles.map(c => c.volume);
            const price = close[close.length-1].toFixed(2);
            const last = candles[candles.length-1];

            // Indicators
            const trendUp = ema(close, 40) >= ema(close, 40);
            const st = superTrend(candles, 10, 3);
            const ehlers = ehlersCyberCycle(close);
            const rsiVal = (() => {
                let up = 0, down = 0;
                for (let i = close.length - 7; i < close.length; i++) {
                    const d = close[i] - close[i-1];
                    if (d > 0) up += d; else down -= d;
                }
                return 100 - (100 / (1 + (up / (down || 1))));
            })();
            const volSpike = volume[volume.length-1] > sma(volume, 10) * 1.3;
            const range = last.high - last.low;
            const body = Math.abs(last.close - last.open);
            const avgRange = sma(high.map((h,i) => h - low[i]), 20);
            const impBull = last.close > last.open && range > avgRange * 1.5 && body/range > 0.65;
            const impBear = last.close < last.open && range > avgRange * 1.5 && body/range > 0.65;

            const confluence = [
                trendUp,
                st.trend === 1,
                ehlers.bullish,
                rsiVal > 55,
                volSpike,
                impBull
            ].filter(Boolean).length;

            const scalpBuy = confluence >= 5;
            const scalpSell = confluence <= 1 && !trendUp && rsiVal < 45 && impBear;

            if ((scalpBuy || scalpSell) && Date.now() - lastSignalTime > 5 * 60 * 1000) {
                const direction = scalpBuy ? "LONG" : "SHORT";
                const emoji = direction === "LONG" ? "LONG" : "SHORT";

                console.log(`\n ${emoji} SIGNAL @ ${price} | Conf: ${confluence}/6\n`);

                // Gemini AI
                const prompt = `Scalp ${direction} on ${SYMBOL} ${TIMEFRAME}m at ${price}. Confluence: ${confluence}/6. SuperTrend: ${st.trend===1?"Bullish":"Bearish"}. Ehlers: ${ehlers.bullish?"Bullish":"Bearish"}. Give entry, TP, SL, confidence.`;
                const result = await model.generateContent(prompt);
                const aiText = (await result.response).text();

                const entry = aiText.match(/ENTRY:\s*([\d.]+)/i)?.[1] || price;
                const tp = aiText.match(/TP:\s*([\d.]+)/i)?.[1] || (scalpBuy ? (+price*1.008).toFixed(2) : (+price*0.992).toFixed(2));
                const sl = aiText.match(/SL:\s*([\d.]+)/i)?.[1] || (scalpBuy ? (+price*0.994).toFixed(2) : (+price*1.006).toFixed(2));
                const conf = aiText.match(/CONFIDENCE:\s*(High|Medium|Low)/i)?.[1] || "Medium";
                const reason = aiText.match(/REASONING?:?\s*([^.\n]+)/i)?.[1]?.trim() || "Strong signal";

                // OPTIMIZED SMS
                const sms = `${SYMBOL.replace("USDT","")} ${TIMEFRAME}m ${emoji}\n` +
                           `Entry: ${entry}\n` +
                           `TP: ${tp} | SL: ${sl}\n` +
                           `Conf: ${conf}\n` +
                           `AI: ${reason.substring(0,50)}${reason.length>50?"...":""}`;

                sendSMS(sms);
                console.log(`SMS:\n${sms}\n`);

                lastSignalTime = Date.now();
            }

            await new Promise(r => setTimeout(r, 12000));

        } catch (err) {
            console.log("Error:", err.message);
            await new Promise(r => setTimeout(r, 30000));
        }
    }
})();
