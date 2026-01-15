# activities/pagination.py
"""
Cursor-based pagination for large datasets.
"""

from rest_framework.pagination import CursorPagination
from .constants import MAX_ROWS_PER_PAGE


class SheetRowCursorPagination(CursorPagination):
    """
    Cursor pagination for sheet rows.
    Optimized for large datasets - no count queries.
    """
    
    page_size = MAX_ROWS_PER_PAGE
    ordering = 'row_number'
    cursor_query_param = 'cursor'
    
    def get_paginated_response_data(self, data, total_count=None):
        """
        Return pagination data for serializer.
        """
        return {
            'rows': data,
            'next_cursor': self.get_next_link(),
            'prev_cursor': self.get_previous_link(),
            'total_count': total_count or 0,
            'has_more': self.has_next
        }


class TemplateListPagination(CursorPagination):
    """
    Cursor pagination for templates.
    """
    
    page_size = 20
    ordering = '-updated_at'
    cursor_query_param = 'cursor'


class SheetListPagination(CursorPagination):
    """
    Cursor pagination for sheets.
    """
    
    page_size = 20
    ordering = '-updated_at'
    cursor_query_param = 'cursor'
