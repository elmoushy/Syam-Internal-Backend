# test_ldap_connection.py
"""
LDAP Connection Test Script
===========================
Run this script BEFORE deploying the LDAP login feature.
It will verify that the server can connect to Active Directory.

Usage:
    python test_ldap_connection.py

Make sure to update the configuration values below before running.
"""

from ldap3 import Server, Connection, ALL, NTLM
import sys

# ============================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================
LDAP_SERVER = 'ldap://your-ad-server.company.local'  # Or use IP: ldap://192.168.1.5
LDAP_DOMAIN = 'YOURDOMAIN'                           # NetBIOS Name (e.g. WHSO)
TEST_USERNAME = 'svc_ldap_user'                      # Just the username (no domain prefix)
TEST_PASSWORD = 'StrongPassword123'
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
    success = test_connection()
    sys.exit(0 if success else 1)
