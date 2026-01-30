# activities/dashboard_utils.py
"""
Utility functions for Dashboard KPI calculations.

IMPORTANT: Calculations are based on TWO KEY COLUMNS in each activity row:
- required_achievement_percentage: The planned/target percentage (0-100)
- actual_achievement_percentage: The actual achieved percentage (0-100)

Status Determination:
- Completed: actual >= required AND actual > 0
- In Progress: actual > 0 AND actual < required
- Not Started: actual = 0 OR actual is not set

These columns are MANDATORY in all templates (see constants.py MANDATORY_COLUMNS).
"""

from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from django.db.models import Count, Case, When, IntegerField, Q, F, Sum, Avg
from django.db.models.functions import TruncMonth, TruncQuarter, ExtractMonth, ExtractQuarter, Coalesce
from django.utils import timezone

from .models import (
    Department,
    ActivityTemplate,
    ActivitySheet,
    ActivitySheetRow,
)


# Arabic month names for frontend display
ARABIC_MONTHS = [
    'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
]

# Status colors matching frontend design
STATUS_COLORS = {
    'completed': '#00A651',      # Green
    'in_progress': '#FFD166',    # Gold/Yellow
    'not_started': '#E76F51',    # Red/Orange
}

# Arabic status labels
STATUS_LABELS = {
    'completed': 'مكتمل',
    'in_progress': 'قيد التنفيذ',
    'not_started': 'لم يبدأ',
}


def get_achievement_values(row: ActivitySheetRow) -> Tuple[float, float]:
    """
    Extract actual and required achievement percentages from row data.
    Checks for both variants: with and without _2 suffix.
    
    Args:
        row: ActivitySheetRow instance
        
    Returns:
        Tuple of (actual_percentage, required_percentage)
    """
    data = row.data or {}
    
    # Get actual achievement percentage (default 0)
    # Check for both field variants (with _2 suffix first as it's the newer format)
    actual = data.get('actual_achievement_percentage_2')
    if actual is None or actual == '':
        actual = data.get('actual_achievement_percentage', 0)
    if actual is None or actual == '':
        actual = 0
    try:
        actual = float(actual)
    except (ValueError, TypeError):
        actual = 0
    
    # Get required achievement percentage (default 100)
    # Check for both field variants (with _2 suffix first as it's the newer format)
    required = data.get('required_achievement_percentage_2')
    if required is None or required == '':
        required = data.get('required_achievement_percentage', 100)
    if required is None or required == '':
        required = 100
    try:
        required = float(required)
    except (ValueError, TypeError):
        required = 100
    
    return (actual, required)


def get_row_calculated_status(row: ActivitySheetRow) -> str:
    """
    Calculate the status of a row based on achievement percentages.
    
    Status logic:
    - completed: actual >= required AND actual > 0
    - in_progress: actual > 0 AND actual < required
    - not_started: actual = 0
    
    Args:
        row: ActivitySheetRow instance
        
    Returns:
        Status string: 'completed', 'in_progress', or 'not_started'
    """
    actual, required = get_achievement_values(row)
    
    if actual <= 0:
        return 'not_started'
    elif actual >= required:
        return 'completed'
    else:
        return 'in_progress'


def calculate_rows_statistics(rows_qs) -> Dict:
    """
    Calculate statistics for a queryset of rows.
    Uses actual_achievement_percentage and required_achievement_percentage.
    
    Args:
        rows_qs: QuerySet of ActivitySheetRow
        
    Returns:
        Dict with calculated statistics
    """
    total = 0
    completed = 0
    in_progress = 0
    not_started = 0
    
    sum_actual = 0.0
    sum_required = 0.0
    
    for row in rows_qs:
        total += 1
        actual, required = get_achievement_values(row)
        
        sum_actual += actual
        sum_required += required
        
        # Determine status based on achievement
        if actual <= 0:
            not_started += 1
        elif actual >= required:
            completed += 1
        else:
            in_progress += 1
    
    # Calculate overall completion rate
    completion_rate = 0.0
    if sum_required > 0:
        completion_rate = round((sum_actual / sum_required) * 100, 1)
    elif total > 0:
        # Fallback: use count-based calculation
        completion_rate = round((completed / total) * 100, 1)
    
    return {
        'total': total,
        'completed': completed,
        'in_progress': in_progress,
        'not_started': not_started,
        'sum_actual': sum_actual,
        'sum_required': sum_required,
        'completion_rate': min(100, completion_rate),  # Cap at 100%
    }


def get_quarter_dates(year: int, quarter: int) -> Tuple[date, date]:
    """
    Get start and end dates for a specific quarter.
    
    Args:
        year: The year
        quarter: Quarter number (1-4)
        
    Returns:
        Tuple of (start_date, end_date)
    """
    quarter_starts = {
        1: (1, 1),   # Jan 1
        2: (4, 1),   # Apr 1
        3: (7, 1),   # Jul 1
        4: (10, 1),  # Oct 1
    }
    quarter_ends = {
        1: (3, 31),  # Mar 31
        2: (6, 30),  # Jun 30
        3: (9, 30),  # Sep 30
        4: (12, 31), # Dec 31
    }
    
    start_month, start_day = quarter_starts[quarter]
    end_month, end_day = quarter_ends[quarter]
    
    return (
        date(year, start_month, start_day),
        date(year, end_month, end_day)
    )


def get_available_years() -> List[int]:
    """
    Get list of years that have activity data.
    Returns last 3 years or years with actual data.
    Only considers submitted activities (is_submitted=True).
    """
    # Get years with actual submitted activity data
    # Based on ActivitySheetRow.is_submitted, not sheet-level
    years_with_data = ActivitySheetRow.objects.filter(
        is_submitted=True
    ).values_list(
        'sheet__created_at__year', flat=True
    ).distinct().order_by('-sheet__created_at__year')
    
    years = list(years_with_data)
    
    # Ensure at least current year and 2 previous years
    current_year = timezone.now().year
    for y in range(current_year, current_year - 3, -1):
        if y not in years:
            years.append(y)
    
    return sorted(set(years), reverse=True)[:5]  # Max 5 years


def get_kpi_summary(year: int, department_id: Optional[int] = None) -> Dict:
    """
    Calculate main KPI summary for dashboard.
    Uses actual_achievement_percentage and required_achievement_percentage for calculations.
    Only includes SUBMITTED activities (is_submitted=True) - excludes drafts that may be deleted.
    
    Args:
        year: Year to calculate KPIs for
        department_id: Optional department filter (None = all departments)
        
    Returns:
        Dict with KPI values
    """
    # Ensure default department exists
    default_dept = Department.get_default_department()
    
    # Base queryset for rows - ONLY submitted activities
    # Draft activities (is_submitted=False) are excluded as they may be deleted
    rows_qs = ActivitySheetRow.objects.filter(
        sheet__created_at__year=year,
        is_submitted=True  # Only submitted activities
    ).select_related('sheet')
    
    if department_id:
        rows_qs = rows_qs.filter(sheet__department_id=department_id)
    
    # Calculate statistics based on achievement percentages
    stats = calculate_rows_statistics(rows_qs)
    
    total_activities = stats['total']
    completed_count = stats['completed']
    in_progress_count = stats['in_progress']
    not_started_count = stats['not_started']
    completion_rate = stats['completion_rate']
    
    # Participating departments - departments with at least one SUBMITTED activity in the year
    # ALWAYS include default department if it has data
    # Based on submitted activities (rows), not sheets
    participating_dept_ids = set(
        ActivitySheetRow.objects.filter(
            sheet__created_at__year=year,
            is_submitted=True  # Only submitted activities
        ).exclude(sheet__department__isnull=True).values_list('sheet__department_id', flat=True).distinct()
    )
    
    # Check if default department has submitted activities (sheets without department = default)
    has_default_dept_submitted = ActivitySheetRow.objects.filter(
        sheet__created_at__year=year,
        sheet__department__isnull=True,
        is_submitted=True  # Only submitted activities
    ).exists()
    if has_default_dept_submitted:
        participating_dept_ids.add(default_dept.id)
    
    participating_depts = len(participating_dept_ids)
    
    # Total active departments (always at least 1 = default)
    total_depts = max(1, Department.objects.filter(is_active=True).count())
    
    # Non-participating departments
    non_participating_depts = max(0, total_depts - participating_depts)
    
    # Calculate trend (compare with previous month)
    now = timezone.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    current_month_activities = rows_qs.filter(
        created_at__gte=current_month_start
    ).count()
    
    # Previous month
    if now.month == 1:
        prev_month_start = now.replace(year=now.year-1, month=12, day=1)
    else:
        prev_month_start = now.replace(month=now.month-1, day=1)
    
    prev_month_activities = rows_qs.filter(
        created_at__gte=prev_month_start,
        created_at__lt=current_month_start
    ).count()
    
    # Calculate percentage change
    if prev_month_activities > 0:
        change_percentage = round(
            ((current_month_activities - prev_month_activities) / prev_month_activities) * 100
        )
    else:
        change_percentage = 100 if current_month_activities > 0 else 0
    
    # Determine trend direction
    if change_percentage > 0:
        trend = 'up'
    elif change_percentage < 0:
        trend = 'down'
    else:
        trend = 'flat'
    
    return {
        'total_activities': total_activities,
        'participating_departments': participating_depts,
        'non_participating_departments': non_participating_depts,
        'overall_completion_rate': completion_rate,
        'trend': trend,
        'change_percentage': abs(change_percentage),
        'current_month_activities': current_month_activities,
    }


def get_status_distribution(year: int, department_id: Optional[int] = None) -> Dict:
    """
    Get activity status distribution for donut chart.
    
    Status Logic (for FULL dashboard - all departments):
    - مكتمل (Completed): Activities (rows) with is_submitted=True
    - قيد التنفيذ (In Progress): Activities (rows) with is_submitted=False (drafts)
    - لم يبدأ (Not Started): Number of non-participating departments (departments with no activities)
    
    Args:
        year: Year to calculate for
        department_id: Optional department filter
        
    Returns:
        Dict with status distribution data
    """
    # Ensure default department exists
    default_dept = Department.get_default_department()
    
    # Base queryset for ALL rows (both submitted and draft)
    all_rows_qs = ActivitySheetRow.objects.filter(
        sheet__created_at__year=year
    ).select_related('sheet')
    
    if department_id:
        all_rows_qs = all_rows_qs.filter(sheet__department_id=department_id)
    
    # مكتمل (Completed): Count of submitted activities
    submitted_count = all_rows_qs.filter(is_submitted=True).count()
    
    # قيد التنفيذ (In Progress): Count of draft activities
    draft_count = all_rows_qs.filter(is_submitted=False).count()
    
    # لم يبدأ (Not Started): Non-participating departments
    # For full dashboard, this is the count of departments with no activities
    if department_id is None:
        # Get departments that have any activity (submitted or draft)
        participating_dept_ids = set(
            all_rows_qs.exclude(
                sheet__department__isnull=True
            ).values_list('sheet__department_id', flat=True).distinct()
        )
        
        # Check if default department has activities
        has_default_dept_activity = all_rows_qs.filter(
            sheet__department__isnull=True
        ).exists()
        if has_default_dept_activity:
            participating_dept_ids.add(default_dept.id)
        
        # Total active departments
        total_depts = max(1, Department.objects.filter(is_active=True).count())
        
        # Non-participating = not started
        not_started_count = max(0, total_depts - len(participating_dept_ids))
    else:
        # For department-specific view, not_started is 0 (handled in get_department_detail)
        not_started_count = 0
    
    # Total includes submitted + draft + not_started (departments)
    total = submitted_count + draft_count + not_started_count
    
    items = [
        {
            'label': STATUS_LABELS['completed'],
            'value': submitted_count,
            'color': STATUS_COLORS['completed']
        },
        {
            'label': STATUS_LABELS['in_progress'],
            'value': draft_count,
            'color': STATUS_COLORS['in_progress']
        },
        {
            'label': STATUS_LABELS['not_started'],
            'value': not_started_count,
            'color': STATUS_COLORS['not_started']
        },
    ]
    
    return {
        'year': year,
        'total': total,
        'items': items
    }


def get_quarterly_data(year: int, department_id: Optional[int] = None) -> Dict:
    """
    Get quarterly planned vs actual data for bar chart.
    
    Planned = Sum of required_achievement_percentage for activities in the quarter
    Actual = Sum of actual_achievement_percentage for activities in the quarter
    
    NOTE: Values are shown as average percentages per quarter for better visualization.
    
    Args:
        year: Year to calculate for
        department_id: Optional department filter
        
    Returns:
        Dict with quarterly data
    """
    quarters = []
    
    for q in range(1, 5):
        q_start, q_end = get_quarter_dates(year, q)
        
        # Convert to datetime for filtering
        q_start_dt = timezone.make_aware(
            datetime.combine(q_start, datetime.min.time())
        )
        q_end_dt = timezone.make_aware(
            datetime.combine(q_end, datetime.max.time())
        )
        
        # Base queryset for SUBMITTED activities created in this quarter
        # Draft activities are excluded as they may be deleted
        base_qs = ActivitySheetRow.objects.filter(
            created_at__range=(q_start_dt, q_end_dt),
            is_submitted=True  # Only submitted activities
        ).select_related('sheet')
        
        if department_id:
            base_qs = base_qs.filter(sheet__department_id=department_id)
        
        # Calculate sum of achievement percentages
        sum_actual = 0.0
        sum_required = 0.0
        count = 0
        
        for row in base_qs:
            actual, required = get_achievement_values(row)
            sum_actual += actual
            sum_required += required
            count += 1
        
        # Use average percentage for visualization (0-100 scale)
        avg_planned = round(sum_required / count, 1) if count > 0 else 0
        avg_actual = round(sum_actual / count, 1) if count > 0 else 0
        
        quarters.append({
            'label': f'Q{q}',
            'planned': avg_planned,
            'actual': avg_actual,
            'count': count  # Number of activities for reference
        })
    
    return {
        'year': year,
        'quarters': quarters
    }


def get_monthly_trend(year: int, department_id: Optional[int] = None) -> Dict:
    """
    Get monthly planned vs actual trend data for line chart.
    
    Planned = Average of required_achievement_percentage for activities in the month
    Actual = Average of actual_achievement_percentage for activities in the month
    
    Args:
        year: Year to calculate for
        department_id: Optional department filter
        
    Returns:
        Dict with monthly trend data
    """
    months = []
    planned_values = []
    actual_values = []
    
    for month in range(1, 13):
        # Get month date range
        month_start = timezone.make_aware(
            datetime(year, month, 1)
        )
        if month == 12:
            month_end = timezone.make_aware(
                datetime(year + 1, 1, 1)
            )
        else:
            month_end = timezone.make_aware(
                datetime(year, month + 1, 1)
            )
        
        # Base queryset for SUBMITTED activities in this month
        # Draft activities are excluded as they may be deleted
        base_qs = ActivitySheetRow.objects.filter(
            created_at__gte=month_start,
            created_at__lt=month_end,
            is_submitted=True  # Only submitted activities
        ).select_related('sheet')
        
        if department_id:
            base_qs = base_qs.filter(sheet__department_id=department_id)
        
        # Calculate sum of achievement percentages
        sum_actual = 0.0
        sum_required = 0.0
        count = 0
        
        for row in base_qs:
            actual, required = get_achievement_values(row)
            sum_actual += actual
            sum_required += required
            count += 1
        
        # Use average percentage for visualization (0-100 scale)
        avg_planned = round(sum_required / count, 1) if count > 0 else 0
        avg_actual = round(sum_actual / count, 1) if count > 0 else 0
        
        months.append(ARABIC_MONTHS[month - 1])
        planned_values.append(avg_planned)
        actual_values.append(avg_actual)
    
    return {
        'year': year,
        'months': months,
        'planned': planned_values,
        'actual': actual_values
    }


def get_programs_performance(
    year: int,
    department_id: Optional[int] = None,
    search: Optional[str] = None
) -> List[Dict]:
    """
    Get performance data for all programs (templates).
    Completion rate is calculated from actual vs required achievement percentages.
    
    Args:
        year: Year to calculate for
        department_id: Optional department filter
        search: Optional search term for template names
        
    Returns:
        List of program performance data
    """
    # Get published templates
    templates_qs = ActivityTemplate.objects.filter(
        status='published',
        is_deleted=False
    )
    
    if department_id:
        templates_qs = templates_qs.filter(
            Q(target_department_id=department_id) |
            Q(target_department__isnull=True)  # Legacy templates
        )
    
    if search:
        templates_qs = templates_qs.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    programs = []
    
    for template in templates_qs:
        # Get all SUBMITTED rows for this template in the given year
        # Only submitted activities are included - drafts may be deleted
        rows_qs = ActivitySheetRow.objects.filter(
            sheet__template=template,
            sheet__created_at__year=year,
            is_submitted=True  # Only submitted activities
        ).select_related('sheet')
        
        if department_id:
            rows_qs = rows_qs.filter(sheet__department_id=department_id)
        
        # Calculate statistics based on achievement percentages
        stats = calculate_rows_statistics(rows_qs)
        
        total_activities = stats['total']
        completion_rate = stats['completion_rate']
        
        # Count participating departments for this template
        # Based on submitted activities, not sheets
        # Include default department if applicable
        dept_ids = set(
            ActivitySheetRow.objects.filter(
                sheet__template=template,
                sheet__created_at__year=year,
                is_submitted=True  # Only submitted activities
            ).exclude(sheet__department__isnull=True).values_list('sheet__department_id', flat=True).distinct()
        )
        
        # Check for submitted activities without department (= default department)
        if ActivitySheetRow.objects.filter(
            sheet__template=template,
            sheet__created_at__year=year,
            sheet__department__isnull=True,
            is_submitted=True  # Only submitted activities
        ).exists():
            default_dept = Department.get_default_department()
            dept_ids.add(default_dept.id)
        
        departments_count = max(1, len(dept_ids))  # At least 1 for Phase 1
        
        # Determine mode based on completion rate
        mode = 'gold' if completion_rate >= 50 else 'danger'
        
        programs.append({
            'id': template.id,
            'title': template.name,
            'description': template.description or template.notes or '',
            'completion_rate': completion_rate,
            'departments_count': departments_count,
            'activities_total': total_activities,
            'mode': mode,
            'details_link': f'/programs/details/{template.id}'
        })
    
    # Sort by completion rate descending
    programs.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    return programs


def get_full_dashboard_data(year: int, department_id: Optional[int] = None) -> Dict:
    """
    Get all dashboard data in a single call.
    
    Args:
        year: Year to calculate for
        department_id: Optional department filter
        
    Returns:
        Dict with all dashboard data
    """
    return {
        'kpis': get_kpi_summary(year, department_id),
        'status_distribution': get_status_distribution(year, department_id),
        'quarterly_data': get_quarterly_data(year, department_id),
        'monthly_trend': get_monthly_trend(year, department_id),
        'programs': get_programs_performance(year, department_id),
        'available_years': get_available_years(),
    }


def get_department_stats(year: int) -> List[Dict]:
    """
    Get statistics for each department.
    Used for admin view comparing departments.
    
    Args:
        year: Year to calculate for
        
    Returns:
        List of department statistics
    """
    departments = Department.objects.filter(is_active=True)
    
    stats = []
    for dept in departments:
        kpis = get_kpi_summary(year, dept.id)
        stats.append({
            'department_id': dept.id,
            'department_name': dept.name,
            'department_code': dept.code,
            **kpis
        })
    
    return stats


def get_program_detail(template_id: int, year: int) -> Optional[Dict]:
    """
    Get detailed statistics for a specific program (template).
    
    Status Definitions (based on ActivitySheetRow.is_submitted, NOT sheet level):
    - مكتمل (completed): Activities (rows) with is_submitted=True
    - قيد التنفيذ (in_progress): Activities (rows) with is_submitted=False (draft)
    - متأخر (late): Users in the department who haven't created any activity for this template
    - ملغي (cancelled): Reserved for future use
    
    Overall percentage is calculated as the average of actual vs required achievement
    from SUBMITTED activities (rows) only.
    
    Args:
        template_id: ID of the ActivityTemplate
        year: Year to calculate for
        
    Returns:
        Dict with program details or None if not found
    """
    # Import User model here to avoid circular imports
    from authentication.models import User
    
    try:
        template = ActivityTemplate.objects.get(
            id=template_id,
            is_deleted=False
        )
    except ActivityTemplate.DoesNotExist:
        return None
    
    # Get all sheets for this template in the given year
    all_sheets = ActivitySheet.objects.filter(
        template=template,
        created_at__year=year
    ).select_related('owner', 'department')
    
    # Get all activity rows for this template
    all_rows = ActivitySheetRow.objects.filter(
        sheet__template=template,
        sheet__created_at__year=year
    ).select_related('sheet', 'sheet__owner', 'sheet__department')
    
    # Count activities (rows) by submission status
    submitted_rows = all_rows.filter(is_submitted=True)
    draft_rows = all_rows.filter(is_submitted=False)
    
    submitted_count = submitted_rows.count()
    draft_count = draft_rows.count()
    
    # Get all active users (these are the users who should have activities)
    all_users = User.objects.filter(is_active=True)
    total_users = all_users.count()
    
    # Users who have any activity (row) for this template
    users_with_activities = set(all_rows.values_list('sheet__owner_id', flat=True))
    
    # Late = users who should have filled but didn't (no activity at all)
    late_count = max(0, total_users - len(users_with_activities))
    
    # Cancelled is reserved for future use
    cancelled_count = 0
    
    # Total activities = all activity rows + late users
    total_activities = submitted_count + draft_count + late_count
    
    # Calculate overall completion percentage from SUBMITTED activities only
    # Based on average of actual_achievement vs required_achievement
    overall_percentage = 0.0
    sum_actual = 0.0
    sum_required = 0.0
    
    if submitted_rows.exists():
        for row in submitted_rows:
            actual, required = get_achievement_values(row)
            sum_actual += actual
            sum_required += required
        
        if sum_required > 0:
            overall_percentage = round((sum_actual / sum_required) * 100, 1)
            overall_percentage = min(100, overall_percentage)  # Cap at 100%
    
    # Get department-wise stats
    # First, get all participating departments
    dept_ids = set(
        all_sheets.exclude(department__isnull=True).values_list('department_id', flat=True).distinct()
    )
    
    # Check for sheets without department (= default department)
    has_default_dept_sheets = all_sheets.filter(department__isnull=True).exists()
    default_dept = Department.get_default_department()
    
    if has_default_dept_sheets or not dept_ids:
        # Always include default department
        dept_ids.add(default_dept.id)
    
    participating_depts = Department.objects.filter(
        is_active=True,
        id__in=dept_ids
    )
    
    departments_count = max(1, len(dept_ids))
    
    # Get department-wise stats for bar chart and cards
    department_stats = []
    bar_chart_data = []
    
    for dept in participating_depts:
        # Get activity rows for this department
        if dept.is_default:
            # Default department includes sheets with NULL department
            dept_rows = all_rows.filter(
                Q(sheet__department=dept) | Q(sheet__department__isnull=True)
            )
        else:
            dept_rows = all_rows.filter(sheet__department=dept)
        
        # Count activities (rows) by submission status
        dept_submitted_rows = dept_rows.filter(is_submitted=True)
        dept_draft_rows = dept_rows.filter(is_submitted=False)
        
        dept_submitted_count = dept_submitted_rows.count()
        dept_draft_count = dept_draft_rows.count()
        
        # Users with activities in this department
        dept_users_with_activities = set(dept_rows.values_list('sheet__owner_id', flat=True))
        
        # Late users for this department = users without any activity
        dept_late_count = max(0, total_users - len(dept_users_with_activities))
        
        dept_total = dept_submitted_count + dept_draft_count + dept_late_count
        
        # Calculate department completion rate from submitted activities
        dept_sum_actual = 0.0
        dept_sum_required = 0.0
        dept_completion_rate = 0.0
        
        if dept_submitted_rows.exists():
            for row in dept_submitted_rows:
                actual, required = get_achievement_values(row)
                dept_sum_actual += actual
                dept_sum_required += required
            
            if dept_sum_required > 0:
                dept_completion_rate = round((dept_sum_actual / dept_sum_required) * 100, 1)
                dept_completion_rate = min(100, dept_completion_rate)
        
        # Bar chart data entry - show average achievement percentages
        avg_required = round(dept_sum_required / dept_submitted_count, 1) if dept_submitted_count > 0 else 100.0
        avg_actual = round(dept_sum_actual / dept_submitted_count, 1) if dept_submitted_count > 0 else 0.0
        
        bar_chart_data.append({
            'label': dept.name,
            'planned': avg_required,
            'actual': avg_actual
        })
        
        # Department stats card data
        department_stats.append({
            'department_id': dept.id,
            'title': dept.name,
            'completion_rate': dept_completion_rate,
            'total_activities': dept_total,
            'icon': 'bi bi-building',
            'buckets': {
                'cancelled': {'label': 'ملغي', 'count': 0},
                'late': {'label': 'متأخر', 'count': dept_late_count},
                'in_progress': {'label': 'قيد التنفيذ', 'count': dept_draft_count},
                'completed': {'label': 'مكتمل', 'count': dept_submitted_count}
            }
        })
    
    # KPIs formatted for frontend
    kpis = [
        {
            'title': 'إجمالي الأنشطة',
            'icon': 'bi bi-activity',
            'value': total_activities,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'مكتمل',
            'icon': 'bi bi-check-circle',
            'value': submitted_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'قيد التنفيذ',
            'icon': 'bi bi-clock-history',
            'value': draft_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'متأخر',
            'icon': 'bi bi-exclamation-triangle',
            'value': late_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'ملغي',
            'icon': 'bi bi-x-circle',
            'value': cancelled_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        }
    ]
    
    # Overall completion data
    overall = {
        'percentage': overall_percentage,
        'completed': submitted_count,
        'total': total_activities,
        'departments_count': max(1, departments_count)
    }
    
    return {
        'id': template.id,
        'title': template.name,
        'description': template.description or template.notes or '',
        'kpis': kpis,
        'overall': overall,
        'bar_chart_data': {
            year: {
                'quarters': bar_chart_data  # Using 'quarters' key for compatibility
            }
        },
        'department_stats': department_stats,
        'available_years': get_available_years()
    }


def get_department_detail(department_id: int, year: int) -> Optional[Dict]:
    """
    Get detailed statistics for a specific department.
    Used for DepartmentActivities page.
    
    Status Logic (for DEPARTMENT dashboard):
    - مكتمل (Completed): Activities (rows) with is_submitted=True
    - قيد التنفيذ (In Progress): Activities (rows) with is_submitted=False (drafts)
    - لم يبدأ (Not Started): Users who are allowed to submit on active templates but haven't submitted any activity
    
    Args:
        department_id: ID of the Department
        year: Year to calculate for
        
    Returns:
        Dict with department details or None if not found
    """
    # Import User model here to avoid circular imports
    from authentication.models import User
    
    try:
        department = Department.objects.get(id=department_id, is_active=True)
    except Department.DoesNotExist:
        return None
    
    # Build base query for department
    if department.is_default:
        department_filter = Q(sheet__department=department) | Q(sheet__department__isnull=True)
    else:
        department_filter = Q(sheet__department=department)
    
    # Get ALL rows for this department (both submitted and draft)
    all_rows_qs = ActivitySheetRow.objects.filter(
        department_filter,
        sheet__created_at__year=year
    ).select_related('sheet', 'sheet__template', 'sheet__owner')
    
    # مكتمل (Completed): Count of submitted activities
    submitted_rows_qs = all_rows_qs.filter(is_submitted=True)
    submitted_count = submitted_rows_qs.count()
    
    # قيد التنفيذ (In Progress): Count of draft activities
    draft_count = all_rows_qs.filter(is_submitted=False).count()
    
    # لم يبدأ (Not Started): Users who haven't submitted any activity on active templates
    # Get active templates (published and active) for this department
    active_templates = ActivityTemplate.objects.filter(
        Q(target_department=department) | Q(target_department__isnull=True),
        status='published',
        is_deleted=False,
        is_active_title=True
    )
    
    # Get all active users who should submit activities
    all_active_users = User.objects.filter(is_active=True)
    total_users = all_active_users.count()
    
    # Get users who have at least one activity (any row, submitted or draft) on any active template
    users_with_any_activity = set(
        all_rows_qs.filter(
            sheet__template__in=active_templates
        ).values_list('sheet__owner_id', flat=True).distinct()
    )
    
    # Not started = users who haven't submitted any activity
    not_started_count = max(0, total_users - len(users_with_any_activity))
    
    # Cancelled is reserved for future use
    cancelled_count = 0
    
    # Total includes submitted + draft + not_started (users)
    total_activities = submitted_count + draft_count + not_started_count
    
    # KPIs formatted for frontend
    kpis = [
        {
            'title': 'إجمالي الأنشطة',
            'icon': 'bi bi-activity',
            'value': total_activities,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'مكتمل',
            'icon': 'bi bi-check-circle',
            'value': submitted_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'قيد التنفيذ',
            'icon': 'bi bi-clock-history',
            'value': draft_count,
            'value_label': 'نشاط',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        },
        {
            'title': 'لم يبدأ',
            'icon': 'bi bi-x-circle',
            'value': not_started_count,
            'value_label': 'مستخدم',
            'trend': 'flat',
            'percentage': 10,
            'footer_text': 'في هذا الشهر'
        }
    ]
    
    # Status distribution for donut chart
    status_distribution = {
        'year': year,
        'total': total_activities,
        'items': [
            {'label': 'مكتمل', 'value': submitted_count, 'color': STATUS_COLORS['completed']},
            {'label': 'قيد التنفيذ', 'value': draft_count, 'color': STATUS_COLORS['in_progress']},
            {'label': 'لم يبدأ', 'value': not_started_count, 'color': STATUS_COLORS['not_started']}
        ]
    }
    
    # Weekly trend data (4 weeks of the current month)
    # Calculate average achievement percentages per week
    current_month = timezone.now().month
    weekly_data = []
    
    # Use submitted rows for weekly trend calculations
    submitted_rows_list = list(submitted_rows_qs)
    
    for week in range(1, 5):
        # Get rows for this week (approximate week boundaries)
        week_rows = [r for r in submitted_rows_list if r.created_at.month == current_month]
        
        # Calculate average achievement for this portion of rows
        week_sum_actual = 0.0
        week_sum_required = 0.0
        week_count = 0
        
        # Divide rows among 4 weeks
        chunk_size = max(1, len(week_rows) // 4)
        start_idx = (week - 1) * chunk_size
        end_idx = week * chunk_size if week < 4 else len(week_rows)
        
        for row in week_rows[start_idx:end_idx]:
            actual, required = get_achievement_values(row)
            week_sum_actual += actual
            week_sum_required += required
            week_count += 1
        
        avg_planned = round(week_sum_required / week_count, 1) if week_count > 0 else 0
        avg_actual = round(week_sum_actual / week_count, 1) if week_count > 0 else 0
        
        weekly_data.append({
            'week': week,
            'planned': avg_planned,
            'actual': avg_actual
        })
    
    # Get activities for this department with details (show all: submitted and draft)
    activities = []
    for row in all_rows_qs[:50]:  # Limit for performance
        row_data = row.data or {}
        
        # Get activity title from data or use default
        title = row_data.get('activityName', row_data.get('name', 'نشاط بدون عنوان'))
        
        # Get assignee name from sheet owner
        assignee = 'غير محدد'
        if row.sheet and row.sheet.owner:
            assignee = f"{row.sheet.owner.first_name} {row.sheet.owner.last_name}".strip()
            if not assignee:
                assignee = row.sheet.owner.email.split('@')[0] if row.sheet.owner.email else 'غير محدد'
        
        # Get dates from data
        start_date = row_data.get('startDate', row_data.get('start_date', ''))
        end_date = row_data.get('endDate', row_data.get('end_date', ''))
        
        # Get achievement percentages for completion rate
        actual_pct, required_pct = get_achievement_values(row)
        
        # Determine status based on is_submitted flag (new logic)
        # مكتمل (completed) = submitted, قيد التنفيذ (in_progress) = draft
        if row.is_submitted:
            display_status = 'completed'
        else:
            display_status = 'in_progress'
        
        # Use actual achievement percentage as completion rate
        row_completion = round(actual_pct)
        
        activities.append({
            'id': row.id,
            'title': title,
            'status': display_status,
            'assignee': assignee,
            'startDate': start_date,
            'endDate': end_date,
            'completionRate': row_completion
        })
    
    return {
        'id': department.id,
        'name': department.name,
        'code': department.code,
        'description': department.description or '',
        'kpis': kpis,
        'status_distribution': status_distribution,
        'weekly_trend': {
            'weeks': ['الأسبوع 1', 'الأسبوع 2', 'الأسبوع 3', 'الأسبوع 4'],
            'planned': [w['planned'] for w in weekly_data],
            'actual': [w['actual'] for w in weekly_data]
        },
        'activities': activities,
        'total_activities': total_activities,
        'available_years': get_available_years()
    }
