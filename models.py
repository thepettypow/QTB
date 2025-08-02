from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

class User(db.Model):
    """Telegram user model"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone_number = Column(String(20), nullable=True)
    email = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_activity = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    quiz_attempts = relationship('QuizAttempt', back_populates='user', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.telegram_id}: {self.first_name} {self.last_name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone_number': self.phone_number,
            'email': self.email,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }

class Quiz(db.Model):
    """Quiz/Test model"""
    __tablename__ = 'quizzes'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    time_limit = Column(Integer, nullable=True)  # in seconds
    max_attempts = Column(Integer, default=1)
    passing_score = Column(Float, default=0.0)  # percentage
    randomize_questions = Column(Boolean, default=False)
    show_results = Column(Boolean, default=True)
    allow_review = Column(Boolean, default=True)
    notification_emails = Column(Text, nullable=True)  # JSON array of emails
    created_by = Column(String(50), nullable=False)  # telegram_id of creator
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    questions = relationship('Question', back_populates='quiz', cascade='all, delete-orphan', order_by='Question.order_index')
    attempts = relationship('QuizAttempt', back_populates='quiz', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Quiz {self.id}: {self.title}>'
    
    @property
    def notification_email_list(self):
        if self.notification_emails:
            try:
                return json.loads(self.notification_emails)
            except json.JSONDecodeError:
                return []
        return []
    
    @notification_email_list.setter
    def notification_email_list(self, emails):
        self.notification_emails = json.dumps(emails) if emails else None
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'instructions': self.instructions,
            'is_active': self.is_active,
            'time_limit': self.time_limit,
            'max_attempts': self.max_attempts,
            'passing_score': self.passing_score,
            'randomize_questions': self.randomize_questions,
            'show_results': self.show_results,
            'allow_review': self.allow_review,
            'notification_emails': self.notification_email_list,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'question_count': len(self.questions),
            'attempt_count': len(self.attempts)
        }

class Question(db.Model):
    """Question model"""
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    quiz_id = Column(Integer, ForeignKey('quizzes.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), default='multiple_choice')  # multiple_choice, text, boolean
    order_index = Column(Integer, nullable=False)
    points = Column(Float, default=1.0)
    is_required = Column(Boolean, default=True)
    explanation = Column(Text, nullable=True)
    
    # Relationships
    quiz = relationship('Quiz', back_populates='questions')
    options = relationship('QuestionOption', back_populates='question', cascade='all, delete-orphan', order_by='QuestionOption.order_index')
    answers = relationship('Answer', back_populates='question', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Question {self.id}: {self.question_text[:50]}...>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'quiz_id': self.quiz_id,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'order_index': self.order_index,
            'points': self.points,
            'is_required': self.is_required,
            'explanation': self.explanation,
            'options': [option.to_dict() for option in self.options]
        }

class QuestionOption(db.Model):
    """Question option model for multiple choice questions"""
    __tablename__ = 'question_options'
    
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    order_index = Column(Integer, nullable=False)
    
    # Relationships
    question = relationship('Question', back_populates='options')
    
    def __repr__(self):
        return f'<QuestionOption {self.id}: {self.option_text[:30]}...>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'question_id': self.question_id,
            'option_text': self.option_text,
            'is_correct': self.is_correct,
            'order_index': self.order_index
        }

class QuizAttempt(db.Model):
    """Quiz attempt model"""
    __tablename__ = 'quiz_attempts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    quiz_id = Column(Integer, ForeignKey('quizzes.id'), nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    is_passed = Column(Boolean, nullable=True)
    time_taken = Column(Integer, nullable=True)  # in seconds
    status = Column(String(20), default='in_progress')  # in_progress, completed, abandoned, expired
    
    # Relationships
    user = relationship('User', back_populates='quiz_attempts')
    quiz = relationship('Quiz', back_populates='attempts')
    answers = relationship('Answer', back_populates='attempt', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<QuizAttempt {self.id}: User {self.user_id} Quiz {self.quiz_id}>'
    
    def calculate_score(self):
        """Calculate the score for this attempt"""
        total_points = 0
        earned_points = 0
        
        for answer in self.answers:
            total_points += answer.question.points
            if answer.is_correct:
                earned_points += answer.question.points
        
        self.score = earned_points
        self.max_score = total_points
        self.percentage = (earned_points / total_points * 100) if total_points > 0 else 0
        self.is_passed = self.percentage >= self.quiz.passing_score
        
        return self.score, self.max_score, self.percentage
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'quiz_id': self.quiz_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'score': self.score,
            'max_score': self.max_score,
            'percentage': self.percentage,
            'is_passed': self.is_passed,
            'time_taken': self.time_taken,
            'status': self.status,
            'user': self.user.to_dict() if self.user else None,
            'quiz': self.quiz.to_dict() if self.quiz else None
        }

class Answer(db.Model):
    """Answer model"""
    __tablename__ = 'answers'
    
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey('quiz_attempts.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    selected_option_id = Column(Integer, ForeignKey('question_options.id'), nullable=True)
    text_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    points_earned = Column(Float, default=0.0)
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    attempt = relationship('QuizAttempt', back_populates='answers')
    question = relationship('Question', back_populates='answers')
    selected_option = relationship('QuestionOption')
    
    def __repr__(self):
        return f'<Answer {self.id}: Attempt {self.attempt_id} Question {self.question_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'attempt_id': self.attempt_id,
            'question_id': self.question_id,
            'selected_option_id': self.selected_option_id,
            'text_answer': self.text_answer,
            'is_correct': self.is_correct,
            'points_earned': self.points_earned,
            'answered_at': self.answered_at.isoformat() if self.answered_at else None
        }

class AdminUser(db.Model):
    """Admin user model for web dashboard"""
    __tablename__ = 'admin_users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_super_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<AdminUser {self.username}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'is_super_admin': self.is_super_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class SystemLog(db.Model):
    """System log model for tracking important events"""
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False)  # user_action, system_event, error, etc.
    message = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    admin_user_id = Column(Integer, ForeignKey('admin_users.id'), nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship('User')
    admin_user = relationship('AdminUser')
    
    def __repr__(self):
        return f'<SystemLog {self.id}: {self.event_type}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'event_type': self.event_type,
            'message': self.message,
            'user_id': self.user_id,
            'admin_user_id': self.admin_user_id,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }