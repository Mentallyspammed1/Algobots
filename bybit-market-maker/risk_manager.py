from datetime import datetime


class RiskManager:
    """Advanced risk management system"""

    def __init__(self, config: dict, logger):
        self.config = config["risk_management"]
        self.logger = logger
        self.daily_pnl = 0
        self.max_drawdown_hit = False
        self.daily_loss_limit_hit = False
        self.last_reset = datetime.now()
        self.peak_balance = 0
        self.current_drawdown = 0
        self.position_value = 0
        self.open_orders_value = 0

    def check_risk_limits(
        self, current_balance: float, position: dict
    ) -> tuple[bool, str]:
        """Check if any risk limits are breached"""
        # Reset daily limits if new day
        if datetime.now().date() > self.last_reset.date():
            self.reset_daily_limits()

        # Update peak balance and drawdown
        self.peak_balance = max(self.peak_balance, current_balance)

        self.current_drawdown = (
            self.peak_balance - current_balance
        ) / self.peak_balance

        # Check maximum drawdown
        if self.current_drawdown > self.config["max_drawdown"]:
            self.max_drawdown_hit = True
            return False, f"Maximum drawdown limit hit: {self.current_drawdown:.2%}"

        # Check daily loss limit
        if self.daily_pnl < -self.config["daily_loss_limit"] * self.peak_balance:
            self.daily_loss_limit_hit = True
            return False, f"Daily loss limit hit: ${self.daily_pnl:.2f}"

        # Check position limits
        position_size = abs(position.get("size", 0)) if position else 0
        position_value = (
            position_size * position.get("mark_price", 0) if position else 0
        )

        if position_value > self.config["position_limit"]:
            return False, f"Position limit exceeded: ${position_value:.2f}"

        return True, "All risk checks passed"

    def calculate_position_size(
        self, balance: float, price: float, side: str, existing_position: float = 0
    ) -> float:
        """Calculate safe position size based on risk parameters"""
        # Use Kelly Criterion inspired sizing
        # Simplified Kelly: f = W - (1-W)/R, where W is win rate, R is win/loss ratio
        # For market making, we can use a fixed fraction of capital for risk
        # max_risk = balance * self.config['risk_per_trade'] # Old approach

        # New approach using kelly_fraction
        # Assuming a win probability (p) and loss probability (q = 1-p)
        # And a win/loss ratio (b)
        # For simplicity, we'll use kelly_fraction directly as a multiplier for risk_per_trade
        kelly_risk_multiplier = self.config["kelly_fraction"]

        max_risk = balance * self.config["risk_per_trade"] * kelly_risk_multiplier
        stop_loss_distance = price * self.config["stop_loss"]

        if stop_loss_distance == 0:  # Avoid division by zero
            return 0

        position_size = max_risk / stop_loss_distance

        # Adjust for existing position (this logic remains the same)
        if side == "Buy" and existing_position < 0:
            position_size *= 1.5  # Increase size to close short
        elif side == "Sell" and existing_position > 0:
            position_size *= 1.5  # Increase size to close long

        # Apply maximum position limit
        max_position_value = min(
            balance * self.config["max_leverage"], self.config["position_limit"]
        )
        max_position_size = max_position_value / price

        return min(position_size, max_position_size)

    def should_close_position(
        self, position: dict, current_price: float
    ) -> tuple[bool, str]:
        """Determine if position should be closed based on risk parameters"""
        if not position or position.get("size", 0) == 0:
            return False, ""

        entry_price = position.get("avg_price", 0)
        position_pnl = (current_price - entry_price) / entry_price

        if position.get("side") == "Sell":
            position_pnl = -position_pnl

        # Check stop loss
        if position_pnl < -self.config["stop_loss"]:
            return True, "stop_loss"

        # Check take profit
        if position_pnl > self.config["take_profit"]:
            return True, "take_profit"

        return False, ""

    def update_daily_pnl(self, pnl: float):
        """Update daily P&L tracking"""
        self.daily_pnl += pnl
        self.logger.info(f"Daily P&L updated: ${self.daily_pnl:.2f}")

    def reset_daily_limits(self):
        """Reset daily risk limits"""
        self.daily_pnl = 0
        self.daily_loss_limit_hit = False
        self.last_reset = datetime.now()
        self.logger.info("Daily risk limits reset")

    def get_risk_metrics(self) -> dict:
        """Get current risk metrics"""
        return {
            "current_drawdown": self.current_drawdown,
            "daily_pnl": self.daily_pnl,
            "peak_balance": self.peak_balance,
            "max_drawdown_hit": self.max_drawdown_hit,
            "daily_loss_limit_hit": self.daily_loss_limit_hit,
            "position_value": self.position_value,
            "risk_score": self._calculate_risk_score(),
        }

    def _calculate_risk_score(self) -> float:
        """Calculate overall risk score (0-100)"""
        drawdown_score = (self.current_drawdown / self.config["max_drawdown"]) * 40
        daily_loss_score = (
            abs(min(0, self.daily_pnl))
            / (self.config["daily_loss_limit"] * self.peak_balance)
            * 30
        )
        position_score = (self.position_value / self.config["position_limit"]) * 30

        return min(100, drawdown_score + daily_loss_score + position_score)
