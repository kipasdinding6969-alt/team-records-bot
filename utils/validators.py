"""Validation utilities for data input and processing."""
import re
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, date
import phonenumbers
from phonenumbers import NumberParseException

__all__ = [
    'validate_phone_number', 'validate_date_format', 'validate_amount',
    'validate_account_id', 'validate_username', 'validate_chinese_name',
    'validate_category', 'validate_registration_status', 'validate_email',
    'validate_url', 'validate_percentage', 'validate_integer_range',
    'validate_platform_name', 'validate_group_id', 'validate_device_info',
    'validate_note_text', 'DataValidator', 'sanitize_input',
    'normalize_phone_number', 'normalize_chinese_date', 'validate_batch_data'
]


def validate_phone_number(phone: str) -> bool:
    """Validate phone number using international standards."""
    if not phone or not isinstance(phone, str):
        return False

    # Clean the phone number
    phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

    try:
        # Try to parse as international number
        parsed = phonenumbers.parse(phone, None)
        return phonenumbers.is_valid_number(parsed)
    except NumberParseException:
        # Fallback to basic validation for Chinese mobile numbers
        # Chinese mobile: 13x, 14x, 15x, 16x, 17x, 18x, 19x
        chinese_mobile_pattern = r'^(\+86)?1[3-9]\d{9}$'
        if re.match(chinese_mobile_pattern, phone):
            return True

        # Basic international format
        international_pattern = r'^\+\d{7,15}$'
        return bool(re.match(international_pattern, phone))


def validate_date_format(date_str: str) -> bool:
    """Validate Chinese date format (X月X日)."""
    if not date_str or not isinstance(date_str, str):
        return False

    pattern = r'^\d{1,2}月\d{1,2}日$'
    if not re.match(pattern, date_str):
        return False

    # Extract month and day
    match = re.search(r'(\d{1,2})月(\d{1,2})日', date_str)
    if not match:
        return False

    try:
        month = int(match.group(1))
        day = int(match.group(2))

        # Validate month and day ranges
        if not (1 <= month <= 12):
            return False
        if not (1 <= day <= 31):
            return False

        # Check for invalid dates (basic validation)
        if month in [4, 6, 9, 11] and day > 30:
            return False
        if month == 2 and day > 29:
            return False

        return True
    except ValueError:
        return False


def validate_amount(amount: Union[str, float, int]) -> bool:
    """Validate monetary amount."""
    if amount is None:
        return True  # Allow None for optional amounts

    if isinstance(amount, (int, float)):
        return amount >= 0

    if isinstance(amount, str):
        if not amount or amount.lower() in ['', 'n/a', '-', '无', '0']:
            return True

        # Remove currency symbols and formatting
        clean_amount = amount.replace('$', '').replace('¥', '').replace(',', '').replace(' ', '')

        try:
            value = float(clean_amount)
            return value >= 0
        except ValueError:
            return False

    return False


def validate_account_id(account_id: str) -> bool:
    """Validate account ID format."""
    if not account_id or not isinstance(account_id, str):
        return False

    # Remove whitespace
    account_id = account_id.strip()

    # Check length
    if not (3 <= len(account_id) <= 50):
        return False

    # Allow alphanumeric, hyphens, underscores, and forward slashes
    pattern = r'^[A-Za-z0-9_\-/\s]+$'
    return bool(re.match(pattern, account_id))


def validate_username(username: str) -> bool:
    """Validate Telegram username format."""
    if not username or not isinstance(username, str):
        return False

    # Remove @ if present
    if username.startswith('@'):
        username = username[1:]

    # Telegram username rules:
    # - 5-32 characters
    # - Only letters, numbers, and underscores
    # - Must start with a letter
    # - Cannot end with underscore
    # - Cannot have multiple consecutive underscores
    if not (5 <= len(username) <= 32):
        return False

    if not re.match(r'^[a-zA-Z]', username):
        return False

    if username.endswith('_'):
        return False

    if '__' in username:
        return False

    pattern = r'^[a-zA-Z][a-zA-Z0-9_]*[a-zA-Z0-9]$'
    return bool(re.match(pattern, username))


def validate_chinese_name(name: str) -> bool:
    """Validate Chinese name format."""
    if not name or not isinstance(name, str):
        return False

    name = name.strip()

    # Check length (2-10 characters for Chinese names)
    if not (2 <= len(name) <= 10):
        return False

    # Allow Chinese characters, letters, and some special characters
    pattern = r'^[\u4e00-\u9fff\u3400-\u4dbfA-Za-z阿小]+$'
    return bool(re.match(pattern, name))


def validate_category(category: str, valid_categories: List[str] = None) -> bool:
    """Validate category selection."""
    if not category or not isinstance(category, str):
        return False

    if valid_categories is None:
        # Default valid categories from config
        valid_categories = ["飞机筛选", "RCS筛选", "手动筛选", "推荐筛选"]

    return category in valid_categories


def validate_registration_status(status: str) -> bool:
    """Validate registration status."""
    if not status or not isinstance(status, str):
        return False

    valid_statuses = ["注册", "不注册", "待定", "暂未确定"]
    return status in valid_statuses


def validate_email(email: str) -> bool:
    """Validate email address format."""
    if not email or not isinstance(email, str):
        return False

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """Validate URL format."""
    if not url or not isinstance(url, str):
        return False

    pattern = r'^https?://(?:[-\w.])+(?:\:[0-9]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:\#(?:[\w.])*)?)?$'
    return bool(re.match(pattern, url))


def validate_percentage(percentage: Union[str, float, int]) -> bool:
    """Validate percentage value (0-100)."""
    if percentage is None:
        return True

    try:
        if isinstance(percentage, str):
            # Remove % sign if present
            percentage = percentage.replace('%', '').strip()
            if not percentage:
                return True
            percentage = float(percentage)
        elif isinstance(percentage, int):
            percentage = float(percentage)

        return 0 <= percentage <= 100
    except (ValueError, TypeError):
        return False


def validate_integer_range(value: Union[str, int], min_val: int = None, max_val: int = None) -> bool:
    """Validate integer within specified range."""
    try:
        if isinstance(value, str):
            if not value.strip():
                return True  # Allow empty string for optional fields
            value = int(value)
        elif not isinstance(value, int):
            return False

        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False

        return True
    except (ValueError, TypeError):
        return False


def validate_platform_name(platform: str) -> bool:
    """Validate trading platform name."""
    if not platform or not isinstance(platform, str):
        return False

    platform = platform.strip()

    # Check length
    if not (2 <= len(platform) <= 50):
        return False

    # Allow alphanumeric, spaces, and some special characters
    pattern = r'^[A-Za-z0-9\s\-_.]+$'
    return bool(re.match(pattern, platform))


def validate_group_id(group_id: str) -> bool:
    """Validate group ID format."""
    if not group_id or not isinstance(group_id, str):
        return False

    # Format: "1234 / 12345678910"
    pattern = r'^\d+\s*/\s*\d+$'
    return bool(re.match(pattern, group_id))


def validate_device_info(device_info: str) -> bool:
    """Validate device information format."""
    if not device_info or not isinstance(device_info, str):
        return False

    device_info = device_info.strip()

    # Check length
    if not (3 <= len(device_info) <= 100):
        return False

    # Allow alphanumeric, spaces, and common device-related characters
    pattern = r'^[A-Za-z0-9\s\-_+.()]+$'
    return bool(re.match(pattern, device_info))


def validate_note_text(note: str) -> bool:
    """Validate note/comment text."""
    if not note:
        return True  # Allow empty notes

    if not isinstance(note, str):
        return False

    note = note.strip()

    # Check length
    if len(note) > 500:
        return False

    # Prevent potential injection attacks
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'onload=',
        r'onerror=',
        r'eval\(',
        r'document\.',
        r'window\.'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, note, re.IGNORECASE):
            return False

    return True


class DataValidator:
    """Comprehensive data validator for different record types."""

    @staticmethod
    def validate_client_record(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate client record data."""
        errors = []

        # Required fields
        required_fields = ['date', 'frontdesk', 'client_number', 'account_id', 'first_day', 'second_day']
        for field in required_fields:
            if not data.get(field):
                errors.append(f"必填字段 '{field}' 不能为空")

        # Validate specific fields
        if data.get('date') and not validate_date_format(data['date']):
            errors.append("日期格式错误，应为 'X月X日' 格式")

        if data.get('client_number') and not validate_phone_number(data['client_number']):
            errors.append("客户手机号格式错误")

        if data.get('frontdesk_number') and not validate_phone_number(data['frontdesk_number']):
            errors.append("前台手机号格式错误")

        if data.get('account_id') and not validate_account_id(data['account_id']):
            errors.append("账户ID格式错误")

        if data.get('frontdesk_username') and not validate_username(data['frontdesk_username']):
            errors.append("前台用户名格式错误")

        if data.get('frontdesk') and not validate_chinese_name(data['frontdesk']):
            errors.append("前台姓名格式错误")

        if data.get('first_day') and not validate_registration_status(data['first_day']):
            errors.append("第一天状态值无效")

        if data.get('second_day') and not validate_registration_status(data['second_day']):
            errors.append("第二天状态值无效")

        if data.get('client_condition') and not validate_note_text(data['client_condition']):
            errors.append("客户情况备注格式错误")

        return len(errors) == 0, errors

    @staticmethod
    def validate_financial_record(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate financial record data."""
        errors = []

        # Required fields
        required_fields = ['date', 'account_id', 'group_id', 'frontdesk', 'platform']
        for field in required_fields:
            if not data.get(field):
                errors.append(f"必填字段 '{field}' 不能为空")

        # Validate specific fields
        if data.get('date') and not validate_date_format(data['date']):
            errors.append("日期格式错误")

        if data.get('account_id') and not validate_account_id(data['account_id']):
            errors.append("账户ID格式错误")

        if data.get('group_id') and not validate_group_id(data['group_id']):
            errors.append("群组ID格式错误")

        if data.get('platform') and not validate_platform_name(data['platform']):
            errors.append("平台名称格式错误")

        # Validate amounts
        amount_fields = ['new_order_amount', 'pressure_amount', 'total_in',
                        'knife_1', 'knife_2', 'knife_3', 'knife_4',
                        'knife_5', 'knife_6', 'knife_7', 'knife_8']

        for field in amount_fields:
            if data.get(field) is not None and not validate_amount(data[field]):
                errors.append(f"金额字段 '{field}' 格式错误")

        if data.get('note') and not validate_note_text(data['note']):
            errors.append("备注格式错误")

        return len(errors) == 0, errors

    @staticmethod
    def validate_performance_record(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate performance record data."""
        errors = []

        # Required fields
        required_fields = ['name', 'category', 'powder_count']
        for field in required_fields:
            if data.get(field) is None:
                errors.append(f"必填字段 '{field}' 不能为空")

        # Validate name
        if data.get('name') and not validate_chinese_name(data['name']):
            errors.append("姓名格式错误")

        # Validate integer fields
        integer_fields = ['powder_count', 'no_initial_reply', 'stuck_explanation',
                         'blocked_or_play', 'been_scammed', 'sent_link_no_reply',
                         'completed_register', 'completed_training', 'scheduled_time',
                         'withdrawal', 'new_order', 'new_kill', 'dead_client']

        for field in integer_fields:
            if data.get(field) is not None and not validate_integer_range(data[field], 0):
                errors.append(f"整数字段 '{field}' 必须为非负整数")

        # Validate percentage fields
        percentage_fields = ['reply_rate', 'review_rate', 'conversion_rate']
        for field in percentage_fields:
            if data.get(field) is not None and not validate_percentage(data[field]):
                errors.append(f"百分比字段 '{field}' 必须在 0-100 之间")

        return len(errors) == 0, errors

    @staticmethod
    def validate_team_member(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate team member data."""
        errors = []

        # Required fields
        if not data.get('user_id'):
            errors.append("用户ID不能为空")

        if not data.get('chat_id'):
            errors.append("聊天ID不能为空")

        # Validate optional fields
        if data.get('username') and not validate_username(data['username']):
            errors.append("用户名格式错误")

        if data.get('phone_number') and not validate_phone_number(data['phone_number']):
            errors.append("手机号格式错误")

        if data.get('frontdesk_name') and not validate_chinese_name(data['frontdesk_name']):
            errors.append("前台姓名格式错误")

        # Validate role
        valid_roles = ['frontdesk', 'manager', 'admin', 'unregistered']
        if data.get('role') and data['role'] not in valid_roles:
            errors.append(f"角色必须是以下之一: {', '.join(valid_roles)}")

        return len(errors) == 0, errors


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input to prevent injection attacks."""
    if not text or not isinstance(text, str):
        return ""

    # Truncate to maximum length
    text = text[:max_length]

    # Remove potentially dangerous characters
    # Keep only alphanumeric, Chinese characters, and safe punctuation
    safe_pattern = r'[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9\s\-_.,!?@#()\/:\+]'
    text = re.sub(safe_pattern, '', text)

    # Remove excessive whitespace
    text = ' '.join(text.split())

    return text.strip()


def normalize_phone_number(phone: str) -> str:
    """Normalize phone number format."""
    if not phone:
        return ""

    # Remove all non-digit characters except +
    phone = re.sub(r'[^\d+]', '', phone)

    # Add +86 for Chinese numbers if missing
    if phone.startswith('1') and len(phone) == 11:
        phone = '+86' + phone
    elif phone.startswith('86') and len(phone) == 13:
        phone = '+' + phone

    return phone


def normalize_chinese_date(date_str: str) -> str:
    """Normalize Chinese date format."""
    if not date_str:
        return ""

    # Extract numbers from date string
    numbers = re.findall(r'\d+', date_str)
    if len(numbers) >= 2:
        month = int(numbers[0])
        day = int(numbers[1])
        return f"{month}月{day}日"

    return date_str


def validate_batch_data(records: List[Dict[str, Any]], record_type: str) -> Dict[str, Any]:
    """Validate a batch of records."""
    results = {
        'valid_count': 0,
        'invalid_count': 0,
        'errors': [],
        'valid_records': [],
        'invalid_records': []
    }

    validator_map = {
        'client': DataValidator.validate_client_record,
        'financial': DataValidator.validate_financial_record,
        'performance': DataValidator.validate_performance_record,
        'team_member': DataValidator.validate_team_member
    }

    validator = validator_map.get(record_type)
    if not validator:
        results['errors'].append(f"Unknown record type: {record_type}")
        return results

    for i, record in enumerate(records):
        is_valid, errors = validator(record)

        if is_valid:
            results['valid_count'] += 1
            results['valid_records'].append(record)
        else:
            results['invalid_count'] += 1
            results['invalid_records'].append({
                'index': i,
                'record': record,
                'errors': errors
            })
            results['errors'].extend([f"Record {i+1}: {error}" for error in errors])

    return results