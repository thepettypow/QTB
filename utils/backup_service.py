import logging
import os
import shutil
import subprocess
import gzip
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import schedule
import time
from threading import Thread

from config import Config
from utils.database import DatabaseManager
from utils.email_service import EmailService

logger = logging.getLogger(__name__)

class BackupService:
    """Service for handling database backups and system maintenance"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config)
        self.email_service = EmailService(config)
        self.backup_dir = Path(config.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup settings
        self.max_backups = getattr(config, 'MAX_BACKUPS', 30)
        self.backup_schedule = getattr(config, 'BACKUP_SCHEDULE', 'daily')
        self.compress_backups = getattr(config, 'COMPRESS_BACKUPS', True)
        
        # Initialize backup scheduler
        self._setup_backup_schedule()
    
    def _setup_backup_schedule(self):
        """Setup automatic backup scheduling"""
        try:
            if self.backup_schedule == 'daily':
                schedule.every().day.at("02:00").do(self.create_automatic_backup)
            elif self.backup_schedule == 'weekly':
                schedule.every().sunday.at("02:00").do(self.create_automatic_backup)
            elif self.backup_schedule == 'hourly':
                schedule.every().hour.do(self.create_automatic_backup)
            
            logger.info(f"Backup schedule set to: {self.backup_schedule}")
        except Exception as e:
            logger.error(f"Failed to setup backup schedule: {e}")
    
    def start_backup_scheduler(self):
        """Start the backup scheduler in a separate thread"""
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        scheduler_thread = Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("Backup scheduler started")
    
    def create_backup(self, backup_type: str = 'manual') -> Dict[str, Any]:
        """Create a database backup"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"quiz_bot_backup_{backup_type}_{timestamp}"
            
            # Create backup directory for this backup
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(exist_ok=True)
            
            result = {
                'success': False,
                'backup_name': backup_name,
                'backup_path': str(backup_path),
                'timestamp': timestamp,
                'type': backup_type,
                'files': [],
                'size': 0,
                'error': None
            }
            
            # 1. Database dump
            db_backup_file = self._create_database_dump(backup_path, timestamp)
            if db_backup_file:
                result['files'].append(db_backup_file)
            
            # 2. Configuration backup
            config_backup_file = self._backup_configuration(backup_path)
            if config_backup_file:
                result['files'].append(config_backup_file)
            
            # 3. System metadata
            metadata_file = self._create_backup_metadata(backup_path, backup_type, timestamp)
            if metadata_file:
                result['files'].append(metadata_file)
            
            # 4. Compress backup if enabled
            if self.compress_backups:
                compressed_file = self._compress_backup(backup_path)
                if compressed_file:
                    # Remove uncompressed directory
                    shutil.rmtree(backup_path)
                    result['backup_path'] = str(compressed_file)
                    result['compressed'] = True
            
            # Calculate total size
            if self.compress_backups and 'compressed' in result:
                result['size'] = os.path.getsize(result['backup_path'])
            else:
                result['size'] = self._calculate_directory_size(backup_path)
            
            result['success'] = True
            
            # Log backup creation
            self.db_manager.log_system_event(
                'backup_created',
                f"Backup created: {backup_name}",
                {'backup_type': backup_type, 'size': result['size']}
            )
            
            logger.info(f"Backup created successfully: {backup_name}")
            
            # Clean up old backups
            self._cleanup_old_backups()
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to create backup: {e}"
            logger.error(error_msg)
            
            result['error'] = str(e)
            
            # Log backup failure
            self.db_manager.log_system_event(
                'backup_failed',
                error_msg,
                {'backup_type': backup_type, 'error': str(e)}
            )
            
            return result
    
    def _create_database_dump(self, backup_path: Path, timestamp: str) -> Optional[str]:
        """Create PostgreSQL database dump"""
        try:
            dump_file = backup_path / f"database_dump_{timestamp}.sql"
            
            # Build pg_dump command
            cmd = [
                'pg_dump',
                '--host', self.config.DB_HOST,
                '--port', str(self.config.DB_PORT),
                '--username', self.config.DB_USER,
                '--dbname', self.config.DB_NAME,
                '--no-password',
                '--verbose',
                '--clean',
                '--if-exists',
                '--create',
                '--file', str(dump_file)
            ]
            
            # Set environment variable for password
            env = os.environ.copy()
            env['PGPASSWORD'] = self.config.DB_PASSWORD
            
            # Execute pg_dump
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Database dump created: {dump_file}")
                return str(dump_file)
            else:
                logger.error(f"pg_dump failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Database dump timed out")
            return None
        except Exception as e:
            logger.error(f"Failed to create database dump: {e}")
            return None
    
    def _backup_configuration(self, backup_path: Path) -> Optional[str]:
        """Backup configuration files"""
        try:
            config_file = backup_path / "configuration.json"
            
            # Collect non-sensitive configuration
            config_data = {
                'app_name': getattr(self.config, 'APP_NAME', 'Telegram Quiz Bot'),
                'environment': getattr(self.config, 'ENVIRONMENT', 'production'),
                'database_url': self.config.DATABASE_URL.split('@')[-1] if hasattr(self.config, 'DATABASE_URL') else None,  # Remove credentials
                'max_content_length': getattr(self.config, 'MAX_CONTENT_LENGTH', None),
                'backup_settings': {
                    'max_backups': self.max_backups,
                    'backup_schedule': self.backup_schedule,
                    'compress_backups': self.compress_backups
                },
                'quiz_settings': {
                    'default_time_limit': getattr(self.config, 'DEFAULT_QUIZ_TIME_LIMIT', None),
                    'max_questions_per_quiz': getattr(self.config, 'MAX_QUESTIONS_PER_QUIZ', None),
                    'max_options_per_question': getattr(self.config, 'MAX_OPTIONS_PER_QUESTION', None)
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
            
            logger.info(f"Configuration backup created: {config_file}")
            return str(config_file)
            
        except Exception as e:
            logger.error(f"Failed to backup configuration: {e}")
            return None
    
    def _create_backup_metadata(self, backup_path: Path, backup_type: str, timestamp: str) -> Optional[str]:
        """Create backup metadata file"""
        try:
            metadata_file = backup_path / "metadata.json"
            
            # Get system statistics
            stats = self.db_manager.get_system_stats()
            
            metadata = {
                'backup_info': {
                    'timestamp': timestamp,
                    'type': backup_type,
                    'created_at': datetime.now().isoformat(),
                    'version': '1.0'
                },
                'system_stats': stats,
                'database_info': {
                    'host': self.config.DB_HOST,
                    'port': self.config.DB_PORT,
                    'name': self.config.DB_NAME,
                    'user': self.config.DB_USER
                }
            }
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            logger.info(f"Backup metadata created: {metadata_file}")
            return str(metadata_file)
            
        except Exception as e:
            logger.error(f"Failed to create backup metadata: {e}")
            return None
    
    def _compress_backup(self, backup_path: Path) -> Optional[Path]:
        """Compress backup directory"""
        try:
            compressed_file = backup_path.with_suffix('.tar.gz')
            
            # Create tar.gz archive
            shutil.make_archive(
                str(backup_path),
                'gztar',
                str(backup_path.parent),
                str(backup_path.name)
            )
            
            logger.info(f"Backup compressed: {compressed_file}")
            return compressed_file
            
        except Exception as e:
            logger.error(f"Failed to compress backup: {e}")
            return None
    
    def _calculate_directory_size(self, path: Path) -> int:
        """Calculate total size of directory"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                total_size += os.path.getsize(file_path)
        return total_size
    
    def _cleanup_old_backups(self):
        """Remove old backups beyond the retention limit"""
        try:
            # Get all backup files/directories
            backups = []
            
            for item in self.backup_dir.iterdir():
                if item.name.startswith('quiz_bot_backup_'):
                    backups.append({
                        'path': item,
                        'created': item.stat().st_ctime
                    })
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            # Remove old backups
            if len(backups) > self.max_backups:
                for backup in backups[self.max_backups:]:
                    try:
                        if backup['path'].is_file():
                            backup['path'].unlink()
                        else:
                            shutil.rmtree(backup['path'])
                        
                        logger.info(f"Removed old backup: {backup['path'].name}")
                    except Exception as e:
                        logger.error(f"Failed to remove old backup {backup['path'].name}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
    
    def create_automatic_backup(self):
        """Create automatic backup and send notification"""
        try:
            result = self.create_backup('automatic')
            
            if result['success']:
                # Send success notification
                self._send_backup_notification(result, success=True)
            else:
                # Send failure notification
                self._send_backup_notification(result, success=False)
                
        except Exception as e:
            logger.error(f"Automatic backup failed: {e}")
            
            # Send failure notification
            self._send_backup_notification(
                {'error': str(e), 'backup_name': 'automatic_backup'},
                success=False
            )
    
    def _send_backup_notification(self, backup_result: Dict[str, Any], success: bool):
        """Send backup notification email"""
        try:
            if success:
                subject = f"✅ Backup Successful - {backup_result['backup_name']}"
                
                body = f"""
                Backup completed successfully!
                
                Backup Details:
                - Name: {backup_result['backup_name']}
                - Type: {backup_result['type']}
                - Size: {backup_result['size'] / (1024*1024):.2f} MB
                - Files: {len(backup_result['files'])}
                - Path: {backup_result['backup_path']}
                - Created: {backup_result['timestamp']}
                
                System is running normally.
                """
            else:
                subject = f"❌ Backup Failed - {backup_result['backup_name']}"
                
                body = f"""
                Backup failed!
                
                Error Details:
                - Backup Name: {backup_result['backup_name']}
                - Error: {backup_result.get('error', 'Unknown error')}
                - Timestamp: {datetime.now().isoformat()}
                
                Please check the system logs and resolve the issue.
                """
            
            # Send to admin emails
            admin_emails = getattr(self.config, 'ADMIN_EMAILS', [])
            if admin_emails:
                self.email_service.send_email(
                    to_emails=admin_emails,
                    subject=subject,
                    body=body
                )
                
        except Exception as e:
            logger.error(f"Failed to send backup notification: {e}")
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups"""
        try:
            backups = []
            
            for item in self.backup_dir.iterdir():
                if item.name.startswith('quiz_bot_backup_'):
                    stat = item.stat()
                    
                    backup_info = {
                        'name': item.name,
                        'path': str(item),
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime),
                        'modified': datetime.fromtimestamp(stat.st_mtime),
                        'is_compressed': item.suffix == '.gz'
                    }
                    
                    # Try to extract backup type from name
                    name_parts = item.name.split('_')
                    if len(name_parts) >= 4:
                        backup_info['type'] = name_parts[3]
                    
                    backups.append(backup_info)
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def restore_backup(self, backup_name: str) -> Dict[str, Any]:
        """Restore from a backup (placeholder - requires careful implementation)"""
        # WARNING: This is a placeholder implementation
        # Actual restore functionality should be implemented with extreme care
        # and proper testing, as it involves dropping and recreating the database
        
        logger.warning(f"Restore requested for backup: {backup_name}")
        
        return {
            'success': False,
            'error': 'Restore functionality not implemented for safety reasons. '
                    'Please restore manually using the backup files.'
        }
    
    def delete_backup(self, backup_name: str) -> Dict[str, Any]:
        """Delete a specific backup"""
        try:
            backup_path = self.backup_dir / backup_name
            
            if not backup_path.exists():
                return {
                    'success': False,
                    'error': f'Backup {backup_name} not found'
                }
            
            if backup_path.is_file():
                backup_path.unlink()
            else:
                shutil.rmtree(backup_path)
            
            logger.info(f"Backup deleted: {backup_name}")
            
            return {
                'success': True,
                'message': f'Backup {backup_name} deleted successfully'
            }
            
        except Exception as e:
            error_msg = f"Failed to delete backup {backup_name}: {e}"
            logger.error(error_msg)
            
            return {
                'success': False,
                'error': error_msg
            }
    
    def get_backup_status(self) -> Dict[str, Any]:
        """Get backup system status"""
        try:
            backups = self.list_backups()
            
            total_size = sum(backup['size'] for backup in backups)
            
            # Get last backup info
            last_backup = backups[0] if backups else None
            
            # Check disk space
            disk_usage = shutil.disk_usage(self.backup_dir)
            
            status = {
                'backup_count': len(backups),
                'total_size': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'last_backup': {
                    'name': last_backup['name'] if last_backup else None,
                    'created': last_backup['created'].isoformat() if last_backup else None,
                    'size_mb': last_backup['size'] / (1024 * 1024) if last_backup else 0
                } if last_backup else None,
                'disk_space': {
                    'total': disk_usage.total,
                    'used': disk_usage.used,
                    'free': disk_usage.free,
                    'free_mb': disk_usage.free / (1024 * 1024)
                },
                'settings': {
                    'max_backups': self.max_backups,
                    'schedule': self.backup_schedule,
                    'compress': self.compress_backups,
                    'backup_dir': str(self.backup_dir)
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get backup status: {e}")
            return {
                'error': str(e)
            }

def create_backup_service(config: Config) -> BackupService:
    """Factory function to create BackupService instance"""
    return BackupService(config)