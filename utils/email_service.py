import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Optional, Dict, Any
import os
import json

from config import Config
from models import Quiz, QuizAttempt, User

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending notifications and reports"""
    
    def __init__(self, config: Config):
        self.config = config
        self.smtp_server = config.SMTP_SERVER
        self.smtp_port = config.SMTP_PORT
        self.smtp_username = config.SMTP_USERNAME
        self.smtp_password = config.SMTP_PASSWORD
        self.smtp_use_tls = config.SMTP_USE_TLS
        self.default_from_email = config.DEFAULT_FROM_EMAIL
    
    def _create_smtp_connection(self):
        """Create SMTP connection"""
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.smtp_use_tls:
                server.starttls()
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            return server
        except Exception as e:
            logger.error(f"Failed to create SMTP connection: {e}")
            raise
    
    def send_email(self, 
                   to_emails: List[str], 
                   subject: str, 
                   body: str, 
                   html_body: Optional[str] = None,
                   attachments: Optional[List[Dict[str, Any]]] = None,
                   from_email: Optional[str] = None) -> bool:
        """Send email with optional HTML body and attachments"""
        try:
            if not to_emails:
                logger.warning("No recipient emails provided")
                return False
            
            from_email = from_email or self.default_from_email
            if not from_email:
                logger.error("No from email configured")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = from_email
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            
            # Add text body
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Add HTML body if provided
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    self._add_attachment(msg, attachment)
            
            # Send email
            with self._create_smtp_connection() as server:
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {', '.join(to_emails)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]):
        """Add attachment to email message"""
        try:
            filename = attachment['filename']
            content = attachment['content']
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            part = MIMEBase(*content_type.split('/'))
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            msg.attach(part)
            
        except Exception as e:
            logger.error(f"Failed to add attachment {attachment.get('filename', 'unknown')}: {e}")
    
    async def send_quiz_completion_notification(self, 
                                              quiz: Quiz, 
                                              attempt: QuizAttempt, 
                                              user: User) -> bool:
        """Send notification when a user completes a quiz"""
        try:
            if not quiz.notification_email_list:
                logger.info(f"No notification emails configured for quiz {quiz.id}")
                return True
            
            # Prepare email content
            subject = f"Quiz Completed: {quiz.title} - {user.first_name} {user.last_name or ''}"
            
            # Text body
            body = f"""Quiz Completion Notification

User Details:
- Name: {user.first_name} {user.last_name or ''}
- Username: @{user.username or 'Not set'}
- Telegram ID: {user.telegram_id}
- Email: {user.email or 'Not provided'}

Quiz Details:
- Title: {quiz.title}
- Description: {quiz.description or 'No description'}

Results:
- Score: {attempt.score}/{attempt.max_score} ({attempt.percentage:.1f}%)
- Status: {'Passed' if attempt.is_passed else 'Failed'}
- Time Taken: {attempt.time_taken//60 if attempt.time_taken else 0}m {attempt.time_taken%60 if attempt.time_taken else 0}s
- Completed At: {attempt.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if attempt.completed_at else 'Unknown'}

Passing Score: {quiz.passing_score}%

This is an automated notification from the Telegram Quiz Bot system."""
            
            # HTML body
            html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Quiz Completion Notification</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .result-box {{ background-color: {'#d4edda' if attempt.is_passed else '#f8d7da'}; 
                      border: 1px solid {'#c3e6cb' if attempt.is_passed else '#f5c6cb'}; 
                      color: {'#155724' if attempt.is_passed else '#721c24'}; 
                      padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .details {{ background-color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .label {{ font-weight: bold; width: 30%; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Quiz Completion Notification</h1>
        </div>
        <div class="content">
            <div class="result-box">
                <h2>{'✅ Quiz Passed!' if attempt.is_passed else '❌ Quiz Failed'}</h2>
                <p><strong>Score: {attempt.score}/{attempt.max_score} ({attempt.percentage:.1f}%)</strong></p>
            </div>
            
            <div class="details">
                <h3>👤 User Information</h3>
                <table>
                    <tr><td class="label">Name:</td><td>{user.first_name} {user.last_name or ''}</td></tr>
                    <tr><td class="label">Username:</td><td>@{user.username or 'Not set'}</td></tr>
                    <tr><td class="label">Telegram ID:</td><td>{user.telegram_id}</td></tr>
                    <tr><td class="label">Email:</td><td>{user.email or 'Not provided'}</td></tr>
                </table>
            </div>
            
            <div class="details">
                <h3>📝 Quiz Information</h3>
                <table>
                    <tr><td class="label">Title:</td><td>{quiz.title}</td></tr>
                    <tr><td class="label">Description:</td><td>{quiz.description or 'No description'}</td></tr>
                    <tr><td class="label">Passing Score:</td><td>{quiz.passing_score}%</td></tr>
                </table>
            </div>
            
            <div class="details">
                <h3>📊 Results</h3>
                <table>
                    <tr><td class="label">Score:</td><td>{attempt.score}/{attempt.max_score} ({attempt.percentage:.1f}%)</td></tr>
                    <tr><td class="label">Status:</td><td>{'Passed' if attempt.is_passed else 'Failed'}</td></tr>
                    <tr><td class="label">Time Taken:</td><td>{attempt.time_taken//60 if attempt.time_taken else 0}m {attempt.time_taken%60 if attempt.time_taken else 0}s</td></tr>
                    <tr><td class="label">Completed:</td><td>{attempt.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if attempt.completed_at else 'Unknown'}</td></tr>
                </table>
            </div>
        </div>
        <div class="footer">
            <p>This is an automated notification from the Telegram Quiz Bot system.</p>
            <p>Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
    </div>
</body>
</html>"""
            
            # Send email
            return self.send_email(
                to_emails=quiz.notification_email_list,
                subject=subject,
                body=body,
                html_body=html_body
            )
            
        except Exception as e:
            logger.error(f"Failed to send quiz completion notification: {e}")
            return False
    
    def send_daily_report(self, stats: Dict[str, Any], to_emails: List[str]) -> bool:
        """Send daily statistics report"""
        try:
            subject = f"Daily Quiz Bot Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            body = f"""Daily Quiz Bot Statistics Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

User Statistics:
- Total Users: {stats.get('total_users', 0)}
- Active Users: {stats.get('active_users', 0)}
- New Users (Last 7 days): {stats.get('new_users_week', 0)}
- New Users (Last 30 days): {stats.get('new_users_month', 0)}

Quiz Statistics:
- Total Quizzes: {stats.get('total_quizzes', 0)}
- Active Quizzes: {stats.get('active_quizzes', 0)}
- Total Questions: {stats.get('total_questions', 0)}

Attempt Statistics:
- Total Attempts: {stats.get('total_attempts', 0)}
- Completed Attempts: {stats.get('completed_attempts', 0)}
- Attempts Today: {stats.get('attempts_today', 0)}
- Attempts This Week: {stats.get('attempts_week', 0)}
- Average Score: {stats.get('average_score', 0):.1f}%
- Pass Rate: {stats.get('pass_rate', 0):.1f}%

Most Popular Quiz: {stats.get('most_popular_quiz', 'None')}

System Information:
- Database Size: {stats.get('db_size', 'Unknown')}
- Last Backup: {stats.get('last_backup', 'Never')}

This is an automated report from the Telegram Quiz Bot system."""
            
            html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Daily Quiz Bot Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
        .stat-section {{ background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
        .stat-item {{ background-color: #f8f9fa; padding: 10px; border-radius: 3px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
        .stat-label {{ font-size: 12px; color: #666; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Daily Quiz Bot Report</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        <div class="content">
            <div class="stat-section">
                <h3>👥 User Statistics</h3>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('total_users', 0)}</div>
                        <div class="stat-label">Total Users</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('active_users', 0)}</div>
                        <div class="stat-label">Active Users</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('new_users_week', 0)}</div>
                        <div class="stat-label">New Users (7 days)</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('new_users_month', 0)}</div>
                        <div class="stat-label">New Users (30 days)</div>
                    </div>
                </div>
            </div>
            
            <div class="stat-section">
                <h3>📝 Quiz Statistics</h3>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('total_quizzes', 0)}</div>
                        <div class="stat-label">Total Quizzes</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('active_quizzes', 0)}</div>
                        <div class="stat-label">Active Quizzes</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('total_questions', 0)}</div>
                        <div class="stat-label">Total Questions</div>
                    </div>
                </div>
            </div>
            
            <div class="stat-section">
                <h3>📊 Attempt Statistics</h3>
                <div class="stat-grid">
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('total_attempts', 0)}</div>
                        <div class="stat-label">Total Attempts</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('completed_attempts', 0)}</div>
                        <div class="stat-label">Completed Attempts</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('attempts_today', 0)}</div>
                        <div class="stat-label">Attempts Today</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('attempts_week', 0)}</div>
                        <div class="stat-label">Attempts This Week</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('average_score', 0):.1f}%</div>
                        <div class="stat-label">Average Score</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats.get('pass_rate', 0):.1f}%</div>
                        <div class="stat-label">Pass Rate</div>
                    </div>
                </div>
            </div>
            
            <div class="stat-section">
                <h3>🏆 Popular Content</h3>
                <p><strong>Most Popular Quiz:</strong> {stats.get('most_popular_quiz', 'None')}</p>
            </div>
            
            <div class="stat-section">
                <h3>⚙️ System Information</h3>
                <p><strong>Database Size:</strong> {stats.get('db_size', 'Unknown')}</p>
                <p><strong>Last Backup:</strong> {stats.get('last_backup', 'Never')}</p>
            </div>
        </div>
        <div class="footer">
            <p>This is an automated report from the Telegram Quiz Bot system.</p>
        </div>
    </div>
</body>
</html>"""
            
            return self.send_email(
                to_emails=to_emails,
                subject=subject,
                body=body,
                html_body=html_body
            )
            
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")
            return False
    
    def send_quiz_export_email(self, 
                              to_emails: List[str], 
                              quiz_title: str, 
                              export_data: bytes, 
                              export_format: str = 'csv') -> bool:
        """Send quiz export data via email"""
        try:
            subject = f"Quiz Export: {quiz_title} - {datetime.now().strftime('%Y-%m-%d')}"
            
            body = f"""Quiz Export Data

Quiz: {quiz_title}
Export Format: {export_format.upper()}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Please find the exported quiz data attached to this email.

This is an automated export from the Telegram Quiz Bot system."""
            
            # Prepare attachment
            filename = f"quiz_export_{quiz_title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format}"
            attachments = [{
                'filename': filename,
                'content': export_data,
                'content_type': f'application/{export_format}' if export_format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }]
            
            return self.send_email(
                to_emails=to_emails,
                subject=subject,
                body=body,
                attachments=attachments
            )
            
        except Exception as e:
            logger.error(f"Failed to send quiz export email: {e}")
            return False
    
    def send_system_alert(self, 
                         alert_type: str, 
                         message: str, 
                         details: Optional[Dict[str, Any]] = None,
                         to_emails: Optional[List[str]] = None) -> bool:
        """Send system alert email"""
        try:
            if not to_emails:
                # Use default admin emails if not specified
                to_emails = [self.default_from_email] if self.default_from_email else []
            
            if not to_emails:
                logger.warning("No email addresses for system alert")
                return False
            
            subject = f"🚨 System Alert: {alert_type} - Quiz Bot"
            
            body = f"""System Alert Notification

Alert Type: {alert_type}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Message:
{message}
"""
            
            if details:
                body += "\nAdditional Details:\n"
                for key, value in details.items():
                    body += f"- {key}: {value}\n"
            
            body += "\nThis is an automated alert from the Telegram Quiz Bot system."
            
            return self.send_email(
                to_emails=to_emails,
                subject=subject,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Failed to send system alert: {e}")
            return False
    
    def test_email_configuration(self) -> Dict[str, Any]:
        """Test email configuration"""
        try:
            # Test SMTP connection
            with self._create_smtp_connection() as server:
                pass
            
            # Send test email if default email is configured
            if self.default_from_email:
                test_result = self.send_email(
                    to_emails=[self.default_from_email],
                    subject="Test Email - Quiz Bot Configuration",
                    body="This is a test email to verify the Quiz Bot email configuration is working correctly."
                )
                
                return {
                    'success': True,
                    'message': 'Email configuration is working correctly',
                    'test_email_sent': test_result
                }
            else:
                return {
                    'success': True,
                    'message': 'SMTP connection successful, but no default email configured for test',
                    'test_email_sent': False
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Email configuration test failed: {str(e)}',
                'test_email_sent': False
            }