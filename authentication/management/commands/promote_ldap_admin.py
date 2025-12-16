"""
Django management command to promote an LDAP user to super_admin role.

Usage:
    python manage.py promote_ldap_admin <username>

Example:
    python manage.py promote_ldap_admin ahmed
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Promote an LDAP user to super_admin role'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='The LDAP username to promote to super_admin'
        )

    def handle(self, *args, **options):
        username = options['username']
        
        # Try to find the user
        user = User.objects.filter(username__iexact=username).first()
        
        if not user:
            # User doesn't exist yet - create a placeholder that will be updated on first LDAP login
            self.stdout.write(
                self.style.WARNING(f'User "{username}" not found in database.')
            )
            self.stdout.write(
                self.style.NOTICE(
                    f'Creating placeholder user "{username}" with super_admin role.\n'
                    f'User details will be updated when they first login via LDAP.'
                )
            )
            
            user = User.objects.create(
                username=username,
                email=f'{username}@placeholder.local',
                auth_type='ldap',
                role='super_admin',
                is_active=True
            )
            user.set_unusable_password()
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created user "{username}" with super_admin role')
            )
        else:
            # User exists - update their role
            old_role = user.role
            user.role = 'super_admin'
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ User "{username}" promoted from "{old_role}" to "super_admin"'
                )
            )
