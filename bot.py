import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

from models import db, User, Quiz, Question, QuestionOption, QuizAttempt, Answer, SystemLog
from config import Config
from utils.email_service import EmailService
from utils.database import DatabaseManager
from utils.security import SecurityManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramQuizBot:
    def __init__(self, config: Config):
        self.config = config
        self.db_manager = DatabaseManager(config)
        self.email_service = EmailService(config)
        self.security_manager = SecurityManager(config)
        self.user_sessions: Dict[int, Dict] = {}  # Store user session data
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Get or create user in database
        db_user = await self.get_or_create_user(user)
        
        if not db_user.is_active:
            await update.message.reply_text(
                "❌ Your account has been deactivated. Please contact an administrator."
            )
            return
        
        # Update last activity
        db_user.last_activity = datetime.now(timezone.utc)
        self.db_manager.save_changes()
        
        welcome_message = f"""🎯 **Welcome to Quiz Bot, {db_user.first_name}!**

I can help you take quizzes and tests. Here's what you can do:

📝 /quizzes - View available quizzes
📊 /my_results - View your quiz results
👤 /profile - Manage your profile
❓ /help - Get help

To get started, use /quizzes to see available tests!"""
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Log user activity
        await self.log_system_event(
            'user_action',
            f'User {db_user.telegram_id} started the bot',
            user_id=db_user.id
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_text = """🤖 **Quiz Bot Help**

**Available Commands:**
/start - Start the bot
/quizzes - View available quizzes
/my_results - View your quiz results
/profile - Manage your profile
/help - Show this help message

**How to take a quiz:**
1. Use /quizzes to see available tests
2. Select a quiz from the list
3. Read the instructions carefully
4. Answer all questions
5. Submit your answers
6. View your results

**Need assistance?**
Contact an administrator if you encounter any issues."""
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def quizzes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /quizzes command - show available quizzes"""
        user = update.effective_user
        db_user = await self.get_or_create_user(user)
        
        if not db_user.is_active:
            await update.message.reply_text("❌ Your account has been deactivated.")
            return
        
        # Get active quizzes
        active_quizzes = self.db_manager.get_active_quizzes()
        
        if not active_quizzes:
            await update.message.reply_text(
                "📝 No quizzes are currently available. Please check back later!"
            )
            return
        
        # Create inline keyboard with quiz options
        keyboard = []
        for quiz in active_quizzes:
            # Check if user has attempts left
            attempt_count = self.db_manager.get_user_quiz_attempts(db_user.id, quiz.id)
            attempts_left = quiz.max_attempts - attempt_count
            
            if attempts_left > 0:
                button_text = f"📝 {quiz.title}"
                if quiz.time_limit:
                    button_text += f" ({quiz.time_limit//60}min)"
                
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"quiz_info_{quiz.id}"
                    )
                ])
        
        if not keyboard:
            await update.message.reply_text(
                "📝 You have completed all available quizzes or reached the maximum attempts."
            )
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📚 **Available Quizzes:**\n\nSelect a quiz to view details and start:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def my_results_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /my_results command - show user's quiz results"""
        user = update.effective_user
        db_user = await self.get_or_create_user(user)
        
        attempts = self.db_manager.get_user_attempts(db_user.id)
        
        if not attempts:
            await update.message.reply_text(
                "📊 You haven't taken any quizzes yet. Use /quizzes to get started!"
            )
            return
        
        results_text = "📊 **Your Quiz Results:**\n\n"
        
        for attempt in attempts:
            status_emoji = "✅" if attempt.is_passed else "❌"
            results_text += f"{status_emoji} **{attempt.quiz.title}**\n"
            results_text += f"   Score: {attempt.score}/{attempt.max_score} ({attempt.percentage:.1f}%)\n"
            results_text += f"   Date: {attempt.completed_at.strftime('%Y-%m-%d %H:%M') if attempt.completed_at else 'In Progress'}\n"
            if attempt.time_taken:
                results_text += f"   Time: {attempt.time_taken//60}m {attempt.time_taken%60}s\n"
            results_text += "\n"
        
        await update.message.reply_text(
            results_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /profile command - show and manage user profile"""
        user = update.effective_user
        db_user = await self.get_or_create_user(user)
        
        profile_text = f"""👤 **Your Profile:**

**Name:** {db_user.first_name} {db_user.last_name or ''}
**Username:** @{db_user.username or 'Not set'}
**Phone:** {db_user.phone_number or 'Not set'}
**Email:** {db_user.email or 'Not set'}
**Member since:** {db_user.created_at.strftime('%Y-%m-%d')}
**Total quizzes taken:** {len(db_user.quiz_attempts)}"""
        
        keyboard = [
            [InlineKeyboardButton("📧 Update Email", callback_data="update_email")],
            [InlineKeyboardButton("📱 Update Phone", callback_data="update_phone")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            profile_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        db_user = await self.get_or_create_user(user)
        
        data = query.data
        
        if data.startswith("quiz_info_"):
            quiz_id = int(data.split("_")[2])
            await self.show_quiz_info(query, db_user, quiz_id)
        
        elif data.startswith("start_quiz_"):
            quiz_id = int(data.split("_")[2])
            await self.start_quiz(query, db_user, quiz_id)
        
        elif data.startswith("answer_"):
            await self.handle_quiz_answer(query, db_user, data)
        
        elif data == "update_email":
            await self.request_email_update(query, db_user)
        
        elif data == "update_phone":
            await self.request_phone_update(query, db_user)
    
    async def show_quiz_info(self, query, db_user: User, quiz_id: int) -> None:
        """Show detailed information about a quiz"""
        quiz = self.db_manager.get_quiz_by_id(quiz_id)
        
        if not quiz or not quiz.is_active:
            await query.edit_message_text("❌ Quiz not found or no longer available.")
            return
        
        # Check attempts left
        attempt_count = self.db_manager.get_user_quiz_attempts(db_user.id, quiz.id)
        attempts_left = quiz.max_attempts - attempt_count
        
        if attempts_left <= 0:
            await query.edit_message_text("❌ You have reached the maximum number of attempts for this quiz.")
            return
        
        info_text = f"""📝 **{quiz.title}**

**Description:**
{quiz.description or 'No description available.'}

**Details:**
• Questions: {len(quiz.questions)}
• Time limit: {f'{quiz.time_limit//60} minutes' if quiz.time_limit else 'No limit'}
• Passing score: {quiz.passing_score}%
• Attempts left: {attempts_left}/{quiz.max_attempts}

**Instructions:**
{quiz.instructions or 'Answer all questions to the best of your ability.'}"""
        
        keyboard = [
            [InlineKeyboardButton("🚀 Start Quiz", callback_data=f"start_quiz_{quiz.id}")],
            [InlineKeyboardButton("⬅️ Back to Quizzes", callback_data="back_to_quizzes")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            info_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def start_quiz(self, query, db_user: User, quiz_id: int) -> None:
        """Start a new quiz attempt"""
        quiz = self.db_manager.get_quiz_by_id(quiz_id)
        
        if not quiz or not quiz.is_active:
            await query.edit_message_text("❌ Quiz not found or no longer available.")
            return
        
        # Create new quiz attempt
        attempt = QuizAttempt(
            user_id=db_user.id,
            quiz_id=quiz.id,
            started_at=datetime.now(timezone.utc),
            status='in_progress'
        )
        
        self.db_manager.add_and_commit(attempt)
        
        # Initialize user session
        self.user_sessions[db_user.telegram_id] = {
            'attempt_id': attempt.id,
            'quiz_id': quiz.id,
            'current_question': 0,
            'start_time': datetime.now(timezone.utc),
            'answers': {}
        }
        
        # Show first question
        await self.show_question(query, db_user, 0)
        
        # Log quiz start
        await self.log_system_event(
            'user_action',
            f'User {db_user.telegram_id} started quiz {quiz.title}',
            user_id=db_user.id,
            metadata={'quiz_id': quiz.id, 'attempt_id': attempt.id}
        )
    
    async def show_question(self, query, db_user: User, question_index: int) -> None:
        """Show a specific question to the user"""
        session = self.user_sessions.get(db_user.telegram_id)
        if not session:
            await query.edit_message_text("❌ No active quiz session found. Please start a new quiz.")
            return
        
        quiz = self.db_manager.get_quiz_by_id(session['quiz_id'])
        questions = quiz.questions
        
        if question_index >= len(questions):
            await self.finish_quiz(query, db_user)
            return
        
        question = questions[question_index]
        session['current_question'] = question_index
        
        # Check time limit
        if quiz.time_limit:
            elapsed = (datetime.now(timezone.utc) - session['start_time']).total_seconds()
            if elapsed > quiz.time_limit:
                await self.timeout_quiz(query, db_user)
                return
        
        question_text = f"""❓ **Question {question_index + 1} of {len(questions)}**

{question.question_text}

"""
        
        if question.question_type == 'multiple_choice':
            keyboard = []
            for i, option in enumerate(question.options):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{chr(65 + i)}. {option.option_text}",
                        callback_data=f"answer_{question.id}_{option.id}"
                    )
                ])
            
            # Add navigation buttons
            nav_buttons = []
            if question_index > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_question_{question_index}")
                )
            if question_index < len(questions) - 1:
                nav_buttons.append(
                    InlineKeyboardButton("➡️ Skip", callback_data=f"skip_question_{question_index}")
                )
            else:
                nav_buttons.append(
                    InlineKeyboardButton("✅ Finish Quiz", callback_data="finish_quiz")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
        else:  # text or boolean questions
            question_text += "Please type your answer:"
            reply_markup = None
        
        # Add time remaining if applicable
        if quiz.time_limit:
            elapsed = (datetime.now(timezone.utc) - session['start_time']).total_seconds()
            remaining = max(0, quiz.time_limit - elapsed)
            question_text += f"\n⏰ Time remaining: {int(remaining//60)}:{int(remaining%60):02d}"
        
        await query.edit_message_text(
            question_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_quiz_answer(self, query, db_user: User, callback_data: str) -> None:
        """Handle quiz answer selection"""
        session = self.user_sessions.get(db_user.telegram_id)
        if not session:
            await query.edit_message_text("❌ No active quiz session found.")
            return
        
        parts = callback_data.split("_")
        question_id = int(parts[1])
        option_id = int(parts[2])
        
        # Store answer in session
        session['answers'][question_id] = option_id
        
        # Move to next question
        next_question = session['current_question'] + 1
        await self.show_question(query, db_user, next_question)
    
    async def finish_quiz(self, query, db_user: User) -> None:
        """Finish the quiz and calculate results"""
        session = self.user_sessions.get(db_user.telegram_id)
        if not session:
            await query.edit_message_text("❌ No active quiz session found.")
            return
        
        attempt = self.db_manager.get_quiz_attempt(session['attempt_id'])
        quiz = self.db_manager.get_quiz_by_id(session['quiz_id'])
        
        # Save answers to database
        for question_id, option_id in session['answers'].items():
            question = self.db_manager.get_question_by_id(question_id)
            option = self.db_manager.get_question_option_by_id(option_id)
            
            answer = Answer(
                attempt_id=attempt.id,
                question_id=question_id,
                selected_option_id=option_id,
                is_correct=option.is_correct if option else False,
                points_earned=question.points if (option and option.is_correct) else 0
            )
            
            self.db_manager.add_and_commit(answer)
        
        # Calculate final score
        attempt.completed_at = datetime.now(timezone.utc)
        attempt.time_taken = int((attempt.completed_at - attempt.started_at).total_seconds())
        attempt.status = 'completed'
        
        score, max_score, percentage = attempt.calculate_score()
        self.db_manager.save_changes()
        
        # Clear user session
        del self.user_sessions[db_user.telegram_id]
        
        # Prepare results message
        status_emoji = "🎉" if attempt.is_passed else "😔"
        status_text = "Passed" if attempt.is_passed else "Failed"
        
        results_text = f"""{status_emoji} **Quiz Completed!**

**{quiz.title}**

**Results:**
• Score: {score}/{max_score} ({percentage:.1f}%)
• Status: {status_text}
• Time taken: {attempt.time_taken//60}m {attempt.time_taken%60}s
• Passing score: {quiz.passing_score}%

"""
        
        if quiz.show_results and quiz.allow_review:
            results_text += "Use /my_results to view detailed answers."
        
        await query.edit_message_text(
            results_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send email notification if configured
        if quiz.notification_email_list:
            await self.email_service.send_quiz_completion_notification(
                quiz, attempt, db_user
            )
        
        # Log quiz completion
        await self.log_system_event(
            'user_action',
            f'User {db_user.telegram_id} completed quiz {quiz.title} with score {percentage:.1f}%',
            user_id=db_user.id,
            metadata={
                'quiz_id': quiz.id,
                'attempt_id': attempt.id,
                'score': score,
                'percentage': percentage,
                'passed': attempt.is_passed
            }
        )
    
    async def timeout_quiz(self, query, db_user: User) -> None:
        """Handle quiz timeout"""
        session = self.user_sessions.get(db_user.telegram_id)
        if not session:
            return
        
        attempt = self.db_manager.get_quiz_attempt(session['attempt_id'])
        attempt.status = 'expired'
        attempt.completed_at = datetime.now(timezone.utc)
        self.db_manager.save_changes()
        
        del self.user_sessions[db_user.telegram_id]
        
        await query.edit_message_text(
            "⏰ **Time's up!**\n\nThe quiz has expired. You can start a new attempt if you have attempts remaining.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def get_or_create_user(self, telegram_user) -> User:
        """Get existing user or create new one"""
        user = self.db_manager.get_user_by_telegram_id(str(telegram_user.id))
        
        if not user:
            user = User(
                telegram_id=str(telegram_user.id),
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                is_active=True
            )
            self.db_manager.add_and_commit(user)
        else:
            # Update user info if changed
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            self.db_manager.save_changes()
        
        return user
    
    async def log_system_event(self, event_type: str, message: str, user_id: Optional[int] = None, metadata: Optional[dict] = None) -> None:
        """Log system events"""
        log_entry = SystemLog(
            event_type=event_type,
            message=message,
            user_id=user_id,
            metadata=metadata
        )
        self.db_manager.add_and_commit(log_entry)
    
    def setup_handlers(self, application: Application) -> None:
        """Setup bot command and message handlers"""
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("quizzes", self.quizzes_command))
        application.add_handler(CommandHandler("my_results", self.my_results_command))
        application.add_handler(CommandHandler("profile", self.profile_command))
        
        # Callback query handler
        application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers for text answers
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages (for text-based quiz answers)"""
        user = update.effective_user
        db_user = await self.get_or_create_user(user)
        
        session = self.user_sessions.get(db_user.telegram_id)
        if not session:
            await update.message.reply_text(
                "I don't understand. Use /help to see available commands."
            )
            return
        
        # Handle text answer for current question
        quiz = self.db_manager.get_quiz_by_id(session['quiz_id'])
        questions = quiz.questions
        current_question = questions[session['current_question']]
        
        if current_question.question_type in ['text', 'boolean']:
            # Store text answer
            session['answers'][current_question.id] = update.message.text
            
            # Move to next question
            next_question = session['current_question'] + 1
            if next_question < len(questions):
                await self.show_question_text(update, db_user, next_question)
            else:
                await self.finish_quiz_text(update, db_user)
    
    async def show_question_text(self, update: Update, db_user: User, question_index: int) -> None:
        """Show question via text message"""
        session = self.user_sessions.get(db_user.telegram_id)
        quiz = self.db_manager.get_quiz_by_id(session['quiz_id'])
        questions = quiz.questions
        question = questions[question_index]
        
        session['current_question'] = question_index
        
        question_text = f"""❓ **Question {question_index + 1} of {len(questions)}**

{question.question_text}

Please type your answer:"""
        
        await update.message.reply_text(
            question_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def finish_quiz_text(self, update: Update, db_user: User) -> None:
        """Finish quiz via text message"""
        # Similar to finish_quiz but for text-based completion
        await update.message.reply_text(
            "✅ Quiz completed! Processing your results...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Process results (similar to finish_quiz method)
        # ... (implementation similar to finish_quiz)

def create_bot_application(config: Config) -> Application:
    """Create and configure the bot application"""
    # Create bot instance
    bot = TelegramQuizBot(config)
    
    # Create application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Setup handlers
    bot.setup_handlers(application)
    
    return application, bot

if __name__ == "__main__":
    from config import config
    
    # Load configuration
    app_config = config['development']
    
    # Create bot application
    application, bot = create_bot_application(app_config)
    
    # Run the bot
    print("Starting Telegram Quiz Bot...")
    application.run_polling()