
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath("."))

from agents.vendor_management.schemas import VendorManagementInput
from pydantic import ValidationError

def test_parameter_survival():
    print("--- Testing Parameter Survival through Schema Validation ---")
    
    test_input = {
        "action": "search_vendors",
        "tier": "preferred",
        "contract_status": "active",
        "country": "US",
        "top_n": 10
    }
    
    try:
        # Simulate validation logic
        validated_obj = VendorManagementInput(**test_input)
        validated = validated_obj.model_dump()
        print("Validated Input:", validated)
        
        # Check if fields survived
        success = True
        for key in ["tier", "contract_status", "country"]:
            if key not in validated or validated[key] != test_input[key]:
                print(f"FAILED: Field '{key}' was lost or changed!")
                success = False
        
        if success:
            print("SUCCESS: All parameters survived validation.")
            
    except ValidationError as e:
        print("FAILED: Validation Error:", e)
    except Exception as e:
        print("FAILED: Unexpected Error:", e)

if __name__ == "__main__":
    test_parameter_survival()
