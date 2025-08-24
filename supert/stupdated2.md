```python
            else:
                self.logger.info("Auto-close on shutdown is disabled or no active position. Not closing positions.")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)
        finally:
            self.logger.info(Fore.LIGHTBLUE_EX + Style.BRIGHT + "Ehlers SuperTrend Bot has ceased its operations. Until next time!" + Style.RESET_ALL)
            subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations."])
            if self.sms_notifier.is_enabled:
                self.sms_notifier.send_sms(f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations.")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    # Load configuration
    config = Config()

    # Create and run the bot
    bot = EhlersSuperTrendBot(config)
    bot.run()
```
