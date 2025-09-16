module.exports = {

"[project]/src/lib/supertrend.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "Supertrend": (()=>Supertrend),
    "SupertrendInput": (()=>SupertrendInput)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/indicator/indicator.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$directionalmovement$2f$ATR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/directionalmovement/ATR.js [app-rsc] (ecmascript)");
;
;
class SupertrendInput extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorInput"] {
    multiplier;
    period;
    high;
    low;
    close;
}
class Supertrend extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"] {
    result;
    constructor(input){
        super(input);
        const atr = new __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$directionalmovement$2f$ATR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ATR"]({
            high: input.high,
            low: input.low,
            close: input.close,
            period: input.period
        });
        const atrValues = atr.result;
        this.result = [];
        if (atrValues.length === 0) {
            return;
        }
        let direction = 1;
        let up = (input.high[0] + input.low[0]) / 2 - input.multiplier * atrValues[0];
        let down = (input.high[0] + input.low[0]) / 2 + input.multiplier * atrValues[0];
        let trend = up;
        for(let i = 1; i < input.close.length; i++){
            const currentClose = input.close[i];
            const prevClose = input.close[i - 1];
            const atrValue = atrValues[i - 1];
            if (!atrValue) continue;
            let newUp = (input.high[i] + input.low[i]) / 2 - input.multiplier * atrValue;
            let newDown = (input.high[i] + input.low[i]) / 2 + input.multiplier * atrValue;
            if (direction === 1 && currentClose < trend) {
                direction = -1;
                trend = newDown;
            } else if (direction === -1 && currentClose > trend) {
                direction = 1;
                trend = newUp;
            } else {
                if (direction === 1) {
                    trend = Math.max(trend, newUp);
                } else {
                    trend = Math.min(trend, newDown);
                }
            }
            this.result.push({
                value: trend,
                direction: direction,
                up: direction === 1 ? trend : newDown,
                down: direction === -1 ? trend : newUp
            });
        }
    }
    static calculate(input) {
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        const result = new Supertrend(input).result;
        if (input.reversedInput) {
            result.reverse();
        }
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        return result;
    }
}
}}),
"[project]/src/lib/fisher.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "FisherTransform": (()=>FisherTransform),
    "FisherTransformInput": (()=>FisherTransformInput),
    "FisherTransformOutput": (()=>FisherTransformOutput)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/indicator/indicator.js [app-rsc] (ecmascript)");
;
class FisherTransformInput extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorInput"] {
    period;
    high;
    low;
}
class FisherTransformOutput {
    fisher;
    trigger;
}
class FisherTransform extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"] {
    // Note: The implementation is a refactored version of the original generator-based code.
    // The non-standard smoothing logic has been preserved for consistency.
    static calculate(input) {
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        const { high, low, period } = input;
        const results = [];
        // Previous state values needed for the loop
        let prevValue = 0;
        let prevFisher = 0;
        for(let i = 0; i < high.length; i++){
            // Determine the min/max over the lookback period
            const start = Math.max(0, i - period + 1);
            const periodHighs = high.slice(start, i + 1);
            const periodLows = low.slice(start, i + 1);
            const maxHigh = Math.max(...periodHighs);
            const minLow = Math.min(...periodLows);
            const price = (high[i] + low[i]) / 2;
            // Calculate normalized price term. This normalizes the price to a range of -0.5 to 0.5.
            let normPrice = 0;
            if (maxHigh - minLow !== 0) {
                normPrice = (price - minLow) / (maxHigh - minLow) - 0.5;
            }
            // Apply the non-standard smoothing from the original implementation
            let value = 0.33 * 2 * normPrice + 0.67 * prevValue;
            // Clamp the value to avoid undefined results from Math.log
            value = Math.max(-0.999, Math.min(0.999, value));
            // Calculate the Fisher Transform value and apply another non-standard smoothing
            const fisherRaw = 0.5 * Math.log((1 + value) / (1 - value));
            const fisher = fisherRaw + 0.5 * prevFisher;
            // The trigger is the fisher value from the previous period
            const trigger = prevFisher;
            results.push({
                fisher,
                trigger
            });
            // Update state for the next iteration
            prevValue = value;
            prevFisher = fisher;
        }
        if (input.reversedInput) {
            results.reverse();
        }
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        return results;
    }
}
}}),
"[project]/src/lib/ehlers.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "EhlersInstantaneousTrendline": (()=>EhlersInstantaneousTrendline),
    "EhlersInstantaneousTrendlineInput": (()=>EhlersInstantaneousTrendlineInput)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/indicator/indicator.js [app-rsc] (ecmascript)");
;
class EhlersInstantaneousTrendlineInput extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorInput"] {
    values;
    period;
}
class EhlersInstantaneousTrendline extends __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"] {
    result;
    constructor(input){
        super(input);
        const prices = input.values;
        const alpha = 2 / (input.period + 1);
        this.result = [];
        let trend = [];
        let iTrend = [];
        for(let i = 0; i < prices.length; i++){
            if (i < 2) {
                trend.push(0);
                iTrend.push(0);
                this.result.push(0);
                continue;
            }
            if (i === 2) {
                trend.push((prices[i] + 2 * prices[i - 1] + prices[i - 2]) / 4);
            } else {
                trend.push((alpha - alpha * alpha / 4) * prices[i] + 0.5 * alpha * alpha * prices[i - 1] - (alpha - 0.75 * alpha * alpha) * prices[i - 2] + 2 * (1 - alpha) * trend[i - 1] - (1 - alpha) * (1 - alpha) * trend[i - 2]);
            }
            if (i < 6) {
                iTrend.push(0);
                this.result.push(0);
                continue;
            }
            if (i === 6) {
                iTrend.push((trend[i] + 2 * trend[i - 1] + 3 * trend[i - 2] + 3 * trend[i - 3] + 2 * trend[i - 4] + trend[i - 5]) / 12);
            } else {
                iTrend.push(alpha / 2 * trend[i] + (1 - alpha / 2) * iTrend[i - 1]);
            }
            this.result.push(iTrend[i]);
        }
    }
    static calculate = (input)=>{
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        const result = new EhlersInstantaneousTrendline(input).result;
        if (input.reversedInput) {
            result.reverse();
        }
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$indicator$2f$indicator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Indicator"].reverseInputs(input);
        return result;
    };
}
}}),
"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
/* __next_internal_action_entry_do_not_use__ [{"7c3de3629a44afc87f3082340ba2b84ba185ec957f":"calculateIndicators","7f2e70fe065ef52da281045a61720821ecf0d71418":"defaultIndicatorSettings","7f6bdcfaab54ceca1993e9b1f5ad75ae8ef8b01100":"IndicatorSettings","7fe133d97d20940a7d947e33f739fe010229b10fc7":"IndicatorDataSchema"},"",""] */ __turbopack_context__.s({
    "IndicatorDataSchema": (()=>IndicatorDataSchema),
    "IndicatorSettings": (()=>IndicatorSettings),
    "calculateIndicators": (()=>calculateIndicators),
    "defaultIndicatorSettings": (()=>defaultIndicatorSettings)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/server-reference.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$app$2d$render$2f$encryption$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/app-render/encryption.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/zod/lib/index.mjs [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$RSI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/oscillators/RSI.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$moving_averages$2f$MACD$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/moving_averages/MACD.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volatility$2f$BollingerBands$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/volatility/BollingerBands.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$Stochastic$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/momentum/Stochastic.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$directionalmovement$2f$ATR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/directionalmovement/ATR.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volume$2f$OBV$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/volume/OBV.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$WilliamsR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/momentum/WilliamsR.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$CCI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/oscillators/CCI.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$ROC$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/momentum/ROC.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volume$2f$MFI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/volume/MFI.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$AwesomeOscillator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/oscillators/AwesomeOscillator.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$ichimoku$2f$IchimokuCloud$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/ichimoku/IchimokuCloud.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$moving_averages$2f$SMA$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/technicalindicators/lib/moving_averages/SMA.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$supertrend$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/supertrend.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$fisher$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/fisher.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$ehlers$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/ehlers.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/action-validate.js [app-rsc] (ecmascript)");
;
;
;
;
;
;
;
const IndicatorSettings = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    rsi: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(14),
        overbought: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(70),
        oversold: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(30)
    }),
    macd: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        fast: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(12),
        slow: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(26),
        signal: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(9)
    }),
    bollingerBands: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(20),
        stdDev: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().positive().default(2)
    }),
    stochastic: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(14),
        slowing: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(3),
        overbought: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(80),
        oversold: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(20)
    }),
    atr: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(14)
    }),
    williamsR: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(14),
        overbought: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(-20),
        oversold: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(-80)
    }),
    cci: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(20),
        overbought: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(100),
        oversold: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(-100)
    }),
    roc: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(12)
    }),
    mfi: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(14),
        overbought: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(80),
        oversold: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().default(20)
    }),
    awesomeOscillator: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        fast: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(5),
        slow: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(34)
    }),
    ichimokuCloud: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        tenkan: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(9),
        kijun: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(26),
        senkou: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(52),
        displacement: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(26)
    }),
    sma: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(20)
    }),
    supertrendFast: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        atrPeriod: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(10),
        multiplier: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().positive().default(2)
    }),
    supertrendSlow: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        atrPeriod: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(20),
        multiplier: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().positive().default(4)
    }),
    fisher: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(9)
    }),
    ehlers: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        period: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().int().positive().default(10)
    })
});
const defaultIndicatorSettings = IndicatorSettings.parse({});
// #endregion
// #region Result Schemas
const RsiResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    rsi: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const MacdResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    macd: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable(),
    signal: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable(),
    histogram: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const BollingerBandsResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    upper: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number(),
    middle: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number(),
    lower: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number()
}).nullable();
const StochasticResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    k: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable(),
    d: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const AtrResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    atr: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const ObvResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    obv: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const WilliamsRResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    williamsR: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const CciResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    cci: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const RocResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    roc: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const MfiResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    mfi: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const AwesomeOscillatorResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    ao: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const IchimokuCloudResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    tenkanSen: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number(),
    kijunSen: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number(),
    senkouSpanA: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number(),
    senkouSpanB: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number()
}).nullable();
const SmaResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    sma: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const SupertrendResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    direction: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].enum([
        'buy',
        'sell'
    ]),
    supertrend: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number()
}).nullable();
const FisherTransformResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    fisher: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable(),
    trigger: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const EhlersTrendlineResultSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    trendline: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().nullable()
}).nullable();
const IndicatorDataSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    rsi: RsiResultSchema,
    macd: MacdResultSchema,
    bollingerBands: BollingerBandsResultSchema,
    stochastic: StochasticResultSchema,
    atr: AtrResultSchema,
    obv: ObvResultSchema,
    williamsR: WilliamsRResultSchema,
    cci: CciResultSchema,
    roc: RocResultSchema,
    mfi: MfiResultSchema,
    awesomeOscillator: AwesomeOscillatorResultSchema,
    ichimokuCloud: IchimokuCloudResultSchema,
    sma: SmaResultSchema,
    supertrendFast: SupertrendResultSchema,
    supertrendSlow: SupertrendResultSchema,
    fisher: FisherTransformResultSchema,
    ehlers: EhlersTrendlineResultSchema
});
const createIndicatorResult = (result, mapping)=>{
    if (result === null || result === undefined || typeof result === 'number' && isNaN(result)) {
        return null;
    }
    return mapping(result);
};
function calculateIndicators(closePrices, highPrices, lowPrices, volumes, settings = defaultIndicatorSettings) {
    if (closePrices.length === 0) {
        return null;
    }
    const input = {
        high: highPrices,
        low: lowPrices,
        close: closePrices,
        volume: volumes,
        period: 0
    };
    const safeLast = (arr)=>arr && arr.length > 0 ? arr[arr.length - 1] : null;
    // RSI
    const rsi = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$RSI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["RSI"].calculate({
        values: closePrices,
        period: settings.rsi.period
    })), (res)=>({
            rsi: res
        }));
    // MACD
    const macd = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$moving_averages$2f$MACD$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["MACD"].calculate({
        values: closePrices,
        fastPeriod: settings.macd.fast,
        slowPeriod: settings.macd.slow,
        signalPeriod: settings.macd.signal,
        SimpleMAOscillator: false,
        SimpleMASignal: false
    })), (res)=>({
            macd: res.MACD,
            signal: res.signal,
            histogram: res.histogram
        }));
    // Bollinger Bands
    const bollingerBands = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volatility$2f$BollingerBands$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["BollingerBands"].calculate({
        values: closePrices,
        period: settings.bollingerBands.period,
        stdDev: settings.bollingerBands.stdDev
    })), (res)=>res);
    // Stochastic
    const stochastic = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$Stochastic$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Stochastic"].calculate({
        ...input,
        period: settings.stochastic.period,
        signalPeriod: settings.stochastic.slowing
    })), (res)=>res);
    // ATR
    const atr = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$directionalmovement$2f$ATR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ATR"].calculate({
        ...input,
        period: settings.atr.period
    })), (res)=>({
            atr: res
        }));
    // OBV (On-Balance Volume)
    const obv = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volume$2f$OBV$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["OBV"].calculate(input)), (res)=>({
            obv: res
        }));
    // Williams %R
    const williamsR = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$WilliamsR$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["WilliamsR"].calculate({
        ...input,
        period: settings.williamsR.period
    })), (res)=>({
            williamsR: res
        }));
    // CCI
    const cci = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$CCI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["CCI"].calculate({
        ...input,
        period: settings.cci.period
    })), (res)=>({
            cci: res
        }));
    // ROC
    const roc = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$momentum$2f$ROC$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ROC"].calculate({
        values: closePrices,
        period: settings.roc.period
    })), (res)=>({
            roc: res
        }));
    // MFI
    const mfi = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$volume$2f$MFI$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["MFI"].calculate({
        ...input,
        period: settings.mfi.period
    })), (res)=>({
            mfi: res
        }));
    // Awesome Oscillator
    const awesomeOscillator = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$oscillators$2f$AwesomeOscillator$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["AwesomeOscillator"].calculate({
        ...input,
        fastPeriod: settings.awesomeOscillator.fast,
        slowPeriod: settings.awesomeOscillator.slow,
        format: (a)=>a
    })), (res)=>({
            ao: res
        }));
    // Ichimoku Cloud
    const ichimokuCloud = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$ichimoku$2f$IchimokuCloud$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IchimokuCloud"].calculate({
        high: highPrices,
        low: lowPrices,
        conversionPeriod: settings.ichimokuCloud.tenkan,
        basePeriod: settings.ichimokuCloud.kijun,
        spanPeriod: settings.ichimokuCloud.senkou,
        displacement: settings.ichimokuCloud.displacement
    })), (res)=>({
            tenkanSen: res.conversion,
            kijunSen: res.base,
            senkouSpanA: res.spanA,
            senkouSpanB: res.spanB
        }));
    // SMA
    const sma = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$technicalindicators$2f$lib$2f$moving_averages$2f$SMA$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["SMA"].calculate({
        values: closePrices,
        period: settings.sma.period
    })), (res)=>({
            sma: res
        }));
    // Supertrend
    const supertrendFast = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$supertrend$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Supertrend"].calculate({
        ...input,
        period: settings.supertrendFast.atrPeriod,
        multiplier: settings.supertrendFast.multiplier
    })), (res)=>({
            direction: res.direction > 0 ? 'buy' : 'sell',
            supertrend: res.value
        }));
    const supertrendSlow = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$supertrend$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["Supertrend"].calculate({
        ...input,
        period: settings.supertrendSlow.atrPeriod,
        multiplier: settings.supertrendSlow.multiplier
    })), (res)=>({
            direction: res.direction > 0 ? 'buy' : 'sell',
            supertrend: res.value
        }));
    // Fisher Transform
    const fisher = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$fisher$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["FisherTransform"].calculate({
        ...input,
        period: settings.fisher.period
    })), (res)=>res);
    // Ehlers Instantaneous Trendline
    const ehlers = createIndicatorResult(safeLast(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$ehlers$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["EhlersInstantaneousTrendline"].calculate({
        values: closePrices,
        period: settings.ehlers.period
    })), (res)=>({
            trendline: res
        }));
    return {
        rsi,
        macd,
        bollingerBands,
        stochastic,
        atr,
        obv,
        williamsR,
        cci,
        roc,
        mfi,
        awesomeOscillator,
        ichimokuCloud,
        sma,
        supertrendFast,
        supertrendSlow,
        fisher,
        ehlers
    };
}
;
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ensureServerEntryExports"])([
    IndicatorSettings,
    defaultIndicatorSettings,
    IndicatorDataSchema,
    calculateIndicators
]);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(IndicatorSettings, "7f6bdcfaab54ceca1993e9b1f5ad75ae8ef8b01100", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(defaultIndicatorSettings, "7f2e70fe065ef52da281045a61720821ecf0d71418", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(IndicatorDataSchema, "7fe133d97d20940a7d947e33f739fe010229b10fc7", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(calculateIndicators, "7c3de3629a44afc87f3082340ba2b84ba185ec957f", null);
}}),
"[externals]/perf_hooks [external] (perf_hooks, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("perf_hooks", () => require("perf_hooks"));

module.exports = mod;
}}),
"[externals]/node:perf_hooks [external] (node:perf_hooks, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("node:perf_hooks", () => require("node:perf_hooks"));

module.exports = mod;
}}),
"[externals]/express [external] (express, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("express", () => require("express"));

module.exports = mod;
}}),
"[externals]/fs/promises [external] (fs/promises, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("fs/promises", () => require("fs/promises"));

module.exports = mod;
}}),
"[externals]/net [external] (net, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("net", () => require("net"));

module.exports = mod;
}}),
"[externals]/crypto [external] (crypto, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("crypto", () => require("crypto"));

module.exports = mod;
}}),
"[externals]/fs [external] (fs, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("fs", () => require("fs"));

module.exports = mod;
}}),
"[externals]/process [external] (process, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("process", () => require("process"));

module.exports = mod;
}}),
"[externals]/buffer [external] (buffer, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("buffer", () => require("buffer"));

module.exports = mod;
}}),
"[externals]/node:crypto [external] (node:crypto, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("node:crypto", () => require("node:crypto"));

module.exports = mod;
}}),
"[externals]/node:async_hooks [external] (node:async_hooks, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("node:async_hooks", () => require("node:async_hooks"));

module.exports = mod;
}}),
"[externals]/async_hooks [external] (async_hooks, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("async_hooks", () => require("async_hooks"));

module.exports = mod;
}}),
"[externals]/events [external] (events, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("events", () => require("events"));

module.exports = mod;
}}),
"[externals]/os [external] (os, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("os", () => require("os"));

module.exports = mod;
}}),
"[externals]/child_process [external] (child_process, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("child_process", () => require("child_process"));

module.exports = mod;
}}),
"[externals]/util [external] (util, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("util", () => require("util"));

module.exports = mod;
}}),
"[externals]/require-in-the-middle [external] (require-in-the-middle, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("require-in-the-middle", () => require("require-in-the-middle"));

module.exports = mod;
}}),
"[externals]/import-in-the-middle [external] (import-in-the-middle, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("import-in-the-middle", () => require("import-in-the-middle"));

module.exports = mod;
}}),
"[externals]/http [external] (http, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("http", () => require("http"));

module.exports = mod;
}}),
"[externals]/https [external] (https, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("https", () => require("https"));

module.exports = mod;
}}),
"[externals]/zlib [external] (zlib, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("zlib", () => require("zlib"));

module.exports = mod;
}}),
"[externals]/stream [external] (stream, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("stream", () => require("stream"));

module.exports = mod;
}}),
"[externals]/tls [external] (tls, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("tls", () => require("tls"));

module.exports = mod;
}}),
"[externals]/http2 [external] (http2, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("http2", () => require("http2"));

module.exports = mod;
}}),
"[externals]/dns [external] (dns, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("dns", () => require("dns"));

module.exports = mod;
}}),
"[externals]/dgram [external] (dgram, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("dgram", () => require("dgram"));

module.exports = mod;
}}),
"[externals]/assert [external] (assert, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("assert", () => require("assert"));

module.exports = mod;
}}),
"[project]/src/ai/genkit.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "ai": (()=>ai)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i("[project]/node_modules/genkit/lib/index.mjs [app-rsc] (ecmascript) <module evaluation>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$genkit$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/genkit/lib/genkit.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$genkit$2d$ai$2f$googleai$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i("[project]/node_modules/@genkit-ai/googleai/lib/index.mjs [app-rsc] (ecmascript) <module evaluation>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$genkit$2d$ai$2f$googleai$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/@genkit-ai/googleai/lib/index.mjs [app-rsc] (ecmascript) <locals>");
;
;
const ai = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$genkit$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["genkit"])({
    plugins: [
        (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$genkit$2d$ai$2f$googleai$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$locals$3e$__["googleAI"])()
    ],
    model: 'googleai/gemini-2.5-flash',
    enableDevUI: true
});
}}),
"[project]/src/lib/cache.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "withCache": (()=>withCache)
});
const cache = new Map();
function withCache(fn, options = {
    ttl: 60 * 1000
}) {
    return async function(...args) {
        const key = options.getKey ? options.getKey(...args) : JSON.stringify({
            name: fn.name,
            args
        });
        const now = Date.now();
        const cached = cache.get(key);
        if (cached && now < cached.expiry) {
            return cached.value;
        }
        const result = await fn(...args);
        cache.set(key, {
            value: result,
            expiry: now + options.ttl
        });
        return result;
    };
}
}}),
"[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "BYBIT_WEBSOCKET_URL": (()=>BYBIT_WEBSOCKET_URL),
    "DEFAULT_REQUEST_TIMEOUT": (()=>DEFAULT_REQUEST_TIMEOUT),
    "KlineEntrySchema": (()=>KlineEntrySchema),
    "OrderBookEntrySchema": (()=>OrderBookEntrySchema),
    "OrderBookSchema": (()=>OrderBookSchema),
    "RecentTradeSchema": (()=>RecentTradeSchema),
    "TickerInfoSchema": (()=>TickerInfoSchema),
    "getKline": (()=>getKline),
    "getOrderBook": (()=>getOrderBook),
    "getRecentTrades": (()=>getRecentTrades),
    "getTicker": (()=>getTicker),
    "getTickers": (()=>getTickers)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/zod/lib/index.mjs [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/cache.ts [app-rsc] (ecmascript)");
;
;
const TickerInfoSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    lastPrice: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    highPrice24h: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    lowPrice24h: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    turnover24h: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    volume24h: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    price24hPcnt: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
});
const OrderBookEntrySchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].tuple([
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
]); // [price, size]
const OrderBookSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    bids: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(OrderBookEntrySchema),
    asks: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(OrderBookEntrySchema),
    ts: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
});
const RecentTradeSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    execId: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    execTime: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].union([
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
        __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number()
    ]),
    price: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    qty: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    side: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].enum([
        'Buy',
        'Sell'
    ]),
    isBlockTrade: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].boolean().optional()
});
const KlineEntrySchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].tuple([
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
    __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string().optional() // Optional: Confirm flag (1 if the kline is closed)
]);
// #endregion
// #region Constants
const BYBIT_API_URL = 'https://api.bybit.com';
const BYBIT_WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/spot';
const DEFAULT_REQUEST_TIMEOUT = 10000; // 10 seconds
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
/**
 * An enhanced fetch function for interacting with the Bybit API.
 * Includes retry logic, request timeout, and standardized error handling.
 *
 * @param endpoint - The API endpoint path (e.g., '/v5/market/tickers').
 * @param params - A record of query parameters to include in the request.
 * @param options - Standard RequestInit options to pass to fetch.
 * @returns A promise that resolves to the 'result' field of the API response, or null if an error occurs.
 */ async function fetchFromBybit(endpoint, params = {}, options = {}) {
    const url = new URL(endpoint, BYBIT_API_URL);
    url.search = new URLSearchParams(params).toString();
    const controller = new AbortController();
    const timeoutId = setTimeout(()=>controller.abort(), DEFAULT_REQUEST_TIMEOUT);
    const fetchOptions = {
        cache: 'no-store',
        signal: options.signal || controller.signal,
        headers: {
            'Content-Type': 'application/json'
        },
        ...options
    };
    let retryCount = 0;
    while(retryCount <= MAX_RETRIES){
        try {
            const response = await fetch(url.toString(), fetchOptions);
            clearTimeout(timeoutId); // Clear timeout once response is received
            if (!response.ok) {
                throw new Error(`Bybit API error: ${response.status} ${response.statusText}`);
            }
            const data = await response.json();
            if (data.retCode !== 0) {
                throw new Error(`Bybit API error: ${data.retMsg} (Code: ${data.retCode})`);
            }
            return data.result;
        } catch (error) {
            clearTimeout(timeoutId);
            // Don't retry on abort errors or if we've reached max retries
            if (error instanceof Error && error.name === 'AbortError') {
                console.error(`Request to ${endpoint} timed out or was aborted`);
                return null;
            }
            if (retryCount === MAX_RETRIES) {
                console.error(`Failed to fetch from Bybit endpoint ${endpoint} after ${MAX_RETRIES} retries:`, error);
                return null;
            }
            // Exponential backoff
            const delay = RETRY_DELAY_MS * Math.pow(2, retryCount);
            console.warn(`Retry ${retryCount + 1}/${MAX_RETRIES} for ${endpoint} in ${delay}ms`);
            await new Promise((resolve)=>setTimeout(resolve, delay));
            retryCount++;
        }
    }
    return null;
}
/**
 * Fetches ticker information for a specific symbol.
 *
 * @param symbol - The trading symbol (e.g., 'BTCUSDT').
 * @returns A promise resolving to a validated TickerInfo object or null.
 */ async function getTickerFn(symbol) {
    try {
        const result = await fetchFromBybit('/v5/market/tickers', {
            category: 'spot',
            symbol
        });
        if (!result || !result.list || result.list.length === 0) {
            console.warn(`No ticker data found for symbol: ${symbol}`);
            return null;
        }
        // Extract and validate the ticker data
        const ticker = result.list[0];
        const validation = TickerInfoSchema.safeParse(ticker);
        if (!validation.success) {
            console.warn(`Invalid ticker data received for ${symbol}:`, validation.error);
            return null;
        }
        return validation.data;
    } catch (error) {
        console.error(`Error fetching ticker for ${symbol}:`, error);
        return null;
    }
}
/**
 * Fetches the order book for a specific symbol.
 *
 * @param symbol - The trading symbol.
 * @param limit - The number of price levels to fetch (depth).
 * @returns A promise resolving to a validated OrderBook object or null.
 */ async function getOrderBookFn(symbol, limit = 20) {
    try {
        const result = await fetchFromBybit('/v5/market/orderbook', {
            category: 'spot',
            symbol,
            limit: limit.toString()
        });
        if (!result) {
            console.warn(`No orderbook data found for symbol: ${symbol}`);
            return null;
        }
        const validation = OrderBookSchema.safeParse({
            bids: result.b,
            asks: result.a,
            ts: result.ts?.toString() || Date.now().toString()
        });
        if (!validation.success) {
            console.warn(`Invalid orderbook data for ${symbol}:`, validation.error);
            return null;
        }
        return validation.data;
    } catch (error) {
        console.error(`Error fetching orderbook for ${symbol}:`, error);
        return null;
    }
}
/**
 * Fetches the most recent public trades for a symbol.
 *
 * @param symbol - The trading symbol.
 * @param limit - The maximum number of trades to fetch.
 * @param options - Standard RequestInit options to pass to fetch.
 * @returns A promise resolving to an array of validated RecentTrade objects.
 */ async function getRecentTradesFn(symbol, limit = 30, options = {}) {
    try {
        const result = await fetchFromBybit('/v5/market/recent-trade', {
            category: 'spot',
            symbol,
            limit: limit.toString()
        }, options);
        if (!result || !result.list || !Array.isArray(result.list)) {
            return [];
        }
        // Filter and validate trade data
        const validatedTrades = [];
        for (const trade of result.list){
            const mappedTrade = {
                execId: trade.i,
                execTime: trade.T,
                price: trade.p,
                qty: trade.v,
                side: trade.S,
                isBlockTrade: trade.m
            };
            const validation = RecentTradeSchema.safeParse(mappedTrade);
            if (validation.success) {
                validatedTrades.push(validation.data);
            }
        }
        return validatedTrades;
    } catch (error) {
        if (!(error instanceof Error && error.name === 'AbortError')) {
            console.error(`Error fetching recent trades for ${symbol}:`, error);
        }
        return [];
    }
}
/**
 * Fetches Kline (candlestick) data for a symbol and interval.
 *
 * @param symbol - The trading symbol.
 * @param interval - The user-friendly interval string (e.g., '1h', '1d').
 * @param limit - The number of candlesticks to fetch.
 * @returns A promise resolving to an array of validated KlineEntry tuples or null.
 */ async function getKlineFn(symbol, interval, limit = 100) {
    try {
        // Map user-friendly intervals to Bybit's required format
        const intervalMap = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '2h': '120',
            '4h': '240',
            '6h': '360',
            '12h': '720',
            '1d': 'D',
            '1w': 'W',
            '1M': 'M'
        };
        const bybitInterval = intervalMap[interval] || interval;
        const result = await fetchFromBybit('/v5/market/kline', {
            category: 'spot',
            symbol,
            interval: bybitInterval,
            limit: limit.toString()
        });
        if (!result || !result.list || !Array.isArray(result.list)) {
            console.warn(`No kline data found for symbol: ${symbol} with interval: ${interval}`);
            return null;
        }
        const validation = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$zod$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(KlineEntrySchema).safeParse(result.list);
        if (!validation.success) {
            console.warn(`Invalid kline data for ${symbol} with interval ${interval}:`, validation.error);
            return null;
        }
        return validation.data;
    } catch (error) {
        console.error(`Error fetching kline data for ${symbol} with interval ${interval}:`, error);
        return null;
    }
}
/**
 * Fetches ticker information for multiple symbols concurrently.
 *
 * @param symbols - An array of trading symbols.
 * @returns A promise resolving to a record mapping each symbol to its TickerInfo.
 */ async function getTickersFn(symbols) {
    const results = {};
    // Use Promise.allSettled to handle partial failures gracefully
    const promises = symbols.map(async (symbol)=>{
        const ticker = await getTicker(symbol);
        return {
            symbol,
            ticker
        };
    });
    const settledResults = await Promise.allSettled(promises);
    settledResults.forEach((result)=>{
        if (result.status === 'fulfilled' && result.value.ticker) {
            const { symbol, ticker } = result.value;
            results[symbol] = ticker;
        }
    });
    return results;
}
const getTicker = (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["withCache"])(getTickerFn, {
    ttl: 1000 * 10
}); // 10 seconds
const getOrderBook = (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["withCache"])(getOrderBookFn, {
    ttl: 1000 * 10
}); // 10 seconds
const getRecentTrades = (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["withCache"])(getRecentTradesFn, {
    ttl: 1000 * 10
}); // 10 seconds
const getKline = (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["withCache"])(getKlineFn, {
    ttl: 1000 * 60
}); // 1 minute
const getTickers = (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$cache$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["withCache"])(getTickersFn, {
    ttl: 1000 * 10
}); // 10 seconds
 // #endregion
}}),
"[project]/src/ai/flows/generate-trading-signal.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
/* __next_internal_action_entry_do_not_use__ [{"40fe1dd1a8fa94dbff281c3d6bbbf304f3e4c539f8":"generateTradingSignal"},"",""] */ __turbopack_context__.s({
    "generateTradingSignal": (()=>generateTradingSignal)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/server-reference.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$app$2d$render$2f$encryption$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/app-render/encryption.js [app-rsc] (ecmascript)");
/**
 * @fileOverview An AI agent that generates trading signals and market analysis.
 *
 * - generateTradingSignal - A function that generates trading signals and market analysis.
 * - GenerateTradingSignalInput - The input type for the generateTradingSignal function.
 * - GenerateTradingSignalOutput - The return type for the generateTradingSignal function.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/ai/genkit.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$index$2e$mjs__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i("[project]/node_modules/genkit/lib/index.mjs [app-rsc] (ecmascript) <module evaluation>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/genkit/lib/common.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/action-validate.js [app-rsc] (ecmascript)");
;
;
;
;
;
;
;
const GenerateTradingSignalInputSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string().describe('The trading symbol (e.g., BTCUSDT).'),
    timeframe: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string().describe('The timeframe for the chart and data (e.g., 1m, 5m, 1h, 1d).'),
    indicatorSettings: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorSettings"].optional().describe('The settings for the technical indicators.')
});
const GenerateTradingSignalOutputSchema = __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
    currentPrice: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().describe('The current price of the asset.'),
    entryPrice: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().describe('The recommended entry price for the trade.'),
    takeProfit: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().describe('The recommended take-profit price level.'),
    stopLoss: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number().describe('The recommended stop-loss price level.'),
    signal: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].enum([
        'Buy',
        'Sell',
        'Hold'
    ]).describe('The trading signal: Buy, Sell, or Hold.'),
    reasoning: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string().describe('Detailed reasoning for the generated signal, based on market analysis.'),
    confidenceLevel: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].enum([
        'High',
        'Medium',
        'Low'
    ]).describe('The confidence level of the signal.')
});
// Tool Definitions
const getKlineData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getKlineData',
    description: 'Get candlestick (Kline) data.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
        timeframe: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["KlineEntrySchema"]).nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKlineData"]);
const getOrderBookData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getOrderBookData',
    description: 'Get order book data.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["OrderBookSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getOrderBookData"]);
const getRecentTradesData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getRecentTradesData',
    description: 'Get recent public trades.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["RecentTradeSchema"])
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getRecentTrades"]);
const getIndicatorData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getIndicatorData',
    description: 'Get technical indicator data.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
        timeframe: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string(),
        settings: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorSettings"].optional()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorDataSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getIndicatorData"]);
const getMarketData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getMarketData',
    description: 'Get the latest market ticker data.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        symbol: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["TickerInfoSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getMarketData"]);
const analyzeOrderBook = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'analyzeOrderBook',
    description: 'Analyze order book to find support/resistance.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["OrderBookSchema"],
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].object({
        support: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number()),
        resistance: __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].array(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$genkit$2f$lib$2f$common$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["z"].number())
    })
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["analyzeOrderBook"]);
async function generateTradingSignal(input) {
    return generateTradingSignalFlow(input);
}
const tradingSignalPrompt = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].definePrompt({
    name: 'tradingSignalPrompt',
    output: {
        format: 'json',
        schema: GenerateTradingSignalOutputSchema
    },
    tools: [
        getKlineData,
        getOrderBookData,
        getRecentTradesData,
        getIndicatorData,
        getMarketData,
        analyzeOrderBook
    ],
    system: `You are an expert financial analyst AI. Your goal is to generate a trading signal based on a comprehensive analysis of market data.

  **Process:**
  1.  **Get Current Price:** Start by calling \`getMarketData\` to get the current price. This is essential. If it fails, you cannot proceed.
  2.  **Gather Data:** Call all other available data tools (\`getKlineData\`, \`getOrderBookData\`, \`getRecentTradesData\`, \`getIndicatorData\`) to build a complete picture of the market.
  3.  **Analyze Order Book:** If \`getOrderBookData\` was successful, immediately pass its output to \`analyzeOrderBook\` to identify key support and resistance levels.
  4.  **Synthesize Findings:** Review all the data you have gathered. Look for confirmations or divergences between different data sources (e.g., does the RSI confirm the price action? Does the order book support a potential breakout?).
  5.  **Formulate Reasoning:** Construct a detailed, step-by-step \`reasoning\` for your final decision. Reference specific data points (e.g., "RSI is 78, indicating overbought conditions," "Strong resistance identified at $52,000 by order book analysis"). If a tool failed, you MUST mention it in your reasoning (e.g., "Could not retrieve indicator data, so confidence is lowered.").
  6.  **Generate Signal:** Based on your reasoning, determine the \`signal\` (Buy, Sell, or Hold), \`entryPrice\`, \`takeProfit\`, and \`stopLoss\`.
  7.  **Set Confidence:** Determine the \`confidenceLevel\` based on how much data you could retrieve and how strongly it points to a particular outcome.

  Your final output must be a valid JSON object matching the provided schema.`
});
const generateTradingSignalFlow = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineFlow({
    name: 'generateTradingSignalFlow',
    inputSchema: GenerateTradingSignalInputSchema,
    outputSchema: GenerateTradingSignalOutputSchema
}, async (input)=>{
    const response = await tradingSignalPrompt({
        prompt: `Generate a trading signal for ${input.symbol} on the ${input.timeframe} timeframe. Indicator settings: ${JSON.stringify(input.indicatorSettings || {})}`
    });
    if (!response.output) {
        throw new Error("AI failed to produce a valid response.");
    }
    const output = response.output;
    // Final validation
    if (output.currentPrice === null || isNaN(output.currentPrice) || output.currentPrice <= 0) {
        throw new Error("AI failed to generate a valid signal with a positive current price.");
    }
    const requiredNumericFields = [
        'entryPrice',
        'takeProfit',
        'stopLoss'
    ];
    for (const field of requiredNumericFields){
        if (output[field] === null || isNaN(output[field]) || output[field] <= 0) {
            throw new Error(`AI generated an invalid or non-positive value for '${field}'.`);
        }
    }
    return output;
});
;
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ensureServerEntryExports"])([
    generateTradingSignal
]);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(generateTradingSignal, "40fe1dd1a8fa94dbff281c3d6bbbf304f3e4c539f8", null);
}}),
"[project]/src/lib/actions.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
/* __next_internal_action_entry_do_not_use__ [{"404bceabf4524442855236b92fdc7049a3e2aa0d9e":"getOrderBookData","40ecf96ec3829da1facb2822b20b7b6fb2faedc074":"getMarketData","40ed26910e6df74305f6af4c2aa1e4f10fbe170c0d":"analyzeOrderBook","6075278ac703872d2e66765d6f6dbe7646dd10bb25":"getKlineData","70901addb4aa828fa13a5df1151b80af96986e9baf":"getIndicatorData","70c6125dbbad3595350503c517b30b35b439281e36":"getAiTradingSignal"},"",""] */ __turbopack_context__.s({
    "analyzeOrderBook": (()=>analyzeOrderBook),
    "getAiTradingSignal": (()=>getAiTradingSignal),
    "getIndicatorData": (()=>getIndicatorData),
    "getKlineData": (()=>getKlineData),
    "getMarketData": (()=>getMarketData),
    "getOrderBookData": (()=>getOrderBookData)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/server-reference.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$app$2d$render$2f$encryption$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/app-render/encryption.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$flows$2f$generate$2d$trading$2d$signal$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/ai/flows/generate-trading-signal.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/action-validate.js [app-rsc] (ecmascript)");
;
;
;
;
;
async function getAiTradingSignal(symbol, timeframe, indicatorSettings) {
    try {
        const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$flows$2f$generate$2d$trading$2d$signal$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["generateTradingSignal"])({
            symbol,
            timeframe,
            indicatorSettings
        });
        return {
            success: true,
            analysis: result
        };
    } catch (error) {
        console.error('Error generating AI trading signal:', error);
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
        return {
            success: false,
            error: errorMessage
        };
    }
}
async function getMarketData(symbol) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getTicker"])(symbol);
}
async function getOrderBookData(symbol) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getOrderBook"])(symbol);
}
async function getKlineData(symbol, interval) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKline"])(symbol, interval);
}
async function getIndicatorData(symbol, timeframe, settings = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["defaultIndicatorSettings"]) {
    const klineData = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKline"])(symbol, timeframe);
    if (!klineData) return null;
    const reversedKline = [
        ...klineData
    ].reverse();
    const closePrices = reversedKline.map((k)=>parseFloat(k[4]));
    const highPrices = reversedKline.map((k)=>parseFloat(k[2]));
    const lowPrices = reversedKline.map((k)=>parseFloat(k[3]));
    const volumes = reversedKline.map((k)=>parseFloat(k[5]));
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["calculateIndicators"])(closePrices, highPrices, lowPrices, volumes, settings);
}
async function analyzeOrderBook(orderBook) {
    const bids = orderBook.bids.map(([price, size])=>({
            price: parseFloat(price),
            size: parseFloat(size)
        }));
    const asks = orderBook.asks.map(([price, size])=>({
            price: parseFloat(price),
            size: parseFloat(size)
        }));
    // Helper function to find the levels with the largest order sizes
    const findLevels = (orders, count)=>{
        const sorted = [
            ...orders
        ].sort((a, b)=>b.size - a.size);
        return sorted.slice(0, count).map((o)=>o.price);
    };
    const supportLevels = findLevels(bids, 3);
    const resistanceLevels = findLevels(asks, 3);
    return {
        support: supportLevels,
        resistance: resistanceLevels
    };
}
;
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ensureServerEntryExports"])([
    getAiTradingSignal,
    getMarketData,
    getOrderBookData,
    getKlineData,
    getIndicatorData,
    analyzeOrderBook
]);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getAiTradingSignal, "70c6125dbbad3595350503c517b30b35b439281e36", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getMarketData, "40ecf96ec3829da1facb2822b20b7b6fb2faedc074", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getOrderBookData, "404bceabf4524442855236b92fdc7049a3e2aa0d9e", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getKlineData, "6075278ac703872d2e66765d6f6dbe7646dd10bb25", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getIndicatorData, "70901addb4aa828fa13a5df1151b80af96986e9baf", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(analyzeOrderBook, "40ed26910e6df74305f6af4c2aa1e4f10fbe170c0d", null);
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)\", ACTIONS_MODULE1 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <locals>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
;
;
;
;
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)\", ACTIONS_MODULE1 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <module evaluation>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/indicators.ts [app-rsc] (ecmascript)", ACTIONS_MODULE1 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <locals>');
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)\", ACTIONS_MODULE1 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <exports>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "70901addb4aa828fa13a5df1151b80af96986e9baf": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getIndicatorData"]),
    "70c6125dbbad3595350503c517b30b35b439281e36": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getAiTradingSignal"]),
    "7f2e70fe065ef52da281045a61720821ecf0d71418": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["defaultIndicatorSettings"]),
    "7f6bdcfaab54ceca1993e9b1f5ad75ae8ef8b01100": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorSettings"])
});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/indicators.ts [app-rsc] (ecmascript)", ACTIONS_MODULE1 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <locals>');
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)\", ACTIONS_MODULE1 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "70901addb4aa828fa13a5df1151b80af96986e9baf": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["70901addb4aa828fa13a5df1151b80af96986e9baf"]),
    "70c6125dbbad3595350503c517b30b35b439281e36": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["70c6125dbbad3595350503c517b30b35b439281e36"]),
    "7f2e70fe065ef52da281045a61720821ecf0d71418": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["7f2e70fe065ef52da281045a61720821ecf0d71418"]),
    "7f6bdcfaab54ceca1993e9b1f5ad75ae8ef8b01100": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["7f6bdcfaab54ceca1993e9b1f5ad75ae8ef8b01100"])
});
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/indicators.ts [app-rsc] (ecmascript)", ACTIONS_MODULE1 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <module evaluation>');
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29222c$__ACTIONS_MODULE1__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/indicators.ts [app-rsc] (ecmascript)", ACTIONS_MODULE1 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <exports>');
}}),
"[project]/src/app/favicon.ico.mjs { IMAGE => \"[project]/src/app/favicon.ico (static in ecmascript)\" } [app-rsc] (structured image object, ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/favicon.ico.mjs { IMAGE => \"[project]/src/app/favicon.ico (static in ecmascript)\" } [app-rsc] (structured image object, ecmascript)"));
}}),
"[project]/src/app/layout.tsx [app-rsc] (ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/layout.tsx [app-rsc] (ecmascript)"));
}}),
"[project]/src/app/page.tsx (client reference/proxy) <module evaluation>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "default": (()=>__TURBOPACK__default__export__)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/rsc/react-server-dom-turbopack-server-edge.js [app-rsc] (ecmascript)");
;
const __TURBOPACK__default__export__ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerClientReference"])(function() {
    throw new Error("Attempted to call the default export of [project]/src/app/page.tsx <module evaluation> from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.");
}, "[project]/src/app/page.tsx <module evaluation>", "default");
}}),
"[project]/src/app/page.tsx (client reference/proxy)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "default": (()=>__TURBOPACK__default__export__)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/rsc/react-server-dom-turbopack-server-edge.js [app-rsc] (ecmascript)");
;
const __TURBOPACK__default__export__ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerClientReference"])(function() {
    throw new Error("Attempted to call the default export of [project]/src/app/page.tsx from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.");
}, "[project]/src/app/page.tsx", "default");
}}),
"[project]/src/app/page.tsx [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i("[project]/src/app/page.tsx (client reference/proxy) <module evaluation>");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__ = __turbopack_context__.i("[project]/src/app/page.tsx (client reference/proxy)");
;
__turbopack_context__.n(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__);
}}),
"[project]/src/app/page.tsx [app-rsc] (ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/page.tsx [app-rsc] (ecmascript)"));
}}),

};

//# sourceMappingURL=%5Broot-of-the-server%5D__df30f5dc._.js.map