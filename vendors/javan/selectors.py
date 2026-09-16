"""
Javan Electronic Vendor Selectors & Extraction Rules
Derived strictly from docs/VENDORS/JAVAN/SITE_MAP_GRAPH.json and evidence records EV-JAVAN-*.
"""

import re
from typing import Pattern


class JavanSelectors:
    """Catalog of all verified CSS, ID, and XPath selectors for Javan Electronic."""

    # Homepage & Global
    PAGE_HOME_BODY = "body"
    BASE_URL = "https://www.javanelec.com"

    # Search Selectors
    INPUT_SEARCH_PRIMARY = "input#searchAll"
    INPUT_SEARCH_FALLBACK = "input[name='searchAll']"
    RESULTS_GRID_CONTAINER = ".product-list, .products, .container, #filter_items_-1"
    RESULTS_PRODUCT_LINKS = "a[href*='/shop/product/']"
    RESULTS_CARD = ".product-item, .card-product, .product-box, a[href*='/shop/product/']"
    RESULTS_EMPTY_CONTAINER = ".alert, [class*='empty'], .no-product"
    ORIGINAL_BADGE_ORIGINAL = "span[data-prdtype='Original']"
    ORIGINAL_BADGE_COPY = "span[data-prdtype='Copy']"

    # Product Detail Page (PDP)
    PDP_CONTAINER = ".product-detail, .product-main, .container"
    PDP_TITLE = "h1.font-weight-bold, h1, .product-name"
    SPEC_TABLE_ROWS = "table tr"
    PRICE_TABLE_ROWS = "table tr"
    BTN_ADD_TO_CART = "button.btn-success-outline[type='submit'], button[type='submit']"
    FORM_ADD_TO_CART = "form[action*='shoppingcarts'], form.form-horizontal"

    # Shopping Cart
    CART_CONTAINER = ".cart-container, .shopping-cart, .container"
    CART_ITEMS_TABLE = "table.table, .cart-table"
    CART_ITEM_ROWS = "table tbody tr, .cart-table tbody tr"

    # Authentication
    LOGIN_FORM = "form[action*='/account/login'], form"
    LOGIN_USERNAME_ID = "UserName"
    LOGIN_USERNAME_CSS = "input#UserName, input[name='UserName']"
    LOGIN_PASSWORD_ID = "Password"
    LOGIN_PASSWORD_CSS = "input#Password, input[name='Password']"
    LOGIN_REMEMBER_ID = "RememberMe"
    LOGIN_SUBMIT_BTN = "input[type='submit'][value='ورود'], input.btn-info-outline, button[type='submit']"

    # State & Text Markers
    AUTH_LOGOUT_TEXT = "خروج"
    AUTH_PROFILE_TEXT = "کاربر گرامی خوش آمدید"
    EMPTY_CART_MARKER = "سبد خرید شما خالی است"
    ZERO_RESULTS_MARKER = "0 محصول"
    NOT_FOUND_TEXT = "صفحه مورد نظر شما یافت نشد"
    NOT_FOUND_TITLE = "Not Found"

    # URL Patterns & Regexes
    PDP_URL_PATTERN: Pattern = re.compile(
        r"^https?://(?:www\.)?javanelec\.com/shop/product/(?P<product_id>\d+)/(?P<manufacturer>[a-zA-Z0-9_.-]+)/(?P<slug>[a-zA-Z0-9_.-]+)(?:/.*)?$",
        re.IGNORECASE,
    )
    PDP_PATH_PATTERN: Pattern = re.compile(
        r"^/shop/product/(?P<product_id>\d+)/(?P<manufacturer>[a-zA-Z0-9_.-]+)/(?P<slug>[a-zA-Z0-9_.-]+)(?:/.*)?$",
        re.IGNORECASE,
    )
    SEARCH_URL_TEMPLATE = "https://www.javanelec.com/shop?searchfilter={query}#filter_items_-1"
    LOGIN_URL = "https://www.javanelec.com/account/login"
    CART_URL = "https://www.javanelec.com/shoppingcarts"
    ERROR_404_URL = "https://www.javanelec.com/home/notfound"
