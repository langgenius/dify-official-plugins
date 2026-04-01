# ShopSavvy Plugin for Dify

**Author:** shopsavvy
**Version:** 0.0.1
**Type:** Tool

---

## Overview

The ShopSavvy Plugin connects [Dify](https://dify.ai/) with the [ShopSavvy Data API](https://shopsavvy.com/data) for product search, real-time price comparison across thousands of retailers, and price history tracking.

---

## Features

- Search products by keyword with relevance-ranked results
- Get current offers and prices from thousands of retailers for any product
- Retrieve historical price data over custom date ranges
- Identify products by barcode/UPC, Amazon ASIN, model number, URL, or product name
- Filter offers by specific retailer

---

## Configuration

### 1. Get a ShopSavvy API Key

Sign up at [shopsavvy.com/data](https://shopsavvy.com/data) and create an API key from your [dashboard](https://shopsavvy.com/data/api-keys).

### 2. Install the Plugin

Find ShopSavvy in the Dify Plugin Marketplace and install it.

### 3. Authorize

Navigate to `Tools > ShopSavvy > Authorize` and enter your API key.

---

## Available Tools

- **Search Products** — Search for products by keyword. Returns matching products with titles, brands, categories, barcodes, and images.
- **Get Offers** — Get current prices and availability for a product across all retailers, with optional filtering to a single retailer.
- **Price History** — Retrieve historical price and availability data over a specified date range.

Each tool's YAML file in `tools/` documents the required and optional parameters.

---

## Security & Privacy

- Your ShopSavvy API Key is used only for authenticating requests to the ShopSavvy Data API.
- No personal data is stored or shared by this plugin.
- See [PRIVACY.md](./PRIVACY.md) for full details.

---

## License

This plugin is provided as-is for integration with Dify and ShopSavvy.

---

_Last updated: April 1, 2026_
