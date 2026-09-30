import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# No platform branding: empty header, page number only in the footer.
HEADER_TEMPLATE = "<div></div>"

FOOTER_TEMPLATE = (
    '<div style="font-size: 9px; width: 100%; text-align: center; color: #777;">'
    '<span class="pageNumber"></span></div>'
)

# Page geometry — single source of truth for both page.pdf() and the
# «انتهى» pinning (CONTENT_HEIGHT_MM is what the template needs).
PAGE_HEIGHT_MM = 297.0        # A4
MARGIN_TOP_MM = 8.0
MARGIN_BOTTOM_MM = 14.0
MARGIN_SIDE_MM = 10.0
CONTENT_HEIGHT_MM = PAGE_HEIGHT_MM - MARGIN_TOP_MM - MARGIN_BOTTOM_MM   # 275.0


async def _render_pdf_async(html_path: str, output_path: str, timeout_ms: int) -> None:
    """The actual Playwright work. Runs on its own private event loop (see below)."""
    url = Path(html_path).resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()

            # networkidle: the MathJax CDN script must be fully downloaded
            await page.goto(url, wait_until="networkidle")
            await page.evaluate("document.fonts.ready")

            # wait for the template's own signal
            await page.wait_for_function("window.__DOCUMENT_READY__ === true", timeout=timeout_ms)

            math_ok = await page.evaluate("window.__MATHJAX_OK__ === true")
            if not math_ok:
                raise RuntimeError(
                    "MathJax failed to load or render (CDN unreachable?) — "
                    "refusing to emit a broken PDF."
                )

            await page.wait_for_timeout(500)  # small safety buffer

            # Pin «انتهى» to the bottom of the LAST page.
            # (The template defines the function; this is a no-op without it.)
            await page.evaluate(
                "async (mm) => { if (window.__PIN_END_TO_PAGE__) { await window.__PIN_END_TO_PAGE__(mm); } }",
                CONTENT_HEIGHT_MM,
            )

            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=HEADER_TEMPLATE,
                footer_template=FOOTER_TEMPLATE,
                margin={
                    "top": f"{MARGIN_TOP_MM}mm",
                    "bottom": f"{MARGIN_BOTTOM_MM}mm",
                    "left": f"{MARGIN_SIDE_MM}mm",
                    "right": f"{MARGIN_SIDE_MM}mm",
                },
                scale=1,
            )
        finally:
            await browser.close()


def _render_pdf_blocking(html_path: str, output_path: str, timeout_ms: int) -> None:
    """Run Playwright on a private event loop in this thread (uvicorn/Windows workaround)."""
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_render_pdf_async(html_path, output_path, timeout_ms))
    finally:
        asyncio.set_event_loop(None)
        loop.close()


async def render_pdf(html_path: str, output_path: str, timeout_ms: int = 20000) -> None:
    await asyncio.to_thread(_render_pdf_blocking, html_path, output_path, timeout_ms)