# test_ldap_connection.py
"""
LDAP Connection Test Script
===========================
Run this script BEFORE deploying the LDAP login feature.
It will verify that the server can connect to Active Directory.

Usage:
    python test_ldap_connection.py

The script uses environment variables from .env file.
Make sure LDAP_SERVER_URL, LDAP_DOMAIN are set in your .env
"""

import os
import sys

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[!] python-dotenv not installed. Using hardcoded values or system env vars.")

from ldap3 import Server, Connection, ALL, NTLM

# ============================================
# CONFIGURATION - Uses .env or fallback values
# ============================================
LDAP_SERVER = os.getenv('LDAP_SERVER_URL', 'ldap://your-ad-server.company.local')
LDAP_DOMAIN = os.getenv('LDAP_DOMAIN', 'YOURDOMAIN')
LDAP_SEARCH_BASE = os.getenv('LDAP_SEARCH_BASE', 'DC=whso,DC=gov,DC=ae')

# Test credentials - UPDATE THESE or pass as arguments
TEST_USERNAME = sys.argv[1] if len(sys.argv) > 1 else 'test_user'
TEST_PASSWORD = sys.argv[2] if len(sys.argv) > 2 else 'test_password'
# ============================================


def test_connection():
    """
    Attempts to bind to the LDAP server using the provided credentials.
    Returns True on success, False on failure.
    """
    user_dn = f"{LDAP_DOMAIN}\\{TEST_USERNAME}"
    
    print("=" * 50)
    print("LDAP Connection Test")
    print("=" * 50)
    print(f"[*] Server: {LDAP_SERVER}")
    print(f"[*] Binding as: {user_dn}")
    print("-" * 50)

    try:
        # Create server object
        server = Server(LDAP_SERVER, get_info=ALL)
        
        # Attempt NTLM bind (standard for Active Directory)
        conn = Connection(
            server, 
            user=user_dn, 
            password=TEST_PASSWORD, 
            authentication=NTLM, 
            auto_bind=True
        )
        
        print("[+] SUCCESS! LDAP bind successful.")
        print(f"[+] Authenticated user: {conn.extend.standard.who_am_i()}")
        print("-" * 50)
        print("[*] Server Info:")
        print(f"    - Naming Context: {server.info.naming_contexts}")
        print("=" * 50)
        
        conn.unbind()
        return True
        
    except Exception as e:
        print(f"[-] FAILED! Error: {e}")
        print("-" * 50)
        print("[!] Troubleshooting Tips:")
        print("    1. Check if the server hostname/IP is correct")
        print("    2. Verify the username and password are correct")
        print("    3. Ensure port 389 (LDAP) or 636 (LDAPS) is open")
        print("    4. Try using IP address instead of hostname")
        print("    5. Check if the domain name (NetBIOS) is correct")
        print("=" * 50)
        return False


if __name__ == "__main__":
    print("\nStarting LDAP connection test...\n")
    print(f"[*] Using LDAP_SERVER_URL from env: {LDAP_SERVER}")
    print(f"[*] Using LDAP_DOMAIN from env: {LDAP_DOMAIN}")
    print(f"[*] Using LDAP_SEARCH_BASE from env: {LDAP_SEARCH_BASE}")
    
    if TEST_USERNAME == 'test_user':
        print("\n[!] WARNING: Using default test credentials.")
        print("[!] Usage: python test_ldap_connection.py <username> <password>")
        print("")
    
    success = test_connection()
    sys.exit(0 if success else 1)
