import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, func, desc, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import os
import subprocess

from models import db, User, Quiz, Question, QuestionOption, QuizAttempt, Answer, SystemLog, AdminUser
from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self, config: Config):
        self.config = config
        self.engine = create_engine(
            config.SQLALCHEMY_DATABASE_URI,
            **config.SQLALCHEMY_ENGINE_OPTIONS
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._session = None
    
    @property
    def session(self) -> Session:
        """Get current database session"""
        if self._session is None:
            self._session = self.SessionLocal()
        return self._session
    
    def close_session(self):
        """Close current database session"""
        if self._session:
            self._session.close()
            self._session = None
    
    def save_changes(self):
        """Commit current session changes"""
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error: {e}")
            raise
    
    def add_and_commit(self, obj):
        """Add object to session and commit"""
        try:
            self.session.add(obj)
            self.session.commit()
            return obj
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Database error: {e}")
            raise
    
    # User operations
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        """Get user by Telegram ID"""
        return self.session.query(User).filter(User.telegram_id == telegram_id).first()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        return self.session.query(User).filter(User.id == user_id).first()
    
    def get_all_users(self, active_only: bool = False) -> List[User]:
        """Get all users"""
        query = self.session.query(User)
        if active_only:
            query = query.filter(User.is_active == True)
        return query.order_by(User.created_at.desc()).all()
    
    def get_users_by_activity(self, days: int = 30) -> List[User]:
        """Get users active within specified days"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return self.session.query(User).filter(
            User.last_activity >= cutoff_date
        ).order_by(User.last_activity.desc()).all()
    
    def update_user_activity(self, user_id: int):
        """Update user's last activity timestamp"""
        user = self.get_user_by_id(user_id)
        if user:
            user.last_activity = datetime.now(timezone.utc)
            self.save_changes()
    
    # Quiz operations
    def get_quiz_by_id(self, quiz_id: int) -> Optional[Quiz]:
        """Get quiz by ID"""
        return self.session.query(Quiz).filter(Quiz.id == quiz_id).first()
    
    def get_active_quizzes(self) -> List[Quiz]:
        """Get all active quizzes"""
        return self.session.query(Quiz).filter(
            Quiz.is_active == True
        ).order_by(Quiz.created_at.desc()).all()
    
    def get_all_quizzes(self) -> List[Quiz]:
        """Get all quizzes"""
        return self.session.query(Quiz).order_by(Quiz.created_at.desc()).all()
    
    def get_quiz_with_questions(self, quiz_id: int) -> Optional[Quiz]:
        """Get quiz with all questions and options"""
        return self.session.query(Quiz).filter(
            Quiz.id == quiz_id
        ).first()
    
    def create_quiz(self, quiz_data: Dict[str, Any]) -> Quiz:
        """Create a new quiz"""
        quiz = Quiz(**quiz_data)
        return self.add_and_commit(quiz)
    
    def update_quiz(self, quiz_id: int, quiz_data: Dict[str, Any]) -> Optional[Quiz]:
        """Update existing quiz"""
        quiz = self.get_quiz_by_id(quiz_id)
        if quiz:
            for key, value in quiz_data.items():
                if hasattr(quiz, key):
                    setattr(quiz, key, value)
            quiz.updated_at = datetime.now(timezone.utc)
            self.save_changes()
        return quiz
    
    def delete_quiz(self, quiz_id: int) -> bool:
        """Delete a quiz"""
        quiz = self.get_quiz_by_id(quiz_id)
        if quiz:
            self.session.delete(quiz)
            self.save_changes()
            return True
        return False
    
    # Question operations
    def get_question_by_id(self, question_id: int) -> Optional[Question]:
        """Get question by ID"""
        return self.session.query(Question).filter(Question.id == question_id).first()
    
    def get_question_option_by_id(self, option_id: int) -> Optional[QuestionOption]:
        """Get question option by ID"""
        return self.session.query(QuestionOption).filter(QuestionOption.id == option_id).first()
    
    def create_question(self, question_data: Dict[str, Any]) -> Question:
        """Create a new question"""
        question = Question(**question_data)
        return self.add_and_commit(question)
    
    def create_question_option(self, option_data: Dict[str, Any]) -> QuestionOption:
        """Create a new question option"""
        option = QuestionOption(**option_data)
        return self.add_and_commit(option)
    
    # Quiz attempt operations
    def get_quiz_attempt(self, attempt_id: int) -> Optional[QuizAttempt]:
        """Get quiz attempt by ID"""
        return self.session.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
    
    def get_user_quiz_attempts(self, user_id: int, quiz_id: int) -> int:
        """Get count of user's attempts for a specific quiz"""
        return self.session.query(QuizAttempt).filter(
            and_(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz_id)
        ).count()
    
    def get_user_attempts(self, user_id: int) -> List[QuizAttempt]:
        """Get all attempts by a user"""
        return self.session.query(QuizAttempt).filter(
            QuizAttempt.user_id == user_id
        ).order_by(QuizAttempt.started_at.desc()).all()
    
    def get_quiz_attempts(self, quiz_id: int) -> List[QuizAttempt]:
        """Get all attempts for a quiz"""
        return self.session.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz_id
        ).order_by(QuizAttempt.started_at.desc()).all()
    
    def get_recent_attempts(self, days: int = 7) -> List[QuizAttempt]:
        """Get recent quiz attempts"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        return self.session.query(QuizAttempt).filter(
            QuizAttempt.started_at >= cutoff_date
        ).order_by(QuizAttempt.started_at.desc()).all()
    
    def create_quiz_attempt(self, attempt_data: Dict[str, Any]) -> QuizAttempt:
        """Create a new quiz attempt"""
        attempt = QuizAttempt(**attempt_data)
        return self.add_and_commit(attempt)
    
    # Answer operations
    def create_answer(self, answer_data: Dict[str, Any]) -> Answer:
        """Create a new answer"""
        answer = Answer(**answer_data)
        return self.add_and_commit(answer)
    
    def get_attempt_answers(self, attempt_id: int) -> List[Answer]:
        """Get all answers for an attempt"""
        return self.session.query(Answer).filter(
            Answer.attempt_id == attempt_id
        ).order_by(Answer.answered_at).all()
    
    # System logs
    def create_system_log(self, log_data: Dict[str, Any]) -> SystemLog:
        """Create a system log entry"""
        log = SystemLog(**log_data)
        return self.add_and_commit(log)
    
    def get_recent_logs(self, limit: int = 100, event_type: Optional[str] = None) -> List[SystemLog]:
        """Get recent system logs"""
        query = self.session.query(SystemLog)
        if event_type:
            query = query.filter(SystemLog.event_type == event_type)
        return query.order_by(SystemLog.created_at.desc()).limit(limit).all()
    
    def cleanup_old_logs(self, days: int = 90):
        """Clean up old system logs"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = self.session.query(SystemLog).filter(
            SystemLog.created_at < cutoff_date
        ).delete()
        self.save_changes()
        return deleted_count
    
    # Admin user operations
    def get_admin_user_by_username(self, username: str) -> Optional[AdminUser]:
        """Get admin user by username"""
        return self.session.query(AdminUser).filter(AdminUser.username == username).first()
    
    def get_admin_user_by_email(self, email: str) -> Optional[AdminUser]:
        """Get admin user by email"""
        return self.session.query(AdminUser).filter(AdminUser.email == email).first()
    
    def create_admin_user(self, admin_data: Dict[str, Any]) -> AdminUser:
        """Create a new admin user"""
        admin = AdminUser(**admin_data)
        return self.add_and_commit(admin)
    
    # Statistics and analytics
    def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # User statistics
        total_users = self.session.query(User).count()
        active_users = self.session.query(User).filter(User.is_active == True).count()
        new_users_week = self.session.query(User).filter(User.created_at >= week_ago).count()
        new_users_month = self.session.query(User).filter(User.created_at >= month_ago).count()
        
        # Quiz statistics
        total_quizzes = self.session.query(Quiz).count()
        active_quizzes = self.session.query(Quiz).filter(Quiz.is_active == True).count()
        total_questions = self.session.query(Question).count()
        
        # Attempt statistics
        total_attempts = self.session.query(QuizAttempt).count()
        completed_attempts = self.session.query(QuizAttempt).filter(
            QuizAttempt.status == 'completed'
        ).count()
        
        attempts_today = self.session.query(QuizAttempt).filter(
            QuizAttempt.started_at >= today_start
        ).count()
        
        attempts_week = self.session.query(QuizAttempt).filter(
            QuizAttempt.started_at >= week_ago
        ).count()
        
        # Average score and pass rate
        completed_attempts_query = self.session.query(QuizAttempt).filter(
            and_(QuizAttempt.status == 'completed', QuizAttempt.percentage.isnot(None))
        )
        
        avg_score_result = completed_attempts_query.with_entities(
            func.avg(QuizAttempt.percentage)
        ).scalar()
        average_score = float(avg_score_result) if avg_score_result else 0.0
        
        passed_attempts = self.session.query(QuizAttempt).filter(
            QuizAttempt.is_passed == True
        ).count()
        pass_rate = (passed_attempts / max(completed_attempts, 1)) * 100
        
        # Most popular quiz
        popular_quiz_result = self.session.query(
            Quiz.title,
            func.count(QuizAttempt.id).label('attempt_count')
        ).join(QuizAttempt).group_by(Quiz.id, Quiz.title).order_by(
            desc('attempt_count')
        ).first()
        
        most_popular_quiz = popular_quiz_result[0] if popular_quiz_result else 'None'
        
        # Database size (approximate)
        db_size = self._get_database_size()
        
        # Last backup info
        last_backup = self._get_last_backup_info()
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'new_users_week': new_users_week,
            'new_users_month': new_users_month,
            'total_quizzes': total_quizzes,
            'active_quizzes': active_quizzes,
            'total_questions': total_questions,
            'total_attempts': total_attempts,
            'completed_attempts': completed_attempts,
            'attempts_today': attempts_today,
            'attempts_week': attempts_week,
            'average_score': average_score,
            'pass_rate': pass_rate,
            'most_popular_quiz': most_popular_quiz,
            'db_size': db_size,
            'last_backup': last_backup
        }
    
    def get_quiz_analytics(self, quiz_id: int) -> Dict[str, Any]:
        """Get detailed analytics for a specific quiz"""
        quiz = self.get_quiz_by_id(quiz_id)
        if not quiz:
            return {}
        
        attempts = self.get_quiz_attempts(quiz_id)
        completed_attempts = [a for a in attempts if a.status == 'completed']
        
        if not completed_attempts:
            return {
                'quiz_id': quiz_id,
                'quiz_title': quiz.title,
                'total_attempts': len(attempts),
                'completed_attempts': 0,
                'average_score': 0,
                'pass_rate': 0,
                'completion_rate': 0,
                'average_time': 0,
                'score_distribution': {},
                'question_analytics': []
            }
        
        # Basic statistics
        total_attempts = len(attempts)
        completed_count = len(completed_attempts)
        completion_rate = (completed_count / max(total_attempts, 1)) * 100
        
        scores = [a.percentage for a in completed_attempts if a.percentage is not None]
        average_score = sum(scores) / len(scores) if scores else 0
        
        passed_count = len([a for a in completed_attempts if a.is_passed])
        pass_rate = (passed_count / max(completed_count, 1)) * 100
        
        times = [a.time_taken for a in completed_attempts if a.time_taken is not None]
        average_time = sum(times) / len(times) if times else 0
        
        # Score distribution
        score_ranges = {'0-20': 0, '21-40': 0, '41-60': 0, '61-80': 0, '81-100': 0}
        for score in scores:
            if score <= 20:
                score_ranges['0-20'] += 1
            elif score <= 40:
                score_ranges['21-40'] += 1
            elif score <= 60:
                score_ranges['41-60'] += 1
            elif score <= 80:
                score_ranges['61-80'] += 1
            else:
                score_ranges['81-100'] += 1
        
        # Question-level analytics
        question_analytics = []
        for question in quiz.questions:
            correct_answers = self.session.query(Answer).filter(
                and_(
                    Answer.question_id == question.id,
                    Answer.is_correct == True
                )
            ).count()
            
            total_answers = self.session.query(Answer).filter(
                Answer.question_id == question.id
            ).count()
            
            accuracy = (correct_answers / max(total_answers, 1)) * 100
            
            question_analytics.append({
                'question_id': question.id,
                'question_text': question.question_text[:100] + '...' if len(question.question_text) > 100 else question.question_text,
                'total_answers': total_answers,
                'correct_answers': correct_answers,
                'accuracy': accuracy
            })
        
        return {
            'quiz_id': quiz_id,
            'quiz_title': quiz.title,
            'total_attempts': total_attempts,
            'completed_attempts': completed_count,
            'completion_rate': completion_rate,
            'average_score': average_score,
            'pass_rate': pass_rate,
            'average_time': average_time,
            'score_distribution': score_ranges,
            'question_analytics': question_analytics
        }
    
    def _get_database_size(self) -> str:
        """Get approximate database size"""
        try:
            # This is a simplified approach - in production, you might want to use database-specific queries
            result = self.session.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ).scalar()
            return result or 'Unknown'
        except Exception:
            return 'Unknown'
    
    def _get_last_backup_info(self) -> str:
        """Get last backup information"""
        backup_path = self.config.BACKUP_PATH
        if os.path.exists(backup_path):
            try:
                files = [f for f in os.listdir(backup_path) if f.endswith('.sql')]
                if files:
                    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(backup_path, x)))
                    timestamp = os.path.getctime(os.path.join(backup_path, latest_file))
                    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass
        return 'Never'
    
    def create_backup(self) -> str:
        """Create database backup"""
        try:
            backup_dir = self.config.BACKUP_PATH
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'quiz_bot_backup_{timestamp}.sql')
            
            # Extract database connection details
            db_url = self.config.SQLALCHEMY_DATABASE_URI
            # This is a simplified backup - in production, use proper pg_dump with credentials
            
            # For now, return a placeholder
            with open(backup_file, 'w') as f:
                f.write(f"-- Database backup created at {datetime.now()}\n")
                f.write("-- This is a placeholder backup file\n")
            
            return backup_file
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            raise
    
    def cleanup_old_backups(self, retention_days: int = None):
        """Clean up old backup files"""
        if retention_days is None:
            retention_days = self.config.BACKUP_RETENTION_DAYS
        
        backup_dir = self.config.BACKUP_PATH
        if not os.path.exists(backup_dir):
            return 0
        
        cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 3600)
        deleted_count = 0
        
        try:
            for filename in os.listdir(backup_dir):
                if filename.endswith('.sql'):
                    file_path = os.path.join(backup_dir, filename)
                    if os.path.getctime(file_path) < cutoff_time:
                        os.remove(file_path)
                        deleted_count += 1
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
        
        return deleted_count
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_session()