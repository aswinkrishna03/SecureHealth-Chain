"""
Verification Test for Authentication & Portal Access
Tests user lookup, password verification, and session creation.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from services.db_service import db_service, verify_password, hash_password

def run_tests():
    print("Testing SecureHealth Authentication Service...")
    credentials = [
        ("admin@securehealth.org", "admin", "admin"),
        ("doctor@securehealth.org", "doctor", "doctor"),
        ("patient@securehealth.org", "patient", "patient"),
    ]
    
    for email, pwd, expected_role in credentials:
        user = db_service.get_user_by_email(email)
        assert user is not None, f"User {email} not found in database!"
        assert verify_password(pwd, user["password_hash"]), f"Password mismatch for {email}!"
        assert user["role"] == expected_role, f"Role mismatch for {email}: expected {expected_role}, got {user['role']}"
        print(f" [PASS] {email} -> Role: {user['role']}, Name: {user['name']}")

    # Negative test
    wrong_check = verify_password("wrong_password", user["password_hash"])
    assert not wrong_check, "Negative password check failed!"
    print(" [PASS] Invalid password correctly rejected.")
    
    print("\nAll authentication checks passed successfully!")

if __name__ == "__main__":
    run_tests()
