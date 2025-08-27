# Maskan Breakfast Management System

## Overview
Maskan Breakfast Management is a comprehensive kitchen management system designed for multi-floor residential settings like apartments or dormitories. The system manages meal planning, expense tracking, tea service scheduling, user feedback, and procurement across multiple floors (1-11). It features role-based access control with four distinct user types: Admin, Pantry Head, Tea Manager, and Member, each with specific permissions and responsibilities.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask web application with SQLAlchemy ORM for database operations
- **Database**: SQLite database (`maskan_breakfast.db`) for data persistence
- **Authentication**: Session-based authentication with Werkzeug password hashing
- **Models**: Core entities include User, Menu, Expense, TeaTask with additional models for Suggestions, Feedback, Requests, and ProcurementItem
- **Role-Based Access Control**: Four-tier permission system (Admin > Pantry Head/Tea Manager > Member) with floor-based data isolation

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Bootstrap 5 for responsive UI
- **Styling**: Custom CSS with CSS variables for theming, including dark/light mode toggle
- **JavaScript**: Vanilla JavaScript for client-side interactions, form validation, and offline support
- **Navigation**: Fixed top navigation bar with role-based menu visibility

### Data Models
- **User Management**: Users are associated with specific floors (1-11) and roles, with email verification workflow
- **Menu System**: Daily meal planning with assignment capabilities to users
- **Expense Tracking**: Categorized expense management with filtering and reporting
- **Task Management**: Tea service scheduling with time-based assignments
- **Communication**: Suggestion and feedback systems with admin moderation
- **Procurement**: Shopping list management with priority levels and assignment tracking

### Authentication Flow
- **Admin**: Fixed initial credentials (Administrator/administrator) with password change capability
- **Other Roles**: Email-based verification followed by username/password creation
- **Session Management**: Server-side session storage with persistent login functionality

### Permission Matrix
- **Admin**: Full access to all features including user management and system settings
- **Pantry Head**: Edit access to Menus, Expenses, and Procurement; view-only for other features
- **Tea Manager**: Edit access to Tea management; view-only for other features  
- **Member**: Submit-only access to Suggestions, Feedbacks, and Requests; view-only for operational data

## External Dependencies

### Frontend Libraries
- **Bootstrap 5.3.0**: UI framework for responsive design and components
- **Font Awesome 6.4.0**: Icon library for UI elements and navigation
- **CDN Delivery**: External CSS and JavaScript libraries loaded via CDN

### Python Packages
- **Flask**: Web framework for application structure and routing
- **Flask-SQLAlchemy**: ORM for database operations and model definitions
- **Werkzeug**: Security utilities for password hashing and authentication
- **SQLAlchemy**: Database toolkit and ORM core functionality

### Browser APIs
- **LocalStorage**: Theme preferences and navigation state persistence
- **Notifications API**: User notification system for updates and alerts
- **Print API**: Expense report generation and printing functionality

### Database
- **SQLite**: Embedded database for development and small-scale deployments
- **Connection Pooling**: Configured with pool recycling and pre-ping for reliability