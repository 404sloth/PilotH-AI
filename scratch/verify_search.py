
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath("."))

from integrations.data_warehouse.vendor_db import search_vendors

def test_search():
    print("--- 1. Testing Fuzzy Country (United States -> US) ---")
    res = search_vendors(country="United States", limit=2)
    for r in res:
        print(f"Found: {r['name']} ({r['country']})")

    print("\n--- 2. Testing Tier Filter (preferred) ---")
    res = search_vendors(tier="preferred", limit=2)
    for r in res:
        print(f"Found: {r['name']} (Tier: {r['tier']})")

    print("\n--- 3. Testing Status Filter (active) ---")
    res = search_vendors(contract_status="active", limit=2)
    for r in res:
        print(f"Found: {r['name']} (Status: {r['contract_status']})")

    print("\n--- 4. Testing Multi-filter (US + standard) ---")
    res = search_vendors(country="US", tier="standard", limit=2)
    for r in res:
        print(f"Found: {r['name']} ({r['country']}, {r['tier']})")

if __name__ == "__main__":
    test_search()
