import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
import io
import csv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

from models import db, User, Quiz, Question, QuestionOption, QuizAttempt, Answer, SystemLog, AdminUser
from config import Config
from utils.database import DatabaseManager
from utils.email_service import EmailService
from utils.export_service import ExportService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramAdminBot:
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config)
        self.email_service = EmailService(config)
        self.export_service = ExportService(config)
        self.admin_sessions: Dict[int, Dict] = {}  # Store admin session data
        
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.config.ADMIN_CHAT_IDS
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command for admin bot"""
        user = update.effective_user
        
        if not self.is_admin(user.id):
            await update.message.reply_text(
                "❌ Access denied. This bot is for administrators only."
            )
            return
        
        welcome_message = f"""🔧 **Admin Quiz Bot Control Panel**

Welcome, {user.first_name}!

**Available Commands:**

📊 **Analytics & Reports:**
/stats - View system statistics
/export_data - Export quiz data
/user_reports - Generate user reports

📝 **Quiz Management:**
/create_quiz - Create a new quiz
/list_quizzes - List all quizzes
/edit_quiz - Edit existing quiz
/delete_quiz - Delete a quiz

👥 **User Management:**
/list_users - List all users
/user_details - View user details
/deactivate_user - Deactivate a user
/activate_user - Activate a user

🔧 **System:**
/system_logs - View system logs
/backup_db - Create database backup
/help - Show this help message

Use any command to get started!"""
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system statistics"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        stats = self.db_manager.get_system_stats()
        
        stats_text = f"""📊 **System Statistics**

👥 **Users:**
• Total users: {stats['total_users']}
• Active users: {stats['active_users']}
• New users (last 7 days): {stats['new_users_week']}
• New users (last 30 days): {stats['new_users_month']}

📝 **Quizzes:**
• Total quizzes: {stats['total_quizzes']}
• Active quizzes: {stats['active_quizzes']}
• Total questions: {stats['total_questions']}

📊 **Attempts:**
• Total attempts: {stats['total_attempts']}
• Completed attempts: {stats['completed_attempts']}
• Average score: {stats['average_score']:.1f}%
• Pass rate: {stats['pass_rate']:.1f}%

⏰ **Recent Activity:**
• Attempts today: {stats['attempts_today']}
• Attempts this week: {stats['attempts_week']}
• Most popular quiz: {stats['most_popular_quiz']}

💾 **System:**
• Database size: {stats['db_size']}
• Last backup: {stats['last_backup']}"""
        
        keyboard = [
            [InlineKeyboardButton("📈 Detailed Analytics", callback_data="detailed_analytics")],
            [InlineKeyboardButton("📊 Export Report", callback_data="export_stats_report")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            stats_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def create_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start quiz creation process"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        user_id = update.effective_user.id
        
        # Initialize quiz creation session
        self.admin_sessions[user_id] = {
            'action': 'create_quiz',
            'step': 'title',
            'quiz_data': {
                'created_by': str(user_id)
            }
        }
        
        await update.message.reply_text(
            "📝 **Creating New Quiz**\n\nStep 1/6: Enter the quiz title:",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def list_quizzes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all quizzes"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        quizzes = self.db_manager.get_all_quizzes()
        
        if not quizzes:
            await update.message.reply_text(
                "📝 No quizzes found. Use /create_quiz to create your first quiz!"
            )
            return
        
        quiz_text = "📚 **All Quizzes:**\n\n"
        
        keyboard = []
        for quiz in quizzes:
            status_emoji = "✅" if quiz.is_active else "❌"
            quiz_text += f"{status_emoji} **{quiz.title}**\n"
            quiz_text += f"   Questions: {len(quiz.questions)} | Attempts: {len(quiz.attempts)}\n"
            quiz_text += f"   Created: {quiz.created_at.strftime('%Y-%m-%d')}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"📝 {quiz.title}",
                    callback_data=f"quiz_details_{quiz.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("➕ Create New Quiz", callback_data="create_new_quiz")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            quiz_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def list_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all users"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        users = self.db_manager.get_all_users()
        
        if not users:
            await update.message.reply_text("👥 No users found.")
            return
        
        # Paginate users (show 10 per page)
        page_size = 10
        total_pages = (len(users) + page_size - 1) // page_size
        
        await self.show_users_page(update.message, users, 0, total_pages)
    
    async def show_users_page(self, message, users: List[User], page: int, total_pages: int) -> None:
        """Show a page of users"""
        page_size = 10
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, len(users))
        page_users = users[start_idx:end_idx]
        
        users_text = f"👥 **Users (Page {page + 1}/{total_pages})**\n\n"
        
        keyboard = []
        for user in page_users:
            status_emoji = "✅" if user.is_active else "❌"
            admin_emoji = "👑" if user.is_admin else ""
            
            users_text += f"{status_emoji}{admin_emoji} **{user.first_name} {user.last_name or ''}**\n"
            users_text += f"   @{user.username or 'No username'} | ID: {user.telegram_id}\n"
            users_text += f"   Quizzes taken: {len(user.quiz_attempts)}\n"
            users_text += f"   Last activity: {user.last_activity.strftime('%Y-%m-%d %H:%M') if user.last_activity else 'Never'}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {user.first_name}",
                    callback_data=f"user_details_{user.id}"
                )
            ])
        
        # Navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton("⬅️ Previous", callback_data=f"users_page_{page-1}")
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton("➡️ Next", callback_data=f"users_page_{page+1}")
            )
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([
            InlineKeyboardButton("📊 Export Users", callback_data="export_users")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            users_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def export_data_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Export quiz data"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 Quiz Results (CSV)", callback_data="export_results_csv")],
            [InlineKeyboardButton("📊 Quiz Results (Excel)", callback_data="export_results_excel")],
            [InlineKeyboardButton("👥 Users Data (CSV)", callback_data="export_users_csv")],
            [InlineKeyboardButton("📝 Quizzes Data (CSV)", callback_data="export_quizzes_csv")],
            [InlineKeyboardButton("📈 Analytics Report (PDF)", callback_data="export_analytics_pdf")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📊 **Data Export Options**\n\nSelect the type of data you want to export:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def system_logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system logs"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        logs = self.db_manager.get_recent_logs(limit=20)
        
        if not logs:
            await update.message.reply_text("📋 No recent logs found.")
            return
        
        logs_text = "📋 **Recent System Logs:**\n\n"
        
        for log in logs:
            event_emoji = {
                'user_action': '👤',
                'system_event': '⚙️',
                'error': '❌',
                'warning': '⚠️',
                'info': 'ℹ️'
            }.get(log.event_type, '📝')
            
            logs_text += f"{event_emoji} **{log.event_type.title()}**\n"
            logs_text += f"   {log.message}\n"
            logs_text += f"   {log.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_logs")],
            [InlineKeyboardButton("📊 Export Logs", callback_data="export_logs")],
            [InlineKeyboardButton("🗑️ Clear Old Logs", callback_data="clear_old_logs")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            logs_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_admin(query.from_user.id):
            await query.edit_message_text("❌ Access denied.")
            return
        
        data = query.data
        
        if data.startswith("quiz_details_"):
            quiz_id = int(data.split("_")[2])
            await self.show_quiz_details(query, quiz_id)
        
        elif data.startswith("user_details_"):
            user_id = int(data.split("_")[2])
            await self.show_user_details(query, user_id)
        
        elif data.startswith("export_"):
            await self.handle_export_request(query, data)
        
        elif data == "detailed_analytics":
            await self.show_detailed_analytics(query)
        
        elif data == "refresh_stats":
            await self.refresh_stats(query)
        
        elif data == "create_new_quiz":
            await self.start_quiz_creation(query)
    
    async def show_quiz_details(self, query, quiz_id: int) -> None:
        """Show detailed information about a quiz"""
        quiz = self.db_manager.get_quiz_by_id(quiz_id)
        
        if not quiz:
            await query.edit_message_text("❌ Quiz not found.")
            return
        
        # Calculate quiz statistics
        total_attempts = len(quiz.attempts)
        completed_attempts = len([a for a in quiz.attempts if a.status == 'completed'])
        average_score = sum([a.percentage for a in quiz.attempts if a.percentage is not None]) / max(completed_attempts, 1)
        pass_rate = len([a for a in quiz.attempts if a.is_passed]) / max(completed_attempts, 1) * 100
        
        details_text = f"""📝 **Quiz Details: {quiz.title}**

**Basic Information:**
• Status: {'✅ Active' if quiz.is_active else '❌ Inactive'}
• Questions: {len(quiz.questions)}
• Time limit: {f'{quiz.time_limit//60} minutes' if quiz.time_limit else 'No limit'}
• Max attempts: {quiz.max_attempts}
• Passing score: {quiz.passing_score}%

**Description:**
{quiz.description or 'No description'}

**Statistics:**
• Total attempts: {total_attempts}
• Completed attempts: {completed_attempts}
• Average score: {average_score:.1f}%
• Pass rate: {pass_rate:.1f}%

**Notifications:**
• Email recipients: {len(quiz.notification_email_list)}

**Created:** {quiz.created_at.strftime('%Y-%m-%d %H:%M')}
**Last updated:** {quiz.updated_at.strftime('%Y-%m-%d %H:%M')}"""
        
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Quiz", callback_data=f"edit_quiz_{quiz.id}")],
            [InlineKeyboardButton("📊 View Results", callback_data=f"quiz_results_{quiz.id}")],
            [InlineKeyboardButton("📧 Test Notifications", callback_data=f"test_notifications_{quiz.id}")],
            [
                InlineKeyboardButton(
                    "❌ Deactivate" if quiz.is_active else "✅ Activate",
                    callback_data=f"toggle_quiz_{quiz.id}"
                ),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_quiz_{quiz.id}")
            ],
            [InlineKeyboardButton("⬅️ Back to Quizzes", callback_data="back_to_quizzes")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            details_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages for admin operations"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        user_id = update.effective_user.id
        session = self.admin_sessions.get(user_id)
        
        if not session:
            await update.message.reply_text(
                "I don't understand. Use /help to see available commands."
            )
            return
        
        if session['action'] == 'create_quiz':
            await self.handle_quiz_creation_step(update, session)
        else:
            await update.message.reply_text(
                "Unknown session state. Please start over with a command."
            )
    
    async def handle_quiz_creation_step(self, update: Update, session: Dict) -> None:
        """Handle quiz creation steps"""
        step = session['step']
        text = update.message.text
        quiz_data = session['quiz_data']
        
        if step == 'title':
            quiz_data['title'] = text
            session['step'] = 'description'
            await update.message.reply_text(
                "📝 Step 2/6: Enter the quiz description (or type 'skip' to skip):"
            )
        
        elif step == 'description':
            quiz_data['description'] = text if text.lower() != 'skip' else None
            session['step'] = 'instructions'
            await update.message.reply_text(
                "📝 Step 3/6: Enter quiz instructions (or type 'skip' to skip):"
            )
        
        elif step == 'instructions':
            quiz_data['instructions'] = text if text.lower() != 'skip' else None
            session['step'] = 'time_limit'
            await update.message.reply_text(
                "⏰ Step 4/6: Enter time limit in minutes (or type 'none' for no limit):"
            )
        
        elif step == 'time_limit':
            if text.lower() == 'none':
                quiz_data['time_limit'] = None
            else:
                try:
                    quiz_data['time_limit'] = int(text) * 60  # Convert to seconds
                except ValueError:
                    await update.message.reply_text(
                        "❌ Invalid time limit. Please enter a number or 'none':"
                    )
                    return
            
            session['step'] = 'passing_score'
            await update.message.reply_text(
                "🎯 Step 5/6: Enter passing score percentage (0-100):"
            )
        
        elif step == 'passing_score':
            try:
                passing_score = float(text)
                if 0 <= passing_score <= 100:
                    quiz_data['passing_score'] = passing_score
                    session['step'] = 'notification_emails'
                    await update.message.reply_text(
                        "📧 Step 6/6: Enter notification email addresses (comma-separated, or type 'skip'):"
                    )
                else:
                    await update.message.reply_text(
                        "❌ Passing score must be between 0 and 100. Please try again:"
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid passing score. Please enter a number between 0 and 100:"
                )
                return
        
        elif step == 'notification_emails':
            if text.lower() != 'skip':
                emails = [email.strip() for email in text.split(',') if email.strip()]
                quiz_data['notification_emails'] = json.dumps(emails)
            else:
                quiz_data['notification_emails'] = None
            
            # Create the quiz
            await self.create_quiz_from_data(update, quiz_data)
            del self.admin_sessions[update.effective_user.id]
    
    async def create_quiz_from_data(self, update: Update, quiz_data: Dict) -> None:
        """Create quiz from collected data"""
        try:
            quiz = Quiz(
                title=quiz_data['title'],
                description=quiz_data.get('description'),
                instructions=quiz_data.get('instructions'),
                time_limit=quiz_data.get('time_limit'),
                passing_score=quiz_data['passing_score'],
                notification_emails=quiz_data.get('notification_emails'),
                created_by=quiz_data['created_by'],
                is_active=True
            )
            
            self.db_manager.add_and_commit(quiz)
            
            await update.message.reply_text(
                f"✅ **Quiz Created Successfully!**\n\n"
                f"**Title:** {quiz.title}\n"
                f"**ID:** {quiz.id}\n\n"
                f"Now you can add questions to this quiz using the web dashboard or by editing the quiz.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Log quiz creation
            log_entry = SystemLog(
                event_type='admin_action',
                message=f'Admin {update.effective_user.id} created quiz: {quiz.title}',
                metadata={'quiz_id': quiz.id, 'admin_id': update.effective_user.id}
            )
            self.db_manager.add_and_commit(log_entry)
            
        except Exception as e:
            logger.error(f"Error creating quiz: {e}")
            await update.message.reply_text(
                f"❌ Error creating quiz: {str(e)}"
            )
    
    def setup_handlers(self, application: Application) -> None:
        """Setup bot command and message handlers"""
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.start_command))  # Same as start
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(CommandHandler("create_quiz", self.create_quiz_command))
        application.add_handler(CommandHandler("list_quizzes", self.list_quizzes_command))
        application.add_handler(CommandHandler("list_users", self.list_users_command))
        application.add_handler(CommandHandler("export_data", self.export_data_command))
        application.add_handler(CommandHandler("system_logs", self.system_logs_command))
        
        # Callback query handler
        application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

def create_admin_bot_application(config: Config) -> Application:
    """Create and configure the admin bot application"""
    # Create admin bot instance
    admin_bot = TelegramAdminBot(config)
    
    # Create application
    application = Application.builder().token(config.TELEGRAM_ADMIN_BOT_TOKEN).build()
    
    # Setup handlers
    admin_bot.setup_handlers(application)
    
    return application, admin_bot

if __name__ == "__main__":
    from config import config
    
    # Load configuration
    app_config = config['development']
    
    # Create admin bot application
    application, admin_bot = create_admin_bot_application(app_config)
    
    # Run the admin bot
    print("Starting Telegram Admin Bot...")
    application.run_polling()