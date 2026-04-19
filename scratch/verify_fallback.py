
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath("."))

def mock_manual_fallback(result, query):
    lines = [f"## Results for: {query.capitalize()}", ""]
    
    # Identify the primary data list
    data_list = []
    headers = []
    
    if "vendors" in result and isinstance(result["vendors"], list) and result["vendors"]:
        data_list = result["vendors"]
        headers = ["Vendor ID", "Name", "Tier", "Country", "Status"]
    elif "ranked_vendors" in result and isinstance(result["ranked_vendors"], list) and result["ranked_vendors"]:
        data_list = result["ranked_vendors"]
        headers = ["Name", "Tier", "Fit Score", "Country"]
        
    if data_list:
        # Build Table
        header_row = "| " + " | ".join(headers) + " |"
        sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
        lines.append(header_row)
        lines.append(sep_row)
        
        for item in data_list[:20]:
            row = []
            for h in headers:
                key = h.lower().replace(" ", "_")
                if key == "status": key = "contract_status"
                val = item.get(key, item.get(h.lower(), "N/A"))
                row.append(str(val))
            lines.append("| " + " | ".join(row) + " |")
            
        lines.append("\n### Executive Analysis (Auto-Generated)")
        lines.append(f"Successfully retrieved {len(data_list)} record(s) matching your request. Displaying the top matches in tabular form.")
    else:
        lines.append("No matching records found.")

    return "\n".join(lines)

if __name__ == "__main__":
    mock_data = {
        "vendors": [
            {"vendor_id": "V-001", "name": "Acme", "tier": "Preferred", "country": "US", "contract_status": "Active"},
            {"vendor_id": "V-002", "name": "Globex", "tier": "Standard", "country": "UK", "contract_status": "Active"}
        ]
    }
    output = mock_manual_fallback(mock_data, "list all vendors")
    print(output)
