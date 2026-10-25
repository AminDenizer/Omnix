"""
Lion Electronic Vendor Selectors & Extraction Rules
Derived strictly from docs/VENDORS/LION/SITE_MAP_GRAPH.json (29 verified selectors).
"""

import re
from typing import Pattern


class LionSelectors:
    """Catalog of all verified CSS, ID, and XPath selectors for Lion Electronic."""

    # Homepage & Global
    PAGE_HOME_BODY = "body"
    FORM_SEARCH_BOX = "form.searchBox[action='/products']"

    # Search Selectors
    INPUT_SEARCH_PRIMARY = "input#w0.header-search-input.form-control[name='search']"
    INPUT_SEARCH_FALLBACK = "input[name='search']"
    RESULTS_GRID_CONTAINER = ".products-list, .product-grid, .container"
    RESULTS_PRODUCT_LINKS = "a[href^='/products/']"
    RESULTS_CARD = ".product-item, .card-product, .product-box"
    RESULTS_EMPTY_CONTAINER = ".empty-result, .no-products, .alert-info"

    # Product Detail Page (PDP)
    PDP_CONTAINER = ".product-detail, .product-main, .container"
    PDP_TITLE = "h1.font-weight-bold, h1, .product-title"
    SPEC_TABLE_ROWS = "table.table.table-bordered.table-striped tr, table tr"
    STOCK_AMOUNT_SPAN = "span.stock-amount"
    STOCK_CONTAINER = ".product-stock, .stock-status"
    INPUT_QUANTITY_CELL = "quantity-cell"
    INPUT_QUANTITY_CSS = "#quantity-cell, input.quantity-cell"
    BTN_BUY_PRIMARY = "button.btn-buy, button.add-btn"
    BTN_BUY_FALLBACK = ".btn-buy"
    BTN_INQUIRY_PRIMARY = "button.add-inquiry, button.save-btn"

    # Shopping Cart
    CART_CONTAINER = ".order-cart-view, .cart-items"
    CART_ITEMS_TABLE = "table.table, .cart-table"
    CART_ITEM_ROWS = "table.table tbody tr, .cart-table tbody tr"

    # Authentication
    LOGIN_FORM = "login-form"
    LOGIN_USERNAME_ID = "loginform-username"
    LOGIN_PASSWORD_ID = "loginform-password"
    LOGIN_SUBMIT_BTN = "button[name='signup-button'], #login-form button[type='submit'], button.blue-btn"
    AUTH_LOGOUT_TEXT = "خروج"
    AUTH_PROFILE_TEXT = "حساب کاربری"
    GUEST_LOGIN_LINK = "a[href*='/login']"

    # SweetAlert & Modals
    SWAL_CONTAINER = ".swal2-container"
    SWAL_MODAL = ".swal2-modal"
    SWAL_HTML_CONTAINER = ".swal2-html-container, .swal2-title, .alert-danger, .toast-message, .error-summary, .help-block-error"
    SWAL_CONFIRM_BTN = "button.swal2-confirm, button.swal2-styled"

    # URL Patterns & Regexes
    PDP_URL_PATTERN: Pattern = re.compile(
        r"^https?://(?:www\.)?lionelectronic\.ir/products/(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.-]+)$",
        re.IGNORECASE,
    )
    PDP_PATH_PATTERN: Pattern = re.compile(
        r"^/products/(?P<product_id>\d+)-(?P<slug>[a-zA-Z0-9_.-]+)$",
        re.IGNORECASE,
    )
    SEARCH_URL_TEMPLATE = "https://lionelectronic.ir/products?search={query}"
    LOGIN_URL = "https://lionelectronic.ir/login"
    CART_URL = "https://lionelectronic.ir/orders/cart"
    BASE_URL = "https://lionelectronic.ir"
