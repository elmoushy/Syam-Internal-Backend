# activities/views.py
"""
Views for the Activities system.
Supports chunked operations for large datasets.
"""

from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q, F

from .models import (
    ActivityColumnDefinition,
    ActivityColumnValidation,
    ActivityTemplate,
    ActivityTemplateColumn,
    ActivitySheet,
    ActivitySheetRow,
)
from .serializers import (
    ActivityColumnDefinitionSerializer,
    ActivityColumnDefinitionCreateSerializer,
    ActivityColumnDefinitionUpdateSerializer,
    ActivityColumnValidationSerializer,
    ActivityColumnValidationCreateSerializer,
    ActivityTemplateListSerializer,
    ActivityTemplateDetailSerializer,
    ActivityTemplateCreateSerializer,
    ActivityTemplateUpdateSerializer,
    ActivityTemplateColumnSerializer,
    TemplateColumnsUpdateSerializer,
    ActivitySheetListSerializer,
    ActivitySheetDetailSerializer,
    ActivitySheetCreateSerializer,
    ActivitySheetRowSerializer,
    ActivitySheetRowCreateSerializer,
    BulkRowCreateSerializer,
    BulkRowUpdateSerializer,
    BulkRowDeleteSerializer,
)
from .permissions import (
    IsAdminUser,
    IsTemplateOwner,
    IsSheetOwner,
    IsColumnDefinitionEditable,
)
from .pagination import (
    SheetRowCursorPagination,
    TemplateListPagination,
    SheetListPagination,
)
from .constants import MAX_ROWS_PER_PAGE


# ============================================================================
# Column Definition Views (Admin Only)
# ============================================================================

class ColumnDefinitionListCreateView(generics.ListCreateAPIView):
    """
    GET: List all column definitions (active only by default)
    POST: Create a new column definition (admin only)
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ActivityColumnDefinition.objects.all()
        
        # Filter by active status
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)
        
        # Filter by system status
        system_only = self.request.query_params.get('system_only', 'false')
        if system_only.lower() == 'true':
            queryset = queryset.filter(is_system=True)
        
        # Filter by data type
        data_type = self.request.query_params.get('data_type')
        if data_type:
            queryset = queryset.filter(data_type=data_type)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(key__icontains=search) | Q(label__icontains=search)
            )
        
        return queryset.order_by('order', 'id')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivityColumnDefinitionCreateSerializer
        return ActivityColumnDefinitionSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        column = serializer.save()
        
        # Return full serializer for response
        response_serializer = ActivityColumnDefinitionSerializer(column)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ColumnDefinitionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a column definition
    PUT/PATCH: Update a column definition (admin only)
    DELETE: Soft-delete a column definition (admin only, non-system only)
    """
    queryset = ActivityColumnDefinition.objects.all()
    permission_classes = [IsAuthenticated, IsColumnDefinitionEditable]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ActivityColumnDefinitionUpdateSerializer
        return ActivityColumnDefinitionSerializer
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsAdminUser(), IsColumnDefinitionEditable()]
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        if instance.is_system:
            return Response(
                {'error': 'Cannot delete system columns'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not instance.can_delete():
            return Response(
                {'error': 'Cannot delete column that is used in templates'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Soft delete
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Column Validation Views (Admin Only)
# ============================================================================

class ColumnValidationListCreateView(generics.ListCreateAPIView):
    """
    GET: List validations for a column
    POST: Create a validation rule (admin only)
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        column_id = self.kwargs['column_id']
        return ActivityColumnValidation.objects.filter(column_id=column_id)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivityColumnValidationCreateSerializer
        return ActivityColumnValidationSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def create(self, request, *args, **kwargs):
        column = get_object_or_404(ActivityColumnDefinition, pk=self.kwargs['column_id'])
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validation = serializer.save(column=column)
        
        response_serializer = ActivityColumnValidationSerializer(validation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ColumnValidationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a validation rule
    PUT/PATCH: Update a validation rule (admin only)
    DELETE: Delete a validation rule (admin only)
    """
    queryset = ActivityColumnValidation.objects.all()
    serializer_class = ActivityColumnValidationSerializer
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [IsAdminUser()]


# ============================================================================
# Template Views
# ============================================================================

class TemplateListCreateView(generics.ListCreateAPIView):
    """
    GET: List templates (user's own + published templates)
    POST: Create a new template
    """
    permission_classes = [IsAuthenticated]
    pagination_class = TemplateListPagination
    
    def get_queryset(self):
        user = self.request.user
        queryset = ActivityTemplate.objects.all()
        
        # Filter by ownership
        mine_only = self.request.query_params.get('mine_only', 'false')
        if mine_only.lower() == 'true':
            queryset = queryset.filter(owner=user)
        elif not user.is_staff:
            # Regular users see their own + published templates
            queryset = queryset.filter(
                Q(owner=user) | Q(status='published', is_deleted=False)
            )
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Exclude deleted by default
        show_deleted = self.request.query_params.get('show_deleted', 'false')
        if show_deleted.lower() != 'true':
            queryset = queryset.filter(is_deleted=False)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        
        return queryset.select_related('owner').order_by('-updated_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivityTemplateCreateSerializer
        return ActivityTemplateListSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = serializer.save(owner=request.user)
        
        response_serializer = ActivityTemplateDetailSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve template details
    PUT/PATCH: Update template (owner/admin only, draft only for major changes)
    DELETE: Archive or delete template (owner/admin only)
    """
    queryset = ActivityTemplate.objects.select_related('owner')
    permission_classes = [IsAuthenticated, IsTemplateOwner]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ActivityTemplateUpdateSerializer
        return ActivityTemplateDetailSerializer
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        if instance.can_delete():
            # Hard delete if no sheets exist
            instance.delete()
        else:
            # Soft delete (archive) if sheets exist
            instance.archive()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class TemplatePublishView(views.APIView):
    """
    POST: Publish a draft template
    """
    permission_classes = [IsAuthenticated, IsTemplateOwner]
    
    def post(self, request, pk):
        template = get_object_or_404(ActivityTemplate, pk=pk)
        self.check_object_permissions(request, template)
        
        try:
            template.publish()
            serializer = ActivityTemplateDetailSerializer(template)
            return Response(serializer.data)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class TemplateArchiveView(views.APIView):
    """
    POST: Archive a template
    """
    permission_classes = [IsAuthenticated, IsTemplateOwner]
    
    def post(self, request, pk):
        template = get_object_or_404(ActivityTemplate, pk=pk)
        self.check_object_permissions(request, template)
        
        template.archive()
        serializer = ActivityTemplateDetailSerializer(template)
        return Response(serializer.data)


class TemplateColumnListView(views.APIView):
    """
    GET: List columns for a template
    PUT: Replace all columns for a template (draft only)
    """
    permission_classes = [IsAuthenticated, IsTemplateOwner]
    
    def get(self, request, pk):
        template = get_object_or_404(ActivityTemplate, pk=pk)
        self.check_object_permissions(request, template)
        
        columns = template.template_columns.select_related('column_definition').order_by('order')
        serializer = ActivityTemplateColumnSerializer(columns, many=True)
        return Response(serializer.data)
    
    def put(self, request, pk):
        template = get_object_or_404(ActivityTemplate, pk=pk)
        self.check_object_permissions(request, template)
        
        serializer = TemplateColumnsUpdateSerializer(
            data=request.data,
            context={'template': template}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(template)
        
        # Return updated columns
        columns = template.template_columns.select_related('column_definition').order_by('order')
        response_serializer = ActivityTemplateColumnSerializer(columns, many=True)
        return Response(response_serializer.data)


# ============================================================================
# Sheet Views
# ============================================================================

class SheetListCreateView(generics.ListCreateAPIView):
    """
    GET: List user's sheets
    POST: Create a new sheet from a template
    """
    permission_classes = [IsAuthenticated]
    pagination_class = SheetListPagination
    
    def get_queryset(self):
        user = self.request.user
        queryset = ActivitySheet.objects.all()
        
        # Filter by owner (admins can see all)
        if not user.is_staff:
            queryset = queryset.filter(owner=user)
        else:
            owner_filter = self.request.query_params.get('owner')
            if owner_filter:
                queryset = queryset.filter(owner_id=owner_filter)
        
        # Filter by template
        template_id = self.request.query_params.get('template')
        if template_id:
            queryset = queryset.filter(template_id=template_id)
        
        # Filter by active status
        show_inactive = self.request.query_params.get('show_inactive', 'false')
        if show_inactive.lower() != 'true':
            queryset = queryset.filter(is_active=True)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        return queryset.select_related('owner', 'template').order_by('-updated_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitySheetCreateSerializer
        return ActivitySheetListSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sheet = serializer.save(owner=request.user)
        
        response_serializer = ActivitySheetDetailSerializer(sheet)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SheetDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve sheet details (includes column_snapshot)
    PUT/PATCH: Update sheet name
    DELETE: Soft-delete sheet
    """
    queryset = ActivitySheet.objects.select_related('owner', 'template')
    permission_classes = [IsAuthenticated, IsSheetOwner]
    serializer_class = ActivitySheetDetailSerializer
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Soft delete
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Sheet Row Views (Chunked Operations)
# ============================================================================

class SheetRowListCreateView(views.APIView):
    """
    GET: List rows with cursor pagination
    POST: Create a single row
    """
    permission_classes = [IsAuthenticated, IsSheetOwner]
    pagination_class = SheetRowCursorPagination
    
    def get(self, request, sheet_id):
        sheet = get_object_or_404(ActivitySheet, pk=sheet_id)
        self.check_object_permissions(request, sheet)
        
        queryset = sheet.rows.all().order_by('row_number')
        
        # Filter by row number range
        from_row = request.query_params.get('from_row')
        to_row = request.query_params.get('to_row')
        if from_row:
            queryset = queryset.filter(row_number__gte=int(from_row))
        if to_row:
            queryset = queryset.filter(row_number__lte=int(to_row))
        
        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        
        serializer = ActivitySheetRowSerializer(page, many=True)
        
        return Response({
            'rows': serializer.data,
            'next_cursor': paginator.get_next_link(),
            'prev_cursor': paginator.get_previous_link(),
            'total_count': sheet.row_count,
            'has_more': paginator.has_next if hasattr(paginator, 'has_next') else False
        })
    
    def post(self, request, sheet_id):
        sheet = get_object_or_404(ActivitySheet, pk=sheet_id)
        self.check_object_permissions(request, sheet)
        
        serializer = ActivitySheetRowCreateSerializer(
            data=request.data,
            context={'sheet': sheet}
        )
        serializer.is_valid(raise_exception=True)
        row = serializer.save(sheet=sheet)
        
        response_serializer = ActivitySheetRowSerializer(row)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def check_object_permissions(self, request, obj):
        for permission in [IsSheetOwner()]:
            if not permission.has_object_permission(request, self, obj):
                self.permission_denied(request)


class SheetRowBulkView(views.APIView):
    """
    POST: Bulk create rows (max 100 per request)
    PUT: Bulk update rows (max 100 per request)
    DELETE: Bulk delete rows
    """
    permission_classes = [IsAuthenticated]
    
    def get_sheet(self, sheet_id, request):
        sheet = get_object_or_404(ActivitySheet, pk=sheet_id)
        # Check ownership
        if not request.user.is_staff and sheet.owner != request.user:
            self.permission_denied(request)
        return sheet
    
    def post(self, request, sheet_id):
        """Bulk create rows"""
        sheet = self.get_sheet(sheet_id, request)
        
        serializer = BulkRowCreateSerializer(
            data=request.data,
            context={'sheet': sheet}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        
        created_serializer = ActivitySheetRowSerializer(result['created'], many=True)
        
        return Response({
            'success': True,
            'created_count': len(result['created']),
            'created': created_serializer.data,
            'errors': result['errors'],
            'chunk_id': result.get('chunk_id', ''),
            'warnings': serializer.context.get('warnings', [])
        }, status=status.HTTP_201_CREATED if not result['errors'] else status.HTTP_207_MULTI_STATUS)
    
    def put(self, request, sheet_id):
        """Bulk update rows"""
        sheet = self.get_sheet(sheet_id, request)
        
        serializer = BulkRowUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.update(sheet, serializer.validated_data)
        
        updated_serializer = ActivitySheetRowSerializer(result['updated'], many=True)
        
        return Response({
            'success': True,
            'updated_count': len(result['updated']),
            'updated': updated_serializer.data,
            'errors': result['errors'],
            'chunk_id': result.get('chunk_id', '')
        }, status=status.HTTP_200_OK if not result['errors'] else status.HTTP_207_MULTI_STATUS)
    
    def delete(self, request, sheet_id):
        """Bulk delete rows"""
        sheet = self.get_sheet(sheet_id, request)
        
        serializer = BulkRowDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.delete(sheet)
        
        return Response({
            'success': True,
            'deleted_count': result['deleted_count']
        })


class SheetRowDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a single row
    PUT/PATCH: Update a single row
    DELETE: Delete a single row
    """
    queryset = ActivitySheetRow.objects.all()
    serializer_class = ActivitySheetRowSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        obj = super().get_object()
        # Check sheet ownership
        if not self.request.user.is_staff and obj.sheet.owner != self.request.user:
            self.permission_denied(self.request)
        return obj


# ============================================================================
# Excel Import/Export Views
# ============================================================================

class SheetExportView(views.APIView):
    """
    GET: Export sheet to Excel
    
    Query params:
    - include_data: bool (default=true) - Include row data or just headers
    - streaming: bool (default=auto) - Force streaming mode for large files
    """
    permission_classes = [IsAuthenticated, IsSheetOwner]
    
    def get(self, request, sheet_id):
        from django.http import StreamingHttpResponse, HttpResponse
        from .excel_service import ExcelService, export_sheet_streaming
        
        sheet = get_object_or_404(ActivitySheet, pk=sheet_id)
        self.check_object_permissions(request, sheet)
        
        include_data = request.query_params.get('include_data', 'true').lower() == 'true'
        force_streaming = request.query_params.get('streaming', '').lower() == 'true'
        
        # Use streaming for large sheets (>1000 rows) or if forced
        use_streaming = force_streaming or (include_data and sheet.row_count > 1000)
        
        filename = f"{sheet.name.replace(' ', '_')}.xlsx"
        
        if use_streaming:
            # Stream the response for large files
            response = StreamingHttpResponse(
                export_sheet_streaming(sheet.id),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            # Regular response for smaller files
            service = ExcelService(sheet)
            excel_buffer = service.export_to_excel(include_data=include_data)
            
            response = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    
    def check_object_permissions(self, request, obj):
        for permission in [IsSheetOwner()]:
            if not permission.has_object_permission(request, self, obj):
                self.permission_denied(request)


class SheetImportView(views.APIView):
    """
    POST: Import Excel data into sheet
    
    Body (multipart/form-data):
    - file: Excel file (.xlsx, .xls)
    - validate: bool (default=true) - Run validation before import
    - replace: bool (default=true) - Replace existing data or append
    """
    permission_classes = [IsAuthenticated, IsSheetOwner]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, sheet_id):
        from .excel_service import ExcelService
        from .validators import RowValidator
        
        sheet = get_object_or_404(ActivitySheet, pk=sheet_id)
        self.check_object_permissions(request, sheet)
        
        # Get uploaded file
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {'error': 'لم يتم تحميل أي ملف', 'error_en': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file extension
        allowed_extensions = ['.xlsx', '.xls']
        file_ext = uploaded_file.name.lower()
        if not any(file_ext.endswith(ext) for ext in allowed_extensions):
            return Response(
                {'error': 'نوع الملف غير مدعوم. استخدم ملف Excel (.xlsx أو .xls)',
                 'error_en': 'Invalid file type. Use Excel file (.xlsx or .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if uploaded_file.size > max_size:
            return Response(
                {'error': 'حجم الملف كبير جداً. الحد الأقصى 10 ميجابايت',
                 'error_en': 'File too large. Maximum size is 10MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Options
        validate = request.data.get('validate', 'true').lower() == 'true'
        replace = request.data.get('replace', 'true').lower() == 'true'
        
        try:
            service = ExcelService(sheet)
            result = service.import_from_excel(
                file_content=uploaded_file.read(),
                validate=validate
            )
            
            if result['errors']:
                return Response({
                    'success': False,
                    'message': 'فشل استيراد البيانات بسبب أخطاء التحقق',
                    'message_en': 'Import failed due to validation errors',
                    'errors': result['errors'],
                    'imported_count': result['imported_count'],
                    'skipped_count': result['skipped_count']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': 'تم استيراد البيانات بنجاح',
                'message_en': 'Data imported successfully',
                'imported_count': result['imported_count'],
                'skipped_count': result['skipped_count'],
                'warnings': result.get('warnings', [])
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'حدث خطأ أثناء استيراد الملف: {str(e)}',
                'error_en': f'Error importing file: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def check_object_permissions(self, request, obj):
        for permission in [IsSheetOwner()]:
            if not permission.has_object_permission(request, self, obj):
                self.permission_denied(request)


class TemplateDownloadView(views.APIView):
    """
    GET: Download empty Excel template based on ActivityTemplate
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, template_id):
        from django.http import HttpResponse
        from .excel_service import create_template_excel
        
        template = get_object_or_404(ActivityTemplate, pk=template_id)
        
        # Check access - published templates are public, draft only to owner
        if template.status != 'published':
            if not request.user.is_staff and template.owner != request.user:
                return Response(
                    {'error': 'ليس لديك صلاحية لتحميل هذا النموذج'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            excel_buffer = create_template_excel(template)
            filename = f"template_{template.name.replace(' ', '_')}.xlsx"
            
            response = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            return Response({
                'error': f'حدث خطأ أثناء إنشاء النموذج: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# USER-FACING SIMPLIFIED API (Title Selection Flow)
# ============================================================================

class PublishedTitlesListView(views.APIView):
    """
    GET: List all published titles (templates) for dropdown selection.
    Returns only id, name, description, column_count for each published template.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        titles = ActivityTemplate.objects.filter(
            status='published',
            is_deleted=False
        ).prefetch_related('template_columns').order_by('name')
        
        data = []
        for template in titles:
            data.append({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'column_count': template.template_columns.count(),
            })
        
        return Response(data)


class TitleColumnsView(views.APIView):
    """
    GET: Get columns for a specific published title.
    Returns column definitions with their validations.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, title_id):
        template = get_object_or_404(
            ActivityTemplate.objects.prefetch_related(
                'template_columns__column_definition__validations'
            ),
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        columns = []
        for tc in template.template_columns.all().order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'options': col_def.options or [],
                'validations': [
                    {
                        'rule_type': v.rule_type,
                        'rule_value': v.rule_value,
                        'error_message': v.error_message,
                    }
                    for v in col_def.validations.filter(is_active=True)
                ]
            })
        
        return Response({
            'title_id': template.id,
            'title_name': template.name,
            'columns': columns,
        })


class SheetColumnValuesView(views.APIView):
    """
    Get unique values for a specific column in a sheet.
    Used for populating filter dropdowns with actual data from the entire dataset.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, title_id):
        """
        Query params:
          - sheet_id (required)
          - column_key (required) - the column to get values for
          - limit (optional, default=1000) - max unique values to return
        """
        sheet_id = request.query_params.get('sheet_id')
        column_key = request.query_params.get('column_key')
        
        if not sheet_id:
            return Response(
                {'error': 'sheet_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not column_key:
            return Response(
                {'error': 'column_key مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            limit = min(1000, max(1, int(request.query_params.get('limit', 1000))))
        except ValueError:
            limit = 1000
        
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            template=template,
            owner=request.user,
            is_active=True
        )
        
        # Extract unique values from the column across all rows
        unique_values = set()
        has_blanks = False
        
        for row in sheet.rows.all().only('data'):
            cell_value = row.data.get(column_key, '')
            if cell_value is None:
                cell_value = ''
            cell_value = str(cell_value).strip()
            
            if cell_value == '':
                has_blanks = True
            else:
                unique_values.add(cell_value)
                if len(unique_values) >= limit:
                    break
        
        # Sort values alphabetically (Arabic-aware)
        sorted_values = sorted(unique_values, key=lambda x: x.lower())
        
        return Response({
            'column_key': column_key,
            'values': sorted_values,
            'has_blanks': has_blanks,
            'total_unique': len(sorted_values),
            'truncated': len(sorted_values) >= limit,
        })


class UserTitleDataView(views.APIView):
    """
    GET: Get user's data for a specific sheet with pagination
    POST: Save/update user's data for a sheet
    PATCH: Differential update - PROPERLY handles insertions, deletions, and updates
    
    CRITICAL: The PATCH endpoint uses database IDs for identification, not row positions.
    This ensures data integrity when rows are inserted/deleted in the middle.
    
    Note: sheet_id is now required in query params for GET, or in body for POST/PATCH
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, title_id):
        """
        Get user's sheet data with pagination, filtering, and sorting.
        
        Query params:
          - sheet_id (required)
          - page (optional, default=1)
          - page_size (optional, default=100, max=500)
          - sort_by (optional) - column key to sort by
          - sort_order (optional) - 'asc' or 'desc', default 'asc'
          - filters (optional) - JSON string of column filters
              Format: {"col_key": {"excluded": ["value1", "value2"], "show_blanks": true}, ...}
        
        Returns rows with:
          - id: Database primary key (stable identifier)
          - row_order: Current display position (1-indexed)
          - data, styles, height: Cell content
        """
        import json
        from .constants import USER_ROWS_PER_PAGE
        
        sheet_id = request.query_params.get('sheet_id')
        
        if not sheet_id:
            return Response(
                {'error': 'sheet_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        # Get the specific sheet (must belong to user and this title)
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            template=template,
            owner=request.user,
            is_active=True
        )
        
        # Pagination params
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(500, max(1, int(request.query_params.get('page_size', USER_ROWS_PER_PAGE))))
        except ValueError:
            page = 1
            page_size = USER_ROWS_PER_PAGE
        
        # Sorting params
        sort_by = request.query_params.get('sort_by', None)
        sort_order = request.query_params.get('sort_order', 'asc')
        
        # Filters param - parse JSON
        filters_json = request.query_params.get('filters', None)
        filters = {}
        if filters_json:
            try:
                filters = json.loads(filters_json)
            except json.JSONDecodeError:
                filters = {}
        
        # Start with all rows for this sheet
        queryset = sheet.rows.all()
        
        # Apply filters (done in Python since data is JSON field)
        if filters:
            filtered_ids = []
            for row in queryset:
                include_row = True
                for col_key, filter_config in filters.items():
                    excluded_values = filter_config.get('excluded', [])
                    show_blanks = filter_config.get('show_blanks', True)
                    
                    cell_value = row.data.get(col_key, '').strip() if row.data.get(col_key) else ''
                    is_blank = cell_value == ''
                    
                    if is_blank:
                        if not show_blanks:
                            include_row = False
                            break
                    else:
                        if cell_value in excluded_values:
                            include_row = False
                            break
                
                if include_row:
                    filtered_ids.append(row.id)
            
            queryset = sheet.rows.filter(id__in=filtered_ids)
        
        # Get total count after filtering
        total_count = queryset.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        
        # Apply sorting (Python-based for JSON field)
        if sort_by:
            rows_list = list(queryset)
            reverse = (sort_order == 'desc')
            
            def sort_key(row):
                val = row.data.get(sort_by, '') or ''
                return val.lower() if isinstance(val, str) else str(val)
            
            rows_list.sort(key=sort_key, reverse=reverse)
            
            # Apply pagination to sorted list
            offset = (page - 1) * page_size
            rows_list = rows_list[offset:offset + page_size]
        else:
            # Default ordering by row_order with pagination
            offset = (page - 1) * page_size
            rows_list = list(queryset.order_by('row_order')[offset:offset + page_size])
        
        rows_data = [
            {
                'id': row.id,
                'row_order': row.row_order,
                'row_number': row.row_order,
                'data': row.data,
                'styles': row.styles,
                'height': row.height,
            }
            for row in rows_list
        ]
        
        return Response({
            'sheet_id': sheet.id,
            'sheet_name': sheet.name,
            'sheet_description': sheet.description,
            'title_id': template.id,
            'title_name': template.name,
            'rows': rows_data,
            'columns': sheet.column_snapshot,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            },
            # Include active filters/sort in response for UI sync
            'active_filters': filters,
            'sort_by': sort_by,
            'sort_order': sort_order,
        })
    
    def post(self, request, title_id):
        """Save user's data (rows) for a specific sheet - FULL REPLACE mode."""
        sheet_id = request.data.get('sheet_id')
        
        if not sheet_id:
            return Response(
                {'error': 'sheet_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        # Get the specific sheet
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            template=template,
            owner=request.user,
            is_active=True
        )
        
        rows_data = request.data.get('rows', [])
        
        with transaction.atomic():
            # Delete existing rows
            sheet.rows.all().delete()
            
            # Create new rows with sequential row_order
            new_rows = []
            for idx, row_data in enumerate(rows_data, start=1):
                new_rows.append(ActivitySheetRow(
                    sheet=sheet,
                    row_number=idx,  # Backward compatibility
                    row_order=idx,   # New ordering field
                    data=row_data.get('data', {}),
                    styles=row_data.get('styles', {}),
                    height=row_data.get('height', 32),
                ))
            
            if new_rows:
                ActivitySheetRow.objects.bulk_create(new_rows)
            
            # Update row count
            sheet.row_count = len(new_rows)
            sheet.save(update_fields=['row_count', 'updated_at'])
        
        return Response({
            'success': True,
            'message': 'تم حفظ البيانات بنجاح',
            'sheet_id': sheet.id,
            'row_count': len(new_rows),
        })
    
    def patch(self, request, title_id):
        """
        COMPREHENSIVE DIFFERENTIAL UPDATE with proper row ordering.
        
        This endpoint handles ALL types of spreadsheet operations safely:
        1. UPDATE existing rows (by database ID)
        2. INSERT new rows at specific positions (shifts subsequent rows)
        3. DELETE rows (renumbers remaining rows to fill gaps)
        4. APPEND rows at the end
        
        CRITICAL: Uses database IDs for identification, NOT row positions.
        Row positions (row_order) CAN and WILL change with insertions.
        
        Request Body Format:
        {
            "sheet_id": 123,
            "operations": {
                "updates": [
                    {"id": 45, "data": {...}, "styles": {...}, "height": 32}
                ],
                "insertions": [
                    {"insert_at_order": 5, "data": {...}, "styles": {...}, "height": 32}
                ],
                "deletions": [67, 89],  // Database IDs to delete
                "appends": [
                    {"data": {...}, "styles": {...}, "height": 32}
                ]
            }
        }
        
        OR (backward compatible simple format):
        {
            "sheet_id": 123,
            "updated_rows": [...],  // Uses id field
            "new_rows": [...],      // Appended at end
            "deleted_row_ids": [],  // Database IDs to delete
            "deleted_row_numbers": []  // DEPRECATED: Delete by old row_number
        }
        
        Processing Order (CRITICAL for data integrity):
        1. Deletions (to free up space)
        2. Insertions (shifts existing rows)
        3. Updates (modifies existing data)
        4. Appends (adds at end)
        5. Renumber all rows sequentially
        """
        sheet_id = request.data.get('sheet_id')
        
        if not sheet_id:
            return Response(
                {'error': 'sheet_id مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            template=template,
            owner=request.user,
            is_active=True
        )
        
        # Parse request - support both new and backward-compatible formats
        operations = request.data.get('operations', {})
        
        # New format
        updates = operations.get('updates', [])
        insertions = operations.get('insertions', [])
        deletions = operations.get('deletions', [])  # Database IDs
        appends = operations.get('appends', [])
        
        # Backward-compatible format (deprecated but supported)
        if not operations:
            updated_rows = request.data.get('updated_rows', [])
            new_rows = request.data.get('new_rows', [])
            deleted_row_ids = request.data.get('deleted_row_ids', [])
            deleted_row_numbers = request.data.get('deleted_row_numbers', [])  # DEPRECATED
            
            # Convert old format to new format
            for row_data in updated_rows:
                row_id = row_data.get('id')
                if row_id:
                    updates.append({
                        'id': row_id,
                        'data': row_data.get('data', {}),
                        'styles': row_data.get('styles', {}),
                        'height': row_data.get('height', 32)
                    })
            
            # New rows become appends (at end)
            for row_data in new_rows:
                appends.append({
                    'data': row_data.get('data', {}),
                    'styles': row_data.get('styles', {}),
                    'height': row_data.get('height', 32)
                })
            
            # Deleted IDs
            deletions.extend(deleted_row_ids)
            
            # Handle deprecated row_number deletions (convert to IDs)
            if deleted_row_numbers:
                rows_to_delete = sheet.rows.filter(row_order__in=deleted_row_numbers)
                deletions.extend([r.id for r in rows_to_delete])
        
        updated_count = 0
        inserted_count = 0
        deleted_count = 0
        appended_count = 0
        errors = []
        
        with transaction.atomic():
            # ================================================
            # STEP 1: DELETIONS (free up space first)
            # ================================================
            if deletions:
                # Validate all IDs exist and belong to this sheet
                existing_ids = set(sheet.rows.filter(id__in=deletions).values_list('id', flat=True))
                invalid_ids = set(deletions) - existing_ids
                
                if invalid_ids:
                    for inv_id in invalid_ids:
                        errors.append({'id': inv_id, 'error': 'Row ID not found'})
                
                # Delete valid rows
                deleted_count = sheet.rows.filter(id__in=existing_ids).delete()[0]
            
            # ================================================
            # STEP 2: INSERTIONS (with row shifting)
            # ================================================
            if insertions:
                # Sort insertions by position (ascending) to process in order
                insertions_sorted = sorted(insertions, key=lambda x: x.get('insert_at_order', 1))
                
                for insert_data in insertions_sorted:
                    insert_at = insert_data.get('insert_at_order', 1)
                    
                    # Shift all rows at or after this position DOWN by 1
                    # CRITICAL: Update in DESCENDING order to avoid UNIQUE constraint violations
                    rows_to_shift = sheet.rows.filter(row_order__gte=insert_at).order_by('-row_order')
                    for row in rows_to_shift:
                        row.row_order += 1
                        row.save(update_fields=['row_order'])
                    
                    # Create new row at the position
                    ActivitySheetRow.objects.create(
                        sheet=sheet,
                        row_number=insert_at,  # Will be fixed in renumbering
                        row_order=insert_at,
                        data=insert_data.get('data', {}),
                        styles=insert_data.get('styles', {}),
                        height=insert_data.get('height', 32),
                    )
                    inserted_count += 1
            
            # ================================================
            # STEP 3: UPDATES (modify existing rows by ID)
            # ================================================
            if updates:
                # Get all rows that need updating in one query
                update_ids = [u.get('id') for u in updates if u.get('id')]
                existing_rows = {
                    r.id: r 
                    for r in sheet.rows.filter(id__in=update_ids)
                }
                
                rows_to_update = []
                for update_data in updates:
                    row_id = update_data.get('id')
                    if row_id in existing_rows:
                        row = existing_rows[row_id]
                        # Only update provided fields
                        if 'data' in update_data:
                            row.data = update_data['data']
                        if 'styles' in update_data:
                            row.styles = update_data['styles']
                        if 'height' in update_data:
                            row.height = update_data['height']
                        rows_to_update.append(row)
                        updated_count += 1
                    else:
                        errors.append({'id': row_id, 'error': 'Row not found for update'})
                
                if rows_to_update:
                    ActivitySheetRow.objects.bulk_update(
                        rows_to_update, 
                        ['data', 'styles', 'height']
                    )
            
            # ================================================
            # STEP 4: APPENDS (add new rows at end)
            # ================================================
            if appends:
                # Get the current maximum row_order
                max_order = sheet.rows.aggregate(
                    max_order=models.Max('row_order')
                )['max_order'] or 0
                
                rows_to_create = []
                for idx, append_data in enumerate(appends, start=1):
                    new_order = max_order + idx
                    rows_to_create.append(ActivitySheetRow(
                        sheet=sheet,
                        row_number=new_order,
                        row_order=new_order,
                        data=append_data.get('data', {}),
                        styles=append_data.get('styles', {}),
                        height=append_data.get('height', 32),
                    ))
                
                if rows_to_create:
                    ActivitySheetRow.objects.bulk_create(rows_to_create)
                    appended_count = len(rows_to_create)
            
            # ================================================
            # STEP 5: RENUMBER ALL ROWS (fill gaps, ensure sequential)
            # ================================================
            # This is CRITICAL after deletions or insertions
            all_rows = list(sheet.rows.all().order_by('row_order'))
            needs_update = []
            
            for idx, row in enumerate(all_rows, start=1):
                if row.row_order != idx:
                    row.row_order = idx
                    row.row_number = idx  # Keep in sync
                    needs_update.append(row)
            
            if needs_update:
                # Update in batches for efficiency
                ActivitySheetRow.objects.bulk_update(
                    needs_update, 
                    ['row_order', 'row_number'],
                    batch_size=500
                )
            
            # ================================================
            # STEP 6: UPDATE SHEET ROW COUNT
            # ================================================
            sheet.row_count = sheet.rows.count()
            sheet.save(update_fields=['row_count', 'updated_at'])
        
        return Response({
            'success': len(errors) == 0,
            'message': 'تم تحديث البيانات بنجاح' if len(errors) == 0 else 'تم التحديث مع بعض الأخطاء',
            'sheet_id': sheet.id,
            'updated_count': updated_count,
            'inserted_count': inserted_count,
            'created_count': appended_count,  # Backward compatible alias
            'deleted_count': deleted_count,
            'row_count': sheet.row_count,
            'errors': errors,
        })
    
    def _get_column_snapshot(self, template):
        """Generate column snapshot from template."""
        columns = []
        for tc in template.template_columns.all().order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'options': col_def.options or [],
            })
        return columns


class UserTitleSheetsView(views.APIView):
    """
    GET: List user's sheets for a specific title
    POST: Create a new sheet for a title
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, title_id):
        """List user's sheets for this title."""
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        sheets = ActivitySheet.objects.filter(
            template=template,
            owner=request.user,
            is_active=True
        ).order_by('-updated_at')
        
        data = [
            {
                'id': sheet.id,
                'name': sheet.name,
                'description': sheet.description,
                'row_count': sheet.row_count,
                'created_at': sheet.created_at.isoformat(),
                'updated_at': sheet.updated_at.isoformat(),
            }
            for sheet in sheets
        ]
        
        return Response({
            'title_id': template.id,
            'title_name': template.name,
            'sheets': data,
            'count': len(data),
        })
    
    def post(self, request, title_id):
        """Create a new sheet for this title."""
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        name = request.data.get('name', '').strip()
        description = request.data.get('description', '').strip()
        
        if not name:
            return Response(
                {'error': 'اسم الجدول مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate column snapshot
        column_snapshot = self._get_column_snapshot(template)
        
        # Create new sheet
        sheet = ActivitySheet.objects.create(
            name=name,
            description=description,
            template=template,
            owner=request.user,
            column_snapshot=column_snapshot,
        )
        
        return Response({
            'id': sheet.id,
            'name': sheet.name,
            'description': sheet.description,
            'row_count': 0,
            'created_at': sheet.created_at.isoformat(),
            'updated_at': sheet.updated_at.isoformat(),
        }, status=status.HTTP_201_CREATED)
    
    def _get_column_snapshot(self, template):
        """Generate column snapshot from template."""
        columns = []
        for tc in template.template_columns.all().order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'options': col_def.options or [],
            })
        return columns


class UserSheetDetailView(views.APIView):
    """
    GET: Get sheet details
    PATCH: Update sheet name/description
    DELETE: Soft delete a sheet
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, sheet_id):
        """Get sheet details."""
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            owner=request.user,
            is_active=True
        )
        
        return Response({
            'id': sheet.id,
            'name': sheet.name,
            'description': sheet.description,
            'template_id': sheet.template_id,
            'template_name': sheet.template.name if sheet.template else None,
            'row_count': sheet.row_count,
            'created_at': sheet.created_at.isoformat(),
            'updated_at': sheet.updated_at.isoformat(),
        })
    
    def patch(self, request, sheet_id):
        """Update sheet name/description."""
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            owner=request.user,
            is_active=True
        )
        
        name = request.data.get('name')
        description = request.data.get('description')
        
        if name is not None:
            name = name.strip()
            if not name:
                return Response(
                    {'error': 'اسم الجدول مطلوب'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            sheet.name = name
        
        if description is not None:
            sheet.description = description.strip()
        
        sheet.save(update_fields=['name', 'description', 'updated_at'])
        
        return Response({
            'id': sheet.id,
            'name': sheet.name,
            'description': sheet.description,
            'updated_at': sheet.updated_at.isoformat(),
        })
    
    def delete(self, request, sheet_id):
        """Soft delete a sheet."""
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            owner=request.user,
            is_active=True
        )
        
        sheet.is_active = False
        sheet.save(update_fields=['is_active', 'updated_at'])
        
        return Response({'message': 'تم حذف الجدول بنجاح'}, status=status.HTTP_200_OK)