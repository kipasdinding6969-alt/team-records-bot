"""Tests for validation utilities."""
import pytest
from datetime import datetime

from utils.validators import (
    validate_phone_number, validate_date_format, validate_amount,
    validate_account_id, validate_username, validate_chinese_name,
    validate_category, validate_registration_status, validate_email,
    validate_url, validate_percentage, validate_integer_range,
    validate_platform_name, validate_group_id, validate_device_info,
    validate_note_text, DataValidator, sanitize_input, normalize_phone_number,
    normalize_chinese_date, validate_batch_data
)


class TestBasicValidators:
    """Test basic validation functions."""

    def test_validate_phone_number(self):
        """Test phone number validation."""
        # Valid phone numbers
        assert validate_phone_number("+8613800000000") is True
        assert validate_phone_number("13800000000") is True
        assert validate_phone_number("+14155552671") is True  # Valid US number
        assert validate_phone_number("+86 138 0000 0000") is True

        # Invalid phone numbers
        assert validate_phone_number("") is False
        assert validate_phone_number("123") is False
        assert validate_phone_number("abcd") is False
        assert validate_phone_number(None) is False
        assert validate_phone_number("12345") is False

    def test_validate_date_format(self):
        """Test Chinese date format validation."""
        # Valid dates
        assert validate_date_format("3月15日") is True
        assert validate_date_format("12月31日") is True
        assert validate_date_format("1月1日") is True

        # Invalid dates
        assert validate_date_format("") is False
        assert validate_date_format("3-15") is False
        assert validate_date_format("March 15") is False
        assert validate_date_format("13月1日") is False  # Invalid month
        assert validate_date_format("2月32日") is False  # Invalid day
        assert validate_date_format(None) is False

    def test_validate_amount(self):
        """Test amount validation."""
        # Valid amounts
        assert validate_amount(100.0) is True
        assert validate_amount(0) is True
        assert validate_amount("100.50") is True
        assert validate_amount("$100.50") is True
        assert validate_amount("") is True  # Empty is valid (optional)
        assert validate_amount(None) is True  # None is valid (optional)

        # Invalid amounts
        assert validate_amount(-100) is False
        assert validate_amount("abc") is False
        assert validate_amount("-100") is False

    def test_validate_account_id(self):
        """Test account ID validation."""
        # Valid account IDs
        assert validate_account_id("ACC123456") is True
        assert validate_account_id("123456 / 123456") is True
        assert validate_account_id("TEST_ACC") is True

        # Invalid account IDs
        assert validate_account_id("") is False
        assert validate_account_id("AB") is False  # Too short
        assert validate_account_id("A" * 51) is False  # Too long
        assert validate_account_id(None) is False

    def test_validate_username(self):
        """Test Telegram username validation."""
        # Valid usernames
        assert validate_username("@test_user") is True
        assert validate_username("test_user") is True
        assert validate_username("TestUser123") is True

        # Invalid usernames
        assert validate_username("") is False
        assert validate_username("@123") is False  # Too short
        assert validate_username("test_") is False  # Ends with underscore
        assert validate_username("test__user") is False  # Double underscore
        assert validate_username("1test") is False  # Starts with number
        assert validate_username(None) is False

    def test_validate_chinese_name(self):
        """Test Chinese name validation."""
        # Valid names
        assert validate_chinese_name("阿YIM") is True
        assert validate_chinese_name("小王") is True
        assert validate_chinese_name("TestName") is True

        # Invalid names
        assert validate_chinese_name("") is False
        assert validate_chinese_name("A") is False  # Too short
        assert validate_chinese_name("A" * 11) is False  # Too long
        assert validate_chinese_name(None) is False

    def test_validate_category(self):
        """Test category validation."""
        valid_categories = ["飞机筛选", "RCS筛选", "手动筛选"]

        # Valid categories
        assert validate_category("飞机筛选", valid_categories) is True
        assert validate_category("RCS筛选", valid_categories) is True

        # Invalid categories
        assert validate_category("invalid", valid_categories) is False
        assert validate_category("", valid_categories) is False
        assert validate_category(None, valid_categories) is False

    def test_validate_registration_status(self):
        """Test registration status validation."""
        # Valid statuses
        assert validate_registration_status("注册") is True
        assert validate_registration_status("不注册") is True
        assert validate_registration_status("待定") is True

        # Invalid statuses
        assert validate_registration_status("invalid") is False
        assert validate_registration_status("") is False
        assert validate_registration_status(None) is False

    def test_validate_email(self):
        """Test email validation."""
        # Valid emails
        assert validate_email("test@example.com") is True
        assert validate_email("user.name@domain.co.uk") is True

        # Invalid emails
        assert validate_email("") is False
        assert validate_email("invalid") is False
        assert validate_email("@example.com") is False
        assert validate_email("test@") is False
        assert validate_email(None) is False

    def test_validate_url(self):
        """Test URL validation."""
        # Valid URLs
        assert validate_url("https://example.com") is True
        assert validate_url("http://test.com/path") is True
        assert validate_url("https://example.com:8080/path?query=1") is True

        # Invalid URLs
        assert validate_url("") is False
        assert validate_url("not_a_url") is False
        assert validate_url("ftp://example.com") is False
        assert validate_url(None) is False

    def test_validate_percentage(self):
        """Test percentage validation."""
        # Valid percentages
        assert validate_percentage(50.0) is True
        assert validate_percentage(0) is True
        assert validate_percentage(100) is True
        assert validate_percentage("80%") is True
        assert validate_percentage("80") is True
        assert validate_percentage(None) is True  # Optional

        # Invalid percentages
        assert validate_percentage(-10) is False
        assert validate_percentage(150) is False
        assert validate_percentage("invalid") is False

    def test_validate_integer_range(self):
        """Test integer range validation."""
        # Valid integers
        assert validate_integer_range(50, 0, 100) is True
        assert validate_integer_range("50", 0, 100) is True
        assert validate_integer_range(0, 0, 100) is True
        assert validate_integer_range("", None, None) is True  # Empty allowed

        # Invalid integers
        assert validate_integer_range(-10, 0, 100) is False
        assert validate_integer_range(150, 0, 100) is False
        assert validate_integer_range("abc", 0, 100) is False

    def test_validate_platform_name(self):
        """Test trading platform name validation."""
        # Valid platform names
        assert validate_platform_name("Iconnect") is True
        assert validate_platform_name("MetaTrader 4") is True
        assert validate_platform_name("Test-Platform_1.0") is True

        # Invalid platform names
        assert validate_platform_name("") is False
        assert validate_platform_name("A") is False  # Too short
        assert validate_platform_name("A" * 51) is False  # Too long
        assert validate_platform_name(None) is False

    def test_validate_group_id(self):
        """Test group ID validation."""
        # Valid group IDs
        assert validate_group_id("1234 / 12345678910") is True
        assert validate_group_id("123/456") is True

        # Invalid group IDs
        assert validate_group_id("") is False
        assert validate_group_id("1234") is False  # Missing separator
        assert validate_group_id("abc / def") is False  # Non-numeric
        assert validate_group_id(None) is False

    def test_validate_device_info(self):
        """Test device info validation."""
        # Valid device info
        assert validate_device_info("65 IPHONE SE") is True
        assert validate_device_info("Samsung Galaxy S21") is True
        assert validate_device_info("MacBook Pro (2021)") is True

        # Invalid device info
        assert validate_device_info("") is False
        assert validate_device_info("AB") is False  # Too short
        assert validate_device_info("A" * 101) is False  # Too long
        assert validate_device_info(None) is False

    def test_validate_note_text(self):
        """Test note text validation."""
        # Valid notes
        assert validate_note_text("这是一个测试备注") is True
        assert validate_note_text("") is True  # Empty allowed
        assert validate_note_text("Normal text with numbers 123") is True

        # Invalid notes (security concerns)
        assert validate_note_text("<script>alert('xss')</script>") is False
        assert validate_note_text("javascript:void(0)") is False
        assert validate_note_text("A" * 501) is False  # Too long
        assert validate_note_text("eval(malicious)") is False


class TestDataValidator:
    """Test comprehensive data validator."""

    def test_validate_client_record(self):
        """Test client record validation."""
        # Valid client record
        valid_data = {
            'date': '3月15日',
            'frontdesk': '阿YIM',
            'client_number': '+8613800000000',
            'account_id': 'ACC123456',
            'first_day': '注册',
            'second_day': '注册',
            'phone_remark': '65 IPHONE SE',
            'category': '飞机筛选',
            'recruiter': '测试员',
            'frontdesk_number': '+8613800000001',
            'frontdesk_username': '@test_user'
        }

        is_valid, errors = DataValidator.validate_client_record(valid_data)
        assert is_valid is True
        assert len(errors) == 0

        # Invalid client record (missing required fields)
        invalid_data = {
            'date': '',
            'frontdesk': '',
            'client_number': 'invalid',
            'account_id': '',
            'first_day': 'invalid_status',
            'second_day': 'invalid_status'
        }

        is_valid, errors = DataValidator.validate_client_record(invalid_data)
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_financial_record(self):
        """Test financial record validation."""
        # Valid financial record
        valid_data = {
            'date': '3月15日',
            'account_id': '123456 / 123456',
            'group_id': '1234 / 12345678910',
            'frontdesk': '阿YIM',
            'platform': 'Iconnect',
            'new_order_amount': '1000.00',
            'pressure_amount': '500.00'
        }

        is_valid, errors = DataValidator.validate_financial_record(valid_data)
        assert is_valid is True
        assert len(errors) == 0

        # Invalid financial record
        invalid_data = {
            'date': 'invalid_date',
            'account_id': '',
            'group_id': 'invalid',
            'frontdesk': '',
            'platform': '',
            'new_order_amount': 'invalid_amount'
        }

        is_valid, errors = DataValidator.validate_financial_record(invalid_data)
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_performance_record(self):
        """Test performance record validation."""
        # Valid performance record
        valid_data = {
            'name': '阿YIM',
            'category': '飞机筛选',
            'powder_count': 100,
            'reply_rate': 80.0,
            'conversion_rate': 75.0,
            'no_initial_reply': 20,
            'completed_register': 60
        }

        is_valid, errors = DataValidator.validate_performance_record(valid_data)
        assert is_valid is True
        assert len(errors) == 0

        # Invalid performance record
        invalid_data = {
            'name': '',
            'category': '',
            'powder_count': 'invalid',
            'reply_rate': 150.0,  # Invalid percentage
            'no_initial_reply': -5  # Invalid negative
        }

        is_valid, errors = DataValidator.validate_performance_record(invalid_data)
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_team_member(self):
        """Test team member validation."""
        # Valid team member
        valid_data = {
            'user_id': 123456,
            'chat_id': 123456,
            'username': 'test_user',
            'phone_number': '+8613800000000',
            'frontdesk_name': '阿YIM',
            'role': 'frontdesk'
        }

        is_valid, errors = DataValidator.validate_team_member(valid_data)
        assert is_valid is True
        assert len(errors) == 0

        # Invalid team member
        invalid_data = {
            'user_id': None,
            'chat_id': None,
            'username': 'invalid_username_',
            'phone_number': 'invalid',
            'role': 'invalid_role'
        }

        is_valid, errors = DataValidator.validate_team_member(invalid_data)
        assert is_valid is False
        assert len(errors) > 0


class TestUtilityFunctions:
    """Test utility and helper functions."""

    def test_sanitize_input(self):
        """Test input sanitization."""
        # Normal text
        assert sanitize_input("Normal text") == "Normal text"
        assert sanitize_input("中文文本") == "中文文本"

        # Remove dangerous characters
        dangerous_input = "<script>alert('xss')</script>"
        sanitized = sanitize_input(dangerous_input)
        assert "<script>" not in sanitized

        # Truncate long text
        long_text = "A" * 2000
        sanitized = sanitize_input(long_text, max_length=100)
        assert len(sanitized) <= 100

        # Handle None input
        assert sanitize_input(None) == ""

    def test_normalize_phone_number(self):
        """Test phone number normalization."""
        # Chinese mobile numbers
        assert normalize_phone_number("13800000000") == "+8613800000000"
        assert normalize_phone_number("8613800000000") == "+8613800000000"
        assert normalize_phone_number("+86 138 0000 0000") == "+8613800000000"

        # Already normalized
        assert normalize_phone_number("+8613800000000") == "+8613800000000"

        # Empty input
        assert normalize_phone_number("") == ""
        assert normalize_phone_number(None) == ""

    def test_normalize_chinese_date(self):
        """Test Chinese date normalization."""
        # Standard format
        assert normalize_chinese_date("3月15日") == "3月15日"

        # With extra spaces/characters
        assert normalize_chinese_date("3 月 15 日") == "3月15日"
        assert normalize_chinese_date("第3月第15日") == "3月15日"

        # Empty input
        assert normalize_chinese_date("") == ""
        assert normalize_chinese_date(None) == ""

    def test_validate_batch_data(self):
        """Test batch data validation."""
        # Valid client records
        valid_records = [
            {
                'date': '3月15日',
                'frontdesk': '阿YIM',
                'client_number': '+8613800000000',
                'account_id': 'ACC123',
                'first_day': '注册',
                'second_day': '注册',
                'phone_remark': 'iPhone',
                'category': '测试',
                'recruiter': '测试员',
                'frontdesk_number': '+8613800000001',
                'frontdesk_username': '@test'
            },
            {
                'date': '3月16日',
                'frontdesk': '阿俊',
                'client_number': '+8613800000002',
                'account_id': 'ACC124',
                'first_day': '注册',
                'second_day': '不注册',
                'phone_remark': 'Android',
                'category': '测试',
                'recruiter': '测试员',
                'frontdesk_number': '+8613800000003',
                'frontdesk_username': '@test2'
            }
        ]

        results = validate_batch_data(valid_records, 'client')
        assert results['valid_count'] >= 1
        assert results['invalid_count'] <= 1
        assert len(results['valid_records']) >= 1

        # Mixed valid and invalid records
        mixed_records = valid_records + [
            {
                'date': 'invalid_date',
                'frontdesk': '',
                'client_number': 'invalid',
                'account_id': '',
                'first_day': 'invalid',
                'second_day': 'invalid'
            }
        ]

        results = validate_batch_data(mixed_records, 'client')
        assert results['valid_count'] >= 1
        assert results['invalid_count'] >= 1
        assert len(results['errors']) > 0

        # Unknown record type
        results = validate_batch_data(valid_records, 'unknown')
        assert 'Unknown record type' in results['errors'][0]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_and_none_inputs(self):
        """Test validation with empty and None inputs."""
        validators = [
            validate_phone_number, validate_date_format, validate_account_id,
            validate_username, validate_chinese_name, validate_platform_name
        ]

        for validator in validators:
            assert validator(None) is False
            assert validator("") is False

    def test_boundary_values(self):
        """Test validation at boundary values."""
        # Test minimum and maximum string lengths
        assert validate_account_id("ABC") is True  # Minimum length
        assert validate_account_id("A" * 50) is True  # Maximum length
        assert validate_account_id("AB") is False  # Below minimum
        assert validate_account_id("A" * 51) is False  # Above maximum

        # Test percentage boundaries
        assert validate_percentage(0) is True
        assert validate_percentage(100) is True
        assert validate_percentage(-0.1) is False
        assert validate_percentage(100.1) is False

    def test_unicode_and_special_characters(self):
        """Test validation with Unicode and special characters."""
        # Chinese characters should be valid in names
        assert validate_chinese_name("阿YIM测试") is True
        assert validate_chinese_name("小王👍") is False  # Emojis not allowed

        # Special characters in notes
        assert validate_note_text("正常文本 (备注)") is True
        assert validate_note_text("Text with emoji 😀") is True

    def test_case_sensitivity(self):
        """Test case sensitivity in validation."""
        # Registration status should be case sensitive
        assert validate_registration_status("注册") is True
        assert validate_registration_status("注冊") is False  # Different character

        # Platform names should allow mixed case
        assert validate_platform_name("MetaTrader") is True
        assert validate_platform_name("metatrader") is True

    def test_whitespace_handling(self):
        """Test handling of whitespace in inputs."""
        # Leading/trailing whitespace should be handled appropriately
        assert validate_account_id("  ACC123  ") is True  # Should be trimmed internally
        assert validate_chinese_name("  阿YIM  ") is True

        # Internal whitespace should be preserved where appropriate
        assert validate_platform_name("Meta Trader 4") is True
        assert validate_device_info("iPhone 12 Pro") is True