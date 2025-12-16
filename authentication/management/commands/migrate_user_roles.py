"""
Django management command to migrate existing users from string roles to FK roles.

This command should be run AFTER the Role table is populated with seed data.
It converts users' legacy string 'role' field values to proper Role FK references.
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from authentication.models import Role, User


class Command(BaseCommand):
    help = 'Migrate existing users from string role field to Role FK'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        self.stdout.write(self.style.NOTICE('Starting user role migration...'))
        
        # First, ensure roles exist
        roles = {role.name: role for role in Role.objects.all()}
        if not roles:
            self.stdout.write(self.style.ERROR(
                'No roles found! Please run "python manage.py seed_roles" first.'
            ))
            return
        
        self.stdout.write(f'Found {len(roles)} roles: {", ".join(roles.keys())}')
        
        # Check if there's a legacy 'role' column in the database
        # This is needed because we're transitioning from CharField to ForeignKey
        has_legacy_role_column = self._check_legacy_role_column()
        
        if has_legacy_role_column:
            self.stdout.write(self.style.NOTICE('Found legacy role column, migrating users...'))
            self._migrate_from_legacy_column(roles, dry_run)
        else:
            # Just ensure all users have a valid role FK
            self.stdout.write(self.style.NOTICE('No legacy column, checking users with null roles...'))
            self._fix_null_roles(roles, dry_run)
        
        self.stdout.write(self.style.SUCCESS('Migration complete!'))

    def _check_legacy_role_column(self):
        """Check if the legacy 'role' CharField still exists in the database."""
        with connection.cursor() as cursor:
            # Get table columns
            if connection.vendor == 'oracle':
                cursor.execute("""
                    SELECT column_name FROM user_tab_columns 
                    WHERE table_name = 'AUTH_USER' AND column_name = 'ROLE'
                """)
            elif connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'auth_user' AND column_name = 'role'
                """)
            elif connection.vendor == 'mysql':
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'auth_user' AND column_name = 'role'
                """)
            else:  # SQLite and others
                cursor.execute("PRAGMA table_info(auth_user)")
                columns = cursor.fetchall()
                return any(col[1] == 'role' for col in columns)
            
            return cursor.fetchone() is not None

    @transaction.atomic
    def _migrate_from_legacy_column(self, roles, dry_run):
        """Migrate users from legacy string role column to FK."""
        # Read legacy role values using raw SQL
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, role FROM auth_user WHERE role IS NOT NULL
            """)
            users_to_migrate = cursor.fetchall()
        
        migrated = 0
        errors = 0
        
        for user_id, legacy_role in users_to_migrate:
            role = roles.get(legacy_role)
            if not role:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ User {user_id}: Unknown role "{legacy_role}", defaulting to "user"'
                ))
                role = roles.get('user')
            
            if not dry_run:
                try:
                    user = User.objects.get(pk=user_id)
                    user.user_role = role
                    user.save(update_fields=['user_role'])
                    migrated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ User {user_id}: {e}'))
                    errors += 1
            else:
                self.stdout.write(f'  Would migrate user {user_id}: "{legacy_role}" -> {role.name}')
                migrated += 1
        
        self.stdout.write(f'  Migrated: {migrated}, Errors: {errors}')

    @transaction.atomic
    def _fix_null_roles(self, roles, dry_run):
        """Fix users with null user_role FK."""
        users_without_role = User.objects.filter(user_role__isnull=True)
        count = users_without_role.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('  All users have valid roles!'))
            return
        
        self.stdout.write(f'  Found {count} users without role, setting to "user"')
        
        default_role = roles.get('user')
        if not default_role:
            self.stdout.write(self.style.ERROR('  ✗ Default "user" role not found!'))
            return
        
        if not dry_run:
            updated = users_without_role.update(user_role=default_role)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Updated {updated} users'))
        else:
            self.stdout.write(f'  Would update {count} users to role "user"')
