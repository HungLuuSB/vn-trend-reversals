"""Per-stock long-only simulation under Vietnamese trading rules (DECISIONS.md D-021).

Signals are computed from information at the close of row s and act at the open of row s + 1
(the 09:00 decision time). Returns are open-to-open on adjusted prices; fill checks use raw
opens against that day's ceiling and floor. Settlement: the earliest sell is the open of the
session after the settlement day (buy session + cycle + 1), with the cycle in force on the
buy date (T+3 before 2016-01-04, T+2 after; dbt/seeds/settlement_cycle.csv).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from vnbank.common import paths


@dataclass(frozen=True)
class Costs:
    buy: float = 0.0015  # brokerage
    sell: float = 0.0025  # brokerage 0.15% + sales tax 0.10%

    @classmethod
    def round_trip(cls, total: float, tax: float = 0.001) -> Costs:
        """D-021: tax fixed at 0.10%; the rest is brokerage split evenly."""
        b = (total - tax) / 2
        return cls(buy=b, sell=b + tax)


def settlement_cycle(dates: np.ndarray) -> np.ndarray:
    seed = pd.read_csv(paths.SEEDS / "settlement_cycle.csv", parse_dates=["valid_from"])
    seed = seed.sort_values("valid_from")
    idx = np.searchsorted(seed.valid_from.to_numpy(), dates, side="right") - 1
    if (idx < 0).any():
        raise ValueError("trade date before the first settlement-cycle row")
    return seed.cycle_days.to_numpy()[idx]


@dataclass
class StockDays:
    """One stock's rows (its own trading days, sorted), aligned arrays."""

    dates: np.ndarray  # datetime64
    session: np.ndarray  # HOSE session number (for settlement counting)
    open_adj: np.ndarray
    open_raw: np.ndarray
    ceiling: np.ndarray  # NaN when unknown
    floor: np.ndarray
    limit_known: np.ndarray  # bool
    close_at_floor: np.ndarray  # bool
    eligible: np.ndarray  # bool: in the universe and >= 250 prior days
    swing_dir: np.ndarray  # +1 / -1 / 0 at the close of each row


def simulate(
    sd: StockDays,
    rule: str,
    p5: np.ndarray | None = None,
    tau: float = 1.0,
    costs: Costs = Costs(),
    window: tuple | None = None,
    unknown_limit: str = "fill",
    fail_on_floor_close: bool = False,
) -> pd.DataFrame:
    """Simulate one stock. rule: "model" (needs p5, tau), "dc" or "bh" (buy-and-hold).

    window = (first_date, last_date): trading happens only inside it; open positions are
    closed notionally at the last open of the window (sell cost charged, D-021).
    Returns one row per stock row inside the window: date, held (after the open), slot
    return attributed to that date, buys, sells, flags.
    """
    n = len(sd.dates)
    lo, hi = (0, n - 1) if window is None else (
        int(np.searchsorted(sd.dates, np.datetime64(window[0]))),
        int(np.searchsorted(sd.dates, np.datetime64(window[1]), side="right")) - 1)  # fmt: skip
    cycle = settlement_cycle(sd.dates)
    held, pending, earliest = False, False, -1
    out = []
    for i in range(max(lo, 1), hi + 1):
        s = i - 1  # signal row: information at the close of s, action at the open of i
        held_before = held
        ret = sd.open_adj[i] / sd.open_adj[s] - 1 if held else 0.0
        buy = sell = assumed = False
        known = bool(sd.limit_known[i])
        last = i == hi
        p_exit = rule == "model" and p5 is not None and np.isfinite(p5[s]) and p5[s] > tau
        if rule != "bh":
            if sd.swing_dir[s] == 1 and (s == 0 or sd.swing_dir[s - 1] != 1):
                pending = not held  # an up-swing was confirmed at the close of s: order placed
            if sd.swing_dir[s] != 1:
                pending = False  # the up-swing is over: an unfilled buy order lapses
        if held:
            if rule == "bh":
                want_sell = not sd.eligible[i]
            else:
                want_sell = sd.swing_dir[s] == -1 or not sd.eligible[i] or p_exit
            if want_sell and sd.session[i] >= earliest:
                blocked = known and sd.open_raw[i] <= sd.floor[i]
                if fail_on_floor_close and known and sd.close_at_floor[i]:
                    blocked = True
                if not known and unknown_limit == "skip":
                    blocked = True
                if not blocked:
                    sell, held, assumed = True, False, not known
                    ret -= costs.sell
        elif not last:
            if rule == "bh":
                want_buy = bool(sd.eligible[i])
            else:
                if pending and (not sd.eligible[i] or p_exit):
                    pending = False  # not tradable now, or the exit condition already holds
                want_buy = pending
            if want_buy:
                blocked = known and sd.open_raw[i] >= sd.ceiling[i]
                if not known and unknown_limit == "skip":
                    blocked = True
                if not blocked:  # a blocked order stays pending and is retried
                    buy, held, pending, assumed = True, True, False, not known
                    earliest = sd.session[i] + cycle[i] + 1
                    ret -= costs.buy
        if last and held:  # notional close at the window's last open (D-021)
            ret -= costs.sell
            sell, held = True, False
        counted = bool(sd.eligible[i]) or held_before
        out.append((sd.dates[i], counted, ret, buy, sell, assumed))
    return pd.DataFrame(out, columns=["date", "counted", "ret", "buy", "sell", "assumed_fill"])
