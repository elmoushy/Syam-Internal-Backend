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
    
    # ============================================================================
    # USER-FACING SIMPLIFIED API (Title Selection Flow)
    # ============================================================================
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
]
