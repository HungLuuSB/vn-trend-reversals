"""Neural logistic-hazard model with a GRU sequence encoder (research/paper1/DECISIONS.md D-022).

    NNHazard(features, hidden=32, weight_decay=1e-4, epochs=15, seeds=(0,)).fit(train)

features: static column names, plus the token "seq" for the stock's last 60 days of daily
channels (features/sequence.py). Without "seq" the same head runs on the static features only.
Output: 20 logits = hazard at steps s = 1..20 after the prediction day (the D-013 landmark
target); loss = discrete-time negative log-likelihood over each row's at-risk steps
(Kvamme, Borgan & Scheel 2019). All preprocessing is fitted on training rows only. With
several seeds, the survival curves of the separately trained networks are averaged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torch import nn

from vnbank.research.shared.config import load
from vnbank.research.survival.features.sequence import CHANNELS, SEQ, SEQ_LEN, seq_columns

CFG = load(1)
NCFG = CFG["neural"]
MAX_STEP = CFG["evaluation"]["max_step"]
THREADS = 8


class _Net(nn.Module):
    def __init__(self, n_static: int, use_seq: bool, hidden: int, dropout: float, max_step: int):
        super().__init__()
        self.gru = nn.GRU(len(CHANNELS), hidden, batch_first=True) if use_seq else None
        n_in = n_static + (hidden if use_seq else 0)
        self.head = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Dropout(dropout),
                                  nn.Linear(hidden, max_step))  # fmt: skip

    def forward(self, xs, xq):
        parts = [xs]
        if self.gru is not None:
            _, h = self.gru(xq)  # xq: (batch, seq_len, channels)
            parts.append(h[-1])
        return self.head(torch.cat(parts, dim=1))


def targets(duration, event, max_step: int = MAX_STEP) -> tuple[np.ndarray, np.ndarray]:
    """(y, mask), each (n, max_step): mask = at risk at step s (s <= duration); y = event at s."""
    d = np.asarray(duration, dtype="int64")[:, None]
    e = np.asarray(event, dtype="int64")[:, None]
    s = np.arange(1, max_step + 1)[None, :]
    return ((s == d) & (e == 1)).astype("float32"), (s <= d).astype("float32")


class NNHazard:
    def __init__(self, features, hidden=32, weight_decay=1e-4, epochs=15, seeds=(0,), seed=None,
                 max_step: int = MAX_STEP):  # fmt: skip
        self.static = [f for f in features if f != SEQ]
        self.use_seq = SEQ in features
        self.hidden, self.weight_decay, self.epochs = int(hidden), float(weight_decay), int(epochs)
        self.seeds = [seed] if seed is not None else list(seeds)
        self.max_step = max_step
        self.nets: list[_Net] = []

    # --- preprocessing (training rows only) ---
    def _seq_raw(self, X: pd.DataFrame) -> np.ndarray:
        a = X[seq_columns()].to_numpy(dtype="float32")
        return a.reshape(len(X), len(CHANNELS), SEQ_LEN).transpose(0, 2, 1)  # (n, T, C)

    def _prep_fit(self, X: pd.DataFrame):
        self.static_prep = None
        if self.static:
            self.static_prep = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
            ).fit(  # fmt: skip
                X[self.static].to_numpy(dtype="float64")
            )
        if self.use_seq:
            q = self._seq_raw(X)
            self.q_mean = np.nanmean(q, axis=(0, 1))
            sd = np.nanstd(q, axis=(0, 1))
            self.q_sd = np.where(sd > 0, sd, 1.0)

    def _transform(self, X: pd.DataFrame) -> tuple[torch.Tensor, torch.Tensor]:
        n = len(X)
        xs = (self.static_prep.transform(X[self.static].to_numpy(dtype="float64"))
              if self.static else np.zeros((n, 0)))  # fmt: skip
        xq = np.zeros((n, 1, len(CHANNELS)), dtype="float32")
        if self.use_seq:
            c = NCFG["clip_sd"]
            xq = np.clip((self._seq_raw(X) - self.q_mean) / self.q_sd, -c, c)
            xq = np.nan_to_num(xq, nan=0.0)
        return (torch.tensor(xs, dtype=torch.float32), torch.tensor(xq, dtype=torch.float32))

    # --- fit / predict ---
    def fit(self, train: pd.DataFrame) -> NNHazard:
        from vnbank.research.survival.models.zoo import capped  # shared fit-time cap (D-014)

        torch.set_num_threads(THREADS)
        torch.use_deterministic_algorithms(True)
        d, e = capped(train)
        y, mask = (torch.tensor(a) for a in targets(d, e, self.max_step))
        self._prep_fit(train)
        xs, xq = self._transform(train)
        # output bias starts at the training rows' empirical hazard per step (KM-like start)
        base = (y.sum(0) + 0.5) / (mask.sum(0) + 1.0)
        self.bias0 = torch.log(base / (1 - base))
        self.nets = [self._train_one(xs, xq, y, mask, s) for s in self.seeds]
        return self

    def _train_one(self, xs, xq, y, mask, seed: int) -> _Net:
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        net = _Net(xs.shape[1], self.use_seq, self.hidden, NCFG["dropout"], self.max_step)
        with torch.no_grad():
            net.head[-1].bias.copy_(self.bias0)
        opt = torch.optim.Adam(net.parameters(), lr=NCFG["learning_rate"],
                               weight_decay=self.weight_decay)  # fmt: skip
        bce = nn.BCEWithLogitsLoss(reduction="none")
        n, bs = len(xs), NCFG["batch_size"]
        net.train()
        for _ in range(self.epochs):
            order = torch.tensor(rng.permutation(n))
            for i in range(0, n, bs):
                b = order[i : i + bs]
                loss = (bce(net(xs[b], xq[b]), y[b]) * mask[b]).sum() / mask[b].sum().clamp(min=1)
                opt.zero_grad()
                loss.backward()
                opt.step()
        net.eval()
        return net

    def hazards(self, X: pd.DataFrame) -> np.ndarray:
        """(n_seeds, n, max_step) hazards."""
        xs, xq = self._transform(X)
        with torch.no_grad():
            return np.stack([torch.sigmoid(net(xs, xq)).numpy() for net in self.nets])

    def survival(self, X: pd.DataFrame, times) -> np.ndarray:
        times = np.asarray(times, dtype="int64")
        if times.max() > self.max_step:
            raise ValueError("horizon beyond the fitted steps")
        s = np.cumprod(1 - self.hazards(X).astype("float64"), axis=2).mean(axis=0)  # seed average
        return s[:, times - 1]
