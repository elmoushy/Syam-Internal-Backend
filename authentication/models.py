"""
Custom User models for Azure AD authentication with Oracle compatibility.

This module defines a User model that includes hash fields for Oracle
database compatibility while maintaining encryption functionality.
Also includes Role and PagePermission models for dynamic RBAC.
"""

import hashlib
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .managers import OracleCompatibleUserManager


class Role(models.Model):
    """
    Dynamic Role model for role-based access control.
    
    This replaces the static ROLE_CHOICES with a database-driven approach.
    Each role can have multiple page permissions associated with it.
    """
    
    # Predefined role names (for reference, actual values stored in DB)
    SUPER_ADMIN = 'super_admin'
    ADMIN = 'admin'
    USER = 'user'
    
    name = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text='Unique role name (e.g., super_admin, admin, user)'
    )
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Human-readable display name for the role'
    )
    description = models.TextField(
        blank=True,
        help_text='Description of the role and its permissions'
    )
    is_system_role = models.BooleanField(
        default=False,
        help_text='Whether this is a system-defined role that cannot be deleted'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the role was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='When the role was last updated'
    )
    
    class Meta:
        db_table = 'auth_role'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['name']
    
    def __str__(self):
        return self.display_name or self.name
    
    @classmethod
    def get_default_role(cls):
        """Get the default 'user' role, creating it if necessary."""
        role, _ = cls.objects.get_or_create(
            name=cls.USER,
            defaults={
                'display_name': 'User',
                'description': 'Regular user with basic access',
                'is_system_role': True
            }
        )
        return role
    
    @classmethod
    def get_role_by_name(cls, name):
        """Get a role by name, returns None if not found."""
        try:
            return cls.objects.get(name=name)
        except cls.DoesNotExist:
            return None


class PagePermission(models.Model):
    """
    Page Permission model linking roles to accessible pages/features.
    
    This allows dynamic configuration of which roles can access which pages.
    The 'name' field corresponds to frontend route names (e.g., 'manage-surveys').
    """
    
    name = models.CharField(
        max_length=100,
        help_text='Page/feature identifier (matches frontend route name)'
    )
    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Human-readable display name for the page/feature'
    )
    description = models.TextField(
        blank=True,
        help_text='Description of the page/feature'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='page_permissions',
        help_text='Role that has access to this page'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the permission was created'
    )
    
    class Meta:
        db_table = 'auth_page_permission'
        verbose_name = 'Page Permission'
        verbose_name_plural = 'Page Permissions'
        ordering = ['name', 'role__name']
        # A role can have only one entry per page
        unique_together = ['name', 'role']
    
    def __str__(self):
        return f"{self.name} -> {self.role.name}"
    
    @classmethod
    def role_has_permission(cls, role, page_name):
        """
        Check if a role has permission to access a specific page.
        
        Args:
            role: Role instance or role name (str)
            page_name: Name of the page to check
            
        Returns:
            bool: True if the role has permission, False otherwise
        """
        if isinstance(role, str):
            return cls.objects.filter(
                role__name=role,
                name=page_name
            ).exists()
        return cls.objects.filter(
            role=role,
            name=page_name
        ).exists()
    
    @classmethod
    def get_pages_for_role(cls, role):
        """
        Get all pages a role has access to.
        
        Args:
            role: Role instance or role name (str)
            
        Returns:
            QuerySet of page names
        """
        if isinstance(role, str):
            return cls.objects.filter(role__name=role).values_list('name', flat=True)
        return cls.objects.filter(role=role).values_list('name', flat=True)
    
    @classmethod
    def get_roles_for_page(cls, page_name):
        """
        Get all roles that have access to a specific page.
        
        Args:
            page_name: Name of the page
            
        Returns:
            QuerySet of Role instances
        """
        role_ids = cls.objects.filter(name=page_name).values_list('role_id', flat=True)
        return Role.objects.filter(id__in=role_ids)


class User(AbstractBaseUser):
    """
    Custom User model for Azure AD authentication with Oracle compatibility.
    
    This model includes hash fields for Oracle database compatibility:
    - email_hash: SHA256 hash of email for filtering
    - username_hash: SHA256 hash of username for filtering
    
    Role system:
    - 'role' column: Direct access level (super_admin, admin, user) stored in AUTH_USER.
    - 'user_role' FK: Links to Role table for page-based permissions.
    
    When user_role is set to a custom role (e.g., News_admin), the 'role' column
    automatically updates to 'admin' to grant endpoint access, while page-level
    permissions are controlled by the Role's PagePermissions.
    """
    
    # Role choices for direct access level (stored in AUTH_USER.role column)
    ROLE_SUPER_ADMIN = 'super_admin'
    ROLE_ADMIN = 'admin'
    ROLE_USER = 'user'
    
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_SUPER_ADMIN, 'Super Administrator'),
    ]
    
    AUTH_TYPE_CHOICES = [
        ('regular', 'Regular Email/Password'),
        ('azure', 'Azure AD SSO'),
        ('ldap', 'LDAP Authentication'),
    ]
    
    # Core required fields
    username = models.CharField(
        max_length=255,
        unique=True,  # Keep unique for Django compatibility, but we'll handle Oracle separately
        help_text='Azure AD Object ID for Azure users, email for regular users'
    )
    email = models.EmailField(
        max_length=254,
        unique=True,  # Keep unique for Django compatibility, but we'll handle Oracle separately
        help_text='User email address'
    )
    
    # Hash fields for Oracle compatibility and filtering
    email_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA256 hash of email for Oracle filtering',
        db_index=True
    )
    username_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA256 hash of username for Oracle filtering',
        db_index=True
    )
    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPE_CHOICES,
        default='regular',
        help_text='Authentication type used for this user'
    )
    
    # Direct role column for endpoint access validation
    # Values: super_admin, admin, user (default: user)
    # This is automatically updated when user_role is assigned
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_USER,
        db_index=True,
        help_text='User access level for endpoint validation (super_admin, admin, user)'
    )
    
    # Foreign key to Role table for page-based permissions (e.g., News_admin)
    # When assigned, the 'role' column auto-updates to 'admin' for endpoint access
    user_role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        related_name='users',
        null=True,
        blank=True,
        db_column='user_role_id',
        help_text='Role for page-level permissions (FK to Role table)'
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this user account is active'
    )
    date_joined = models.DateTimeField(
        default=timezone.now,
        help_text='When the user account was created'
    )
    
    # Optional fields for better user experience
    first_name = models.CharField(
        max_length=150,
        blank=True,
        help_text='User first name from Azure AD'
    )
    last_name = models.CharField(
        max_length=150,
        blank=True,
        help_text='User last name from Azure AD'
    )
    last_login = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Last time user logged in'
    )
    
    # Real-time presence tracking (Phase 2)
    is_online = models.BooleanField(
        default=False,
        help_text='Whether user is currently online (WebSocket connected)'
    )
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time user was seen online'
    )
    
    objects = OracleCompatibleUserManager()
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    
    class Meta:
        db_table = 'auth_user'  # Use Django's default table name
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        # Keep these constraints for Django compatibility
        # Oracle-specific constraints are handled in migrations
    
    def clean(self):
        """Custom validation for Oracle compatibility using hash fields."""
        from .oracle_utils import is_oracle_db
        super().clean()
        
        # For Oracle, use hash-based uniqueness validation
        if is_oracle_db():
            from django.db import connection
            
            if self.email:
                email_hash = hashlib.sha256(self.email.encode('utf-8')).hexdigest()
                # Use N prefix for NVARCHAR2 comparison
                safe_hash = email_hash.replace("'", "''")
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT id FROM auth_user 
                        WHERE email_hash = N'{safe_hash}'
                        AND id != {self.pk or 0}
                        AND ROWNUM = 1
                        """
                    )
                    if cursor.fetchone():
                        from django.core.exceptions import ValidationError
                        raise ValidationError({'email': 'A user with this email already exists.'})
            
            if self.username:
                username_hash = hashlib.sha256(self.username.encode('utf-8')).hexdigest()
                # Use N prefix for NVARCHAR2 comparison
                safe_hash = username_hash.replace("'", "''")
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT id FROM auth_user 
                        WHERE username_hash = N'{safe_hash}'
                        AND id != {self.pk or 0}
                        AND ROWNUM = 1
                        """
                    )
                    if cursor.fetchone():
                        from django.core.exceptions import ValidationError
                        raise ValidationError({'username': 'A user with this username already exists.'})
    
    def save(self, *args, **kwargs):
        """Override save to generate hash fields, validate uniqueness, and sync role."""
        # Generate hashes before saving
        if self.email:
            self.email_hash = hashlib.sha256(self.email.encode('utf-8')).hexdigest()
        if self.username:
            self.username_hash = hashlib.sha256(self.username.encode('utf-8')).hexdigest()
        
        # Auto-update role column based on user_role if user_role is set
        # BUT only if we're not explicitly updating the role field
        # This allows manual role updates while still auto-syncing when assigning user_role
        update_fields = kwargs.get('update_fields')
        skip_role_sync = kwargs.pop('skip_role_sync', False)
        
        # Only auto-sync role if:
        # 1. user_role is set AND
        # 2. We're not explicitly updating just the 'role' field AND
        # 3. skip_role_sync is not True
        if self.user_role_id and not skip_role_sync:
            if update_fields is None or 'role' not in update_fields:
                self.set_role_from_user_role()
        
        # Call clean to validate (including Oracle-specific validation)
        # Skip full_clean if we're only updating specific fields (like last_login)
        if not update_fields or len(update_fields) > 1:
            try:
                self.clean()
            except (ValidationError, TypeError) as e:
                # Handle validation errors gracefully
                # TypeError can occur from isinstance() issues in Django's validation
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Validation warning during save: {e}")
                # Only re-raise ValidationError, not TypeError
                if isinstance(e, ValidationError):
                    raise
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.email or self.username} ({self.role})"
    
    def set_role_from_user_role(self):
        """
        Automatically determine the 'role' column value based on user_role.
        
        Logic:
        - If user_role is 'super_admin' Role -> role = 'super_admin'
        - If user_role is 'admin' Role -> role = 'admin'  
        - If user_role is 'user' Role -> role = 'user'
        - If user_role is a custom Role (e.g., News_admin) -> role = 'admin'
        - If user_role is None -> keep current role or default to 'user'
        """
        if self.user_role:
            role_name = self.user_role.name
            if role_name == Role.SUPER_ADMIN:
                self.role = self.ROLE_SUPER_ADMIN
            elif role_name == Role.ADMIN:
                self.role = self.ROLE_ADMIN
            elif role_name == Role.USER:
                self.role = self.ROLE_USER
            else:
                # Custom role (e.g., News_admin) -> grant admin access level
                self.role = self.ROLE_ADMIN
    
    def assign_user_role(self, role_or_name, auto_update_role=True):
        """
        Assign a user_role and optionally auto-update the role column.
        
        Args:
            role_or_name: Role instance or role name string
            auto_update_role: If True, automatically update the role column
        """
        if isinstance(role_or_name, Role):
            self.user_role = role_or_name
        elif isinstance(role_or_name, str):
            role_obj = Role.get_role_by_name(role_or_name)
            if role_obj:
                self.user_role = role_obj
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Role '{role_or_name}' not found")
                return
        
        if auto_update_role:
            self.set_role_from_user_role()
    
    def get_role_display(self):
        """Return human-readable role name based on role column."""
        role_display_map = {
            self.ROLE_SUPER_ADMIN: 'Super Administrator',
            self.ROLE_ADMIN: 'Administrator',
            self.ROLE_USER: 'User',
        }
        return role_display_map.get(self.role, 'User')
    
    def get_user_role_display(self):
        """Return human-readable user_role name (from Role table)."""
        if self.user_role:
            return self.user_role.display_name or self.user_role.name.replace('_', ' ').title()
        return None
    
    @property
    def full_name(self):
        """Return the user's full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email or self.username
    
    @property
    def is_staff(self):
        """Return True if user is admin or super_admin (for Django admin access)."""
        return self.role in ['admin', 'super_admin']
    
    @property
    def is_superuser(self):
        """Return True if user is super_admin (for Django admin access)."""
        return self.role == 'super_admin'
    
    def has_perm(self, perm, obj=None):
        """
        Check if user has a specific permission.
        
        Since we're not using Django's permission system,
        this is based on user role.
        """
        if self.role == 'super_admin':
            return True
        elif self.role == 'admin':
            # Admins have permissions within their groups
            return True
        # Add custom permission logic based on roles if needed
        return False
    
    def has_module_perms(self, app_label):
        """
        Check if user has permissions to view the app.
        
        Super admins and admins have access to modules.
        """
        return self.role in ['admin', 'super_admin']
    
    def has_page_permission(self, page_name):
        """
        Check if user has permission to access a specific page.
        
        Super admins have access to all pages.
        For other roles, checks the PagePermission table.
        
        Args:
            page_name: Name of the page to check (e.g., 'manage-surveys')
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        if self.role == 'super_admin':
            return True
        if not self.user_role:
            return False
        return PagePermission.role_has_permission(self.user_role, page_name)
    
    def get_allowed_pages(self):
        """
        Get list of all pages this user has permission to access.
        
        Returns:
            list: List of unique page names
        """
        if self.role == 'super_admin':
            # Super admin has access to all pages - get unique names
            return list(set(PagePermission.objects.values_list('name', flat=True)))
        if not self.user_role:
            return []
        return list(set(PagePermission.get_pages_for_role(self.user_role)))


class Group(models.Model):
    """
    Group model for organizing users.
    
    Each group can contain multiple users and must have at least one admin.
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='Unique name of the group'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description of the group'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the group was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='When the group was last updated'
    )
    
    class Meta:
        verbose_name = 'Group'
        verbose_name_plural = 'Groups'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def admin_count(self):
        """Return the number of admins in this group."""
        return self.user_groups.filter(is_group_admin=True).count()
    
    @property
    def user_count(self):
        """Return the total number of users in this group."""
        return self.user_groups.count()
    
    def get_admins(self):
        """Return all admin users in this group."""
        return User.objects.filter(
            user_groups__group=self,
            user_groups__is_group_admin=True
        )
    
    def get_members(self):
        """Return all users in this group."""
        return User.objects.filter(user_groups__group=self)


class UserGroup(models.Model):
    """
    Through model for User-Group many-to-many relationship.
    
    This model tracks which users belong to which groups and
    whether they are administrators of that group.
    """
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_groups',
        help_text='User in the group'
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='user_groups',
        help_text='Group the user belongs to'
    )
    is_group_admin = models.BooleanField(
        default=False,
        help_text='Whether the user is an admin of this group'
    )
    joined_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the user joined the group'
    )
    
    class Meta:
        unique_together = ['user', 'group']
        verbose_name = 'User Group Membership'
        verbose_name_plural = 'User Group Memberships'
        ordering = ['group__name', 'user__email']
    
    def __str__(self):
        admin_status = " (Admin)" if self.is_group_admin else ""
        return f"{self.user.email} - {self.group.name}{admin_status}"
    
    def save(self, *args, **kwargs):
        """
        Override save to handle role assignment logic.
        """
        # If user is not super_admin and being added to a group, make them admin
        if self.user.role != 'super_admin' and self.user.role != 'admin':
            self.user.role = 'admin'
            self.user.save()
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to handle role downgrade logic.
        """
        user = self.user
        super().delete(*args, **kwargs)
        
        # Check if user is still in any groups
        if user.role != 'super_admin' and not user.user_groups.exists():
            user.role = 'user'
            user.save()


# Add groups property to User model
User.add_to_class('groups', models.ManyToManyField(
    Group,
    through=UserGroup,
    related_name='users',
    blank=True,
    help_text='Groups this user belongs to'
))
