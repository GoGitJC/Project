"""Display helpers shared by the dashboard and investigation notes."""


def money(amount: int | None) -> str:
    """Format whole dollars. Negative amounts keep a leading minus."""
    if amount is None:
        return "—"
    value = int(amount)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,}"


def markdown_safe(text: str) -> str:
    """Escape dollar signs so Streamlit does not treat amounts as LaTeX."""
    return text.replace("$", r"\$")
