# activities/constants.py
"""
Constants for the Activities system.
These values control chunking, pagination, and limits.
"""

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
