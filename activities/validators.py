# activities/validators.py
"""
Validation utilities for Activity data.
Used for validating imported Excel data and API row submissions.
"""

import re
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from .models import ActivityColumnValidation


class RowValidator:
    """Validates row data against column validation rules"""
    
    def __init__(self, columns: List[Dict]):
        """
        Initialize validator with column definitions.
        
        Args:
            columns: List of column definition dicts from sheet's column_snapshot
        """
        self.columns = columns
        self.validation_cache: Dict[str, List[ActivityColumnValidation]] = {}
        self._load_validations()
    
    def _load_validations(self):
        """Load validations for all columns from database"""
        for col in self.columns:
            col_key = col.get('key') or col.get('column_definition__key', '')
            col_id = col.get('column_definition_id') or col.get('column_definition__id')
            
            if col_id:
                try:
                    validations = ActivityColumnValidation.objects.filter(
                        column_id=col_id,
                        is_active=True
                    )
                    self.validation_cache[col_key] = list(validations)
                except Exception:
                    self.validation_cache[col_key] = []
            else:
                self.validation_cache[col_key] = []
    
    def validate_row(self, row_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate a single row of data.
        
        Args:
            row_data: Dict mapping column keys to values
            
        Returns:
            Dict of {column_key: error_message} for invalid fields.
            Empty dict if all valid.
        """
        errors = {}
        
        for col in self.columns:
            col_key = col.get('key') or col.get('column_definition__key', '')
            value = row_data.get(col_key, '')
            is_required = col.get('is_required', False)
            
            # Check required first
            if is_required and (not value or not str(value).strip()):
                errors[col_key] = 'هذا الحقل مطلوب'
                continue
            
            # Get validations for this column
            validations = self.validation_cache.get(col_key, [])
            
            for validation in validations:
                error = self._apply_validation(value, validation)
                if error:
                    errors[col_key] = error
                    break  # Stop at first error for this column
        
        return errors
    
    def _apply_validation(self, value: Any, validation: ActivityColumnValidation) -> Optional[str]:
        """
        Apply a single validation rule.
        
        Args:
            value: The cell value to validate
            validation: The validation rule to apply
            
        Returns:
            Error message string if invalid, None if valid
        """
        rule_type = validation.rule_type
        rule_value = validation.rule_value
        error_msg = validation.error_message or f'القيمة غير صالحة'
        
        # Convert value to string for comparison
        str_value = str(value).strip() if value is not None else ''
        
        if rule_type == 'required':
            if not str_value:
                return error_msg
        
        elif rule_type == 'regex':
            if str_value:
                try:
                    if not re.match(rule_value, str_value):
                        return error_msg
                except re.error:
                    # Invalid regex pattern - skip this validation
                    pass
        
        elif rule_type == 'min_length':
            if str_value:
                try:
                    min_len = int(rule_value)
                    if len(str_value) < min_len:
                        return error_msg
                except ValueError:
                    pass
        
        elif rule_type == 'max_length':
            if str_value:
                try:
                    max_len = int(rule_value)
                    if len(str_value) > max_len:
                        return error_msg
                except ValueError:
                    pass
        
        elif rule_type == 'min_value':
            if str_value:
                try:
                    num_value = float(str_value)
                    min_val = float(rule_value)
                    if num_value < min_val:
                        return error_msg
                except ValueError:
                    pass
        
        elif rule_type == 'max_value':
            if str_value:
                try:
                    num_value = float(str_value)
                    max_val = float(rule_value)
                    if num_value > max_val:
                        return error_msg
                except ValueError:
                    pass
        
        elif rule_type == 'options':
            if str_value:
                try:
                    options = json.loads(rule_value)
                    if isinstance(options, list) and str_value not in options:
                        return error_msg
                except json.JSONDecodeError:
                    pass
        
        elif rule_type == 'email':
            if str_value:
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, str_value):
                    return error_msg
        
        elif rule_type == 'url':
            if str_value:
                url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
                if not re.match(url_pattern, str_value, re.IGNORECASE):
                    return error_msg
        
        elif rule_type == 'phone':
            if str_value:
                # Basic phone validation - digits, spaces, hyphens, plus
                phone_pattern = r'^[\d\s\-\+\(\)]{7,20}$'
                if not re.match(phone_pattern, str_value):
                    return error_msg
        
        elif rule_type == 'date_range':
            if str_value:
                try:
                    range_config = json.loads(rule_value)
                    min_date = range_config.get('min')
                    max_date = range_config.get('max')
                    
                    # Try to parse the date value
                    date_value = None
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            date_value = datetime.strptime(str_value, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if date_value:
                        if min_date:
                            min_dt = datetime.strptime(min_date, '%Y-%m-%d')
                            if date_value < min_dt:
                                return error_msg
                        if max_date:
                            max_dt = datetime.strptime(max_date, '%Y-%m-%d')
                            if date_value > max_dt:
                                return error_msg
                except (json.JSONDecodeError, ValueError):
                    pass
        
        elif rule_type == 'unique':
            # Unique validation needs to be handled at the batch level
            # This is a placeholder - actual implementation depends on context
            pass
        
        return None
    
    def validate_rows(self, rows: List[Dict[str, Any]]) -> List[Dict]:
        """
        Validate multiple rows of data.
        
        Args:
            rows: List of row data dicts
            
        Returns:
            List of {row_number, errors} for rows with validation errors.
            Empty list if all rows are valid.
        """
        validation_errors = []
        
        for idx, row_data in enumerate(rows, start=1):
            errors = self.validate_row(row_data)
            if errors:
                validation_errors.append({
                    'row_number': idx,
                    'errors': errors
                })
        
        return validation_errors
    
    def validate_cell(self, col_key: str, value: Any) -> Optional[str]:
        """
        Validate a single cell value.
        
        Args:
            col_key: The column key
            value: The cell value
            
        Returns:
            Error message string if invalid, None if valid
        """
        # Find column definition
        col_def = None
        for col in self.columns:
            key = col.get('key') or col.get('column_definition__key', '')
            if key == col_key:
                col_def = col
                break
        
        if not col_def:
            return None
        
        # Check required
        is_required = col_def.get('is_required', False)
        str_value = str(value).strip() if value is not None else ''
        
        if is_required and not str_value:
            return 'هذا الحقل مطلوب'
        
        # Check validations
        validations = self.validation_cache.get(col_key, [])
        
        for validation in validations:
            error = self._apply_validation(value, validation)
            if error:
                return error
        
        return None


def validate_row_data(columns: List[Dict], row_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Convenience function to validate a single row.
    
    Args:
        columns: Column definitions from sheet snapshot
        row_data: Dict mapping column keys to values
        
    Returns:
        Dict of {column_key: error_message} for invalid fields
    """
    validator = RowValidator(columns)
    return validator.validate_row(row_data)


def validate_bulk_rows(columns: List[Dict], rows: List[Dict[str, Any]]) -> List[Dict]:
    """
    Convenience function to validate multiple rows.
    
    Args:
        columns: Column definitions from sheet snapshot
        rows: List of row data dicts
        
    Returns:
        List of {row_number, errors} for rows with errors
    """
    validator = RowValidator(columns)
    return validator.validate_rows(rows)
