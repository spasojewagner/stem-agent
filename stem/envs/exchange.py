"""A virtual exchange with synthetic markets.

Each session is a reproducible synthetic price history. The agent starts
with cash, can look at past prices, place market orders and move time
forward. At the end, equity is compared with doing the obvious thing
(holding cash or buying and holding) and with the best of a set of simple
reference strategies run on the same series.
"""
from __future__ import annotations

import math
import random
from statistics import fmean, pstdev

from .base import Action, Environment, Task

FEE = 0.001
START_CASH = 10_000.0
REGIMES = {
    #           drift/period  ar(1)  noise
    "range":   (0.0,          0.88,  0.016),
    "range2":  (0.0,          0.84,  0.020),
    "up":      (0.0010,       0.80,  0.024),
    "down":    (-0.0012,      0.82,  0.022),
}

_TASKS = [
    # id, split, seed, {symbol: regime}, periods, start
    ("ex-train-1", "train", 11, {"ALFA": "range"}, 200, 40),
    ("ex-train-2", "train", 12, {"BRAV": "up"}, 200, 40),
    ("ex-train-3", "train", 13, {"CORE": "range", "DELT": "down"}, 200, 40),
    ("ex-test-1", "test", 21, {"ECHO": "range2"}, 220, 40),
    ("ex-test-2", "test", 22, {"FOXT": "range>down"}, 220, 40),
    ("ex-test-3", "test", 23, {"GOLF": "up", "HOTL": "range2"}, 220, 40),
]


def generate_series(seed: int, regime: str, periods: int, start_price: float = 100.0) -> list[float]:
    rng = random.Random(seed)
    parts = regime.split(">")
    x, dev, prices = math.log(start_price), 0.0, []
    for t in range(periods):
        name = parts[min(len(parts) - 1, t * len(parts) // periods)]
        drift, phi, sigma = REGIMES[name]
        dev = phi * dev + rng.gauss(0, sigma)
        x += drift
        prices.append(round(math.exp(x + dev), 4))
    return prices


# -- reference strategies (hidden from the agent; used only for grading) --------
def _run_signal(prices: list[float], start: int, want_long) -> float:
    cash, qty = 1.0, 0.0
    for t in range(start, len(prices)):
        p = prices[t]
        long = want_long(t, qty > 0)
        if long and qty == 0:
            qty, cash = cash * (1 - FEE) / p, 0.0
        elif not long and qty > 0:
            cash, qty = qty * p * (1 - FEE), 0.0
    return cash + qty * prices[-1] - 1.0


def _mean_reversion(prices, start, w, k):
    def sig(t, holding):
        win = prices[t - w:t]
        mu, sd = fmean(win), pstdev(win) or 1e-9
        z = (prices[t] - mu) / sd
        return z < -k or (holding and z < 0)
    return _run_signal(prices, start, sig)


def _trend(prices, start, w):
    return _run_signal(prices, start, lambda t, h: prices[t] > fmean(prices[t - w:t]))


def reference_return(prices: list[float], start: int) -> float:
    best = prices[-1] / prices[start] * (1 - FEE) - 1.0
    for w in (10, 20, 30):
        for k in (0.5, 1.0, 1.5):
            best = max(best, _mean_reversion(prices, start, w, k))
        best = max(best, _trend(prices, start, w))
    return best


class Exchange(Environment):
    name = "exchange"
    brief = ("A simulated exchange. Each session has one or two symbols with their own price "
             "history. You start with 10,000 in cash. You can look at past prices, buy or sell "
             "at the current price (a 0.1% fee is charged on every trade, no short selling), and "
             "move time forward. Positions still open when the session ends are valued at the "
             "final price.")
    max_steps = 14

    def tasks(self, split: str) -> list[Task]:
        out = []
        for tid, sp, seed, symbols, periods, start in _TASKS:
            if sp != split:
                continue
            names = " and ".join(symbols)
            out.append(Task(tid, sp, f"Session {tid}: trading {names} from period {start} to period "
                                     f"{periods}. Finish the session with as much equity as you can.",
                            {"seed": seed, "symbols": symbols, "periods": periods, "start": start}))
        return out

    def _start(self, task: Task) -> None:
        p = task.params
        self.periods, self.t = p["periods"], p["start"]
        self.series = {s: generate_series(p["seed"] * 100 + i, reg, p["periods"], 50 + 30 * i)
                       for i, (s, reg) in enumerate(p["symbols"].items())}
        self.cash = START_CASH
        self.holdings = {s: 0.0 for s in self.series}
        self.trades = 0

    def _price(self, symbol: str) -> float:
        if symbol not in self.series:
            raise ValueError(f"unknown symbol '{symbol}'. Symbols: {list(self.series)}")
        return self.series[symbol][min(self.t, self.periods - 1)]

    def _equity(self) -> float:
        return self.cash + sum(q * self._price(s) for s, q in self.holdings.items())

    # -- actions ------------------------------------------------------------
    def status(self) -> dict:
        return {"period": self.t, "last_period": self.periods - 1, "symbols": list(self.series),
                "cash": round(self.cash, 2), "holdings": {s: round(q, 6) for s, q in self.holdings.items()},
                "equity": round(self._equity(), 2), "fee_rate": FEE}

    def prices(self, symbol: str, lookback: int = 30) -> list[float]:
        lookback = max(1, min(int(lookback), 200))
        series = self.series.get(symbol)
        if series is None:
            raise ValueError(f"unknown symbol '{symbol}'. Symbols: {list(self.series)}")
        return series[max(0, self.t - lookback + 1): self.t + 1]

    def order(self, symbol: str, side: str, quantity: float) -> dict:
        if self.t >= self.periods - 1:
            raise ValueError("session is over")
        price, quantity, side = self._price(symbol), float(quantity), side.lower()
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if side == "buy":
            cost = quantity * price * (1 + FEE)
            if cost > self.cash * (1 + 1e-6) + 0.01:
                raise ValueError(f"insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
            if cost > self.cash:  # rounding: spend exactly what is there
                quantity, cost = self.cash / (price * (1 + FEE)), self.cash
            self.cash -= cost
            self.holdings[symbol] += quantity
        elif side == "sell":
            held = self.holdings[symbol]
            if quantity > held * (1 + 1e-6) + 1e-6:
                raise ValueError(f"cannot sell {quantity}, holding {held}")
            quantity = min(quantity, held)
            self.holdings[symbol] -= quantity
            self.cash += quantity * price * (1 - FEE)
        else:
            raise ValueError("side must be 'buy' or 'sell'")
        self.trades += 1
        return {"filled": quantity, "price": price, "cash": round(self.cash, 2),
                "holdings": {s: round(q, 6) for s, q in self.holdings.items()}}

    def advance(self, periods: int = 1) -> dict:
        n = max(1, min(int(periods), 20))
        if self.t >= self.periods - 1:
            raise ValueError("session is over")
        self.t = min(self.t + n, self.periods - 1)
        return {"period": self.t, "prices": {s: self._price(s) for s in self.series},
                "session_over": self.t >= self.periods - 1}

    def actions(self) -> list[Action]:
        obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
        return [
            Action("status", "Current period, cash, holdings and equity.", obj({}), self.status),
            Action("prices", "Closing prices up to and including the current period (lookback 1-200).",
                   obj({"symbol": {"type": "string"}, "lookback": {"type": "integer"}}, ["symbol"]), self.prices),
            Action("order", "Market order at the current price. side is 'buy' or 'sell'; quantity in units (fractions allowed).",
                   obj({"symbol": {"type": "string"}, "side": {"type": "string"}, "quantity": {"type": "number"}},
                       ["symbol", "side", "quantity"]), self.order),
            Action("advance", "Move time forward by 1-20 periods.",
                   obj({"periods": {"type": "integer"}}), self.advance),
        ]

    # -- grading ------------------------------------------------------------
    def score(self, answer: str) -> tuple[float, str]:
        start = self.task.params["start"]
        final = self.cash + sum(q * self.series[s][-1] for s, q in self.holdings.items())
        agent = final / START_CASH - 1
        n = len(self.series)
        hold = fmean(s[-1] / s[start] * (1 - FEE) - 1 for s in self.series.values())
        naive = max(hold, 0.0)
        ref = fmean(reference_return(s, start) for s in self.series.values())
        if ref - naive < 0.005:
            ref = naive + 0.005
        score = max(0.0, min(1.0, (agent - naive) / (ref - naive)))
        covered = self.t - start
        note = (f"return {agent:+.1%} vs naive {naive:+.1%} and reference {ref:+.1%} -> {score:.2f}; "
                f"{self.trades} trades; time advanced through {covered}/{self.periods - 1 - start} periods; "
                f"{n} symbol(s)")
        return round(score, 3), note
