"""Error bars for eval scores. Questions from one building are correlated, so the honest interval is
clustered by building (Miller 2024, "Adding error bars to evals"); Wilson is shown for small samples."""

import math
from collections import defaultdict

Z95 = 1.96


def wilson(correct: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = correct / total
    denominator = 1 + Z95**2 / total
    centre = (p + Z95**2 / (2 * total)) / denominator
    half = Z95 * math.sqrt(p * (1 - p) / total + Z95**2 / (4 * total**2)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def clustered(rows: list[dict], key: str = "building") -> tuple[float, float] | None:
    """95 % interval with a cluster-robust standard error; None if rows carry no cluster key."""
    scored = [r for r in rows if r.get("correct") is not None]
    if not scored or not all(r.get(key) for r in scored):
        return None
    n = len(scored)
    p = sum(1 for r in scored if r["correct"]) / n
    sums = defaultdict(float)
    for r in scored:
        sums[r[key]] += (1.0 if r["correct"] else 0.0) - p
    clusters = len(sums)
    if clusters < 2:
        return None
    variance = clusters / (clusters - 1) * sum(v * v for v in sums.values()) / n**2
    se = math.sqrt(variance)
    return (max(0.0, p - Z95 * se), min(1.0, p + Z95 * se))
