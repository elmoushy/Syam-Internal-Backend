"""
Django management command to remove default system roles (super_admin, admin, user).

This command removes the hardcoded default roles from the database as the system
is now fully dynamic with custom roles created through the UI.

WARNING: This will affect users who have these roles assigned!
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from authentication.models import Role, User, PagePermission


class Command(BaseCommand):
    help = 'Remove default system roles (super_admin, admin, user) from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion of default roles',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without interactive confirmation',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        default_role_names = ['super_admin', 'admin', 'user']
        
        self.stdout.write(self.style.WARNING('='*60))
        self.stdout.write(self.style.WARNING('REMOVE DEFAULT ROLES'))
        self.stdout.write(self.style.WARNING('='*60))
        self.stdout.write('')
        
        # Check if roles exist
        roles_to_delete = Role.objects.filter(name__in=default_role_names)
        
        if not roles_to_delete.exists():
            self.stdout.write(self.style.SUCCESS('No default roles found in database.'))
            self.stdout.write(self.style.SUCCESS('System is already using dynamic roles only.'))
            return
        
        self.stdout.write(self.style.NOTICE(f'Found {roles_to_delete.count()} default role(s) to remove:'))
        
        # Show impact analysis
        for role in roles_to_delete:
            self.stdout.write('')
            self.stdout.write(f'Role: {role.name} ({role.display_name})')
            
            # Count users with this role in user_role FK
            users_with_role = User.objects.filter(user_role=role).count()
            self.stdout.write(f'  - Users with this role (FK): {users_with_role}')
            
            # Count users with this role in 'role' column
            users_with_access_level = User.objects.filter(role=role.name).count()
            self.stdout.write(f'  - Users with this access level: {users_with_access_level}')
            
            # Count page permissions
            page_permissions = PagePermission.objects.filter(role=role).count()
            self.stdout.write(f'  - Page permissions: {page_permissions}')
        
        self.stdout.write('')
        
        # Dry run check
        if options['dry_run']:
            self.stdout.write(self.style.NOTICE('DRY RUN MODE - No changes made'))
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('To actually delete, run with --confirm flag'))
            return
        
        # Confirmation check
        if not options['confirm'] and not options['force']:
            self.stdout.write(self.style.ERROR('ERROR: This action requires confirmation'))
            self.stdout.write('')
            self.stdout.write('Run with --confirm flag to proceed:')
            self.stdout.write('  python manage.py remove_default_roles --confirm')
            self.stdout.write('')
            self.stdout.write('Or run with --dry-run to see what would be deleted:')
            self.stdout.write('  python manage.py remove_default_roles --dry-run')
            return
        
        # Final confirmation
        if not options['force']:
            self.stdout.write(self.style.WARNING(''))
            self.stdout.write(self.style.WARNING('WARNING: This will:'))
            self.stdout.write(self.style.WARNING('  1. Delete the roles: super_admin, admin, user'))
            self.stdout.write(self.style.WARNING('  2. Set user_role to NULL for affected users'))
            self.stdout.write(self.style.WARNING('  3. Keep the "role" column values (super_admin/admin/user) for access control'))
            self.stdout.write(self.style.WARNING('  4. Delete associated page permissions'))
            self.stdout.write(self.style.WARNING(''))
            
            confirm = input('Type "DELETE" to confirm: ')
            
            if confirm != 'DELETE':
                self.stdout.write(self.style.ERROR('Deletion cancelled.'))
                return
        
        # Perform deletion
        with transaction.atomic():
            self.stdout.write('')
            self.stdout.write(self.style.NOTICE('Deleting default roles...'))
            
            # First, nullify user_role FK references
            for role in roles_to_delete:
                users_updated = User.objects.filter(user_role=role).update(user_role=None)
                if users_updated > 0:
                    self.stdout.write(f'  ✓ Cleared user_role FK for {users_updated} user(s) with role "{role.name}"')
                
                # Delete page permissions
                permissions_deleted = PagePermission.objects.filter(role=role).delete()[0]
                if permissions_deleted > 0:
                    self.stdout.write(f'  ✓ Deleted {permissions_deleted} page permission(s) for role "{role.name}"')
            
            # Now delete the roles
            deleted_count = roles_to_delete.delete()[0]
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'✓ Successfully deleted {deleted_count} default role(s)'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('ROLES REMOVED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Next steps:'))
        self.stdout.write('  1. Create custom roles through the UI')
        self.stdout.write('  2. Assign page permissions to roles')
        self.stdout.write('  3. Assign users to appropriate roles')
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Note: User access levels (role column) are preserved for API access control'))
