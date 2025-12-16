"""
Tests for Audit Log functionality.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from surveys.models import Survey
from newsletters.models import Newsletter
from Audit.models import AuditLog
from Audit.signals import set_current_user

User = get_user_model()


class AuditLogTestCase(TestCase):
    """Test cases for audit logging."""
    
    def setUp(self):
        """Set up test user and context."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        set_current_user(self.user)
    
    def tearDown(self):
        """Clean up user context."""
        set_current_user(None)
    
    def test_survey_create_logged(self):
        """Test that survey creation is logged."""
        survey = Survey.objects.create(
            title='Test Survey',
            creator=self.user,
            visibility='PRIVATE'
        )
        
        log = AuditLog.objects.filter(action=AuditLog.SURVEY_CREATE).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user)
        self.assertIn('Test Survey', log.description)
        self.assertEqual(log.object_id, str(survey.pk))
    
    def test_survey_activate_logged(self):
        """Test that survey activation is logged."""
        survey = Survey.objects.create(
            title='Test Survey',
            creator=self.user,
            is_active=False
        )
        
        # Clear previous logs
        AuditLog.objects.all().delete()
        
        # Activate survey
        survey.is_active = True
        survey.save()
        
        log = AuditLog.objects.filter(action=AuditLog.SURVEY_ACTIVATE).first()
        self.assertIsNotNone(log)
        self.assertIn('activated', log.description.lower())
        self.assertTrue(log.changes['is_active']['new'])
    
    def test_survey_deactivate_logged(self):
        """Test that survey deactivation is logged."""
        survey = Survey.objects.create(
            title='Test Survey',
            creator=self.user,
            is_active=True
        )
        
        # Clear previous logs
        AuditLog.objects.all().delete()
        
        # Deactivate survey
        survey.is_active = False
        survey.save()
        
        log = AuditLog.objects.filter(action=AuditLog.SURVEY_DEACTIVATE).first()
        self.assertIsNotNone(log)
        self.assertIn('deactivated', log.description.lower())
        self.assertFalse(log.changes['is_active']['new'])
    
    def test_newsletter_create_logged(self):
        """Test that newsletter creation is logged."""
        newsletter = Newsletter.objects.create(
            title='Test Newsletter',
            details='Test content',
            news_type='NORMAL',
            author=self.user
        )
        
        log = AuditLog.objects.filter(action=AuditLog.NEWSLETTER_CREATE).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user)
        self.assertIn('Test Newsletter', log.description)
    
    def test_role_change_logged(self):
        """Test that role changes are logged."""
        target_user = User.objects.create_user(
            username='targetuser',
            email='target@example.com',
            password='testpass123',
            role='user'
        )
        
        # Clear previous logs
        AuditLog.objects.all().delete()
        
        # Change role
        target_user.role = 'admin'
        target_user.save()
        
        log = AuditLog.objects.filter(action=AuditLog.ROLE_CHANGE).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['role']['old'], 'user')
        self.assertEqual(log.changes['role']['new'], 'admin')
