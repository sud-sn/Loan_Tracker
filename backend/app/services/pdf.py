"""PDF rendering with WeasyPrint (Pango + HarfBuzz), so Tamil shapes correctly (PRD section 9)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core import clock, i18n
from app.models import BusinessSettings

PDF_DIR = Path(__file__).resolve().parent.parent / "pdf"
_env = Environment(
    loader=FileSystemLoader(PDF_DIR / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _rate(value: Decimal) -> str:
    return f"{Decimal(value).normalize():f}"


def render(template: str, lang: str, business: BusinessSettings, **context: Any) -> bytes:
    from weasyprint import HTML

    html = _env.get_template(template).render(
        lang=lang,
        fonts=(PDF_DIR / "fonts").as_uri(),
        t=lambda key, **kw: i18n.t(lang, key, **kw),
        money=i18n.money,
        date=i18n.fmt_date,
        words=lambda v: i18n.amount_in_words(lang, v),
        rate=_rate,
        today=clock.today(),
        lender_name=business.lender_name,
        lender_address=business.lender_address,
        licence_no=business.licence_no,
        **context,
    )
    return bytes(HTML(string=html, base_url=str(PDF_DIR)).write_pdf())


def table(lang: str, business: BusinessSettings, *, title: str, subtitle: str | None, headers: list[str],
          rows: list[list[Any]], numeric: set[int], summary: list[tuple[str, str]] | None = None) -> bytes:
    return render("table.html", lang, business, title=title, subtitle=subtitle, headers=headers, rows=rows,
                  numeric=numeric, summary=summary)
