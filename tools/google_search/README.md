# Google Search

## Overview

The **Google Search tool** integrates with the official **Google Custom Search JSON API**, enabling real-time access to search results such as web pages, images, and news. It provides structured data that can be directly used in applications.

---

## Configuration

### 1. Enable Google Custom Search API

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).  
2. Create a project (or select an existing one).  
3. Enable the **Custom Search JSON API** service.  
4. Generate an **API Key** under **APIs & Services > Credentials**.

### 2. Create a Programmable Search Engine

1. Open [Programmable Search Engine](https://programmablesearchengine.google.com/).  
2. Create a new search engine:  
   - Choose to search the entire web or specify certain sites.  
3. Copy the **Search Engine ID (CX)**.

### 3. Install Google Search Tool in Dify

1. In the **Dify Console**, go to **Plugin Marketplace**.  
2. Search for **Google Search** and install it.

### 4. Configure in Dify

In **Dify Console > Tools > Google Search > Authorize**, enter:  

- **API Key**: The key from Google Cloud Console.  
- **Search Engine ID (CX)**: The ID from Programmable Search Engine.  

---

## Usage

The Google Search tool can be used in the following application types:

### Chatflow / Workflow Applications
Add a **Google Search node** to fetch real-time search results during flow execution.

### Agent Applications
Enable the **Google Search tool** in Agent applications.  
When users request online searches (e.g., *“Find the latest updates on AI research”*), the tool will automatically call the Google Search API to return results.

---

## Notes

- The **free quota** for Google Custom Search API is limited (typically **100 queries/day**).  
- To increase quota, upgrade your plan in **Google Cloud Console**.  
- Both **API Key** and **Search Engine ID (CX)** are required; missing either will cause request failures.