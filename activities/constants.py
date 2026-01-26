# activities/constants.py
"""
Constants for the Activities system.
These values control chunking, pagination, and limits.
"""

# ============================================================================
# MANDATORY TEMPLATE COLUMNS
# These columns MUST be present in every template during create/update.
# Users cannot remove these columns from templates.
# ============================================================================
MANDATORY_COLUMNS = [
    {
        'label': 'نسبة الإنجاز المطلوبة',
        'label_en': 'Required Achievement Percentage',
        'key': 'required_achievement_percentage',
        'data_type': 'number',
        'is_required': True,
        'order': 9998,  # High order to appear at end by default
    },
    {
        'label': 'نسبة الإنجاز الفعلية',
        'label_en': 'Actual Achievement Percentage',
        'key': 'actual_achievement_percentage',
        'data_type': 'number',
        'is_required': True,
        'order': 9999,  # High order to appear at end by default
    },
]

# Keys of mandatory columns for quick lookup
MANDATORY_COLUMN_KEYS = [col['key'] for col in MANDATORY_COLUMNS]

# Row operations limits
MAX_ROWS_PER_REQUEST = 100      # Maximum rows in single save request
MAX_ROWS_PER_PAGE = 100         # Rows per page for pagination (for large datasets)
USER_ROWS_PER_PAGE = 100        # Rows per page for user data view
MAX_IMPORT_ROWS = 5000          # Maximum rows for Excel import
CHUNK_SIZE = 100                # Rows per chunk for background processing

# Retry settings
MAX_RETRY_ATTEMPTS = 3          # Maximum retry attempts for failed chunks
RETRY_DELAY_SECONDS = 1         # Delay between retry attempts

# File limits
MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024  # 10MB max Excel file size
MAX_HEADER_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB max header image size

# Default values
DEFAULT_ROW_HEIGHT = 32
DEFAULT_COLUMN_WIDTH = 120
DEFAULT_MIN_COLUMN_WIDTH = 80
