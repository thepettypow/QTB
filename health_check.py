#!/usr/bin/env python3
"""
Health Check Script for Telegram Quiz Bot

This script performs comprehensive health checks on all system components:
- Database connectivity
- Redis connectivity
- Email service
- File system permissions
- Environment configuration

Usage:
    python health_check.py [--verbose] [--component COMPONENT]

Components:
    - database: Check PostgreSQL connection
    - redis: Check Redis connection
    - email: Test email configuration
    - filesystem: Check file permissions
    - config: Validate configuration
    - all: Check all components (default)
"""

import argparse
import sys
import os
from typing import Dict, List, Tuple
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import DevelopmentConfig, ProductionConfig, TestingConfig
    from utils.database import DatabaseManager
    from utils.email_service import EmailService
    import redis
    import psycopg2
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Please ensure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)


class HealthChecker:
    """Comprehensive health checker for the Telegram Quiz Bot system."""
    
    def __init__(self, config_class=None, verbose=False):
        self.verbose = verbose
        self.config = config_class or self._get_config()
        self.results = {}
        
    def _get_config(self):
        """Get configuration based on environment."""
        env = os.getenv('FLASK_ENV', 'development').lower()
        if env == 'production':
            return ProductionConfig()
        elif env == 'testing':
            return TestingConfig()
        else:
            return DevelopmentConfig()
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")
    
    def check_database(self) -> Tuple[bool, str]:
        """Check database connectivity and basic operations."""
        try:
            self._log("Testing database connection...")
            
            # Test basic connection
            db_manager = DatabaseManager(self.config)
            if not db_manager.test_connection():
                return False, "Database connection failed"
            
            self._log("Database connection successful")
            
            # Test basic query
            try:
                stats = db_manager.get_system_stats()
                self._log(f"Database query successful. Users: {stats.get('total_users', 0)}")
            except Exception as e:
                self._log(f"Database query failed: {e}", "WARNING")
                return False, f"Database query failed: {str(e)}"
            
            return True, "Database is healthy"
            
        except Exception as e:
            self._log(f"Database check failed: {e}", "ERROR")
            return False, f"Database error: {str(e)}"
    
    def check_redis(self) -> Tuple[bool, str]:
        """Check Redis connectivity."""
        try:
            self._log("Testing Redis connection...")
            
            # Parse Redis URL
            redis_url = getattr(self.config, 'REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url)
            
            # Test connection
            r.ping()
            self._log("Redis ping successful")
            
            # Test basic operations
            test_key = "health_check_test"
            r.set(test_key, "test_value", ex=10)
            value = r.get(test_key)
            r.delete(test_key)
            
            if value != b"test_value":
                return False, "Redis read/write test failed"
            
            self._log("Redis read/write test successful")
            return True, "Redis is healthy"
            
        except Exception as e:
            self._log(f"Redis check failed: {e}", "ERROR")
            return False, f"Redis error: {str(e)}"
    
    def check_email(self) -> Tuple[bool, str]:
        """Check email service configuration."""
        try:
            self._log("Testing email configuration...")
            
            email_service = EmailService(self.config)
            
            # Test email configuration without sending
            if not email_service.test_email_config():
                return False, "Email configuration test failed"
            
            self._log("Email configuration is valid")
            return True, "Email service is configured correctly"
            
        except Exception as e:
            self._log(f"Email check failed: {e}", "ERROR")
            return False, f"Email error: {str(e)}"
    
    def check_filesystem(self) -> Tuple[bool, str]:
        """Check file system permissions and required directories."""
        try:
            self._log("Checking filesystem permissions...")
            
            required_dirs = [
                getattr(self.config, 'UPLOAD_FOLDER', 'uploads'),
                getattr(self.config, 'BACKUP_FOLDER', 'backups'),
                getattr(self.config, 'LOG_FOLDER', 'logs')
            ]
            
            issues = []
            
            for dir_path in required_dirs:
                if not os.path.exists(dir_path):
                    try:
                        os.makedirs(dir_path, exist_ok=True)
                        self._log(f"Created directory: {dir_path}")
                    except Exception as e:
                        issues.append(f"Cannot create directory {dir_path}: {e}")
                        continue
                
                # Test write permissions
                test_file = os.path.join(dir_path, '.health_check_test')
                try:
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    self._log(f"Write permission OK for {dir_path}")
                except Exception as e:
                    issues.append(f"No write permission for {dir_path}: {e}")
            
            if issues:
                return False, "; ".join(issues)
            
            return True, "Filesystem permissions are correct"
            
        except Exception as e:
            self._log(f"Filesystem check failed: {e}", "ERROR")
            return False, f"Filesystem error: {str(e)}"
    
    def check_config(self) -> Tuple[bool, str]:
        """Check configuration completeness."""
        try:
            self._log("Validating configuration...")
            
            required_configs = [
                'TELEGRAM_BOT_TOKEN',
                'ADMIN_BOT_TOKEN',
                'SECRET_KEY',
                'DATABASE_URL'
            ]
            
            missing_configs = []
            
            for config_name in required_configs:
                value = getattr(self.config, config_name, None)
                if not value or (isinstance(value, str) and value.strip() == ''):
                    missing_configs.append(config_name)
                else:
                    self._log(f"Config {config_name}: ✓")
            
            if missing_configs:
                return False, f"Missing required configurations: {', '.join(missing_configs)}"
            
            # Check token format
            bot_token = getattr(self.config, 'TELEGRAM_BOT_TOKEN', '')
            if ':' not in bot_token or len(bot_token.split(':')) != 2:
                return False, "Invalid TELEGRAM_BOT_TOKEN format"
            
            admin_token = getattr(self.config, 'ADMIN_BOT_TOKEN', '')
            if ':' not in admin_token or len(admin_token.split(':')) != 2:
                return False, "Invalid ADMIN_BOT_TOKEN format"
            
            self._log("Configuration validation successful")
            return True, "Configuration is complete and valid"
            
        except Exception as e:
            self._log(f"Configuration check failed: {e}", "ERROR")
            return False, f"Configuration error: {str(e)}"
    
    def run_check(self, component: str = 'all') -> Dict[str, Tuple[bool, str]]:
        """Run health checks for specified component(s)."""
        checks = {
            'config': self.check_config,
            'filesystem': self.check_filesystem,
            'database': self.check_database,
            'redis': self.check_redis,
            'email': self.check_email
        }
        
        if component == 'all':
            components_to_check = list(checks.keys())
        elif component in checks:
            components_to_check = [component]
        else:
            raise ValueError(f"Unknown component: {component}. Available: {list(checks.keys())}")
        
        results = {}
        
        for comp in components_to_check:
            self._log(f"\n=== Checking {comp.upper()} ===")
            try:
                success, message = checks[comp]()
                results[comp] = (success, message)
                status = "✅ PASS" if success else "❌ FAIL"
                print(f"{status} {comp.upper()}: {message}")
            except Exception as e:
                results[comp] = (False, f"Check failed: {str(e)}")
                print(f"❌ FAIL {comp.upper()}: Check failed: {str(e)}")
        
        return results
    
    def get_summary(self, results: Dict[str, Tuple[bool, str]]) -> Tuple[bool, str]:
        """Get overall health summary."""
        total_checks = len(results)
        passed_checks = sum(1 for success, _ in results.values() if success)
        failed_checks = total_checks - passed_checks
        
        overall_health = failed_checks == 0
        
        summary = f"Health Check Summary: {passed_checks}/{total_checks} checks passed"
        
        if failed_checks > 0:
            failed_components = [comp for comp, (success, _) in results.items() if not success]
            summary += f" (Failed: {', '.join(failed_components)})"
        
        return overall_health, summary


def main():
    """Main function to run health checks."""
    parser = argparse.ArgumentParser(
        description="Health Check Script for Telegram Quiz Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python health_check.py                    # Check all components
  python health_check.py --component database  # Check only database
  python health_check.py --verbose         # Verbose output
  python health_check.py -c redis -v       # Check Redis with verbose output
"""
    )
    
    parser.add_argument(
        '--component', '-c',
        choices=['all', 'database', 'redis', 'email', 'filesystem', 'config'],
        default='all',
        help='Component to check (default: all)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--environment', '-e',
        choices=['development', 'production', 'testing'],
        help='Environment to use for configuration'
    )
    
    args = parser.parse_args()
    
    # Set environment if specified
    if args.environment:
        os.environ['FLASK_ENV'] = args.environment
    
    print("🔍 Telegram Quiz Bot - Health Check")
    print("=" * 40)
    
    try:
        checker = HealthChecker(verbose=args.verbose)
        results = checker.run_check(args.component)
        
        print("\n" + "=" * 40)
        overall_health, summary = checker.get_summary(results)
        
        if overall_health:
            print(f"✅ {summary}")
            print("\n🎉 System is healthy and ready to use!")
            sys.exit(0)
        else:
            print(f"❌ {summary}")
            print("\n⚠️  Please fix the issues above before running the application.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Health check interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Health check failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()