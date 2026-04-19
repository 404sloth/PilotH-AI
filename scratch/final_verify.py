import os
import sqlite3
import sys
from config.settings import Settings

# Add project root to path
sys.path.append(os.getcwd())

def verify():
    print("=== Final Verification ===")
    
    # 1. Check LangSmith Env Vars
    print("\nChecking LangSmith configuration...")
    settings = Settings() # This triggers model_post_init which exports to os.environ
    keys = ["LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"]
    for k in keys:
        val = os.environ.get(k, "MISSING")
        masked = val[:5] + "..." if len(val) > 10 else val
        print(f"{k}: {masked}")
    
    # 2. Check Database counts
    print("\nChecking Database counts...")
    db_path = settings.sqlite_db_path
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    queries = {
        "Vendors": "SELECT COUNT(*) FROM vendors",
        "Persons": "SELECT COUNT(*) FROM persons",
        "Communications": "SELECT COUNT(*) FROM communications",
        "Contracts": "SELECT COUNT(*) FROM contracts",
        "Meetings": "SELECT COUNT(*) FROM meetings"
    }
    
    for name, q in queries.items():
        cur.execute(q)
        count = cur.fetchone()[0]
        print(f"{name}: {count}")
    
    conn.close()

if __name__ == "__main__":
    verify()
