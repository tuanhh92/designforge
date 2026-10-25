"""Stage 2a — fuse anchors, OCR, ratios, scale cues and category priors into absolute dimensions.

Log-space weighted least squares: ratios become linear constraints
    log W - log H = log r      (σ_r)
and absolute evidence becomes
    log W = log w_obs          (σ_w)
Solution gives a posterior mean and (via the normal-equation covariance) a σ per unknown,
which we turn into a 0..1 confidence for the Spec Review UI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Evidence:
    """coeffs: unknown name → coefficient in log space; rhs: log value; sigma: relative std-dev."""
    coeffs: dict[str, float]
    value: float           # linear-space value (mm for absolutes, unitless for ratios)
    sigma: float           # relative (0.01 = 1 %)
    source: str


@dataclass
class Solution:
    values_mm: dict[str, int]
    rel_sigma: dict[str, float]
    sources: dict[str, list[str]] = field(default_factory=dict)

    def confidence(self, name: str) -> float:
        # 2 % → ~0.95, 10 % → ~0.6, 25 % → ~0.2
        return round(math.exp(-((self.rel_sigma[name] / 0.12) ** 2) * 0.7), 2)


def absolute(name: str, mm: float, sigma: float, source: str) -> Evidence:
    return Evidence({name: 1.0}, mm, sigma, source)


def ratio(num: str, den: str, r: float, sigma: float, source: str) -> Evidence:
    return Evidence({num: 1.0, den: -1.0}, r, sigma, source)


def solve(unknowns: list[str], evidence: list[Evidence], bounds_mm: dict[str, tuple[int, int]]) -> Solution:
    idx = {u: i for i, u in enumerate(unknowns)}
    A = np.zeros((len(evidence), len(unknowns)))
    b = np.zeros(len(evidence))
    w = np.zeros(len(evidence))
    for row, ev in enumerate(evidence):
        for name, c in ev.coeffs.items():
            A[row, idx[name]] = c
        b[row] = math.log(ev.value)
        w[row] = 1.0 / max(ev.sigma, 1e-4)  # relative σ ≈ σ in log space
    Aw, bw = A * w[:, None], b * w

    from scipy.optimize import lsq_linear  # local import keeps df_ai importable without scipy in web tools

    lo = np.array([math.log(bounds_mm[u][0]) for u in unknowns])
    hi = np.array([math.log(bounds_mm[u][1]) for u in unknowns])
    res = lsq_linear(Aw, bw, bounds=(lo, hi))
    cov = np.linalg.pinv(Aw.T @ Aw)
    values = {u: int(round(math.exp(res.x[i]))) for u, i in idx.items()}
    sig = {u: float(math.sqrt(max(cov[i, i], 0.0))) for u, i in idx.items()}
    sources = {u: [ev.source for ev in evidence if u in ev.coeffs] for u in unknowns}
    return Solution(values, sig, sources)


# Example
# sol = solve(["W", "H", "D"], [
#     absolute("H", 2400, 0.01, "user_anchor"),
#     ratio("W", "H", 1.05, 0.12, "vision_ratio"),
#     absolute("D", 600, 0.08, "category_prior:wardrobe"),
# ], bounds_mm={"W": (300, 6000), "H": (300, 3000), "D": (250, 900)})
