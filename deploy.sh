#!/bin/bash

# Telegram Quiz Bot Deployment Script
# This script helps deploy the Telegram Quiz Bot with Docker Compose

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="telegram-quiz-bot"
DOCKER_COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
ENV_EXAMPLE_FILE=".env.example"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    log_success "Dependencies check passed"
}

check_env_file() {
    log_info "Checking environment configuration..."
    
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE_FILE" ]; then
            log_warning "Environment file not found. Copying from example..."
            cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
            log_warning "Please edit $ENV_FILE with your configuration before continuing."
            log_warning "Required configurations:"
            echo "  - TELEGRAM_BOT_TOKEN"
            echo "  - ADMIN_BOT_TOKEN"
            echo "  - SECRET_KEY"
            echo "  - JWT_SECRET_KEY"
            echo "  - Database credentials"
            echo "  - Email settings"
            echo ""
            read -p "Press Enter after configuring $ENV_FILE..."
        else
            log_error "Neither $ENV_FILE nor $ENV_EXAMPLE_FILE found."
            exit 1
        fi
    fi
    
    # Basic validation
    if ! grep -q "TELEGRAM_BOT_TOKEN=" "$ENV_FILE" || grep -q "TELEGRAM_BOT_TOKEN=$" "$ENV_FILE"; then
        log_error "TELEGRAM_BOT_TOKEN is not set in $ENV_FILE"
        exit 1
    fi
    
    if ! grep -q "ADMIN_BOT_TOKEN=" "$ENV_FILE" || grep -q "ADMIN_BOT_TOKEN=$" "$ENV_FILE"; then
        log_error "ADMIN_BOT_TOKEN is not set in $ENV_FILE"
        exit 1
    fi
    
    log_success "Environment configuration check passed"
}

setup_directories() {
    log_info "Setting up required directories..."
    
    mkdir -p logs
    mkdir -p backups
    mkdir -p uploads
    mkdir -p postgres_data
    mkdir -p redis_data
    
    # Set proper permissions
    chmod 755 logs backups uploads
    
    log_success "Directories created successfully"
}

build_images() {
    log_info "Building Docker images..."
    
    docker-compose build --no-cache
    
    log_success "Docker images built successfully"
}

start_services() {
    log_info "Starting services..."
    
    # Start database and Redis first
    log_info "Starting database and Redis..."
    docker-compose up -d postgres redis
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    sleep 10
    
    # Start the main application
    log_info "Starting main application..."
    docker-compose up -d quiz_bot
    
    # Start background services
    log_info "Starting background services..."
    docker-compose up -d celery_worker celery_beat
    
    log_success "All services started successfully"
}

check_health() {
    log_info "Checking application health..."
    
    # Wait a bit for services to start
    sleep 15
    
    # Check if containers are running
    if ! docker-compose ps | grep -q "Up"; then
        log_error "Some services are not running properly"
        docker-compose ps
        return 1
    fi
    
    # Run health check
    if docker-compose exec -T quiz_bot python health_check.py --component all; then
        log_success "Health check passed"
    else
        log_warning "Health check failed. Check the logs for details."
        return 1
    fi
}

create_admin_user() {
    log_info "Creating admin user..."
    
    echo ""
    echo "Please provide admin user details:"
    read -p "Admin username: " admin_username
    read -p "Admin email: " admin_email
    read -s -p "Admin password: " admin_password
    echo ""
    
    if [ -z "$admin_username" ] || [ -z "$admin_email" ] || [ -z "$admin_password" ]; then
        log_warning "Skipping admin user creation (empty fields)"
        return 0
    fi
    
    if docker-compose exec -T quiz_bot python main.py --create-admin \
        --admin-username "$admin_username" \
        --admin-email "$admin_email" \
        --admin-password "$admin_password" \
        --super-admin; then
        log_success "Admin user created successfully"
    else
        log_warning "Failed to create admin user. You can create it manually later."
    fi
}

show_status() {
    log_info "Deployment Status:"
    echo ""
    docker-compose ps
    echo ""
    
    log_info "Application URLs:"
    echo "  📱 Telegram Bot: Search for your bot on Telegram"
    echo "  🌐 Web Dashboard: http://localhost:5000"
    echo "  📊 Monitoring (if enabled): http://localhost:3000 (Grafana)"
    echo ""
    
    log_info "Useful Commands:"
    echo "  📋 View logs: docker-compose logs -f quiz_bot"
    echo "  🔄 Restart: docker-compose restart quiz_bot"
    echo "  🛑 Stop: docker-compose down"
    echo "  🗑️  Clean up: docker-compose down -v --remove-orphans"
    echo "  🔍 Health check: docker-compose exec quiz_bot python health_check.py"
    echo ""
}

show_help() {
    echo "Telegram Quiz Bot Deployment Script"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  deploy     Full deployment (default)"
    echo "  start      Start existing services"
    echo "  stop       Stop all services"
    echo "  restart    Restart all services"
    echo "  status     Show service status"
    echo "  logs       Show application logs"
    echo "  health     Run health check"
    echo "  clean      Clean up all containers and volumes"
    echo "  update     Update and restart services"
    echo "  backup     Create manual backup"
    echo "  help       Show this help message"
    echo ""
}

# Main deployment function
deploy() {
    log_info "Starting Telegram Quiz Bot deployment..."
    echo ""
    
    check_dependencies
    check_env_file
    setup_directories
    build_images
    start_services
    
    if check_health; then
        create_admin_user
        show_status
        log_success "🎉 Deployment completed successfully!"
    else
        log_error "Deployment completed with issues. Please check the logs."
        docker-compose logs --tail=50 quiz_bot
        exit 1
    fi
}

# Command handlers
case "${1:-deploy}" in
    "deploy")
        deploy
        ;;
    "start")
        log_info "Starting services..."
        docker-compose up -d
        show_status
        ;;
    "stop")
        log_info "Stopping services..."
        docker-compose down
        log_success "Services stopped"
        ;;
    "restart")
        log_info "Restarting services..."
        docker-compose restart
        show_status
        ;;
    "status")
        show_status
        ;;
    "logs")
        docker-compose logs -f quiz_bot
        ;;
    "health")
        docker-compose exec quiz_bot python health_check.py
        ;;
    "clean")
        log_warning "This will remove all containers, volumes, and data!"
        read -p "Are you sure? (y/N): " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            docker-compose down -v --remove-orphans
            docker system prune -f
            log_success "Cleanup completed"
        else
            log_info "Cleanup cancelled"
        fi
        ;;
    "update")
        log_info "Updating services..."
        docker-compose pull
        docker-compose build --no-cache
        docker-compose up -d
        show_status
        ;;
    "backup")
        log_info "Creating manual backup..."
        docker-compose exec quiz_bot python -c "from utils.backup_service import BackupService; from config import ProductionConfig; bs = BackupService(ProductionConfig()); result = bs.create_backup('manual'); print('Backup created:', result['backup_file'] if result['success'] else 'Failed')"
        ;;
    "help")
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac