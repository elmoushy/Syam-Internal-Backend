"""
API Views for Audit Log.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authentication.permissions import IsSuperAdmin
from .models import AuditLog
from .serializers import AuditLogSerializer
from django.core.paginator import Paginator
from django.db.models import Count
from datetime import timedelta
from django.utils import timezone


class AuditLogListView(APIView):
    """
    List audit logs with filtering and pagination.
    
    Only super_admin can access audit logs.
    
    Query Parameters:
        - action: Filter by action type (SURVEY_CREATE, NEWSLETTER_UPDATE, etc.)
        - actor: Filter by actor user ID
        - actor_name: Filter by actor name (case-insensitive partial match)
        - start_date: Filter by start date (YYYY-MM-DD)
        - end_date: Filter by end date (YYYY-MM-DD)
        - page: Page number (default: 1)
        - page_size: Items per page (default: 50, max: 100)
    """
    
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    def get(self, request):
        # Get query params
        action = request.query_params.get('action')
        actor_id = request.query_params.get('actor')
        actor_name = request.query_params.get('actor_name')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 100)  # limited 100 records each time
        
        # Build query
        logs = AuditLog.objects.select_related('actor', 'content_type')
        
        if action:
            logs = logs.filter(action=action)
        if actor_id:
            logs = logs.filter(actor_id=actor_id)
        if actor_name:
            # Case-insensitive partial match on actor_name
            logs = logs.filter(actor_name__icontains=actor_name)
        if start_date:
            logs = logs.filter(timestamp__gte=start_date)
        if end_date:
            logs = logs.filter(timestamp__lte=end_date)
        
        # Paginate
        paginator = Paginator(logs, page_size)
        page_obj = paginator.get_page(page)
        
        serializer = AuditLogSerializer(page_obj, many=True)
        
        return Response({
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'results': serializer.data
        })


class AuditLogStatsView(APIView):
    """
    Get audit log statistics.
    
    Returns:
        - total_logs: Total number of audit log entries
        - logs_today: Number of logs created today
        - logs_this_week: Number of logs created in the last 7 days
        - action_breakdown: Count of each action type
        - top_actors: Top 10 users by number of actions
    """
    
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    def get(self, request):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        stats = {
            'total_logs': AuditLog.objects.count(),
            'logs_today': AuditLog.objects.filter(timestamp__date=today).count(),
            'logs_this_week': AuditLog.objects.filter(timestamp__date__gte=week_ago).count(),
            'action_breakdown': dict(
                AuditLog.objects.values('action')
                .annotate(count=Count('id'))
                .values_list('action', 'count')
            ),
            'top_actors': list(
                AuditLog.objects.values('actor_name')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
                .values('actor_name', 'count')
            ),
        }
        
        return Response(stats)


class ActorsListView(APIView):
    """
    Get list of all system users' full names.
    
    This endpoint is useful for populating search/filter dropdowns.
    Returns only users who have both first_name and last_name set.
    
    Returns:
        List of all users' full names (first_name + last_name) sorted alphabetically
    """
    
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Get all active users who have both first_name and last_name
        users = User.objects.filter(
            is_active=True,
            first_name__isnull=False,
            last_name__isnull=False
        ).exclude(
            first_name='',
            last_name=''
        ).order_by('first_name', 'last_name')
        
        # Build list of full names using the full_name property
        actors = []
        for user in users:
            # Use the full_name property which returns "first_name last_name"
            full_name = user.full_name
            # Only add if it's actually a full name (not email/username fallback)
            if full_name and full_name != user.email and full_name != user.username:
                actors.append(full_name)
        
        # Remove duplicates and sort
        actors = sorted(set(actors))
        
        return Response({
            'count': len(actors),
            'actors': actors
        })


class ActionsListView(APIView):
    """
    Get list of all available action types.
    
    This endpoint is useful for populating action filter dropdowns.
    
    Returns:
        List of action types with their display names
    """
    
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    def get(self, request):
        # Get all action choices from the model
        actions = [
            {
                'value': action[0],      # e.g., 'SURVEY_CREATE'
                'label': action[1],      # e.g., 'Survey Created'
            }
            for action in AuditLog.ACTION_CHOICES
        ]
        
        return Response({
            'count': len(actions),
            'actions': actions
        })
