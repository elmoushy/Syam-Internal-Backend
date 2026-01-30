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
from django.db.models import Q, F, Max
from django.utils import timezone

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
from .constants import MAX_ROWS_PER_PAGE, MANDATORY_COLUMN_KEYS


def is_admin_user(user):
    """
    Helper function to check if user has admin privileges.
    Checks role field for 'admin' or 'super_admin', with is_staff fallback.
    """
    user_role = getattr(user, 'role', None)
    return user_role in ['admin', 'super_admin'] or user.is_staff


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
    pagination_class = None  # No pagination - templates are typically few in number
    
    def get_queryset(self):
        user = self.request.user
        queryset = ActivityTemplate.objects.all()
        
        # Filter by ownership
        mine_only = self.request.query_params.get('mine_only', 'false')
        if mine_only.lower() == 'true':
            queryset = queryset.filter(owner=user)
        elif not is_admin_user(user):
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
    
    def update(self, request, *args, **kwargs):
        """Override update to return DetailSerializer response with columns"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
        
        # Return response using DetailSerializer to include columns
        response_serializer = ActivityTemplateDetailSerializer(instance)
        return Response(response_serializer.data)
    
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
        if not is_admin_user(user):
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
        if not is_admin_user(request.user) and sheet.owner != request.user:
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
        if not is_admin_user(self.request.user) and obj.sheet.owner != self.request.user:
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
            if not is_admin_user(request.user) and template.owner != request.user:
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


class ExcelColumnDetectionView(views.APIView):
    """
    POST: Detect column definitions from an uploaded Excel file.
    Used by frontend to auto-detect columns when creating templates from Excel.
    
    Body (multipart/form-data):
    - file: Excel file (.xlsx, .xls)
    
    Returns list of detected columns with name, type, and width.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        from .excel_service import detect_columns_from_excel
        
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
        
        # Check file size (max 5MB for column detection)
        max_size = 5 * 1024 * 1024  # 5MB
        if uploaded_file.size > max_size:
            return Response(
                {'error': 'حجم الملف كبير جداً. الحد الأقصى 5 ميجابايت',
                 'error_en': 'File too large. Maximum size is 5MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            columns = detect_columns_from_excel(uploaded_file.read())
            
            if not columns:
                return Response({
                    'success': False,
                    'error': 'لم يتم العثور على أعمدة في الملف',
                    'error_en': 'No columns found in file',
                    'columns': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'columns': columns,
                'column_count': len(columns),
                'message': f'تم اكتشاف {len(columns)} عمود',
                'message_en': f'Detected {len(columns)} columns'
            })
            
        except ValueError as e:
            return Response({
                'success': False,
                'error': str(e),
                'columns': []
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'حدث خطأ أثناء قراءة الملف: {str(e)}',
                'error_en': f'Error reading file: {str(e)}',
                'columns': []
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
                'is_active_title': template.is_active_title,
            })
        
        return Response(data)


class ActiveTitleView(views.APIView):
    """
    GET: Get the currently active title (the one users auto-load).
    Returns the active published title or null if none is set.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            active_title = ActivityTemplate.objects.get(
                is_active_title=True,
                status='published',
                is_deleted=False
            )
            
            return Response({
                'id': active_title.id,
                'name': active_title.name,
                'description': active_title.description,
                'column_count': active_title.template_columns.count(),
                'is_active_title': True
            })
        except ActivityTemplate.DoesNotExist:
            return Response({
                'id': None,
                'name': None,
                'description': None,
                'message': 'لا يوجد عنوان نشط حالياً'
            })


class TitleDetailView(views.APIView):
    """
    GET: Get details of a specific title by ID (allows loading non-active templates).
    Includes deleted/archived templates for read-only viewing of user sheets.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, title_id):
        try:
            # Allow retrieving even deleted templates (for viewing user sheets from deleted templates)
            title = ActivityTemplate.objects.get(id=title_id)
            
            return Response({
                'id': title.id,
                'name': title.name,
                'description': title.description,
                'column_count': title.template_columns.count(),
                'is_active_title': title.is_active_title,
                'status': title.status,
                'is_deleted': title.is_deleted  # Include deletion status for frontend
            })
        except ActivityTemplate.DoesNotExist:
            return Response(
                {'error': 'العنوان غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )


class SetActiveTitleView(views.APIView):
    """
    POST: Set a title as the active title (admin only).
    Only one title can be active at a time.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request, title_id):
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id,
            status='published',
            is_deleted=False
        )
        
        # Toggle the active state (multiple templates can be active now)
        template.is_active_title = True
        template.save(update_fields=['is_active_title', 'updated_at'])
        
        return Response({
            'success': True,
            'message': f'تم تعيين "{template.name}" كعنوان نشط',
            'title_id': template.id,
            'title_name': template.name,
        })


class DeactivateTitleView(views.APIView):
    """
    POST: Deactivate a title (admin only).
    Users will need to select a title manually or wait for new active title.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request, title_id):
        template = get_object_or_404(
            ActivityTemplate,
            pk=title_id
        )
        
        if not template.is_active_title:
            return Response({
                'error': 'هذا العنوان ليس نشطاً'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        template.is_active_title = False
        template.save(update_fields=['is_active_title', 'updated_at'])
        
        return Response({
            'success': True,
            'message': f'تم إلغاء تنشيط "{template.name}"',
        })


class SubmitSheetView(views.APIView):
    """
    POST: Submit a sheet to admin. Once submitted, the sheet cannot be edited.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, sheet_id):
        sheet = get_object_or_404(
            ActivitySheet,
            pk=sheet_id,
            owner=request.user,
            is_active=True
        )
        
        if sheet.is_submitted:
            return Response({
                'error': 'هذا الجدول تم تقديمه مسبقاً'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate sheet has data
        if sheet.row_count == 0:
            return Response({
                'error': 'لا يمكن تقديم جدول فارغ'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        sheet.is_submitted = True
        sheet.submitted_at = timezone.now()
        sheet.save(update_fields=['is_submitted', 'submitted_at', 'updated_at'])
        
        return Response({
            'success': True,
            'message': 'تم تقديم الجدول بنجاح',
            'sheet_id': sheet.id,
            'submitted_at': sheet.submitted_at.isoformat(),
        })


class AdminSubmittedSheetsView(views.APIView):
    """
    GET: Get all submitted sheets from all users (admin only).
    Supports filtering by title_id and pagination.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request):
        from .constants import USER_ROWS_PER_PAGE
        
        # Filter params
        title_id = request.query_params.get('title_id')
        search = request.query_params.get('search', '')
        
        # Pagination params
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except ValueError:
            page = 1
            page_size = 20
        
        # Build queryset - only submitted sheets
        queryset = ActivitySheet.objects.filter(
            is_submitted=True,
            is_active=True
        ).select_related('owner', 'template').order_by('-submitted_at')
        
        # Filter by title
        if title_id:
            queryset = queryset.filter(template_id=title_id)
        
        # Search by sheet name or owner username
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(owner__username__icontains=search) |
                Q(owner__first_name__icontains=search) |
                Q(owner__last_name__icontains=search)
            )
        
        # Count total
        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        sheets = queryset[start_idx:end_idx]
        
        data = []
        for sheet in sheets:
            data.append({
                'id': sheet.id,
                'name': sheet.name,
                'description': sheet.description,
                'template_id': sheet.template_id,
                'template_name': sheet.template.name if sheet.template else '(محذوف)',
                'owner_id': sheet.owner_id,
                'owner_name': sheet.owner.full_name or sheet.owner.username,
                'owner_username': sheet.owner.username,
                'row_count': sheet.row_count,
                'submitted_at': sheet.submitted_at.isoformat() if sheet.submitted_at else None,
                'created_at': sheet.created_at.isoformat(),
            })
        
        return Response({
            'sheets': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }
        })


class AdminTemplateActivitiesView(views.APIView):
    """
    GET: Get all submitted activities for a specific template (admin only).
    Returns individual activity rows (not sheets), grouped by user if needed.
    Supports filtering by user_id and search in activity data.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, template_id):
        # Get the template first
        template = get_object_or_404(
            ActivityTemplate.objects.prefetch_related(
                'template_columns__column_definition'
            ),
            pk=template_id,
            is_deleted=False
        )
        
        # Filter params
        user_id = request.query_params.get('user_id')
        search = request.query_params.get('search', '')
        status_filter = request.query_params.get('status', 'submitted')  # Default to 'submitted', or 'draft', 'all'
        
        # Pagination params
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except ValueError:
            page = 1
            page_size = 20
        
        # Build queryset for activity rows
        queryset = ActivitySheetRow.objects.filter(
            sheet__template_id=template_id,
            sheet__is_active=True
        ).select_related('sheet__owner', 'sheet__template').order_by('-updated_at')
        
        # Filter by submitted status - default is submitted only
        if status_filter == 'submitted':
            queryset = queryset.filter(is_submitted=True)
        elif status_filter == 'draft':
            queryset = queryset.filter(is_submitted=False)
        # if status_filter == 'all' or empty string, show all activities
        
        # Filter by user
        if user_id:
            queryset = queryset.filter(sheet__owner_id=user_id)
        
        # Search in row data (JSON field) and owner info
        if search:
            queryset = queryset.filter(
                Q(row_data__icontains=search) | 
                Q(sheet__owner__username__icontains=search) |
                Q(sheet__owner__first_name__icontains=search) |
                Q(sheet__owner__last_name__icontains=search)
            )
        
        # Count total
        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        rows = queryset[start_idx:end_idx]
        
        # Build columns list
        columns = []
        for tc in template.template_columns.all().order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'id': col_def.id,
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'order': tc.order,
            })
        
        # Build activities list
        activities = []
        for row in rows:
            owner = row.sheet.owner
            row_data = row.data or {}
            activities.append({
                'id': row.id,
                'title': row_data.get('title', row_data.get('عنوان_النشاط', f'نشاط #{row.row_number}')),
                'description': row_data.get('description', row_data.get('وصف_النشاط', '')),
                'data': row_data,
                'styles': row.styles or {},
                'status': 'submitted' if row.is_submitted else 'draft',
                'is_submitted': row.is_submitted,
                'submitted_at': row.submitted_at.isoformat() if row.submitted_at else None,
                'row_number': row.row_number,
                'sheet_id': row.sheet_id,
                'owner_id': owner.id,
                'author': owner.full_name or owner.username,
                'owner_username': owner.username,
                'created_at': row.created_at.isoformat(),
                'updated_at': row.updated_at.isoformat(),
            })
        
        # Get unique users with submission counts
        from django.db.models import Count
        
        user_stats = ActivitySheetRow.objects.filter(
            sheet__template_id=template_id,
            sheet__is_active=True,
            is_submitted=True  # Only count submitted activities
        ).values(
            'sheet__owner_id',
            'sheet__owner__username',
            'sheet__owner__first_name',
            'sheet__owner__last_name'
        ).annotate(
            submitted_count=Count('id')
        ).order_by('-submitted_count')
        
        users_list = []
        for u in user_stats:
            full_name = f"{u['sheet__owner__first_name'] or ''} {u['sheet__owner__last_name'] or ''}".strip()
            users_list.append({
                'id': u['sheet__owner_id'],
                'username': u['sheet__owner__username'],
                'full_name': full_name or u['sheet__owner__username'],
                'submitted_count': u['submitted_count'],
            })
        
        return Response({
            'template': {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'status': template.status,
            },
            'columns': columns,
            'activities': activities,
            'users': users_list,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }
        })


class AdminTemplateActivitiesExportView(views.APIView):
    """
    GET: Export activities for a specific template (admin only).
    Supports batched fetching for large datasets.
    Returns data without full pagination overhead for efficient export.
    
    Query params:
    - user_id: Filter by specific user
    - search: Search in row data and owner info
    - status: 'submitted', 'draft', or 'all' (default: submitted)
    - page: Page number for batched fetching (default: 1)
    - page_size: Items per page (default: 100, max: 500)
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, template_id):
        # Get the template first to ensure it exists
        template = get_object_or_404(
            ActivityTemplate,
            pk=template_id,
            is_deleted=False
        )
        
        # Get query parameters
        user_id = request.query_params.get('user_id')
        search = request.query_params.get('search', '').strip()
        status_filter = request.query_params.get('status', 'submitted')  # Default to submitted
        
        # Pagination for batched export (larger page sizes allowed)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(500, max(1, int(request.query_params.get('page_size', 100))))
        except ValueError:
            page = 1
            page_size = 100
        
        # Build queryset for activity rows
        queryset = ActivitySheetRow.objects.filter(
            sheet__template_id=template_id,
            sheet__is_active=True
        ).select_related('sheet__owner', 'sheet__template').order_by('row_number', '-updated_at')
        
        # Filter by submitted status
        if status_filter == 'submitted':
            queryset = queryset.filter(is_submitted=True)
        elif status_filter == 'draft':
            queryset = queryset.filter(is_submitted=False)
        
        # Filter by user
        if user_id:
            queryset = queryset.filter(sheet__owner_id=user_id)
        
        # Search in row data and owner info
        if search:
            queryset = queryset.filter(
                Q(row_data__icontains=search) | 
                Q(sheet__owner__username__icontains=search) |
                Q(sheet__owner__first_name__icontains=search) |
                Q(sheet__owner__last_name__icontains=search)
            )
        
        # Count total
        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        rows = queryset[start_idx:end_idx]
        
        # Build columns list
        columns = []
        for tc in template.template_columns.all().order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'id': col_def.id,
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'order': tc.order,
            })
        
        # Build activities list (simplified for export)
        activities = []
        for row in rows:
            owner = row.sheet.owner
            row_data = row.data or {}
            activities.append({
                'id': row.id,
                'data': row_data,
                'styles': row.styles or {},
                'is_submitted': row.is_submitted,
                'submitted_at': row.submitted_at.isoformat() if row.submitted_at else None,
                'row_number': row.row_number,
                'owner_id': owner.id,
                'author': owner.full_name or owner.username,
                'owner_username': owner.username,
            })
        
        return Response({
            'template': {
                'id': template.id,
                'name': template.name,
            },
            'columns': columns,
            'activities': activities,
            'export_info': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_more': page < total_pages,
                'fetched_count': len(activities),
            }
        })


class AdminTemplateUsersView(views.APIView):
    """
    GET: Get users with submission counts for a specific template (admin only).
    Supports filtering by search query on user names.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, template_id):
        # Get the template first to ensure it exists
        template = get_object_or_404(
            ActivityTemplate,
            pk=template_id,
            is_deleted=False
        )
        
        # Search filter
        search = request.query_params.get('search', '').strip()
        
        # Get unique users with submission counts
        from django.db.models import Count
        
        user_stats = ActivitySheetRow.objects.filter(
            sheet__template_id=template_id,
            sheet__is_active=True,
            is_submitted=True  # Only count submitted activities
        ).values(
            'sheet__owner_id',
            'sheet__owner__username',
            'sheet__owner__first_name',
            'sheet__owner__last_name'
        ).annotate(
            submitted_count=Count('id')
        )
        
        # Apply search filter if provided
        if search:
            user_stats = user_stats.filter(
                Q(sheet__owner__username__icontains=search) |
                Q(sheet__owner__first_name__icontains=search) |
                Q(sheet__owner__last_name__icontains=search)
            )
        
        user_stats = user_stats.order_by('-submitted_count')
        
        users_list = []
        for u in user_stats:
            full_name = f"{u['sheet__owner__first_name'] or ''} {u['sheet__owner__last_name'] or ''}".strip()
            users_list.append({
                'id': u['sheet__owner_id'],
                'username': u['sheet__owner__username'],
                'full_name': full_name or u['sheet__owner__username'],
                'submitted_count': u['submitted_count'],
            })
        
        return Response({
            'template': {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'status': template.status,
            },
            'users': users_list,
            'total_count': len(users_list),
        })


class UserAllSheetsView(views.APIView):
    """
    GET: Get all user's sheets regardless of which title they belong to.
    This is for showing "recent sheets" even if title is deleted/deactivated.
    Includes sheets from deleted/archived templates.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get all user's active sheets (including those with deleted templates)
        sheets = ActivitySheet.objects.filter(
            owner=request.user,
            is_active=True
        ).select_related('template').order_by('-updated_at')
        
        data = []
        for sheet in sheets:
            data.append({
                'id': sheet.id,
                'name': sheet.name,
                'description': sheet.description,
                'template_id': sheet.template_id,
                'template_name': sheet.template.name if sheet.template else '(عنوان محذوف)',
                'template_status': sheet.template.status if sheet.template else 'deleted',
                'template_is_active': sheet.template.is_active_title if sheet.template else False,
                'row_count': sheet.row_count,
                'is_submitted': sheet.is_submitted,
                'submitted_at': sheet.submitted_at.isoformat() if sheet.submitted_at else None,
                'created_at': sheet.created_at.isoformat(),
                'updated_at': sheet.updated_at.isoformat(),
            })
        
        return Response({
            'sheets': data,
            'count': len(data),
        })


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
            'is_submitted': sheet.is_submitted,
            'submitted_at': sheet.submitted_at.isoformat() if sheet.submitted_at else None,
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
        
        # Check if sheet is submitted - cannot edit
        if sheet.is_submitted:
            return Response(
                {'error': 'هذا الجدول تم تقديمه ولا يمكن تعديله'},
                status=status.HTTP_403_FORBIDDEN
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
        
        # Check if sheet is submitted - cannot edit
        if sheet.is_submitted:
            return Response(
                {'error': 'هذا الجدول تم تقديمه ولا يمكن تعديله'},
                status=status.HTTP_403_FORBIDDEN
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
                    max_order=Max('row_order')
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
        
        # Prevent deletion of submitted sheets
        if sheet.is_submitted:
            return Response(
                {'error': 'لا يمكن حذف جدول تم تقديمه'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        sheet.is_active = False
        sheet.save(update_fields=['is_active', 'updated_at'])
        
        return Response({'message': 'تم حذف الجدول بنجاح'}, status=status.HTTP_200_OK)


class AdminSheetDataView(views.APIView):
    """
    GET: Admin endpoint to view any sheet's data (read-only).
    Supports pagination, sorting, and filtering.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get(self, request, sheet_id):
        import json
        
        sheet = get_object_or_404(
            ActivitySheet.objects.select_related('template', 'owner'),
            pk=sheet_id
        )
        
        # Parse pagination
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(500, max(1, int(request.query_params.get('page_size', 100))))
        except ValueError:
            page = 1
            page_size = 100
        
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
        
        # Get columns from template or snapshot
        columns = sheet.column_snapshot or []
        if not columns and sheet.template:
            columns = []
            for tc in sheet.template.template_columns.all().order_by('order'):
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
        
        return Response({
            'sheet_id': sheet.id,
            'sheet_name': sheet.name,
            'sheet_description': sheet.description,
            'is_submitted': sheet.is_submitted,
            'submitted_at': sheet.submitted_at.isoformat() if sheet.submitted_at else None,
            'owner_id': sheet.owner_id,
            'owner_name': sheet.owner.full_name or sheet.owner.username,
            'owner_username': sheet.owner.username,
            'template_id': sheet.template_id,
            'template_name': sheet.template.name if sheet.template else '(محذوف)',
            'rows': rows_data,
            'columns': columns,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }
        })


# ============================================================================
# USER ACTIVITY PAGE - Simplified endpoint for /activities/local
# ============================================================================

class UserActivityPageView(views.APIView):
    """
    GET: Get everything needed for the user activity page (/activities/local).
    
    Returns:
    - templates: All published templates (both active and inactive)
    - has_active_templates: Whether there are any active templates
    
    This is a simplified endpoint for regular users.
    Templates with is_active_title=False are shown but user cannot add/submit activities.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get all published templates (both active and inactive)
        published_templates = ActivityTemplate.objects.filter(
            status='published',
            is_deleted=False
        ).order_by('-is_active_title', '-updated_at')  # Active ones first
        
        if not published_templates.exists():
            return Response({
                'has_active_templates': False,
                'templates': [],
                'active_templates': [],  # For backward compatibility
                'message': 'لا يوجد نموذج منشور حالياً. يرجى الانتظار حتى يقوم المسؤول بنشر نموذج.'
            })
        
        # Serialize all published templates
        templates_data = [
            {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'notes': template.notes,
                'header_image': template.header_image.url if template.header_image else None,
                'column_count': template.template_columns.count(),
                'is_active_title': template.is_active_title,
            }
            for template in published_templates
        ]
        
        # Check if there are any active templates
        has_active = published_templates.filter(is_active_title=True).exists()
        
        # For backward compatibility, also include active_templates list
        active_templates_data = [t for t in templates_data if t['is_active_title']]
        
        return Response({
            'has_active_templates': has_active,
            'templates': templates_data,
            'active_templates': active_templates_data,  # For backward compatibility
            'count': len(templates_data)
        })


# ============================================================================
# USER ACTIVITIES - Per-user activities for a specific template
# ============================================================================

class UserActivitiesListCreateView(views.APIView):
    """
    GET: List user's activities (rows) for a specific template
    POST: Create a new activity (row) for the user
    
    Each user sees only their own activities.
    Activities are stored as rows in a sheet per user per template.
    """
    permission_classes = [IsAuthenticated]
    
    def get_or_create_user_sheet(self, template, user):
        """Get or create a sheet for the user for this template."""
        sheet, created = ActivitySheet.objects.get_or_create(
            template=template,
            owner=user,
            defaults={
                'name': f'{template.name} - {user.full_name or user.username}',
                'description': '',
                'is_active': True,
            }
        )
        return sheet
    
    def get(self, request, template_id):
        # Validate template exists and is published
        try:
            template = ActivityTemplate.objects.get(
                id=template_id,
                status='published',
                is_deleted=False
            )
        except ActivityTemplate.DoesNotExist:
            return Response({
                'error': 'النموذج غير موجود أو غير منشور'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get user's sheet for this template (if exists)
        try:
            sheet = ActivitySheet.objects.get(
                template=template,
                owner=request.user,
                is_active=True
            )
        except ActivitySheet.DoesNotExist:
            # No sheet yet - return empty list
            return Response({
                'template': {
                    'id': template.id,
                    'name': template.name,
                    'description': template.description,
                    'is_active_title': template.is_active_title,
                },
                'activities': [],
                'columns': self._get_template_columns(template),
                'pagination': {
                    'page': 1,
                    'page_size': 20,
                    'total_count': 0,
                    'total_pages': 0,
                    'has_next': False,
                    'has_prev': False,
                }
            })
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        # Get rows for user's sheet
        rows = sheet.rows.all().order_by('-updated_at')
        total_count = rows.count()
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1
        
        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        paginated_rows = rows[start:end]
        
        # Get column definitions for title display
        columns = self._get_template_columns(template)
        
        # Build activities list
        activities = []
        for row in paginated_rows:
            # Extract title from first column or specific field
            first_col_key = columns[0]['key'] if columns else None
            title = row.data.get(first_col_key, 'نشاط') if first_col_key else 'نشاط'
            
            # Build description from all visible columns
            desc_parts = []
            for col in columns[1:4]:  # Use next 3 columns for description
                val = row.data.get(col['key'], '')
                if val is not None and val != '':
                    desc_parts.append(str(val))
            description = ' - '.join(desc_parts) if desc_parts else ''
            
            activities.append({
                'id': row.id,
                'title': title or 'نشاط جديد',
                'description': description,
                'data': row.data,
                'styles': row.styles,
                'attachments': self._get_row_attachments(row),
                'author': request.user.full_name or request.user.username,
                'date': row.updated_at.isoformat(),
                'created_at': row.created_at.isoformat(),
                'updated_at': row.updated_at.isoformat(),
                'status': 'submitted' if row.is_submitted else 'draft',
                'is_submitted': row.is_submitted,
                'submitted_at': row.submitted_at.isoformat() if row.submitted_at else None,
            })
        
        return Response({
            'template': {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'is_active_title': template.is_active_title,
            },
            'sheet': {
                'id': sheet.id,
                'name': sheet.name,
                'is_submitted': sheet.is_submitted,
                'submitted_at': sheet.submitted_at.isoformat() if sheet.submitted_at else None,
            },
            'activities': activities,
            'columns': columns,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1,
            }
        })
    
    def _get_template_columns(self, template):
        """Get column definitions for template with mandatory columns at the end."""
        columns = []
        for tc in template.template_columns.select_related('column_definition').order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'is_visible': tc.is_visible,
                'options': col_def.options or [],
                'allows_attachment': col_def.allows_attachment,
                'attachment_required': col_def.attachment_required,
            })
        
        # Sort columns: non-mandatory first, then mandatory at the end
        def is_mandatory_column(col):
            key = col.get('key', '')
            # Check if key starts with any mandatory column key prefix
            for mandatory_key in MANDATORY_COLUMN_KEYS:
                if key.startswith(mandatory_key):
                    return True
            return False
        
        non_mandatory = [col for col in columns if not is_mandatory_column(col)]
        mandatory = [col for col in columns if is_mandatory_column(col)]
        return non_mandatory + mandatory
    
    def _get_row_attachments(self, row):
        """Get attachments for a row."""
        from .models import ActivityRowAttachment
        attachments = ActivityRowAttachment.objects.filter(row=row)
        return [
            {
                'id': att.id,
                'column_key': att.column_key,
                'original_filename': att.original_filename,
                'file_size': att.file_size,
                'mime_type': att.mime_type,
                'is_image': att.is_image,
                'download_url': att.download_url,
                'preview_url': att.preview_url,
                'created_at': att.created_at.isoformat(),
            }
            for att in attachments
        ]
    
    def post(self, request, template_id):
        """Create a new activity (row) for the user."""
        # Validate template exists and is published
        try:
            template = ActivityTemplate.objects.get(
                id=template_id,
                status='published',
                is_deleted=False
            )
        except ActivityTemplate.DoesNotExist:
            return Response({
                'error': 'النموذج غير موجود أو غير منشور'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if template is active - users cannot add activities to inactive templates
        if not template.is_active_title:
            return Response({
                'error': 'لا يمكن إضافة أنشطة إلى نموذج غير نشط. يرجى الانتظار حتى يقوم المسؤول بتفعيل النموذج.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get or create user's sheet for this template
        sheet = self.get_or_create_user_sheet(template, request.user)
        
        # Check if sheet is submitted
        if sheet.is_submitted:
            return Response({
                'error': 'لا يمكن إضافة أنشطة جديدة بعد تقديم النموذج'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get data from request
        data = request.data.get('data', {})
        styles = request.data.get('styles', {})
        
        # Get next row order
        max_order = sheet.rows.aggregate(Max('row_order'))['row_order__max'] or 0
        next_order = max_order + 1
        
        # Create the row
        row = ActivitySheetRow.objects.create(
            sheet=sheet,
            row_number=next_order,
            row_order=next_order,
            data=data,
            styles=styles,
            height=32
        )
        
        # Update sheet row count
        sheet.update_row_count()
        
        # Get columns for response
        columns = self._get_template_columns(template)
        first_col_key = columns[0]['key'] if columns else None
        title = data.get(first_col_key, 'نشاط') if first_col_key else 'نشاط'
        
        return Response({
            'id': row.id,
            'title': title or 'نشاط جديد',
            'data': row.data,
            'styles': row.styles,
            'author': request.user.full_name or request.user.username,
            'date': row.updated_at.isoformat(),
            'created_at': row.created_at.isoformat(),
            'updated_at': row.updated_at.isoformat(),
            'status': 'draft',
            'is_submitted': False,
        }, status=status.HTTP_201_CREATED)


class UserActivityDetailView(views.APIView):
    """
    GET: Get a single activity (row) by ID
    PUT/PATCH: Update an activity (if sheet not submitted)
    DELETE: Delete an activity (if sheet not submitted)
    
    User can only access their own activities.
    """
    permission_classes = [IsAuthenticated]
    
    def get_activity(self, activity_id, user):
        """Get activity row owned by user."""
        try:
            row = ActivitySheetRow.objects.select_related('sheet', 'sheet__template').get(
                id=activity_id,
                sheet__owner=user,
                sheet__is_active=True
            )
            return row
        except ActivitySheetRow.DoesNotExist:
            return None
    
    def get(self, request, activity_id):
        """Get single activity details."""
        row = self.get_activity(activity_id, request.user)
        if not row:
            return Response({
                'error': 'النشاط غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
        
        template = row.sheet.template
        columns = self._get_template_columns(template) if template else []
        first_col_key = columns[0]['key'] if columns else None
        title = row.data.get(first_col_key, 'نشاط') if first_col_key else 'نشاط'
        
        return Response({
            'id': row.id,
            'title': title or 'نشاط جديد',
            'data': row.data,
            'styles': row.styles,
            'attachments': self._get_row_attachments(row),
            'author': request.user.full_name or request.user.username,
            'date': row.updated_at.isoformat(),
            'created_at': row.created_at.isoformat(),
            'updated_at': row.updated_at.isoformat(),
            'status': 'submitted' if row.is_submitted else 'draft',
            'is_submitted': row.is_submitted,
            'submitted_at': row.submitted_at.isoformat() if row.submitted_at else None,
            'sheet': {
                'id': row.sheet.id,
                'name': row.sheet.name,
                'is_submitted': row.sheet.is_submitted,
            },
            'template': {
                'id': template.id,
                'name': template.name,
            } if template else None,
            'columns': columns,
        })
    
    def _get_template_columns(self, template):
        """Get column definitions for template with mandatory columns at the end."""
        columns = []
        for tc in template.template_columns.select_related('column_definition').order_by('order'):
            col_def = tc.column_definition
            columns.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'is_visible': tc.is_visible,
                'options': col_def.options or [],
                'allows_attachment': col_def.allows_attachment,
                'attachment_required': col_def.attachment_required,
            })
        
        # Sort columns: non-mandatory first, then mandatory at the end
        def is_mandatory_column(col):
            key = col.get('key', '')
            # Check if key starts with any mandatory column key prefix
            for mandatory_key in MANDATORY_COLUMN_KEYS:
                if key.startswith(mandatory_key):
                    return True
            return False
        
        non_mandatory = [col for col in columns if not is_mandatory_column(col)]
        mandatory = [col for col in columns if is_mandatory_column(col)]
        return non_mandatory + mandatory
    
    def _get_row_attachments(self, row):
        """Get attachments for a row, grouped by column_key."""
        from .models import ActivityRowAttachment
        attachments = ActivityRowAttachment.objects.filter(row=row)
        result = {}
        for attachment in attachments:
            if attachment.column_key not in result:
                result[attachment.column_key] = []
            result[attachment.column_key].append({
                'id': attachment.id,
                'column_key': attachment.column_key,
                'original_filename': attachment.original_filename,
                'file_size': attachment.file_size,
                'mime_type': attachment.mime_type,
                'is_image': attachment.is_image,
                'download_url': attachment.download_url,
                'preview_url': attachment.preview_url,
                'created_at': attachment.created_at.isoformat(),
            })
        return result
    
    def put(self, request, activity_id):
        """Update activity (full update)."""
        return self._update_activity(request, activity_id, partial=False)
    
    def patch(self, request, activity_id):
        """Update activity (partial update)."""
        return self._update_activity(request, activity_id, partial=True)
    
    def _update_activity(self, request, activity_id, partial=False):
        """Update activity row."""
        row = self.get_activity(activity_id, request.user)
        if not row:
            return Response({
                'error': 'النشاط غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if activity is submitted (per-activity check)
        if row.is_submitted:
            return Response({
                'error': 'لا يمكن تعديل النشاط بعد تقديمه'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update data
        if 'data' in request.data:
            if partial:
                row.data.update(request.data['data'])
            else:
                row.data = request.data['data']
        
        if 'styles' in request.data:
            if partial:
                row.styles.update(request.data['styles'])
            else:
                row.styles = request.data['styles']
        
        row.save()
        
        template = row.sheet.template
        columns = self._get_template_columns(template) if template else []
        first_col_key = columns[0]['key'] if columns else None
        title = row.data.get(first_col_key, 'نشاط') if first_col_key else 'نشاط'
        
        return Response({
            'id': row.id,
            'title': title or 'نشاط جديد',
            'data': row.data,
            'styles': row.styles,
            'author': request.user.full_name or request.user.username,
            'date': row.updated_at.isoformat(),
            'created_at': row.created_at.isoformat(),
            'updated_at': row.updated_at.isoformat(),
            'status': 'draft',
            'is_submitted': False,
        })
    
    def delete(self, request, activity_id):
        """Delete activity row."""
        row = self.get_activity(activity_id, request.user)
        if not row:
            return Response({
                'error': 'النشاط غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if activity is submitted (per-activity check)
        if row.is_submitted:
            return Response({
                'error': 'لا يمكن حذف النشاط بعد تقديمه'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        sheet = row.sheet
        row.delete()
        
        # Update sheet row count
        sheet.update_row_count()
        
        return Response({
            'success': True,
            'message': 'تم حذف النشاط بنجاح'
        })


class UserActivitySubmitView(views.APIView):
    """
    POST: Submit a single activity (row) by ID.
    Once submitted, that activity cannot be edited.
    Each activity is submitted individually, not the whole sheet.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, activity_id):
        """Submit a single activity."""
        from django.utils import timezone
        
        # Get the activity owned by user
        try:
            row = ActivitySheetRow.objects.select_related('sheet', 'sheet__template').get(
                id=activity_id,
                sheet__owner=request.user,
                sheet__is_active=True
            )
        except ActivitySheetRow.DoesNotExist:
            return Response({
                'error': 'النشاط غير موجود'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if template is active - users cannot submit activities for inactive templates
        if row.sheet.template and not row.sheet.template.is_active_title:
            return Response({
                'error': 'لا يمكن تقديم أنشطة لنموذج غير نشط. يرجى الانتظار حتى يقوم المسؤول بتفعيل النموذج.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already submitted
        if row.is_submitted:
            return Response({
                'error': 'تم تقديم هذا النشاط مسبقاً'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Submit the activity
        row.is_submitted = True
        row.submitted_at = timezone.now()
        row.save()
        
        return Response({
            'success': True,
            'message': 'تم تقديم النشاط بنجاح',
            'activity_id': row.id,
            'submitted_at': row.submitted_at.isoformat()
        })


class UserTemplateSubmitView(views.APIView):
    """
    DEPRECATED: Use UserActivitySubmitView instead for per-activity submission.
    This view now submits ALL unsubmitted activities for a template at once.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, template_id):
        """Submit all unsubmitted activities for a template."""
        from django.utils import timezone
        
        # Validate template exists and is published
        try:
            template = ActivityTemplate.objects.get(
                id=template_id,
                status='published',
                is_deleted=False
            )
        except ActivityTemplate.DoesNotExist:
            return Response({
                'error': 'النموذج غير موجود أو غير منشور'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if template is active - users cannot submit activities for inactive templates
        if not template.is_active_title:
            return Response({
                'error': 'لا يمكن تقديم أنشطة لنموذج غير نشط. يرجى الانتظار حتى يقوم المسؤول بتفعيل النموذج.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get user's sheet for this template
        try:
            sheet = ActivitySheet.objects.get(
                template=template,
                owner=request.user,
                is_active=True
            )
        except ActivitySheet.DoesNotExist:
            return Response({
                'error': 'لا يوجد نموذج للتقديم'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get unsubmitted activities
        unsubmitted = sheet.rows.filter(is_submitted=False)
        count = unsubmitted.count()
        
        if count == 0:
            return Response({
                'error': 'لا توجد أنشطة غير مقدمة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Submit all unsubmitted activities
        now = timezone.now()
        unsubmitted.update(is_submitted=True, submitted_at=now)
        
        return Response({
            'success': True,
            'message': f'تم تقديم {count} نشاط بنجاح',
            'submitted_count': count,
            'submitted_at': now.isoformat()
        })


# ============================================================================
# Attachment Views
# ============================================================================

class RowAttachmentListCreateView(views.APIView):
    """
    GET: List all attachments for a row
    POST: Upload a new attachment for a row
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get(self, request, row_id):
        """List all attachments for a row."""
        from .models import ActivityRowAttachment
        from .serializers import ActivityRowAttachmentSerializer
        
        row = get_object_or_404(ActivitySheetRow, id=row_id)
        
        # Check permissions - owner or admin
        if row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لعرض المرفقات'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        attachments = ActivityRowAttachment.objects.filter(row=row)
        
        # Optional: filter by column_key
        column_key = request.query_params.get('column_key')
        if column_key:
            attachments = attachments.filter(column_key=column_key)
        
        serializer = ActivityRowAttachmentSerializer(attachments, many=True)
        return Response(serializer.data)
    
    def post(self, request, row_id):
        """Upload a new attachment."""
        from .models import ActivityRowAttachment
        from .serializers import ActivityRowAttachmentCreateSerializer, ActivityRowAttachmentSerializer
        
        row = get_object_or_404(ActivitySheetRow, id=row_id)
        
        # Check permissions - owner or admin
        if row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لرفع مرفقات'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if row is already submitted
        if row.is_submitted:
            return Response(
                {'error': 'لا يمكن إضافة مرفقات لنشاط مقدم'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate column allows attachments
        column_key = request.data.get('column_key')
        if column_key:
            template = row.sheet.template
            template_column = template.template_columns.filter(
                column_definition__key=column_key
            ).select_related('column_definition').first()
            if template_column and template_column.column_definition:
                if not template_column.column_definition.allows_attachment:
                    return Response(
                        {'error': 'هذا العمود لا يسمح بالمرفقات'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        # Prepare data
        data = {
            'row_id': row_id,
            'column_key': column_key,
            'file': request.FILES.get('file')
        }
        
        serializer = ActivityRowAttachmentCreateSerializer(data=data)
        if serializer.is_valid():
            attachment = serializer.save()
            return Response(
                ActivityRowAttachmentSerializer(attachment).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AttachmentDetailView(views.APIView):
    """
    GET: Get attachment metadata
    DELETE: Delete an attachment
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, attachment_id):
        """Get attachment metadata (without file content)."""
        from .models import ActivityRowAttachment
        from .serializers import ActivityRowAttachmentSerializer
        
        attachment = get_object_or_404(ActivityRowAttachment, id=attachment_id)
        
        # Check permissions
        if attachment.row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لعرض هذا المرفق'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ActivityRowAttachmentSerializer(attachment)
        return Response(serializer.data)
    
    def delete(self, request, attachment_id):
        """Delete an attachment."""
        from .models import ActivityRowAttachment
        
        attachment = get_object_or_404(ActivityRowAttachment, id=attachment_id)
        
        # Check permissions - owner or admin
        if attachment.row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لحذف هذا المرفق'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if row is already submitted
        if attachment.row.is_submitted:
            return Response(
                {'error': 'لا يمكن حذف مرفقات نشاط مقدم'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttachmentDownloadView(views.APIView):
    """
    GET: Download attachment as base64 (for non-images or explicit download)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, attachment_id):
        """Download attachment as base64."""
        import base64
        from .models import ActivityRowAttachment
        
        attachment = get_object_or_404(ActivityRowAttachment, id=attachment_id)
        
        # Check permissions
        if attachment.row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لتحميل هذا المرفق'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Convert to base64
        file_base64 = base64.b64encode(attachment.file_content).decode('utf-8')
        
        return Response({
            'id': attachment.id,
            'filename': attachment.original_filename,
            'mime_type': attachment.mime_type,
            'file_size': attachment.file_size,
            'is_image': attachment.is_image,
            'content': file_base64
        })


class AttachmentPreviewView(views.APIView):
    """
    GET: Preview image attachment (returns base64 for images only)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, attachment_id):
        """Preview image attachment."""
        import base64
        from .models import ActivityRowAttachment
        
        attachment = get_object_or_404(ActivityRowAttachment, id=attachment_id)
        
        # Check permissions
        if attachment.row.sheet.owner != request.user and not is_admin_user(request.user):
            return Response(
                {'error': 'ليس لديك صلاحية لعرض هذا المرفق'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Only allow preview for images
        if not attachment.is_image:
            return Response(
                {'error': 'المعاينة متاحة للصور فقط'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert to base64
        file_base64 = base64.b64encode(attachment.file_content).decode('utf-8')
        
        return Response({
            'id': attachment.id,
            'filename': attachment.original_filename,
            'mime_type': attachment.mime_type,
            'is_image': True,
            'content': file_base64
        })


# ============================================================================
# DASHBOARD API VIEWS
# ============================================================================

from .dashboard_utils import (
    get_kpi_summary,
    get_status_distribution,
    get_quarterly_data,
    get_monthly_trend,
    get_programs_performance,
    get_full_dashboard_data,
    get_available_years,
    get_department_stats,
    get_program_detail,
    get_department_detail,
)
from .serializers import (
    DepartmentSerializer,
    KPISummarySerializer,
    StatusDistributionSerializer,
    QuarterlyDataSerializer,
    MonthlyTrendSerializer,
    ProgramPerformanceSerializer,
    FullDashboardSerializer,
    DepartmentStatsSerializer,
)
from .models import Department


class DepartmentListView(views.APIView):
    """
    GET: List all active departments.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get list of departments."""
        departments = Department.objects.filter(is_active=True)
        serializer = DepartmentSerializer(departments, many=True)
        return Response(serializer.data)


class DashboardSummaryView(views.APIView):
    """
    GET: Get KPI summary for dashboard.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get KPI summary."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_kpi_summary(year, department_id)
        serializer = KPISummarySerializer(data)
        return Response(serializer.data)


class StatusDistributionView(views.APIView):
    """
    GET: Get status distribution for donut chart.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get status distribution."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_status_distribution(year, department_id)
        serializer = StatusDistributionSerializer(data)
        return Response(serializer.data)


class QuarterlyDataView(views.APIView):
    """
    GET: Get quarterly planned vs actual data for bar chart.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get quarterly data."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_quarterly_data(year, department_id)
        serializer = QuarterlyDataSerializer(data)
        return Response(serializer.data)


class MonthlyTrendView(views.APIView):
    """
    GET: Get monthly trend data for line chart.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get monthly trend."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_monthly_trend(year, department_id)
        serializer = MonthlyTrendSerializer(data)
        return Response(serializer.data)


class ProgramsListView(views.APIView):
    """
    GET: Get programs (templates) performance data.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    - search: Optional search term
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get programs performance."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        search = request.query_params.get('search')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_programs_performance(year, department_id, search)
        
        # Transform to match frontend expected format
        programs = []
        for item in data:
            programs.append({
                'id': item['id'],
                'title': item['title'],
                'description': item['description'],
                'completionRate': item['completion_rate'],
                'departmentsCount': item['departments_count'],
                'activitiesTotal': item['activities_total'],
                'mode': item['mode'],
                'detailsLink': item['details_link']
            })
        
        return Response(programs)


class AvailableYearsView(views.APIView):
    """
    GET: Get list of years with activity data.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get available years."""
        years = get_available_years()
        return Response({'years': years})


class FullDashboardView(views.APIView):
    """
    GET: Get all dashboard data in a single request.
    
    Query params:
    - year: Year to calculate for (default: current year)
    - department_id: Optional department filter
    
    Returns all dashboard data to minimize API calls from frontend.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get full dashboard data."""
        year = int(request.query_params.get('year', timezone.now().year))
        department_id = request.query_params.get('department_id')
        
        if department_id:
            department_id = int(department_id)
        
        data = get_full_dashboard_data(year, department_id)
        
        # Transform programs to match frontend expected format
        programs = []
        for item in data['programs']:
            programs.append({
                'id': item['id'],
                'title': item['title'],
                'description': item['description'],
                'completionRate': item['completion_rate'],
                'departmentsCount': item['departments_count'],
                'activitiesTotal': item['activities_total'],
                'mode': item['mode'],
                'detailsLink': item['details_link']
            })
        
        # Build response matching frontend structure
        response_data = {
            'kpis': data['kpis'],
            'statusDistribution': data['status_distribution'],
            'quarterlyData': data['quarterly_data'],
            'monthlyTrend': data['monthly_trend'],
            'programs': programs,
            'availableYears': data['available_years'],
        }
        
        return Response(response_data)


class DepartmentStatsView(views.APIView):
    """
    GET: Get statistics for all departments (admin only).
    
    Query params:
    - year: Year to calculate for (default: current year)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get department statistics."""
        # Only admins can view all department stats
        if not is_admin_user(request.user):
            return Response(
                {'error': 'صلاحية الوصول مطلوبة'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        year = int(request.query_params.get('year', timezone.now().year))
        data = get_department_stats(year)
        serializer = DepartmentStatsSerializer(data, many=True)
        return Response(serializer.data)


class ProgramDetailView(views.APIView):
    """
    GET: Get detailed statistics for a specific program (template).
    
    URL params:
    - template_id: ID of the ActivityTemplate
    
    Query params:
    - year: Year to calculate for (default: current year)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, template_id):
        """Get program detail statistics."""
        year = int(request.query_params.get('year', timezone.now().year))
        
        data = get_program_detail(template_id, year)
        
        if data is None:
            return Response(
                {'error': 'البرنامج غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Transform to camelCase for frontend compatibility
        response_data = {
            'id': data['id'],
            'title': data['title'],
            'description': data['description'],
            'kpis': [
                {
                    'title': kpi['title'],
                    'icon': kpi['icon'],
                    'value': kpi['value'],
                    'valueLabel': kpi['value_label'],
                    'trend': kpi['trend'],
                    'percentage': kpi['percentage'],
                    'footerText': kpi['footer_text']
                }
                for kpi in data['kpis']
            ],
            'overall': {
                'percentage': data['overall']['percentage'],
                'completed': data['overall']['completed'],
                'total': data['overall']['total'],
                'departmentsCount': data['overall']['departments_count']
            },
            'barChartData': data['bar_chart_data'],
            'departmentStats': [
                {
                    'departmentId': dept['department_id'],
                    'title': dept['title'],
                    'completionRate': dept['completion_rate'],
                    'totalActivities': dept['total_activities'],
                    'icon': dept['icon'],
                    'buckets': dept['buckets']
                }
                for dept in data['department_stats']
            ],
            'availableYears': data['available_years']
        }
        
        return Response(response_data)


class DepartmentDetailView(views.APIView):
    """
    GET: Get detailed statistics for a specific department.
    
    URL params:
    - department_id: ID of the Department
    
    Query params:
    - year: Year to calculate for (default: current year)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, department_id):
        """Get department detail statistics."""
        year = int(request.query_params.get('year', timezone.now().year))
        
        data = get_department_detail(department_id, year)
        
        if data is None:
            return Response(
                {'error': 'القسم غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Transform to camelCase for frontend compatibility
        response_data = {
            'id': data['id'],
            'name': data['name'],
            'code': data['code'],
            'description': data['description'],
            'kpis': [
                {
                    'title': kpi['title'],
                    'icon': kpi['icon'],
                    'value': kpi['value'],
                    'valueLabel': kpi['value_label'],
                    'trend': kpi['trend'],
                    'percentage': kpi['percentage'],
                    'footerText': kpi['footer_text']
                }
                for kpi in data['kpis']
            ],
            'statusDistribution': data['status_distribution'],
            'weeklyTrend': {
                'weeks': data['weekly_trend']['weeks'],
                'planned': data['weekly_trend']['planned'],
                'actual': data['weekly_trend']['actual']
            },
            'activities': data['activities'],
            'totalActivities': data['total_activities'],
            'availableYears': data['available_years']
        }
        
        return Response(response_data)
