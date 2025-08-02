import logging
import io
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie

from config import Config
from models import Quiz, QuizAttempt, User, Question, Answer
from utils.database import DatabaseManager

logger = logging.getLogger(__name__)

class ExportService:
    """Service for exporting quiz data in various formats"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config)
    
    def export_quiz_results_csv(self, quiz_id: Optional[int] = None) -> bytes:
        """Export quiz results to CSV format"""
        try:
            # Get quiz attempts
            if quiz_id:
                attempts = self.db_manager.get_quiz_attempts(quiz_id)
                quiz = self.db_manager.get_quiz_by_id(quiz_id)
                filename_prefix = f"quiz_{quiz.title.replace(' ', '_')}_results" if quiz else "quiz_results"
            else:
                attempts = self.db_manager.session.query(QuizAttempt).filter(
                    QuizAttempt.status == 'completed'
                ).order_by(QuizAttempt.completed_at.desc()).all()
                filename_prefix = "all_quiz_results"
            
            # Prepare CSV data
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = [
                'Attempt ID', 'Quiz Title', 'User Name', 'Username', 'Telegram ID',
                'Email', 'Score', 'Max Score', 'Percentage', 'Status', 'Passed',
                'Time Taken (seconds)', 'Started At', 'Completed At'
            ]
            writer.writerow(headers)
            
            # Write data rows
            for attempt in attempts:
                user = attempt.user
                quiz = attempt.quiz
                
                row = [
                    attempt.id,
                    quiz.title if quiz else 'Unknown',
                    f"{user.first_name} {user.last_name or ''}" if user else 'Unknown',
                    user.username if user else 'Unknown',
                    user.telegram_id if user else 'Unknown',
                    user.email or 'Not provided',
                    attempt.score or 0,
                    attempt.max_score or 0,
                    round(attempt.percentage or 0, 2),
                    attempt.status,
                    'Yes' if attempt.is_passed else 'No',
                    attempt.time_taken or 0,
                    attempt.started_at.isoformat() if attempt.started_at else '',
                    attempt.completed_at.isoformat() if attempt.completed_at else ''
                ]
                writer.writerow(row)
            
            # Convert to bytes
            csv_content = output.getvalue()
            output.close()
            
            return csv_content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to export quiz results to CSV: {e}")
            raise
    
    def export_quiz_results_excel(self, quiz_id: Optional[int] = None) -> bytes:
        """Export quiz results to Excel format"""
        try:
            # Get quiz attempts
            if quiz_id:
                attempts = self.db_manager.get_quiz_attempts(quiz_id)
                quiz = self.db_manager.get_quiz_by_id(quiz_id)
            else:
                attempts = self.db_manager.session.query(QuizAttempt).filter(
                    QuizAttempt.status == 'completed'
                ).order_by(QuizAttempt.completed_at.desc()).all()
                quiz = None
            
            # Prepare data for DataFrame
            data = []
            for attempt in attempts:
                user = attempt.user
                quiz_obj = attempt.quiz
                
                data.append({
                    'Attempt ID': attempt.id,
                    'Quiz Title': quiz_obj.title if quiz_obj else 'Unknown',
                    'User Name': f"{user.first_name} {user.last_name or ''}" if user else 'Unknown',
                    'Username': user.username if user else 'Unknown',
                    'Telegram ID': user.telegram_id if user else 'Unknown',
                    'Email': user.email or 'Not provided',
                    'Score': attempt.score or 0,
                    'Max Score': attempt.max_score or 0,
                    'Percentage': round(attempt.percentage or 0, 2),
                    'Status': attempt.status,
                    'Passed': 'Yes' if attempt.is_passed else 'No',
                    'Time Taken (seconds)': attempt.time_taken or 0,
                    'Started At': attempt.started_at.isoformat() if attempt.started_at else '',
                    'Completed At': attempt.completed_at.isoformat() if attempt.completed_at else ''
                })
            
            # Create DataFrame
            df = pd.DataFrame(data)
            
            # Create Excel file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Main results sheet
                df.to_excel(writer, sheet_name='Quiz Results', index=False)
                
                # Summary sheet if specific quiz
                if quiz:
                    summary_data = self._create_quiz_summary(quiz, attempts)
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Question analysis sheet if specific quiz
                if quiz:
                    question_analysis = self._create_question_analysis(quiz)
                    if question_analysis:
                        qa_df = pd.DataFrame(question_analysis)
                        qa_df.to_excel(writer, sheet_name='Question Analysis', index=False)
            
            output.seek(0)
            return output.read()
            
        except Exception as e:
            logger.error(f"Failed to export quiz results to Excel: {e}")
            raise
    
    def export_users_csv(self) -> bytes:
        """Export users data to CSV format"""
        try:
            users = self.db_manager.get_all_users()
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = [
                'User ID', 'Telegram ID', 'Username', 'First Name', 'Last Name',
                'Email', 'Phone Number', 'Is Active', 'Is Admin', 'Created At',
                'Last Activity', 'Total Quiz Attempts'
            ]
            writer.writerow(headers)
            
            # Write data rows
            for user in users:
                row = [
                    user.id,
                    user.telegram_id,
                    user.username or '',
                    user.first_name or '',
                    user.last_name or '',
                    user.email or '',
                    user.phone_number or '',
                    'Yes' if user.is_active else 'No',
                    'Yes' if user.is_admin else 'No',
                    user.created_at.isoformat() if user.created_at else '',
                    user.last_activity.isoformat() if user.last_activity else '',
                    len(user.quiz_attempts)
                ]
                writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            
            return csv_content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to export users to CSV: {e}")
            raise
    
    def export_quizzes_csv(self) -> bytes:
        """Export quizzes data to CSV format"""
        try:
            quizzes = self.db_manager.get_all_quizzes()
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            headers = [
                'Quiz ID', 'Title', 'Description', 'Is Active', 'Time Limit (minutes)',
                'Max Attempts', 'Passing Score (%)', 'Question Count', 'Total Attempts',
                'Completed Attempts', 'Average Score (%)', 'Pass Rate (%)',
                'Created By', 'Created At', 'Updated At'
            ]
            writer.writerow(headers)
            
            # Write data rows
            for quiz in quizzes:
                completed_attempts = [a for a in quiz.attempts if a.status == 'completed']
                passed_attempts = [a for a in completed_attempts if a.is_passed]
                
                avg_score = 0
                if completed_attempts:
                    scores = [a.percentage for a in completed_attempts if a.percentage is not None]
                    avg_score = sum(scores) / len(scores) if scores else 0
                
                pass_rate = 0
                if completed_attempts:
                    pass_rate = (len(passed_attempts) / len(completed_attempts)) * 100
                
                row = [
                    quiz.id,
                    quiz.title,
                    quiz.description or '',
                    'Yes' if quiz.is_active else 'No',
                    quiz.time_limit // 60 if quiz.time_limit else '',
                    quiz.max_attempts,
                    quiz.passing_score,
                    len(quiz.questions),
                    len(quiz.attempts),
                    len(completed_attempts),
                    round(avg_score, 2),
                    round(pass_rate, 2),
                    quiz.created_by,
                    quiz.created_at.isoformat() if quiz.created_at else '',
                    quiz.updated_at.isoformat() if quiz.updated_at else ''
                ]
                writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            
            return csv_content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to export quizzes to CSV: {e}")
            raise
    
    def export_analytics_pdf(self, quiz_id: Optional[int] = None) -> bytes:
        """Export analytics report to PDF format"""
        try:
            output = io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=30,
                alignment=1  # Center alignment
            )
            
            if quiz_id:
                quiz = self.db_manager.get_quiz_by_id(quiz_id)
                title = f"Quiz Analytics Report: {quiz.title if quiz else 'Unknown'}"
            else:
                title = "System Analytics Report"
            
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 20))
            
            # Report metadata
            meta_style = styles['Normal']
            story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}", meta_style))
            story.append(Spacer(1, 20))
            
            if quiz_id:
                # Quiz-specific analytics
                analytics = self.db_manager.get_quiz_analytics(quiz_id)
                story.extend(self._create_quiz_analytics_content(analytics, styles))
            else:
                # System-wide analytics
                stats = self.db_manager.get_system_stats()
                story.extend(self._create_system_analytics_content(stats, styles))
            
            # Build PDF
            doc.build(story)
            output.seek(0)
            return output.read()
            
        except Exception as e:
            logger.error(f"Failed to export analytics to PDF: {e}")
            raise
    
    def _create_quiz_summary(self, quiz: Quiz, attempts: List[QuizAttempt]) -> List[Dict[str, Any]]:
        """Create summary data for a specific quiz"""
        completed_attempts = [a for a in attempts if a.status == 'completed']
        passed_attempts = [a for a in completed_attempts if a.is_passed]
        
        summary = [
            {'Metric': 'Quiz Title', 'Value': quiz.title},
            {'Metric': 'Total Questions', 'Value': len(quiz.questions)},
            {'Metric': 'Time Limit (minutes)', 'Value': quiz.time_limit // 60 if quiz.time_limit else 'No limit'},
            {'Metric': 'Passing Score (%)', 'Value': quiz.passing_score},
            {'Metric': 'Max Attempts', 'Value': quiz.max_attempts},
            {'Metric': 'Total Attempts', 'Value': len(attempts)},
            {'Metric': 'Completed Attempts', 'Value': len(completed_attempts)},
            {'Metric': 'Passed Attempts', 'Value': len(passed_attempts)},
        ]
        
        if completed_attempts:
            scores = [a.percentage for a in completed_attempts if a.percentage is not None]
            times = [a.time_taken for a in completed_attempts if a.time_taken is not None]
            
            summary.extend([
                {'Metric': 'Average Score (%)', 'Value': round(sum(scores) / len(scores), 2) if scores else 0},
                {'Metric': 'Pass Rate (%)', 'Value': round((len(passed_attempts) / len(completed_attempts)) * 100, 2)},
                {'Metric': 'Average Time (minutes)', 'Value': round(sum(times) / len(times) / 60, 2) if times else 0},
            ])
        
        return summary
    
    def _create_question_analysis(self, quiz: Quiz) -> List[Dict[str, Any]]:
        """Create question-level analysis for a quiz"""
        analysis = []
        
        for question in quiz.questions:
            # Get all answers for this question
            answers = self.db_manager.session.query(Answer).filter(
                Answer.question_id == question.id
            ).all()
            
            total_answers = len(answers)
            correct_answers = len([a for a in answers if a.is_correct])
            accuracy = (correct_answers / max(total_answers, 1)) * 100
            
            analysis.append({
                'Question ID': question.id,
                'Question Text': question.question_text[:100] + '...' if len(question.question_text) > 100 else question.question_text,
                'Question Type': question.question_type,
                'Points': question.points,
                'Total Answers': total_answers,
                'Correct Answers': correct_answers,
                'Accuracy (%)': round(accuracy, 2)
            })
        
        return analysis
    
    def _create_quiz_analytics_content(self, analytics: Dict[str, Any], styles) -> List:
        """Create PDF content for quiz analytics"""
        story = []
        
        # Basic statistics table
        story.append(Paragraph("Quiz Overview", styles['Heading2']))
        
        basic_data = [
            ['Metric', 'Value'],
            ['Quiz Title', analytics.get('quiz_title', 'Unknown')],
            ['Total Attempts', str(analytics.get('total_attempts', 0))],
            ['Completed Attempts', str(analytics.get('completed_attempts', 0))],
            ['Completion Rate', f"{analytics.get('completion_rate', 0):.1f}%"],
            ['Average Score', f"{analytics.get('average_score', 0):.1f}%"],
            ['Pass Rate', f"{analytics.get('pass_rate', 0):.1f}%"],
            ['Average Time', f"{analytics.get('average_time', 0):.1f} seconds"]
        ]
        
        basic_table = Table(basic_data)
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(basic_table)
        story.append(Spacer(1, 20))
        
        # Score distribution
        story.append(Paragraph("Score Distribution", styles['Heading2']))
        
        score_dist = analytics.get('score_distribution', {})
        score_data = [['Score Range', 'Count']]
        for range_name, count in score_dist.items():
            score_data.append([range_name + '%', str(count)])
        
        score_table = Table(score_data)
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(score_table)
        story.append(Spacer(1, 20))
        
        # Question analytics
        question_analytics = analytics.get('question_analytics', [])
        if question_analytics:
            story.append(Paragraph("Question Analysis", styles['Heading2']))
            
            question_data = [['Question', 'Total Answers', 'Correct', 'Accuracy']]
            for qa in question_analytics[:10]:  # Limit to first 10 questions
                question_data.append([
                    qa['question_text'][:50] + '...' if len(qa['question_text']) > 50 else qa['question_text'],
                    str(qa['total_answers']),
                    str(qa['correct_answers']),
                    f"{qa['accuracy']:.1f}%"
                ])
            
            question_table = Table(question_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
            question_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP')
            ]))
            
            story.append(question_table)
        
        return story
    
    def _create_system_analytics_content(self, stats: Dict[str, Any], styles) -> List:
        """Create PDF content for system analytics"""
        story = []
        
        # System overview
        story.append(Paragraph("System Overview", styles['Heading2']))
        
        system_data = [
            ['Metric', 'Value'],
            ['Total Users', str(stats.get('total_users', 0))],
            ['Active Users', str(stats.get('active_users', 0))],
            ['New Users (7 days)', str(stats.get('new_users_week', 0))],
            ['New Users (30 days)', str(stats.get('new_users_month', 0))],
            ['Total Quizzes', str(stats.get('total_quizzes', 0))],
            ['Active Quizzes', str(stats.get('active_quizzes', 0))],
            ['Total Questions', str(stats.get('total_questions', 0))]
        ]
        
        system_table = Table(system_data)
        system_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(system_table)
        story.append(Spacer(1, 20))
        
        # Performance metrics
        story.append(Paragraph("Performance Metrics", styles['Heading2']))
        
        performance_data = [
            ['Metric', 'Value'],
            ['Total Attempts', str(stats.get('total_attempts', 0))],
            ['Completed Attempts', str(stats.get('completed_attempts', 0))],
            ['Attempts Today', str(stats.get('attempts_today', 0))],
            ['Attempts This Week', str(stats.get('attempts_week', 0))],
            ['Average Score', f"{stats.get('average_score', 0):.1f}%"],
            ['Pass Rate', f"{stats.get('pass_rate', 0):.1f}%"],
            ['Most Popular Quiz', str(stats.get('most_popular_quiz', 'None'))]
        ]
        
        performance_table = Table(performance_data)
        performance_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(performance_table)
        story.append(Spacer(1, 20))
        
        # System information
        story.append(Paragraph("System Information", styles['Heading2']))
        
        system_info_data = [
            ['Metric', 'Value'],
            ['Database Size', str(stats.get('db_size', 'Unknown'))],
            ['Last Backup', str(stats.get('last_backup', 'Never'))]
        ]
        
        system_info_table = Table(system_info_data)
        system_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(system_info_table)
        
        return story