import logging
import hashlib
import secrets
import hmac
import base64
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import jwt
from functools import wraps

from config import Config

logger = logging.getLogger(__name__)

class SecurityManager:
    """Security utilities for the Telegram Quiz Bot"""
    
    def __init__(self, config: Config):
        self.config = config
        self.secret_key = config.SECRET_KEY
        self.jwt_secret = config.JWT_SECRET_KEY
        self.encryption_key = self._derive_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
    
    def _derive_encryption_key(self) -> bytes:
        """Derive encryption key from secret key"""
        password = self.secret_key.encode()
        salt = b'telegram_quiz_bot_salt'  # In production, use a random salt stored securely
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            salt, stored_hash = hashed_password.split(':')
            password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return hmac.compare_digest(password_hash, stored_hash)
        except ValueError:
            return False
    
    def generate_token(self, user_id: int, telegram_id: int, expires_hours: int = 24) -> str:
        """Generate JWT token for user authentication"""
        payload = {
            'user_id': user_id,
            'telegram_id': telegram_id,
            'exp': datetime.utcnow() + timedelta(hours=expires_hours),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None
    
    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        try:
            encrypted_data = self.cipher_suite.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt data: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise
    
    def generate_api_key(self, length: int = 32) -> str:
        """Generate a secure API key"""
        return secrets.token_urlsafe(length)
    
    def verify_telegram_webhook(self, token: str, data: str, signature: str) -> bool:
        """Verify Telegram webhook signature"""
        secret_key = hashlib.sha256(token.encode()).digest()
        expected_signature = hmac.new(
            secret_key,
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    
    def sanitize_input(self, text: str, max_length: int = 1000) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not text:
            return ""
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\'\/\\]', '', text)
        
        # Limit length
        sanitized = sanitized[:max_length]
        
        # Strip whitespace
        sanitized = sanitized.strip()
        
        return sanitized
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def validate_phone(self, phone: str) -> bool:
        """Validate phone number format"""
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        
        # Check if it's a valid length (7-15 digits)
        return 7 <= len(digits_only) <= 15
    
    def validate_telegram_username(self, username: str) -> bool:
        """Validate Telegram username format"""
        if not username:
            return True  # Username is optional
        
        # Remove @ if present
        username = username.lstrip('@')
        
        # Telegram username rules: 5-32 characters, alphanumeric + underscore
        pattern = r'^[a-zA-Z0-9_]{5,32}$'
        return bool(re.match(pattern, username))
    
    def rate_limit_key(self, user_id: int, action: str) -> str:
        """Generate rate limiting key"""
        return f"rate_limit:{user_id}:{action}"
    
    def generate_session_id(self) -> str:
        """Generate a secure session ID"""
        return secrets.token_urlsafe(32)
    
    def mask_sensitive_data(self, data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
        """Mask sensitive data for logging"""
        if not data or len(data) <= visible_chars:
            return mask_char * len(data) if data else ""
        
        return data[:visible_chars] + mask_char * (len(data) - visible_chars)
    
    def validate_file_upload(self, filename: str, content_type: str, file_size: int) -> Dict[str, Any]:
        """Validate file upload security"""
        result = {
            'valid': True,
            'errors': []
        }
        
        # Check file size
        max_size = self.config.MAX_CONTENT_LENGTH
        if file_size > max_size:
            result['valid'] = False
            result['errors'].append(f"File size exceeds maximum allowed size of {max_size} bytes")
        
        # Check file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', '.txt'}
        file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        if file_ext not in allowed_extensions:
            result['valid'] = False
            result['errors'].append(f"File type '{file_ext}' is not allowed")
        
        # Check content type
        allowed_content_types = {
            'image/jpeg', 'image/png', 'image/gif',
            'application/pdf', 'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain'
        }
        
        if content_type not in allowed_content_types:
            result['valid'] = False
            result['errors'].append(f"Content type '{content_type}' is not allowed")
        
        # Check filename for dangerous patterns
        dangerous_patterns = ['../', '..\\', '<script', '<?php', '<%']
        filename_lower = filename.lower()
        
        for pattern in dangerous_patterns:
            if pattern in filename_lower:
                result['valid'] = False
                result['errors'].append("Filename contains dangerous patterns")
                break
        
        return result
    
    def log_security_event(self, event_type: str, user_id: Optional[int], details: Dict[str, Any]):
        """Log security-related events"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'details': details
        }
        
        # In a production environment, you might want to send this to a
        # security monitoring system or dedicated security log
        logger.warning(f"Security Event: {log_data}")

class AdminRequired:
    """Decorator for admin-only functions"""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager
    
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # This would be used in a web context where you have access to request headers
            # For Telegram bot context, admin verification is handled differently
            return func(*args, **kwargs)
        return wrapper

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        """Check if request is allowed under rate limit"""
        now = datetime.utcnow()
        
        if key not in self.requests:
            self.requests[key] = []
        
        # Remove old requests outside the window
        cutoff = now - timedelta(seconds=window_seconds)
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > cutoff
        ]
        
        # Check if under limit
        if len(self.requests[key]) < limit:
            self.requests[key].append(now)
            return True
        
        return False
    
    def reset(self, key: str):
        """Reset rate limit for a key"""
        if key in self.requests:
            del self.requests[key]

class InputValidator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_quiz_title(title: str) -> Dict[str, Any]:
        """Validate quiz title"""
        result = {'valid': True, 'errors': []}
        
        if not title or not title.strip():
            result['valid'] = False
            result['errors'].append("Title is required")
        elif len(title.strip()) < 3:
            result['valid'] = False
            result['errors'].append("Title must be at least 3 characters long")
        elif len(title.strip()) > 200:
            result['valid'] = False
            result['errors'].append("Title must be less than 200 characters")
        
        return result
    
    @staticmethod
    def validate_question_text(text: str) -> Dict[str, Any]:
        """Validate question text"""
        result = {'valid': True, 'errors': []}
        
        if not text or not text.strip():
            result['valid'] = False
            result['errors'].append("Question text is required")
        elif len(text.strip()) < 5:
            result['valid'] = False
            result['errors'].append("Question text must be at least 5 characters long")
        elif len(text.strip()) > 1000:
            result['valid'] = False
            result['errors'].append("Question text must be less than 1000 characters")
        
        return result
    
    @staticmethod
    def validate_quiz_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate quiz settings"""
        result = {'valid': True, 'errors': []}
        
        # Validate time limit
        time_limit = settings.get('time_limit')
        if time_limit is not None:
            if not isinstance(time_limit, int) or time_limit < 0:
                result['valid'] = False
                result['errors'].append("Time limit must be a positive integer")
            elif time_limit > 7200:  # 2 hours max
                result['valid'] = False
                result['errors'].append("Time limit cannot exceed 2 hours")
        
        # Validate max attempts
        max_attempts = settings.get('max_attempts')
        if max_attempts is not None:
            if not isinstance(max_attempts, int) or max_attempts < 1:
                result['valid'] = False
                result['errors'].append("Max attempts must be at least 1")
            elif max_attempts > 10:
                result['valid'] = False
                result['errors'].append("Max attempts cannot exceed 10")
        
        # Validate passing score
        passing_score = settings.get('passing_score')
        if passing_score is not None:
            if not isinstance(passing_score, (int, float)) or not (0 <= passing_score <= 100):
                result['valid'] = False
                result['errors'].append("Passing score must be between 0 and 100")
        
        return result

# Global rate limiter instance
rate_limiter = RateLimiter()

def create_security_manager(config: Config) -> SecurityManager:
    """Factory function to create SecurityManager instance"""
    return SecurityManager(config)

def require_admin(func):
    """Decorator to require admin privileges (for Telegram bot context)"""
    @wraps(func)
    def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Check if user is admin (this would typically check against database)
        # For now, we'll check against config admin list
        if hasattr(context.bot_data, 'config'):
            admin_ids = getattr(context.bot_data['config'], 'ADMIN_USER_IDS', [])
            if user_id not in admin_ids:
                update.message.reply_text("❌ Access denied. Admin privileges required.")
                return
        
        return func(update, context, *args, **kwargs)
    return wrapper

def rate_limit(limit: int, window_seconds: int = 60):
    """Decorator to apply rate limiting"""
    def decorator(func):
        @wraps(func)
        def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            key = f"user:{user_id}:{func.__name__}"
            
            if not rate_limiter.is_allowed(key, limit, window_seconds):
                update.message.reply_text(
                    f"⏰ Rate limit exceeded. Please wait before trying again."
                )
                return
            
            return func(update, context, *args, **kwargs)
        return wrapper
    return decorator