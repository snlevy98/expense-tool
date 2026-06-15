#!/usr/bin/env python3
"""
Amazon order-history scraper.

Opens a real (non-headless) Chrome window, waits for the user to log in to
Amazon manually (handling 2FA / CAPTCHA), then scrapes order history and writes
a single CSV — one row per item — with these columns:

    Order Date, Order ID, Order Total, Order Status, Shipping Address Name,
    Item Subtotal, Item Subtotal Tax, Item Total, ASIN, Product Name,
    Quantity, Payment Type, Seller

This is consumed by the expense tool's POST /amazon/pull-and-import endpoint,
which feeds the CSV straight into the existing Amazon import pipeline. It can
also be run by hand:

    python scripts/amazon_order_scraper.py --months 3 --output orders.csv

CLI:
    --year YEAR        Filter to a calendar year.
    --months N         Filter to the last N months (mutually exclusive with --year).
    --output FILE      Where to write the CSV (default: amazon_orders.csv).
    --detail /
      --no-detail      Whether to open each order's detail page for richer fields
                       (shipping name, seller, per-item tax). Default: --detail.
    --headless         Run Chrome headless. Not useful here — login is manual —
                       but kept for parity with the documented interface.

Requires: selenium >= 4.6 (see scripts/requirements.txt). Selenium 4.6+ ships
Selenium Manager, which auto-provisions a matching chromedriver.
"""

import argparse
import csv
import logging
import re
import sys
from datetime import date, datetime

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("amazon_scraper")

ORDERS_URL = "https://www.amazon.com/your-orders/orders"
LOGIN_WAIT_SECONDS = 120
PAGE_WAIT_SECONDS = 20

CSV_COLUMNS = [
    "Order Date",
    "Order ID",
    "Order Total",
    "Order Status",
    "Shipping Address Name",
    "Item Subtotal",
    "Item Subtotal Tax",
    "Item Total",
    "ASIN",
    "Product Name",
    "Quantity",
    "Payment Type",
    "Seller",
]

_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")
_ORDER_ID_RE = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Amazon order history to CSV.")
    parser.add_argument("--year", type=int, default=None, help="Filter to a calendar year.")
    parser.add_argument("--months", type=int, default=None, help="Filter to the last N months.")
    parser.add_argument("--output", default="amazon_orders.csv", help="Output CSV path.")
    parser.add_argument(
        "--detail", dest="detail", action="store_true", default=True,
        help="Visit each order's detail page (default).",
    )
    parser.add_argument(
        "--no-detail", dest="detail", action="store_false",
        help="Skip detail pages — faster but fewer fields.",
    )
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless.")
    args = parser.parse_args(argv)

    if args.year is not None and args.months is not None:
        parser.error("--year and --months are mutually exclusive.")
    if args.months is not None and args.months <= 0:
        parser.error("--months must be a positive integer.")
    if args.year is not None and not (2000 <= args.year <= date.today().year):
        parser.error(f"--year must be between 2000 and {date.today().year}.")
    return args


def _subtract_months(d: date, months: int) -> date:
    """d shifted back by `months`, clamping the day to the target month's length."""
    total = (d.year * 12 + (d.month - 1)) - months
    year, month = divmod(total, 12)
    month += 1
    # Clamp the day (e.g. Mar 31 minus 1 month → Feb 28/29).
    next_month_first = date(year + (month // 12), (month % 12) + 1, 1)
    last_day = (next_month_first - date.resolution).day
    return date(year, month, min(d.day, last_day))


def date_floor(args: argparse.Namespace) -> date | None:
    """Earliest order date to keep, or None for 'all time'."""
    if args.months is not None:
        return _subtract_months(date.today(), args.months)
    if args.year is not None:
        return date(args.year, 1, 1)
    return None


def date_ceiling(args: argparse.Namespace) -> date | None:
    if args.year is not None:
        return date(args.year, 12, 31)
    return None


# ---------------------------------------------------------------------------
# Driver / login
# ---------------------------------------------------------------------------

def build_driver(headless: bool) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise SystemExit(f"Could not start Chrome: {exc}")


def wait_for_login(driver: webdriver.Chrome) -> None:
    """Land on the orders page and block until the user has authenticated."""
    driver.get(ORDERS_URL)
    logger.info("Waiting up to %ss for manual Amazon login…", LOGIN_WAIT_SECONDS)
    try:
        WebDriverWait(driver, LOGIN_WAIT_SECONDS).until(
            lambda d: "your-orders" in d.current_url and _orders_present(d)
        )
    except TimeoutException:
        raise SystemExit("Timed out waiting for login / order history to load.")
    logger.info("Login detected — order history is visible.")


def _orders_present(driver: webdriver.Chrome) -> bool:
    return bool(driver.find_elements(By.CSS_SELECTOR, ".order-card, .js-order-card, .order"))


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _text(el, selector: str) -> str:
    try:
        return el.find_element(By.CSS_SELECTOR, selector).text.strip()
    except NoSuchElementException:
        return ""


def _parse_order_date(raw: str) -> str:
    """Amazon shows e.g. 'April 21, 2026' → return ISO 'YYYY-MM-DD'."""
    raw = (raw or "").strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _extract_order_id(card) -> str:
    # Usually rendered as "ORDER # 123-4567890-1234567" somewhere in the card.
    blob = card.text or ""
    m = _ORDER_ID_RE.search(blob)
    return m.group(1) if m else ""


def _extract_asin(item_el) -> str:
    try:
        href = item_el.find_element(By.CSS_SELECTOR, "a[href*='/dp/'], a[href*='/gp/product/']").get_attribute("href")
    except NoSuchElementException:
        return ""
    m = _ASIN_RE.search(href or "")
    return m.group(1) if m else ""


def scrape_card(card) -> dict | None:
    """Pull order-level fields and item rows out of one order card.

    Returns {"order": {...}, "items": [{...}]} or None if the card is unusable.
    """
    header_values = [v.text.strip() for v in card.find_elements(
        By.CSS_SELECTOR, ".order-header .value, .order-info .value, .a-column .value"
    )]

    order_id = _extract_order_id(card)
    if not order_id:
        return None

    # Date: first header value that parses as a date.
    order_date = ""
    for v in header_values:
        parsed = _parse_order_date(v)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parsed):
            order_date = parsed
            break

    # Total: first header value that looks like money.
    order_total = ""
    for v in header_values:
        if v.startswith("$"):
            order_total = v
            break

    status = _text(card, ".delivery-box .a-text-bold, .shipment-status, .a-row .a-color-success")

    items = []
    item_els = card.find_elements(
        By.CSS_SELECTOR, ".item-box, .yohtmlc-item, .a-fixed-left-grid"
    )
    for item_el in item_els:
        name = _text(item_el, ".product-image + .a-col-right a, a.a-link-normal")
        if not name:
            continue
        qty = ""
        m = re.search(r"\bQty:?\s*(\d+)", item_el.text)
        if m:
            qty = m.group(1)
        items.append({
            "Product Name": name,
            "ASIN": _extract_asin(item_el),
            "Quantity": qty or "1",
            "Item Total": "",
            "Item Subtotal": "",
            "Item Subtotal Tax": "",
            "Seller": "",
        })

    if not items:
        # Still emit a single bare row so the order is represented.
        items.append({
            "Product Name": "", "ASIN": "", "Quantity": "1",
            "Item Total": "", "Item Subtotal": "", "Item Subtotal Tax": "", "Seller": "",
        })

    return {
        "order": {
            "Order Date": order_date,
            "Order ID": order_id,
            "Order Total": order_total,
            "Order Status": status,
            "Shipping Address Name": "",
            "Payment Type": "",
        },
        "items": items,
    }


def enrich_from_detail(driver: webdriver.Chrome, order_id: str, record: dict) -> None:
    """Open the order's detail page and fill shipping name / seller / payment."""
    url = f"https://www.amazon.com/gp/your-account/order-details?orderID={order_id}"
    try:
        driver.get(url)
        WebDriverWait(driver, PAGE_WAIT_SECONDS).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except (TimeoutException, WebDriverException):
        logger.warning("Could not load detail page for %s", order_id)
        return

    body = driver.find_element(By.TAG_NAME, "body").text

    ship_name = _text(driver, ".displayAddressFullName, .a-color-base.displayAddressFullName")
    if ship_name:
        record["order"]["Shipping Address Name"] = ship_name

    pay = ""
    m = re.search(r"(Visa|Mastercard|Amex|American Express|Discover|ending in \d+)", body)
    if m:
        pay = m.group(1)
    record["order"]["Payment Type"] = pay

    seller_m = re.search(r"Sold by:?\s*([^\n]+)", body)
    if seller_m:
        seller = seller_m.group(1).strip()
        for item in record["items"]:
            if not item["Seller"]:
                item["Seller"] = seller


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def go_to_next_page(driver: webdriver.Chrome) -> bool:
    try:
        nxt = driver.find_element(By.CSS_SELECTOR, ".a-pagination .a-last:not(.a-disabled) a")
    except NoSuchElementException:
        return False
    try:
        nxt.click()
        WebDriverWait(driver, PAGE_WAIT_SECONDS).until(_orders_present)
        return True
    except (TimeoutException, WebDriverException):
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    floor = date_floor(args)
    ceiling = date_ceiling(args)

    driver = build_driver(args.headless)
    rows: list[dict] = []
    seen_orders: set[str] = set()
    try:
        wait_for_login(driver)

        page = 1
        while True:
            logger.info("Scraping order list page %d…", page)
            cards = driver.find_elements(By.CSS_SELECTOR, ".order-card, .js-order-card, .order")
            stop_paging = False

            for card in cards:
                record = scrape_card(card)
                if not record:
                    continue
                oid = record["order"]["Order ID"]
                if oid in seen_orders:
                    continue

                od_raw = record["order"]["Order Date"]
                try:
                    od = date.fromisoformat(od_raw) if od_raw else None
                except ValueError:
                    od = None

                if od is not None:
                    if ceiling is not None and od > ceiling:
                        continue
                    if floor is not None and od < floor:
                        # Orders are newest-first; once we pass the floor we're done.
                        stop_paging = True
                        continue

                seen_orders.add(oid)
                if args.detail:
                    enrich_from_detail(driver, oid, record)
                    driver.get(ORDERS_URL)  # return to the list after the detour

                for item in record["items"]:
                    rows.append({**record["order"], **item})

            if stop_paging:
                logger.info("Reached the date floor — stopping pagination.")
                break
            if not go_to_next_page(driver):
                logger.info("No further pages.")
                break
            page += 1

        write_csv(args.output, rows)
        logger.info("Wrote %d item rows from %d orders to %s",
                    len(rows), len(seen_orders), args.output)
        return 0
    finally:
        driver.quit()


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return run(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any scrape failure to the caller
        logger.exception("Scraper failed")
        print(f"Scraper error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
