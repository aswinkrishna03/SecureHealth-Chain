"""
SecureHealth Chain - MySQL Connection & Schema Validator
Run this script to test and verify your MySQL database configuration:
    python backend/test_db.py
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.db_service import db_service

def main():
    print("=" * 70)
    print(" [*] SECUREHEALTH CHAIN: MYSQL DATABASE CONNECTION TEST")
    print("=" * 70)
    
    stat = db_service.get_status()
    print(f" Python Driver:       {stat['driver']}")
    print(f" Target Host:         {stat['host']}:{stat['port']}")
    print(f" Database Name:       {stat['database']}")
    print(f" Database Username:   {stat['user']}")
    print(f" Operation Mode:      {stat['mode']}")
    print(f" Connection Status:   {'CONNECTED' if stat['connected'] else 'NOT CONNECTED (OFFLINE)'}")
    print("-" * 70)

    if stat["connected"]:
        print("[SUCCESS] Successfully connected to MySQL server!")
        print(f" -> Tables verified and ready:")
        print(f"    - users:        {stat['total_users']} accounts")
        print(f"    - ehr_records:  {stat['total_records']} records")
        print(f"    - audit_logs:   {stat['total_audit_logs']} entries")
        print(f"    - fl_rounds:    {stat['total_fl_rounds']} rounds")
        print("\nAll database tables and relationships are active and healthy.")
    else:
        print("[NOTICE] MySQL server is currently not reachable.")
        print(f"Error Details: {stat['last_error']}")
        print("\nHOW TO CONNECT MYSQL:")
        print(" 1. If using XAMPP: Open XAMPP Control Panel and click 'Start' next to MySQL.")
        print(" 2. If using MySQL Workbench / Server: Start MySQL Windows Service (e.g. MySQL80).")
        print(" 3. If your MySQL root account has a password, edit the '.env' file in this folder:")
        print("      MYSQL_PASSWORD=your_mysql_password_here")
        print(" 4. Re-run this test: python backend/test_db.py")
        print("\nNote: The SecureHealth platform will run smoothly in resilient in-memory mode")
        print("until your MySQL server is started.")
    print("=" * 70)

if __name__ == "__main__":
    main()
