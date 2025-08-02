import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import io
import json
from typing import Dict, Any, List, Optional

from config import Config, DevelopmentConfig, ProductionConfig
from models import db, User, Quiz, Question, QuizAttempt, AdminUser, SystemLog
from utils.database import DatabaseManager
from utils.email_service import EmailService
from utils.export_service import ExportService
from utils.backup_service import BackupService
from utils.security import SecurityManager

logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)

# Configuration
if app.config.get('ENVIRONMENT') == 'production':
    config = ProductionConfig()
else:
    config = DevelopmentConfig()

app.config.from_object(config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize services
db_manager = DatabaseManager(config)
email_service = EmailService(config)
export_service = ExportService(config)
backup_service = BackupService(config)
security_manager = SecurityManager(config)

class WebAdminUser(UserMixin):
    """User class for Flask-Login"""
    
    def __init__(self, admin_user: AdminUser):
        self.id = admin_user.id
        self.username = admin_user.username
        self.email = admin_user.email
        self.is_active = admin_user.is_active
        self.is_super_admin = admin_user.is_super_admin
        self.last_login = admin_user.last_login

@login_manager.user_loader
def load_user(user_id):
    admin_user = db_manager.get_admin_user_by_id(int(user_id))
    if admin_user:
        return WebAdminUser(admin_user)
    return None

def admin_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Decorator to require super admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin:
            flash('Super admin privileges required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    """Redirect to dashboard or login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html')
        
        admin_user = db_manager.get_admin_user_by_username(username)
        
        if admin_user and security_manager.verify_password(password, admin_user.password_hash):
            if admin_user.is_active:
                web_user = WebAdminUser(admin_user)
                login_user(web_user)
                
                # Update last login
                db_manager.update_admin_last_login(admin_user.id)
                
                # Log login event
                db_manager.log_system_event(
                    'admin_login',
                    f'Admin user {username} logged in',
                    {'user_id': admin_user.id, 'ip': request.remote_addr}
                )
                
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
            else:
                flash('Account is deactivated.', 'error')
        else:
            flash('Invalid username or password.', 'error')
            
            # Log failed login attempt
            db_manager.log_system_event(
                'admin_login_failed',
                f'Failed login attempt for username: {username}',
                {'username': username, 'ip': request.remote_addr}
            )
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Admin logout"""
    username = current_user.username
    logout_user()
    
    # Log logout event
    db_manager.log_system_event(
        'admin_logout',
        f'Admin user {username} logged out',
        {'ip': request.remote_addr}
    )
    
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@admin_required
def dashboard():
    """Main dashboard"""
    try:
        # Get system statistics
        stats = db_manager.get_system_stats()
        
        # Get recent activity
        recent_attempts = db_manager.session.query(QuizAttempt).filter(
            QuizAttempt.status == 'completed'
        ).order_by(QuizAttempt.completed_at.desc()).limit(10).all()
        
        # Get recent logs
        recent_logs = db_manager.session.query(SystemLog).order_by(
            SystemLog.created_at.desc()
        ).limit(20).all()
        
        # Get quiz performance data
        quiz_performance = []
        quizzes = db_manager.get_all_quizzes()
        
        for quiz in quizzes[:10]:  # Top 10 quizzes
            analytics = db_manager.get_quiz_analytics(quiz.id)
            quiz_performance.append({
                'quiz': quiz,
                'analytics': analytics
            })
        
        return render_template('dashboard.html',
                             stats=stats,
                             recent_attempts=recent_attempts,
                             recent_logs=recent_logs,
                             quiz_performance=quiz_performance)
    
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash('Error loading dashboard data.', 'error')
        return render_template('dashboard.html', stats={}, recent_attempts=[], recent_logs=[])

@app.route('/users')
@admin_required
def users():
    """User management page"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        users_query = db_manager.session.query(User)
        
        # Search filter
        search = request.args.get('search')
        if search:
            users_query = users_query.filter(
                db.or_(
                    User.first_name.ilike(f'%{search}%'),
                    User.last_name.ilike(f'%{search}%'),
                    User.username.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%')
                )
            )
        
        # Status filter
        status = request.args.get('status')
        if status == 'active':
            users_query = users_query.filter(User.is_active == True)
        elif status == 'inactive':
            users_query = users_query.filter(User.is_active == False)
        
        users_pagination = users_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('users.html',
                             users=users_pagination.items,
                             pagination=users_pagination,
                             search=search,
                             status=status)
    
    except Exception as e:
        logger.error(f"Users page error: {e}")
        flash('Error loading users data.', 'error')
        return render_template('users.html', users=[], pagination=None)

@app.route('/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    """User detail page"""
    try:
        user = db_manager.get_user_by_id(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('users'))
        
        # Get user's quiz attempts
        attempts = db_manager.session.query(QuizAttempt).filter(
            QuizAttempt.user_id == user_id
        ).order_by(QuizAttempt.created_at.desc()).all()
        
        return render_template('user_detail.html', user=user, attempts=attempts)
    
    except Exception as e:
        logger.error(f"User detail error: {e}")
        flash('Error loading user details.', 'error')
        return redirect(url_for('users'))

@app.route('/quizzes')
@admin_required
def quizzes():
    """Quiz management page"""
    try:
        quizzes = db_manager.get_all_quizzes()
        
        # Add analytics to each quiz
        quiz_data = []
        for quiz in quizzes:
            analytics = db_manager.get_quiz_analytics(quiz.id)
            quiz_data.append({
                'quiz': quiz,
                'analytics': analytics
            })
        
        return render_template('quizzes.html', quiz_data=quiz_data)
    
    except Exception as e:
        logger.error(f"Quizzes page error: {e}")
        flash('Error loading quizzes data.', 'error')
        return render_template('quizzes.html', quiz_data=[])

@app.route('/quizzes/<int:quiz_id>')
@admin_required
def quiz_detail(quiz_id):
    """Quiz detail page"""
    try:
        quiz = db_manager.get_quiz_by_id(quiz_id)
        if not quiz:
            flash('Quiz not found.', 'error')
            return redirect(url_for('quizzes'))
        
        # Get quiz analytics
        analytics = db_manager.get_quiz_analytics(quiz_id)
        
        # Get recent attempts
        attempts = db_manager.get_quiz_attempts(quiz_id, limit=20)
        
        return render_template('quiz_detail.html',
                             quiz=quiz,
                             analytics=analytics,
                             attempts=attempts)
    
    except Exception as e:
        logger.error(f"Quiz detail error: {e}")
        flash('Error loading quiz details.', 'error')
        return redirect(url_for('quizzes'))

@app.route('/analytics')
@admin_required
def analytics():
    """Analytics page"""
    try:
        # Get date range from request
        days = request.args.get('days', 30, type=int)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get analytics data
        stats = db_manager.get_system_stats()
        
        # Get daily activity data
        daily_activity = db_manager.get_daily_activity(start_date, end_date)
        
        # Get quiz performance data
        quiz_performance = []
        quizzes = db_manager.get_all_quizzes()
        
        for quiz in quizzes:
            analytics = db_manager.get_quiz_analytics(quiz.id)
            if analytics['total_attempts'] > 0:
                quiz_performance.append({
                    'quiz': quiz,
                    'analytics': analytics
                })
        
        # Sort by total attempts
        quiz_performance.sort(key=lambda x: x['analytics']['total_attempts'], reverse=True)
        
        return render_template('analytics.html',
                             stats=stats,
                             daily_activity=daily_activity,
                             quiz_performance=quiz_performance,
                             days=days)
    
    except Exception as e:
        logger.error(f"Analytics page error: {e}")
        flash('Error loading analytics data.', 'error')
        return render_template('analytics.html', stats={}, daily_activity=[], quiz_performance=[])

@app.route('/exports')
@admin_required
def exports():
    """Data export page"""
    return render_template('exports.html')

@app.route('/export/<export_type>')
@admin_required
def export_data(export_type):
    """Export data in various formats"""
    try:
        quiz_id = request.args.get('quiz_id', type=int)
        
        if export_type == 'quiz_results_csv':
            data = export_service.export_quiz_results_csv(quiz_id)
            filename = f"quiz_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            mimetype = 'text/csv'
        
        elif export_type == 'quiz_results_excel':
            data = export_service.export_quiz_results_excel(quiz_id)
            filename = f"quiz_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        
        elif export_type == 'users_csv':
            data = export_service.export_users_csv()
            filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            mimetype = 'text/csv'
        
        elif export_type == 'quizzes_csv':
            data = export_service.export_quizzes_csv()
            filename = f"quizzes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            mimetype = 'text/csv'
        
        elif export_type == 'analytics_pdf':
            data = export_service.export_analytics_pdf(quiz_id)
            filename = f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            mimetype = 'application/pdf'
        
        else:
            flash('Invalid export type.', 'error')
            return redirect(url_for('exports'))
        
        # Log export event
        db_manager.log_system_event(
            'data_export',
            f'Data exported: {export_type}',
            {
                'export_type': export_type,
                'quiz_id': quiz_id,
                'admin_user': current_user.username,
                'filename': filename
            }
        )
        
        return send_file(
            io.BytesIO(data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        logger.error(f"Export error: {e}")
        flash('Error generating export.', 'error')
        return redirect(url_for('exports'))

@app.route('/backups')
@admin_required
def backups():
    """Backup management page"""
    try:
        backup_list = backup_service.list_backups()
        backup_status = backup_service.get_backup_status()
        
        return render_template('backups.html',
                             backups=backup_list,
                             status=backup_status)
    
    except Exception as e:
        logger.error(f"Backups page error: {e}")
        flash('Error loading backup data.', 'error')
        return render_template('backups.html', backups=[], status={})

@app.route('/create_backup', methods=['POST'])
@admin_required
def create_backup():
    """Create a new backup"""
    try:
        result = backup_service.create_backup('manual')
        
        if result['success']:
            flash(f"Backup created successfully: {result['backup_name']}", 'success')
        else:
            flash(f"Backup failed: {result.get('error', 'Unknown error')}", 'error')
    
    except Exception as e:
        logger.error(f"Create backup error: {e}")
        flash('Error creating backup.', 'error')
    
    return redirect(url_for('backups'))

@app.route('/delete_backup/<backup_name>', methods=['POST'])
@super_admin_required
def delete_backup(backup_name):
    """Delete a backup"""
    try:
        result = backup_service.delete_backup(backup_name)
        
        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['error'], 'error')
    
    except Exception as e:
        logger.error(f"Delete backup error: {e}")
        flash('Error deleting backup.', 'error')
    
    return redirect(url_for('backups'))

@app.route('/logs')
@admin_required
def logs():
    """System logs page"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        logs_query = db_manager.session.query(SystemLog)
        
        # Filter by event type
        event_type = request.args.get('event_type')
        if event_type:
            logs_query = logs_query.filter(SystemLog.event_type == event_type)
        
        # Filter by date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            logs_query = logs_query.filter(SystemLog.created_at >= start_date)
        if end_date:
            logs_query = logs_query.filter(SystemLog.created_at <= end_date)
        
        logs_pagination = logs_query.order_by(
            SystemLog.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        # Get unique event types for filter
        event_types = db_manager.session.query(SystemLog.event_type).distinct().all()
        event_types = [et[0] for et in event_types]
        
        return render_template('logs.html',
                             logs=logs_pagination.items,
                             pagination=logs_pagination,
                             event_types=event_types,
                             current_event_type=event_type,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        logger.error(f"Logs page error: {e}")
        flash('Error loading logs data.', 'error')
        return render_template('logs.html', logs=[], pagination=None, event_types=[])

@app.route('/settings')
@super_admin_required
def settings():
    """System settings page"""
    try:
        # Get current settings
        current_settings = {
            'app_name': getattr(config, 'APP_NAME', 'Telegram Quiz Bot'),
            'environment': getattr(config, 'ENVIRONMENT', 'development'),
            'max_content_length': getattr(config, 'MAX_CONTENT_LENGTH', 16777216),
            'backup_schedule': getattr(config, 'BACKUP_SCHEDULE', 'daily'),
            'max_backups': getattr(config, 'MAX_BACKUPS', 30)
        }
        
        return render_template('settings.html', settings=current_settings)
    
    except Exception as e:
        logger.error(f"Settings page error: {e}")
        flash('Error loading settings.', 'error')
        return render_template('settings.html', settings={})

# API Routes
@app.route('/api/stats')
@admin_required
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        stats = db_manager.get_system_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"API stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/<int:quiz_id>/analytics')
@admin_required
def api_quiz_analytics(quiz_id):
    """API endpoint for quiz analytics"""
    try:
        analytics = db_manager.get_quiz_analytics(quiz_id)
        return jsonify(analytics)
    except Exception as e:
        logger.error(f"API quiz analytics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<int:user_id>/toggle_status', methods=['POST'])
@admin_required
def api_toggle_user_status(user_id):
    """API endpoint to toggle user active status"""
    try:
        user = db_manager.get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        new_status = not user.is_active
        db_manager.update_user_status(user_id, new_status)
        
        # Log the action
        db_manager.log_system_event(
            'user_status_changed',
            f'User {user.username or user.first_name} status changed to {"active" if new_status else "inactive"}',
            {
                'user_id': user_id,
                'new_status': new_status,
                'admin_user': current_user.username
            }
        )
        
        return jsonify({
            'success': True,
            'new_status': new_status,
            'message': f'User {"activated" if new_status else "deactivated"} successfully'
        })
    
    except Exception as e:
        logger.error(f"API toggle user status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/<int:quiz_id>/toggle_status', methods=['POST'])
@admin_required
def api_toggle_quiz_status(quiz_id):
    """API endpoint to toggle quiz active status"""
    try:
        quiz = db_manager.get_quiz_by_id(quiz_id)
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        
        new_status = not quiz.is_active
        db_manager.update_quiz_status(quiz_id, new_status)
        
        # Log the action
        db_manager.log_system_event(
            'quiz_status_changed',
            f'Quiz "{quiz.title}" status changed to {"active" if new_status else "inactive"}',
            {
                'quiz_id': quiz_id,
                'new_status': new_status,
                'admin_user': current_user.username
            }
        )
        
        return jsonify({
            'success': True,
            'new_status': new_status,
            'message': f'Quiz {"activated" if new_status else "deactivated"} successfully'
        })
    
    except Exception as e:
        logger.error(f"API toggle quiz status error: {e}")
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Start backup scheduler
    backup_service.start_backup_scheduler()
    
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG
    )