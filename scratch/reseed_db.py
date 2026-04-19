import os
import sys
import logging

# Add project root to path
sys.path.append(os.getcwd())

from integrations.data_warehouse.sqlite_client import init_db, DB_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reseed():
    print(f"=== Database Reseed Strategy ===")
    print(f"Target DB: {DB_PATH}")
    
    # 1. Wipe existing DB
    if os.path.exists(DB_PATH):
        print(f"Removing existing database file...")
        os.remove(DB_PATH)
        # Also remove WAL files if they exist
        for suffix in ["-wal", "-shm"]:
            if os.path.exists(DB_PATH + suffix):
                os.remove(DB_PATH + suffix)
    
    # 2. Re-initialize and seed
    print(f"Initializing and seeding new rich data...")
    try:
        init_db(seed=True)
        print(f"✅ SUCCESS: Database re-seeded.")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reseed()
