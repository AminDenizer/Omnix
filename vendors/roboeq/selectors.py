"""
RoboEq Electronic Vendor Selectors & Extraction Rules
Derived strictly from docs/VENDORS/ROBOEQ/SITE_MAP_GRAPH.json and evidence records EV-ROBOEQ-*.
"""

import re
from typing import Pattern


class RoboEqSelectors:
    """Catalog of all verified CSS, ID, and XPath selectors for RoboEq Electronic."""

    # Homepage & Global
    PAGE_HOME_BODY = "body"
    BASE_URL = "https://roboeq.ir"

    # Search Selectors
    INPUT_SEARCH_PRIMARY = "input.req-field, input[placeholder*='نام محصول']"
    INPUT_SEARCH_FALLBACK = "input[placeholder*='جستجو']"
    RESULTS_GRID_CONTAINER = ".search-results, .products, .container"
    RESULTS_PRODUCT_LINKS = "a[href*='/products/detail/']"
    RESULTS_CARD = "a[href*='/products/detail/']"
    RESULTS_EMPTY_CONTAINER = ".no-result, .alert, body"
    ZERO_RESULTS_MARKER = "بدون نتیجه"

    # Product Detail Page (PDP)
    PDP_CONTAINER = ".product-detail, .product-main, body"
    PDP_TITLE = "h1, .product-title"
    PRICING_TABLE_ROWS = "table tr"
    SPEC_TABLE_ROWS = "table tr"
    BTN_ADD_TO_CART = "button:contains('افزودن به سبد'), button.waves-effect, button[type='submit']"
    QTY_INC_BTN = "button.inc-qty"
    QTY_DEC_BTN = "button.dec-qty"

    # Shopping Cart
    CART_CONTAINER = ".cart-container, table.cart, body"
    CART_URL = "https://roboeq.ir/cart/"

    # Authentication
    LOGIN_URL = "https://auth.roboeq.ir/cas/login?service=https%3A%2F%2Froboeq.ir%2Flogin%2F"
    LOGIN_USERNAME_ID = "username"
    LOGIN_USERNAME_CSS = "input#username, input[name='username']"
    LOGIN_SUBMIT_BTN = "input[type='submit'], button[type='submit'], button.btn-login"

    # State & Text Markers
    AUTH_LOGOUT_TEXT = "خروج"
    AUTH_PROFILE_TEXT = "حساب کاربری"
    ERROR_404_URL = "https://roboeq.ir/error/404/"
    ERROR_404_TITLE = "خطا | روبوایکیو"

    # URL Patterns & Regexes
    PDP_URL_PATTERN: Pattern = re.compile(
        r"^https?://(?:www\.)?roboeq\.ir/products/detail/(?P<product_id>\d+)/(?P<slug>[^/]+)/?$",
        re.IGNORECASE,
    )
    PDP_PATH_PATTERN: Pattern = re.compile(
        r"^/products/detail/(?P<product_id>\d+)/(?P<slug>[^/]+)/?$",
        re.IGNORECASE,
    )
    SEARCH_URL_TEMPLATE = "https://roboeq.ir/search/?q={query}"
