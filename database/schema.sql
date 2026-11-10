
USE greedy_stocks;

-- 1. APPLICATION USERS
CREATE TABLE IF NOT EXISTS app_users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100),
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    preferred_language ENUM('English', 'Hindi', 'Marathi')
        DEFAULT 'English',
    experience_level ENUM(
        'Complete Beginner',
        'Know a Little',
        'Know the Basics'
    ) DEFAULT 'Complete Beginner',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

-- 2. USER PREFERENCES
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL UNIQUE,
    theme VARCHAR(30) DEFAULT 'dark',
    onboarding_completed BOOLEAN DEFAULT FALSE,
    notifications_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES app_users(id)
        ON DELETE CASCADE
);

-- 3. CONVERSATIONS
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) DEFAULT 'New conversation',
    is_pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES app_users(id)
        ON DELETE CASCADE,
    INDEX idx_conversations_user (user_id, updated_at)
);

-- 4. CHAT MESSAGES
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT UNSIGNED NOT NULL,
    role ENUM('user', 'assistant', 'system', 'tool') NOT NULL,
    content LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        ON DELETE CASCADE,
    INDEX idx_messages_conversation (conversation_id, created_at)
);

-- 5. SECTORS
CREATE TABLE IF NOT EXISTS sectors (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. NIFTY 50 COMPANIES
CREATE TABLE IF NOT EXISTS companies (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL UNIQUE,
    company_name VARCHAR(255) NOT NULL,
    isin VARCHAR(20),
    sector_id INT UNSIGNED,
    exchange VARCHAR(10) DEFAULT 'NSE',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (sector_id) REFERENCES sectors(id),
    INDEX idx_companies_sector (sector_id)
);

-- 7. DATA SOURCES
CREATE TABLE IF NOT EXISTS data_sources (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_name VARCHAR(150) NOT NULL,
    source_type VARCHAR(80),
    source_url VARCHAR(1000),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. DATA IMPORT LOGS
CREATE TABLE IF NOT EXISTS data_import_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_id INT UNSIGNED,
    file_name VARCHAR(500),
    import_type VARCHAR(80),
    records_received INT DEFAULT 0,
    records_imported INT DEFAULT 0,
    records_rejected INT DEFAULT 0,
    status ENUM('pending', 'running', 'success', 'failed')
        DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (source_id) REFERENCES data_sources(id),
    INDEX idx_import_status (status, started_at)
);

-- 9. DATA VALIDATION LOGS
CREATE TABLE IF NOT EXISTS validation_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    import_id BIGINT UNSIGNED,
    severity ENUM('info', 'warning', 'error') NOT NULL,
    validation_rule VARCHAR(150) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (import_id) REFERENCES data_import_logs(id)
        ON DELETE CASCADE,
    INDEX idx_validation_import (import_id)
);
