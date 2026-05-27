"""Pure scoring rules. No streamlit, no SQL — easy to unit test."""

from datetime import date
import pandas as pd


def _is_valid(expires_at, today_str: str) -> bool:
    """A cert is valid if it has no expiry date or the date is >= today.
    ISO-format YYYY-MM-DD strings compare lexicographically — same as date order."""
    if expires_at is None or expires_at == "":
        return True
    return str(expires_at) >= today_str


def rank(joined: pd.DataFrame, today: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute ranking + per-(employee, cert) rationale from joined long-form data.

    Algorithm:
      contribution = influence * (1 if valid else 0)
      score = best_contribution + min(extras_count * 0.5, 2.0)
        where extras_count = number of non-zero contributions after the best.

    Returns:
      ranking:   one row per employee, sorted by score desc
      rationale: one row per (employee, cert) input row, with valid + contribution
    """
    today_str = today.isoformat()

    joined = joined.copy()
    joined["valid"] = joined["expires_at"].apply(lambda x: _is_valid(x, today_str))
    joined["contribution"] = joined["influence"] * joined["valid"].astype(int)

    def compute(g: pd.DataFrame) -> pd.Series:
        contribs = sorted(g["contribution"].tolist(), reverse=True)
        best = contribs[0] if contribs else 0
        extras = [c for c in contribs[1:] if c > 0]
        bonus = min(len(extras) * 0.5, 2.0)
        return pd.Series({
            "score":         float(best + bonus),
            "match_count":   len(g),
            "expired_count": int((~g["valid"]).sum()),
        })

    if joined.empty:
        ranking = pd.DataFrame(columns=["employee_id", "name", "dept", "title",
                                         "score", "match_count", "expired_count"])
    else:
        ranking = (
            joined.groupby(["employee_id", "name", "dept", "title"], as_index=False)
            .apply(compute, include_groups=False)
            .sort_values("score", ascending=False, ignore_index=True)
        )

    rationale = joined[["employee_id", "cert_code", "cert_name", "influence",
                        "expires_at", "valid", "contribution"]].copy()
    return ranking, rationale
