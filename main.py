#!/usr/bin/env python3
"""
Telegram Quiz Bot - Main Application Entry Point

This is the main entry point for the Telegram Quiz Bot application.
It initializes and runs both the Telegram bot and the web dashboard.
"""

import logging
import os
import sys
import signal
import threading
import time
from datetime import datetime
from typing import Optional

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, DevelopmentConfig, ProductionConfig, TestingConfig
from models import db, create_tables
from bot import TelegramQuizBot
from admin_bot import AdminBot
from web_dashboard import app as web_app
from utils.database import DatabaseManager
from utils.email_service import EmailService
from utils.backup_service import BackupService
from utils.security import SecurityManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_quiz_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class TelegramQuizBotApplication:
    """Main application class that manages all components"""
    
    def __init__(self, environment: str = None):
        self.environment = environment or os.getenv('ENVIRONMENT', 'development')
        self.config = self._load_config()
        self.running = False
        self.threads = []
        
        # Initialize components
        self.db_manager: Optional[DatabaseManager] = None
        self.email_service: Optional[EmailService] = None
        self.backup_service: Optional[BackupService] = None
        self.security_manager: Optional[SecurityManager] = None
        self.telegram_bot: Optional[TelegramQuizBot] = None
        self.admin_bot: Optional[AdminBot] = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_config(self) -> Config:
        """Load configuration based on environment"""
        if self.environment == 'production':
            return ProductionConfig()
        elif self.environment == 'testing':
            return TestingConfig()
        else:
            return DevelopmentConfig()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()
    
    def initialize(self) -> bool:
        """Initialize all application components"""
        try:
            logger.info(f"Initializing Telegram Quiz Bot in {self.environment} mode...")
            
            # Validate configuration
            if not self._validate_config():
                return False
            
            # Initialize database
            if not self._initialize_database():
                return False
            
            # Initialize services
            self._initialize_services()
            
            # Initialize bots
            if not self._initialize_bots():
                return False
            
            # Initialize web dashboard
            if not self._initialize_web_dashboard():
                return False
            
            logger.info("Application initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """Validate required configuration"""
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'ADMIN_BOT_TOKEN',
            'DATABASE_URL',
            'SECRET_KEY'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not hasattr(self.config, var) or not getattr(self.config, var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.error(f"Missing required configuration variables: {missing_vars}")
            logger.error("Please check your .env file and ensure all required variables are set")
            return False
        
        return True
    
    def _initialize_database(self) -> bool:
        """Initialize database connection and create tables"""
        try:
            logger.info("Initializing database...")
            
            # Initialize database manager
            self.db_manager = DatabaseManager(self.config)
            
            # Test database connection
            if not self.db_manager.test_connection():
                logger.error("Failed to connect to database")
                return False
            
            # Create tables
            with web_app.app_context():
                web_app.config.from_object(self.config)
                db.init_app(web_app)
                create_tables()
            
            logger.info("Database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False
    
    def _initialize_services(self):
        """Initialize application services"""
        logger.info("Initializing services...")
        
        # Initialize email service
        self.email_service = EmailService(self.config)
        
        # Test email configuration if enabled
        if hasattr(self.config, 'MAIL_SERVER') and self.config.MAIL_SERVER:
            try:
                self.email_service.test_email_config()
                logger.info("Email service initialized successfully")
            except Exception as e:
                logger.warning(f"Email service initialization failed: {e}")
        
        # Initialize backup service
        self.backup_service = BackupService(self.config)
        
        # Initialize security manager
        self.security_manager = SecurityManager(self.config)
        
        logger.info("Services initialized successfully")
    
    def _initialize_bots(self) -> bool:
        """Initialize Telegram bots"""
        try:
            logger.info("Initializing Telegram bots...")
            
            # Initialize main bot
            self.telegram_bot = TelegramQuizBot(self.config)
            
            # Initialize admin bot
            self.admin_bot = AdminBot(self.config)
            
            logger.info("Telegram bots initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bots: {e}")
            return False
    
    def _initialize_web_dashboard(self) -> bool:
        """Initialize web dashboard"""
        try:
            logger.info("Initializing web dashboard...")
            
            # Configure Flask app
            web_app.config.from_object(self.config)
            
            # Initialize database with Flask app
            with web_app.app_context():
                db.init_app(web_app)
            
            logger.info("Web dashboard initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize web dashboard: {e}")
            return False
    
    def start(self):
        """Start the application"""
        try:
            if not self.initialize():
                logger.error("Failed to initialize application")
                return False
            
            logger.info("Starting Telegram Quiz Bot application...")
            self.running = True
            
            # Start backup scheduler
            self.backup_service.start_backup_scheduler()
            
            # Start Telegram bots in separate threads
            bot_thread = threading.Thread(
                target=self._run_telegram_bot,
                name="TelegramBot",
                daemon=True
            )
            bot_thread.start()
            self.threads.append(bot_thread)
            
            admin_bot_thread = threading.Thread(
                target=self._run_admin_bot,
                name="AdminBot",
                daemon=True
            )
            admin_bot_thread.start()
            self.threads.append(admin_bot_thread)
            
            # Start web dashboard in separate thread if not in development mode
            if self.environment != 'development' or not self.config.FLASK_DEBUG:
                web_thread = threading.Thread(
                    target=self._run_web_dashboard,
                    name="WebDashboard",
                    daemon=True
                )
                web_thread.start()
                self.threads.append(web_thread)
            
            # Log startup
            self.db_manager.log_system_event(
                'application_started',
                f'Telegram Quiz Bot application started in {self.environment} mode',
                {
                    'environment': self.environment,
                    'timestamp': datetime.now().isoformat(),
                    'version': '1.0.0'
                }
            )
            
            logger.info("Application started successfully")
            
            # In development mode with Flask debug, run web dashboard in main thread
            if self.environment == 'development' and self.config.FLASK_DEBUG:
                self._run_web_dashboard()
            else:
                # Keep main thread alive
                self._keep_alive()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            self.shutdown()
            return False
    
    def _run_telegram_bot(self):
        """Run the main Telegram bot"""
        try:
            logger.info("Starting main Telegram bot...")
            self.telegram_bot.run()
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")
            if self.running:
                self.shutdown()
    
    def _run_admin_bot(self):
        """Run the admin Telegram bot"""
        try:
            logger.info("Starting admin Telegram bot...")
            self.admin_bot.run()
        except Exception as e:
            logger.error(f"Admin bot error: {e}")
            if self.running:
                self.shutdown()
    
    def _run_web_dashboard(self):
        """Run the web dashboard"""
        try:
            logger.info(f"Starting web dashboard on {self.config.FLASK_HOST}:{self.config.FLASK_PORT}...")
            web_app.run(
                host=self.config.FLASK_HOST,
                port=self.config.FLASK_PORT,
                debug=self.config.FLASK_DEBUG,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Web dashboard error: {e}")
            if self.running:
                self.shutdown()
    
    def _keep_alive(self):
        """Keep the main thread alive"""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shutdown the application"""
        if not self.running:
            return
        
        logger.info("Shutting down application...")
        self.running = False
        
        try:
            # Stop Telegram bots
            if self.telegram_bot:
                logger.info("Stopping main Telegram bot...")
                self.telegram_bot.stop()
            
            if self.admin_bot:
                logger.info("Stopping admin Telegram bot...")
                self.admin_bot.stop()
            
            # Log shutdown
            if self.db_manager:
                self.db_manager.log_system_event(
                    'application_stopped',
                    'Telegram Quiz Bot application stopped',
                    {
                        'timestamp': datetime.now().isoformat(),
                        'environment': self.environment
                    }
                )
            
            # Wait for threads to finish
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(timeout=5)
            
            logger.info("Application shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def create_admin_user(self, username: str, email: str, password: str, is_super_admin: bool = False) -> bool:
        """Create an admin user for web dashboard access"""
        try:
            if not self.db_manager:
                self.db_manager = DatabaseManager(self.config)
            
            # Check if user already exists
            existing_user = self.db_manager.get_admin_user_by_username(username)
            if existing_user:
                logger.error(f"Admin user '{username}' already exists")
                return False
            
            # Create admin user
            admin_user = self.db_manager.create_admin_user(
                username=username,
                email=email,
                password=password,
                is_super_admin=is_super_admin
            )
            
            if admin_user:
                logger.info(f"Admin user '{username}' created successfully")
                return True
            else:
                logger.error(f"Failed to create admin user '{username}'")
                return False
                
        except Exception as e:
            logger.error(f"Error creating admin user: {e}")
            return False

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telegram Quiz Bot')
    parser.add_argument(
        '--environment', '-e',
        choices=['development', 'production', 'testing'],
        default=os.getenv('ENVIRONMENT', 'development'),
        help='Environment to run in'
    )
    parser.add_argument(
        '--create-admin',
        action='store_true',
        help='Create an admin user for web dashboard'
    )
    parser.add_argument(
        '--admin-username',
        help='Admin username (required with --create-admin)'
    )
    parser.add_argument(
        '--admin-email',
        help='Admin email (required with --create-admin)'
    )
    parser.add_argument(
        '--admin-password',
        help='Admin password (required with --create-admin)'
    )
    parser.add_argument(
        '--super-admin',
        action='store_true',
        help='Make the admin user a super admin'
    )
    
    args = parser.parse_args()
    
    # Create application instance
    app = TelegramQuizBotApplication(args.environment)
    
    # Handle admin user creation
    if args.create_admin:
        if not all([args.admin_username, args.admin_email, args.admin_password]):
            logger.error("--admin-username, --admin-email, and --admin-password are required with --create-admin")
            sys.exit(1)
        
        success = app.create_admin_user(
            args.admin_username,
            args.admin_email,
            args.admin_password,
            args.super_admin
        )
        
        sys.exit(0 if success else 1)
    
    # Start the application
    try:
        success = app.start()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        app.shutdown()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        app.shutdown()
        sys.exit(1)

if __name__ == '__main__':
    main()