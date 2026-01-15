# activities/tests.py
"""
Tests for Activities system.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import (
    ActivityColumnDefinition,
    ActivityColumnValidation,
    ActivityTemplate,
    ActivityTemplateColumn,
    ActivitySheet,
    ActivitySheetRow,
)


User = get_user_model()


class ActivityColumnDefinitionTests(TestCase):
    """Tests for ActivityColumnDefinition model"""
    
    def test_create_column_definition(self):
        """Test creating a basic column definition"""
        column = ActivityColumnDefinition.objects.create(
            key='test_column',
            label='Test Column',
            data_type='text',
            default_width=150
        )
        self.assertEqual(column.key, 'test_column')
        self.assertEqual(column.label, 'Test Column')
        self.assertFalse(column.is_system)
        self.assertTrue(column.is_active)
    
    def test_system_column_cannot_delete(self):
        """Test that system columns return False for can_delete"""
        column = ActivityColumnDefinition.objects.create(
            key='system_col',
            label='System Column',
            is_system=True
        )
        self.assertFalse(column.can_delete())
    
    def test_column_with_select_options(self):
        """Test column with dropdown options"""
        column = ActivityColumnDefinition.objects.create(
            key='priority',
            label='Priority',
            data_type='select',
            options=['Low', 'Medium', 'High']
        )
        self.assertEqual(column.options, ['Low', 'Medium', 'High'])


class ActivityColumnValidationTests(TestCase):
    """Tests for ActivityColumnValidation model"""
    
    def setUp(self):
        self.column = ActivityColumnDefinition.objects.create(
            key='email_field',
            label='Email',
            data_type='text'
        )
    
    def test_create_validation_rule(self):
        """Test creating a validation rule"""
        validation = ActivityColumnValidation.objects.create(
            column=self.column,
            rule_type='regex',
            rule_value=r'^[\w\.-]+@[\w\.-]+\.\w+$',
            error_message='Invalid email format'
        )
        self.assertEqual(validation.rule_type, 'regex')
        self.assertTrue(validation.is_active)
    
    def test_required_validation(self):
        """Test required field validation"""
        validation = ActivityColumnValidation.objects.create(
            column=self.column,
            rule_type='required',
            rule_value='',
            error_message='This field is required'
        )
        self.assertEqual(validation.rule_type, 'required')


class ActivityTemplateTests(TestCase):
    """Tests for ActivityTemplate model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.column = ActivityColumnDefinition.objects.create(
            key='name',
            label='Name',
            data_type='text'
        )
    
    def test_create_template(self):
        """Test creating a template"""
        template = ActivityTemplate.objects.create(
            name='Test Template',
            description='A test template',
            owner=self.user,
            status='draft'
        )
        self.assertEqual(template.status, 'draft')
        self.assertFalse(template.is_deleted)
    
    def test_publish_template_without_columns(self):
        """Test that publishing without columns raises error"""
        template = ActivityTemplate.objects.create(
            name='Empty Template',
            owner=self.user
        )
        with self.assertRaises(ValueError):
            template.publish()
    
    def test_publish_template_with_columns(self):
        """Test publishing template with columns"""
        template = ActivityTemplate.objects.create(
            name='Valid Template',
            owner=self.user
        )
        ActivityTemplateColumn.objects.create(
            template=template,
            column_definition=self.column,
            order=0
        )
        template.publish()
        self.assertEqual(template.status, 'published')
        self.assertIsNotNone(template.published_at)
    
    def test_archive_template(self):
        """Test archiving a template"""
        template = ActivityTemplate.objects.create(
            name='To Archive',
            owner=self.user
        )
        template.archive()
        self.assertEqual(template.status, 'archived')
        self.assertTrue(template.is_deleted)
    
    def test_can_delete_without_sheets(self):
        """Test can_delete returns True when no sheets exist"""
        template = ActivityTemplate.objects.create(
            name='No Sheets',
            owner=self.user
        )
        self.assertTrue(template.can_delete())
    
    def test_can_delete_with_sheets(self):
        """Test can_delete returns False when sheets exist"""
        template = ActivityTemplate.objects.create(
            name='Has Sheets',
            owner=self.user,
            status='published'
        )
        ActivitySheet.objects.create(
            name='Test Sheet',
            template=template,
            owner=self.user
        )
        self.assertFalse(template.can_delete())


# ============================================================================
# API Tests
# ============================================================================

from rest_framework.test import APITestCase
from rest_framework import status as http_status


class ColumnDefinitionAPITests(APITestCase):
    """API tests for column definitions"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )
        self.regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='userpass123'
        )
    
    def test_list_columns_authenticated(self):
        """Test listing columns requires authentication"""
        response = self.client.get('/api/activities/columns/')
        self.assertEqual(response.status_code, http_status.HTTP_401_UNAUTHORIZED)
        
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/activities/columns/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
    
    def test_create_column_admin_only(self):
        """Test creating columns requires admin"""
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post('/api/activities/columns/', {
            'key': 'test_col',
            'label': 'Test Column',
            'data_type': 'text'
        })
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post('/api/activities/columns/', {
            'key': 'test_col',
            'label': 'Test Column',
            'data_type': 'text'
        })
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
    
    def test_cannot_delete_system_column(self):
        """Test that system columns cannot be deleted"""
        system_col = ActivityColumnDefinition.objects.filter(is_system=True).first()
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(f'/api/activities/columns/{system_col.id}/')
        # Permission denies delete on system columns (403 or 400 both acceptable)
        self.assertIn(response.status_code, [http_status.HTTP_400_BAD_REQUEST, http_status.HTTP_403_FORBIDDEN])


class TemplateAPITests(APITestCase):
    """API tests for templates"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='templateuser',
            email='template@example.com',
            password='pass123'
        )
        self.column = ActivityColumnDefinition.objects.filter(is_active=True).first()
    
    def test_create_template(self):
        """Test creating a template"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/activities/templates/', {
            'name': 'My Template',
            'description': 'Test description'
        })
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'My Template')
        self.assertEqual(response.data['status'], 'draft')
    
    def test_publish_template_with_columns(self):
        """Test publishing a template"""
        self.client.force_authenticate(user=self.user)
        
        # Create template with columns (use format='json')
        response = self.client.post('/api/activities/templates/', {
            'name': 'Publish Test',
            'columns': [{'column_definition_id': self.column.id, 'order': 0}]
        }, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        template_id = response.data['id']
        
        # Verify columns were added
        self.assertEqual(len(response.data['template_columns']), 1)
        
        # Publish it
        response = self.client.post(f'/api/activities/templates/{template_id}/publish/')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'published')


class SheetAPITests(APITestCase):
    """API tests for sheets"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='sheetuser',
            email='sheet@example.com',
            password='pass123'
        )
        self.column = ActivityColumnDefinition.objects.filter(is_active=True).first()
        
        # Create and publish a template
        self.template = ActivityTemplate.objects.create(
            name='Sheet Template',
            owner=self.user
        )
        ActivityTemplateColumn.objects.create(
            template=self.template,
            column_definition=self.column,
            order=0
        )
        self.template.publish()
    
    def test_create_sheet_from_template(self):
        """Test creating a sheet from published template"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/activities/sheets/', {
            'name': 'My Sheet',
            'template_id': self.template.id
        })
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'My Sheet')
        self.assertIn('column_snapshot', response.data)
        self.assertEqual(len(response.data['column_snapshot']), 1)
    
    def test_cannot_create_sheet_from_draft_template(self):
        """Test that sheets cannot be created from draft templates"""
        draft_template = ActivityTemplate.objects.create(
            name='Draft Template',
            owner=self.user,
            status='draft'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/activities/sheets/', {
            'name': 'Failed Sheet',
            'template_id': draft_template.id
        })
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)


class BulkRowAPITests(APITestCase):
    """API tests for bulk row operations"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='bulkuser',
            email='bulk@example.com',
            password='pass123'
        )
        
        # Create template and sheet
        self.template = ActivityTemplate.objects.create(
            name='Bulk Template',
            owner=self.user
        )
        column = ActivityColumnDefinition.objects.filter(is_active=True).first()
        ActivityTemplateColumn.objects.create(
            template=self.template,
            column_definition=column,
            order=0
        )
        self.template.publish()
        
        self.sheet = ActivitySheet.objects.create(
            name='Bulk Sheet',
            template=self.template,
            owner=self.user,
            column_snapshot=[{'key': column.key, 'label': column.label}]
        )
    
    def test_bulk_create_rows(self):
        """Test bulk creating rows"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f'/api/activities/sheets/{self.sheet.id}/rows/bulk/',
            {
                'rows': [
                    {'row_number': 1, 'data': {'col1': 'value1'}},
                    {'row_number': 2, 'data': {'col2': 'value2'}},
                ]
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['created_count'], 2)
    
    def test_bulk_create_max_100_rows(self):
        """Test that bulk create is limited to 100 rows"""
        self.client.force_authenticate(user=self.user)
        
        # Create 101 rows
        rows = [{'row_number': i, 'data': {}} for i in range(1, 102)]
        
        response = self.client.post(
            f'/api/activities/sheets/{self.sheet.id}/rows/bulk/',
            {'rows': rows},
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
    
    def test_bulk_update_rows(self):
        """Test bulk updating rows"""
        # Create some rows first
        ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={'col1': 'old'}
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.put(
            f'/api/activities/sheets/{self.sheet.id}/rows/bulk/',
            {
                'rows': [
                    {'row_number': 1, 'data': {'col1': 'new'}}
                ]
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['updated_count'], 1)
    
    def test_bulk_delete_rows(self):
        """Test bulk deleting rows"""
        row = ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={}
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(
            f'/api/activities/sheets/{self.sheet.id}/rows/bulk/',
            {'row_ids': [row.id]},
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 1)

class ActivitySheetTests(TestCase):
    """Tests for ActivitySheet model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='sheetuser',
            email='sheet@example.com',
            password='testpass123'
        )
        self.column = ActivityColumnDefinition.objects.create(
            key='col1',
            label='Column 1'
        )
        self.template = ActivityTemplate.objects.create(
            name='Sheet Template',
            owner=self.user,
            status='published'
        )
        ActivityTemplateColumn.objects.create(
            template=self.template,
            column_definition=self.column
        )
    
    def test_create_sheet(self):
        """Test creating a sheet"""
        sheet = ActivitySheet.objects.create(
            name='My Sheet',
            template=self.template,
            owner=self.user,
            column_snapshot=[{'key': 'col1', 'label': 'Column 1'}]
        )
        self.assertTrue(sheet.is_active)
        self.assertEqual(sheet.row_count, 0)
    
    def test_sheet_preserves_columns_after_template_delete(self):
        """Test that sheet's column_snapshot remains after template deletion"""
        sheet = ActivitySheet.objects.create(
            name='Preserved Sheet',
            template=self.template,
            owner=self.user,
            column_snapshot=[{'key': 'col1', 'label': 'Column 1'}]
        )
        self.template.delete()
        sheet.refresh_from_db()
        self.assertIsNone(sheet.template)  # SET_NULL
        self.assertEqual(len(sheet.column_snapshot), 1)  # Preserved


class ActivitySheetRowTests(TestCase):
    """Tests for ActivitySheetRow model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='rowuser',
            email='row@example.com',
            password='testpass123'
        )
        self.sheet = ActivitySheet.objects.create(
            name='Row Sheet',
            owner=self.user,
            column_snapshot=[]
        )
    
    def test_create_row(self):
        """Test creating a row"""
        row = ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={'name': 'Test Value'}
        )
        self.assertEqual(row.data['name'], 'Test Value')
    
    def test_row_helpers(self):
        """Test row helper methods"""
        row = ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={},
            styles={}
        )
        
        row.set_cell_value('col1', 'Hello')
        self.assertEqual(row.get_cell_value('col1'), 'Hello')
        self.assertEqual(row.get_cell_value('nonexistent'), '')
        
        row.set_cell_style('col1', {'bold': True, 'textColor': '#FF0000'})
        style = row.get_cell_style('col1')
        self.assertTrue(style['bold'])
        self.assertEqual(row.get_cell_style('nonexistent'), {})
    
    def test_unique_row_number_per_sheet(self):
        """Test that row numbers are unique per sheet"""
        ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={}
        )
        # Should raise error for duplicate row number
        with self.assertRaises(Exception):  # IntegrityError
            ActivitySheetRow.objects.create(
                sheet=self.sheet,
                row_number=1,
                data={}
            )
    
    def test_row_count_updates(self):
        """Test that sheet row_count updates via signal"""
        self.assertEqual(self.sheet.row_count, 0)
        
        row = ActivitySheetRow.objects.create(
            sheet=self.sheet,
            row_number=1,
            data={}
        )
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.row_count, 1)
        
        row.delete()
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.row_count, 0)
