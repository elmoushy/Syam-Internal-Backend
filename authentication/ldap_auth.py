import logging
import os
from django.conf import settings
from django.contrib.auth import get_user_model
from ldap3 import Server, Connection, ALL, NTLM
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)
User = get_user_model()

class LDAPAuthService:
    """
    Service to handle LDAP authentication and user synchronization.
    """
    
    def __init__(self):
        self.server_url = os.getenv('LDAP_SERVER_URL')
        self.domain = os.getenv('LDAP_DOMAIN')
        self.search_base = os.getenv('LDAP_SEARCH_BASE')
        
        if not self.server_url or not self.domain:
            logger.warning("LDAP configuration missing. Please check environment variables.")

    def authenticate(self, username, password):
        """
        Authenticate user against LDAP server.
        
        Args:
            username (str): Username (without domain)
            password (str): User password
            
        Returns:
            tuple: (user, tokens) if successful, (None, None) otherwise
        """
        if not self.server_url or not self.domain:
            logger.error("LDAP configuration missing")
            return None, None

        # Format username for NTLM bind (DOMAIN\username)
        user_dn = f"{self.domain}\\{username}"
        
        try:
            # Connect and bind
            server = Server(self.server_url, get_info=ALL)
            conn = Connection(
                server, 
                user=user_dn, 
                password=password, 
                authentication=NTLM, 
                auto_bind=True
            )
            
            logger.info(f"LDAP bind successful for user: {username}")
            
            # Fetch user details
            ldap_user_info = self._get_user_details(conn, username)
            conn.unbind()
            
            # Create or update Django user
            user = self._get_or_create_user(username, ldap_user_info)
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            tokens = {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }
            
            return user, tokens
            
        except Exception as e:
            logger.error(f"LDAP authentication failed for {username}: {str(e)}")
            return None, None

    def _get_user_details(self, conn, username):
        """
        Fetch user details from LDAP.
        """
        try:
            search_filter = f"(sAMAccountName={username})"
            attributes = ["givenName", "sn", "mail", "displayName", "memberOf"]
            
            conn.search(
                search_base=self.search_base or "DC=whso,DC=gov,DC=ae", # Fallback or config
                search_filter=search_filter,
                attributes=attributes
            )
            
            if conn.entries:
                entry = conn.entries[0]
                return {
                    'first_name': str(entry.givenName.value) if entry.givenName.value else '',
                    'last_name': str(entry.sn.value) if entry.sn.value else '',
                    'email': str(entry.mail.value) if entry.mail.value else f"{username}@{self.domain.lower()}.local",
                    'display_name': str(entry.displayName.value) if entry.displayName.value else username
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error fetching LDAP details for {username}: {str(e)}")
            return {}

    def _get_or_create_user(self, username, ldap_info):
        """
        Get existing user or create new one based on LDAP info.
        Handles role assignment (First user = super_admin).
        """
        # Clean username (just in case)
        clean_username = username.split('\\')[-1]
        
        try:
            # Check if user exists
            user = User.objects.filter(username__iexact=clean_username).first()
            
            if user:
                # Update existing user
                user.first_name = ldap_info.get('first_name', user.first_name)
                user.last_name = ldap_info.get('last_name', user.last_name)
                if ldap_info.get('email'):
                    user.email = ldap_info.get('email')
                
                # Ensure auth_type is ldap
                if user.auth_type != 'ldap':
                    user.auth_type = 'ldap'
                
                user.save()
                logger.info(f"Updated existing LDAP user: {clean_username}")
                
            else:
                # Create new user
                is_first_user = User.objects.count() == 0
                role = 'super_admin' if is_first_user else 'user'
                
                user = User.objects.create(
                    username=clean_username,
                    email=ldap_info.get('email', f"{clean_username}@{self.domain.lower()}.local"),
                    first_name=ldap_info.get('first_name', ''),
                    last_name=ldap_info.get('last_name', ''),
                    auth_type='ldap',
                    role=role,
                    is_active=True
                )
                
                # Set unusable password since we use LDAP
                user.set_unusable_password()
                user.save()
                
                logger.info(f"Created new LDAP user: {clean_username} with role {role}")
                
            return user
            
        except Exception as e:
            logger.error(f"Error creating/updating user {clean_username}: {str(e)}")
            raise e
