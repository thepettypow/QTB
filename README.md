# Telegram Quiz Bot

A comprehensive, self-hosted Telegram bot for creating and managing customizable quizzes with data collection, email reporting, and web-based administration.

## Features

### 🤖 Telegram Bot Functionality
- **User Management**: Automatic user registration and profile management
- **Quiz System**: Multiple choice and text-based questions with scoring
- **Time Limits**: Optional time-limited quizzes
- **Multiple Attempts**: Configurable attempt limits per quiz
- **Real-time Feedback**: Instant results and explanations
- **Progress Tracking**: User statistics and quiz history

### 📊 Admin Dashboard
- **Web Interface**: Modern Flask-based admin panel
- **Quiz Management**: Create, edit, and manage quizzes
- **User Analytics**: Detailed user statistics and activity monitoring
- **Data Export**: CSV, Excel, and PDF export capabilities
- **System Monitoring**: Real-time system health and performance metrics

### 🔒 Security & Data Management
- **Secure Authentication**: JWT-based admin authentication
- **Data Encryption**: Sensitive data encryption at rest
- **Rate Limiting**: Protection against spam and abuse
- **Backup System**: Automated database backups
- **Audit Logging**: Comprehensive system event logging

### 📧 Notification System
- **Email Reports**: Automated quiz completion notifications
- **Admin Alerts**: System status and error notifications
- **Custom Recipients**: Configurable email recipients per quiz
- **Rich Formatting**: HTML emails with attachments

### 🚀 Scalability & Deployment
- **Docker Support**: Complete containerized deployment
- **Database**: PostgreSQL with connection pooling
- **Background Tasks**: Celery for async processing
- **Caching**: Redis for improved performance
- **Load Balancing**: Nginx reverse proxy support

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- Docker & Docker Compose (for containerized deployment)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/telegram-quiz-bot.git
cd telegram-quiz-bot
```

### 2. Environment Configuration

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_main_bot_token_here
ADMIN_BOT_TOKEN=your_admin_bot_token_here

# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/telegram_quiz_bot
DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_quiz_bot
DB_USER=quiz_bot_user
DB_PASSWORD=secure_password_123

# Security
SECRET_KEY=your_very_secure_secret_key_here
JWT_SECRET_KEY=your_jwt_secret_key_here

# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=your_email@gmail.com
ADMIN_EMAILS=admin1@example.com,admin2@example.com

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 3. Docker Deployment (Recommended)

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f quiz_bot
```

### 4. Manual Installation

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Setup Database

```bash
# Create PostgreSQL database
createdb telegram_quiz_bot

# Initialize database tables
python main.py --environment development
```

#### Create Admin User

```bash
python main.py --create-admin \
  --admin-username admin \
  --admin-email admin@example.com \
  --admin-password secure_password \
  --super-admin
```

#### Start the Application

```bash
# Development mode
python main.py --environment development

# Production mode
python main.py --environment production
```

## Configuration

### Telegram Bot Setup

1. **Create Main Bot**:
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command
   - Follow instructions to create your bot
   - Save the bot token

2. **Create Admin Bot**:
   - Repeat the process for a second bot (for admin functions)
   - Save the admin bot token

3. **Configure Bot Settings**:
   ```bash
   # Set bot commands (optional)
   /setcommands
   start - Start the quiz bot
   help - Show help information
   quizzes - List available quizzes
   profile - View your profile
   results - View your quiz results
   ```

### Database Configuration

#### PostgreSQL Setup

```sql
-- Create database and user
CREATE DATABASE telegram_quiz_bot;
CREATE USER quiz_bot_user WITH PASSWORD 'secure_password_123';
GRANT ALL PRIVILEGES ON DATABASE telegram_quiz_bot TO quiz_bot_user;

-- Grant additional permissions
\c telegram_quiz_bot
GRANT ALL ON SCHEMA public TO quiz_bot_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO quiz_bot_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO quiz_bot_user;
```

#### Redis Setup

```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Configure Redis password (optional)
sudo nano /etc/redis/redis.conf
# Uncomment and set: requirepass your_redis_password
```

### Email Configuration

#### Gmail Setup

1. Enable 2-Factor Authentication
2. Generate App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate password for "Mail"
   - Use this password in `MAIL_PASSWORD`

#### Other Email Providers

```env
# Outlook/Hotmail
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USE_TLS=true

# Yahoo
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587
MAIL_USE_TLS=true

# Custom SMTP
MAIL_SERVER=your.smtp.server.com
MAIL_PORT=587
MAIL_USE_TLS=true
```

## Usage

### Creating Your First Quiz

1. **Access Admin Dashboard**:
   - Open http://localhost:5000 in your browser
   - Login with your admin credentials

2. **Create a Quiz**:
   - Navigate to "Quizzes" → "Create New Quiz"
   - Fill in quiz details:
     - Title and description
     - Time limit (optional)
     - Passing score percentage
     - Maximum attempts

3. **Add Questions**:
   - Click "Add Question" for each question
   - Choose question type (multiple choice or text)
   - Add answer options and mark correct answers
   - Set point values

4. **Activate Quiz**:
   - Set quiz status to "Active"
   - Save the quiz

### Using the Telegram Bot

1. **Start the Bot**:
   ```
   /start
   ```

2. **View Available Quizzes**:
   ```
   /quizzes
   ```

3. **Take a Quiz**:
   - Select a quiz from the list
   - Read instructions and start
   - Answer questions within time limit
   - View results and explanations

4. **Check Your Results**:
   ```
   /results
   ```

### Admin Functions

Use the admin bot for management tasks:

```
/admin_start - Access admin functions
/stats - View system statistics
/users - Manage users
/backup - Create system backup
/logs - View system logs
```

## API Documentation

### REST API Endpoints

The web dashboard provides REST API endpoints for integration:

```
GET  /api/stats              - System statistics
GET  /api/quiz/{id}/analytics - Quiz analytics
POST /api/user/{id}/toggle   - Toggle user status
POST /api/quiz/{id}/toggle   - Toggle quiz status
```

### Webhook Integration

For external integrations, you can set up webhooks:

```python
# Example webhook payload
{
    "event": "quiz_completed",
    "user_id": 12345,
    "quiz_id": 1,
    "score": 85,
    "passed": true,
    "timestamp": "2024-01-15T10:30:00Z"
}
```

## Monitoring & Maintenance

### Health Checks

```bash
# Check application health
curl http://localhost:5000/health

# Check database connection
docker-compose exec quiz_bot python -c "from utils.database import DatabaseManager; from config import ProductionConfig; dm = DatabaseManager(ProductionConfig()); print('DB OK' if dm.test_connection() else 'DB Error')"
```

### Backup Management

```bash
# Create manual backup
docker-compose exec quiz_bot python -c "from utils.backup_service import BackupService; from config import ProductionConfig; bs = BackupService(ProductionConfig()); result = bs.create_backup('manual'); print(result)"

# List backups
docker-compose exec quiz_bot ls -la /app/backups/

# Restore from backup (manual process)
# 1. Stop the application
# 2. Restore database from backup file
# 3. Restart the application
```

### Log Management

```bash
# View application logs
docker-compose logs -f quiz_bot

# View specific service logs
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f celery_worker

# Access log files
docker-compose exec quiz_bot tail -f /app/logs/telegram_quiz_bot.log
```

### Performance Monitoring

#### Enable Monitoring Stack

```bash
# Start with monitoring services
docker-compose --profile monitoring up -d

# Access Grafana dashboard
open http://localhost:3000
# Default credentials: admin/admin123

# Access Prometheus
open http://localhost:9090
```

#### Key Metrics to Monitor

- **Response Time**: Bot response latency
- **Database Performance**: Query execution time
- **Memory Usage**: Application memory consumption
- **Error Rate**: Failed requests and exceptions
- **User Activity**: Active users and quiz completions

## Troubleshooting

### Common Issues

#### Bot Not Responding

```bash
# Check bot token
docker-compose logs quiz_bot | grep "token"

# Verify network connectivity
docker-compose exec quiz_bot curl -s https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Check bot permissions
# Ensure bot is added to groups with proper permissions
```

#### Database Connection Issues

```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready

# Test database connection
docker-compose exec quiz_bot python -c "import psycopg2; conn = psycopg2.connect('postgresql://quiz_bot_user:secure_password_123@postgres:5432/telegram_quiz_bot'); print('Connected successfully')"

# Check database logs
docker-compose logs postgres
```

#### Email Delivery Issues

```bash
# Test email configuration
docker-compose exec quiz_bot python -c "from utils.email_service import EmailService; from config import ProductionConfig; es = EmailService(ProductionConfig()); es.test_email_config()"

# Check email logs
docker-compose logs quiz_bot | grep "email"
```

#### Memory Issues

```bash
# Check memory usage
docker stats

# Increase memory limits in docker-compose.yml
services:
  quiz_bot:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

### Debug Mode

```bash
# Run in debug mode
docker-compose exec quiz_bot python main.py --environment development

# Enable verbose logging
export LOG_LEVEL=DEBUG
docker-compose up quiz_bot
```

## Security Considerations

### Production Deployment

1. **Environment Variables**:
   - Use strong, unique passwords
   - Store secrets securely (e.g., Docker secrets, HashiCorp Vault)
   - Rotate keys regularly

2. **Network Security**:
   - Use HTTPS with valid SSL certificates
   - Configure firewall rules
   - Limit database access to application only

3. **Application Security**:
   - Keep dependencies updated
   - Enable rate limiting
   - Monitor for suspicious activity
   - Regular security audits

4. **Data Protection**:
   - Encrypt sensitive data at rest
   - Implement proper backup encryption
   - Follow GDPR/privacy regulations
   - Regular data cleanup

### SSL/TLS Configuration

```nginx
# nginx/nginx.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    location / {
        proxy_pass http://quiz_bot:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/telegram-quiz-bot.git
cd telegram-quiz-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linting
flake8 .
black .
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support and questions:

- 📧 Email: support@example.com
- 💬 Telegram: [@your_support_bot](https://t.me/your_support_bot)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/telegram-quiz-bot/issues)
- 📖 Documentation: [Wiki](https://github.com/yourusername/telegram-quiz-bot/wiki)

## Changelog

### Version 1.0.0 (2024-01-15)

- Initial release
- Core quiz functionality
- Web admin dashboard
- Email notifications
- Docker deployment
- Backup system
- Security features

---

**Made with ❤️ for the Telegram community**