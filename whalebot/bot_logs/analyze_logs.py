import re


def analyze_trade_logs(log_file_path: str) -> list:
    """Analyzes a trading bot log file to extract currently open scalp trade details,
    including execution timestamps and status.

    Args:
        log_file_path (str): The absolute path to the trading bot log file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a currently open scalp trade
              with 'timestamp', 'side', 'entry', 'tp', 'sl', 'current_price',
              'confidence_level', and 'status'.
              Returns an empty list if no trades are found or if the file cannot be read.

    """
    active_trades = {}  # Dictionary to hold trades that are currently OPEN
    current_price = None
    confidence_level = None
    last_timestamp = None

    ansi_escape = re.compile(r"\x1B(?:[@-Z\-_]|[[\[0-?]*[ -/]*[@-~])")
    timestamp_regex = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")

    try:
        with open(log_file_path, encoding="utf-8") as f:
            for line in f:
                timestamp_match = timestamp_regex.match(line)
                if timestamp_match:
                    last_timestamp = timestamp_match.group(1)

                clean_line = ansi_escape.sub("", line).strip()

                current_price_match = re.search(r"Current Price: ([\d.]+)", clean_line)
                if current_price_match:
                    current_price = float(current_price_match.group(1))

                confidence_match = re.search(r"Raw Signal Score: ([\d.-]+)", clean_line)
                if confidence_match:
                    confidence_level = float(confidence_match.group(1))

                # Regex for Opened positions
                opened_position_match = re.search(
                    r"Opened (BUY|SELL) position: \{'entry_time': datetime\.datetime\(([^)]+)\), 'symbol': '([^']+)', 'side': '([^']+)', 'entry_price': Decimal\('([\d.]+)'\), 'qty': Decimal\('([\d.]+)'\), 'stop_loss': Decimal\('([\d.]+)'\), 'take_profit': Decimal\('([\d.]+)'\), 'status': 'OPEN'}",
                    clean_line,
                )

                # Regex for Closed positions
                closed_position_match = re.search(
                    r"Closed (BUY|SELL) position by (TAKE_PROFIT|STOP_LOSS): \{'entry_time': datetime\.datetime\(([^)]+)\), 'symbol': '([^']+)', 'side': '([^']+)', 'entry_price': Decimal\('([\d.]+)'\), 'qty': Decimal\('([\d.]+)'\), 'stop_loss': Decimal\('([\d.]+)'\), 'take_profit': Decimal\('([\d.]+)'\), 'status': 'CLOSED', 'exit_time': datetime\.datetime\(([^)]+)\), 'exit_price': Decimal\('([\d.]+)'\), 'closed_by': '([^']+)'\}\. PnL: ([-\d.]+)",
                    clean_line,
                )

                if opened_position_match:
                    side = opened_position_match.group(1)
                    entry_time_str = opened_position_match.group(2)
                    symbol = opened_position_match.group(3)
                    entry_price = float(opened_position_match.group(5))
                    stop_loss = float(opened_position_match.group(7))
                    take_profit = float(opened_position_match.group(8))

                    trade_id = f"{symbol}_{entry_time_str}"

                    if (
                        current_price is not None
                        and confidence_level is not None
                        and last_timestamp is not None
                    ):
                        trade = {
                            "timestamp": last_timestamp,
                            "side": side,
                            "entry": entry_price,
                            "tp": take_profit,
                            "sl": stop_loss,
                            "current_price": current_price,
                            "confidence_level": confidence_level,
                            "status": "OPEN",
                            "symbol": symbol,  # Store symbol for unique ID
                            "entry_time_raw": entry_time_str,  # Store raw entry time for unique ID
                        }
                        active_trades[trade_id] = trade
                    else:
                        print(
                            f"Warning: Skipped opened trade entry due to missing data: {clean_line}"
                        )

                elif closed_position_match:
                    entry_time_str = closed_position_match.group(3)
                    symbol = closed_position_match.group(4)

                    trade_id = f"{symbol}_{entry_time_str}"

                    active_trades.pop(trade_id, None)  # Remove from active trades
                    # else:
                    # print(f"Warning: Closed trade found but no matching open trade: {clean_line}")

    except FileNotFoundError:
        print(
            f"Error: The log file was not found at the specified path: {log_file_path}"
        )
        return []
    except Exception as e:
        print(
            f"An unexpected error occurred while reading or parsing the log file: {e}"
        )
        return []

    return list(active_trades.values())  # Return only currently active trades


def suggest_trades(current_signals: list, confidence_threshold: float = 1.5) -> list:
    """Suggests new trades based on current open signals and a confidence threshold.

    Args:
        current_signals (list): A list of currently open trade signals.
        confidence_threshold (float): The minimum confidence level required to suggest a trade.

    Returns:
        list: A list of suggested trades.

    """
    suggested_trades = []
    for signal in current_signals:
        if signal["confidence_level"] >= confidence_threshold:
            suggested_trades.append(signal)
    return suggested_trades


# Example Usage:
if __name__ == "__main__":
    log_file_path = (
        "/data/data/com.termux/files/home/Algobots/whalebot/bot_logs/wgwhalex_bot.log"
    )

    current_signals = analyze_trade_logs(log_file_path)
    suggested_trades = suggest_trades(
        current_signals, confidence_threshold=1.5
    )  # Example threshold

    top_confidence_signal = None
    if current_signals:
        top_confidence_signal = max(
            current_signals, key=lambda x: x["confidence_level"]
        )

    # Prepare the styled output
    styled_output = []
    styled_output.append("✨🔮 **Whispers from the Trading Ether** 🔮✨")
    styled_output.append("")

    if current_signals:
        styled_output.append("📜 **Current Open Scalp Trades (Signals):**")
        for signal in current_signals:
            styled_output.append(f"  - **Time:** {signal['timestamp']}")
            styled_output.append(
                f"    **Signal:** {signal['side']} (Confidence: {signal['confidence_level']:.2f})"
            )
            styled_output.append(
                f"    **Entry Price:** {signal['entry']:.5f} | **TP:** {signal['tp']:.5f} | **SL:** {signal['sl']:.5f}"
            )
            styled_output.append(
                f"    **Current Price:** {signal['current_price']:.5f}"
            )
            styled_output.append("")

        if suggested_trades:
            styled_output.append(
                "💡 **Prophecies of New Trades (Suggested based on Confidence):**"
            )
            for trade in suggested_trades:
                styled_output.append(f"  - **Time:** {trade['timestamp']}")
                styled_output.append(
                    f"    **Suggestion:** Initiate a {trade['side']} trade (Confidence: {trade['confidence_level']:.2f})"
                )
                styled_output.append(
                    f"    **Entry Price:** {trade['entry']:.5f} | **Anticipated TP:** {trade['tp']:.5f} | **Protective SL:** {trade['sl']:.5f}"
                )
                styled_output.append(
                    f"    **Current Market Price:** {trade['current_price']:.5f}"
                )
                styled_output.append("")
        else:
            styled_output.append(
                "No new trade prophecies at this moment (no signals met the confidence threshold)."
            )
        styled_output.append("")

        if top_confidence_signal:
            styled_output.append("🌟 **Top Confidence Current Signal:**")
            styled_output.append(f"  - **Time:** {top_confidence_signal['timestamp']}")
            styled_output.append(
                f"    **Signal:** {top_confidence_signal['side']} (Confidence: {top_confidence_signal['confidence_level']:.2f})"
            )
            styled_output.append(
                f"    **Entry Price:** {top_confidence_signal['entry']:.5f} | **TP:** {top_confidence_signal['tp']:.5f} | **SL:** {top_confidence_signal['sl']:.5f}"
            )
            styled_output.append(
                f"    **Current Price:** {top_confidence_signal['current_price']:.5f}"
            )
            styled_output.append("")
    else:
        styled_output.append("No current open scalp trades (signals) found in the log.")

    styled_output.append(
        "--- To leverage the Gemini API for more advanced strategy formulation or signal interpretation, you would integrate a Python library like `google-generativeai` here. This would allow the model to analyze the `current_signals` data and provide nuanced insights or even generate dynamic trading rules based on complex patterns."
    )
    styled_output.append(
        'For example, you could send the `current_signals` data to the Gemini API and ask: "Given these trade signals, what is the optimal strategy?"'
    )

    print("\n".join(styled_output))
