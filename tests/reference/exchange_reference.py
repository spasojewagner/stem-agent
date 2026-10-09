"""Reference tool for the exchange: plain mean reversion. Used only by
`python -m stem selftest` and tests, to show the tasks are solvable through
a tool. The developmental process never sees this file."""
from statistics import fmean, pstdev


def run(env, window=20, k=1.0):
    symbols = env.status()["symbols"]
    while True:
        st = env.status()
        if st["period"] >= st["last_period"]:
            break
        for s in symbols:
            hist = env.prices(symbol=s, lookback=window + 1)
            if len(hist) <= window:
                continue
            past, p = hist[:-1], hist[-1]
            z = (p - fmean(past)) / (pstdev(past) or 1e-9)
            st = env.status()
            held = st["holdings"][s]
            if held == 0 and z < -k:
                free = [x for x in symbols if st["holdings"][x] == 0]
                env.order(symbol=s, side="buy", quantity=st["cash"] / len(free) / (p * 1.0011))
            elif held > 0 and z > 0:
                env.order(symbol=s, side="sell", quantity=held)
        env.advance(periods=1)
    return env.status()
