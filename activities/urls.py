# activities/urls.py
"""
URL configuration for Activities app.
"""

from django.urls import path
from . import views

app_name = 'activities'

urlpatterns = [
    # Column Definitions (Admin)
    path('columns/', views.ColumnDefinitionListCreateView.as_view(), name='column-list'),
    path('columns/<int:pk>/', views.ColumnDefinitionDetailView.as_view(), name='column-detail'),
    
    # Column Validations
    path('columns/<int:column_id>/validations/', views.ColumnValidationListCreateView.as_view(), name='validation-list'),
    path('validations/<int:pk>/', views.ColumnValidationDetailView.as_view(), name='validation-detail'),
    
    # Templates (Admin)
    path('templates/', views.TemplateListCreateView.as_view(), name='template-list'),
    path('templates/<int:pk>/', views.TemplateDetailView.as_view(), name='template-detail'),
    path('templates/<int:pk>/publish/', views.TemplatePublishView.as_view(), name='template-publish'),
    path('templates/<int:pk>/archive/', views.TemplateArchiveView.as_view(), name='template-archive'),
    path('templates/<int:pk>/columns/', views.TemplateColumnListView.as_view(), name='template-columns'),
    
    # Sheets (Advanced - for future use)
    path('sheets/', views.SheetListCreateView.as_view(), name='sheet-list'),
    path('sheets/<int:pk>/', views.SheetDetailView.as_view(), name='sheet-detail'),
    
    # Sheet Rows (Chunked operations)
    path('sheets/<int:sheet_id>/rows/', views.SheetRowListCreateView.as_view(), name='row-list'),
    path('sheets/<int:sheet_id>/rows/bulk/', views.SheetRowBulkView.as_view(), name='row-bulk'),
    path('rows/<int:pk>/', views.SheetRowDetailView.as_view(), name='row-detail'),
    
    # Excel Import/Export
    path('sheets/<int:sheet_id>/export/', views.SheetExportView.as_view(), name='sheet-export'),
    path('sheets/<int:sheet_id>/import/', views.SheetImportView.as_view(), name='sheet-import'),
    path('templates/<int:template_id>/download/', views.TemplateDownloadView.as_view(), name='template-download'),
    path('columns/detect-from-excel/', views.ExcelColumnDetectionView.as_view(), name='detect-columns-from-excel'),
    
    # ============================================================================
    # USER-FACING SIMPLIFIED API (Title Selection Flow)
    # ============================================================================
    # **NEW** - Unified endpoint for /activities/local page
    path('user/activity-page/', views.UserActivityPageView.as_view(), name='user-activity-page'),
    
    # List published titles for dropdown
    path('titles/', views.PublishedTitlesListView.as_view(), name='titles-list'),
    
    # Active Title Management
    path('titles/active/', views.ActiveTitleView.as_view(), name='active-title'),
    path('titles/<int:title_id>/', views.TitleDetailView.as_view(), name='title-detail'),
    path('titles/<int:title_id>/set-active/', views.SetActiveTitleView.as_view(), name='set-active-title'),
    path('titles/<int:title_id>/deactivate/', views.DeactivateTitleView.as_view(), name='deactivate-title'),
    
    # Get columns for a title
    path('titles/<int:title_id>/columns/', views.TitleColumnsView.as_view(), name='title-columns'),
    # List/Create user's sheets for a title
    path('titles/<int:title_id>/sheets/', views.UserTitleSheetsView.as_view(), name='title-sheets'),
    # Get unique values for a column (for filter dropdowns)
    path('titles/<int:title_id>/column-values/', views.SheetColumnValuesView.as_view(), name='column-values'),
    # Get/Save user's data for a specific sheet
    path('titles/<int:title_id>/my-data/', views.UserTitleDataView.as_view(), name='title-my-data'),
    
    # User Sheet Management
    path('my-sheets/', views.UserAllSheetsView.as_view(), name='my-all-sheets'),
    path('my-sheets/<int:sheet_id>/', views.UserSheetDetailView.as_view(), name='my-sheet-detail'),
    path('my-sheets/<int:sheet_id>/submit/', views.SubmitSheetView.as_view(), name='submit-sheet'),
    
    # Admin: View submitted sheets
    path('admin/submitted-sheets/', views.AdminSubmittedSheetsView.as_view(), name='admin-submitted-sheets'),
    
    # Admin: View any sheet's data (read-only)
    path('admin/sheets/<int:sheet_id>/data/', views.AdminSheetDataView.as_view(), name='admin-sheet-data'),
    
    # Admin: View all submitted activities for a specific template
    path('admin/templates/<int:template_id>/activities/', views.AdminTemplateActivitiesView.as_view(), name='admin-template-activities'),
    
    # Admin: Export activities for a template (supports batched fetching for large datasets)
    path('admin/templates/<int:template_id>/activities/export/', views.AdminTemplateActivitiesExportView.as_view(), name='admin-template-activities-export'),
    
    # Admin: Get users with submission counts for a template
    path('admin/templates/<int:template_id>/users/', views.AdminTemplateUsersView.as_view(), name='admin-template-users'),
    
    # ============================================================================
    # USER ACTIVITIES API - Per-user activities CRUD for a specific template
    # ============================================================================
    # List/Create activities for a template
    path('user/templates/<int:template_id>/activities/', views.UserActivitiesListCreateView.as_view(), name='user-activities-list'),
    # Submit all unsubmitted activities for a template (bulk submit)
    path('user/templates/<int:template_id>/submit/', views.UserTemplateSubmitView.as_view(), name='user-template-submit'),
    # Get/Update/Delete single activity
    path('user/activities/<int:activity_id>/', views.UserActivityDetailView.as_view(), name='user-activity-detail'),
    # Submit a single activity
    path('user/activities/<int:activity_id>/submit/', views.UserActivitySubmitView.as_view(), name='user-activity-submit'),
    
    # ============================================================================
    # ATTACHMENTS API
    # ============================================================================
    # List/Create attachments for a row
    path('rows/<int:row_id>/attachments/', views.RowAttachmentListCreateView.as_view(), name='row-attachments'),
    # Get/Delete single attachment
    path('attachments/<int:attachment_id>/', views.AttachmentDetailView.as_view(), name='attachment-detail'),
    # Download attachment (returns base64)
    path('attachments/<int:attachment_id>/download/', views.AttachmentDownloadView.as_view(), name='attachment-download'),
    # Preview image attachment (returns base64 for images only)
    path('attachments/<int:attachment_id>/preview/', views.AttachmentPreviewView.as_view(), name='attachment-preview'),
]
