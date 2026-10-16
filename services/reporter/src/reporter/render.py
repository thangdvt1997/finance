"""Jinja2 -> HTML tự chứa (CSS in được, A4) -> PDF bằng WeasyPrint."""
from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

from tscommon.sources import scrub_sources

from . import __version__

_env = Environment(loader=PackageLoader("reporter", "templates"), autoescape=select_autoescape(["html", "j2"], default=True),
                   trim_blocks=True, lstrip_blocks=True)


def render_html(ctx: dict) -> str:
    html = _env.get_template("report.html.j2").render(r=ctx, version=__version__)
    return scrub_sources(html)  # lop phong thu cuoi: HTML/PDF khong chua ten nguon (docs/UI_NO_SOURCES.md)


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML  # nhập muộn: import nặng, test HTML không cần
    return HTML(string=html, base_url="about:blank").write_pdf()


def render_account_html(ctx: dict) -> str:
    """Báo cáo theo tài khoản (templates/account_report.html.j2) + lớp lọc tên nguồn cuối cùng."""
    html = _env.get_template("account_report.html.j2").render(r=ctx, version=__version__)
    return scrub_sources(html)
