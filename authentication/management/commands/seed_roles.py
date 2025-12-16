"""
Django management command to seed default roles and page permissions.

This command creates the default system roles (super_admin, admin, user)
and sets up the initial page permissions.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from authentication.models import Role, PagePermission


class Command(BaseCommand):
    help = 'Seed default roles and page permissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset all page permissions (keeps roles)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of roles (warning: may affect existing users)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting role and permission seeding...'))
        
        # System is now fully dynamic - no default roles
        # All roles are created by admins through the UI
        self.stdout.write(self.style.NOTICE('System is using dynamic roles - no default roles created.'))
        
        # Get existing roles for permission assignment
        roles = {role.name: role for role in Role.objects.all()}
        
        if not roles:
            self.stdout.write(self.style.WARNING('  ⚠ No roles found in database. Create roles through the UI first.'))
            return
        
        # Reset page permissions if requested
        if options['reset']:
            self.stdout.write(self.style.WARNING('Resetting all page permissions...'))
            PagePermission.objects.all().delete()
        
        # Permissions are now managed through the UI
        # No default page permissions are seeded
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Seeding complete!'))
        self.stdout.write(f'  Roles in database: {len(roles)}')
        
        # Show summary
        if roles:
            self.stdout.write('')
            self.stdout.write(self.style.NOTICE('Role Summary:'))
            for role_name, role in roles.items():
                pages = PagePermission.objects.filter(role=role).values_list('name', flat=True)
                page_list = ", ".join(pages) if pages else "(no pages assigned)"
                self.stdout.write(f'  {role_name}: {page_list}')
