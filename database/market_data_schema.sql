
USE greedy_stocks;

-- 1. HISTORICAL INDEX CONSTITUENTS
CREATE TABLE IF NOT EXISTS index_constituents (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    index_symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50',
    company_id INT UNSIGNED NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    source_name VARCHAR(150),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(id),

    UNIQUE KEY uq_constituent_period (
        index_symbol,
        company_id,
        effective_from
    ),

    INDEX idx_constituent_dates (
        index_symbol,
        effective_from,
        effective_to
    )
);

-- 2. DAILY RAW STOCK PRICES
CREATE TABLE IF NOT EXISTS stock_prices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id INT UNSIGNED NOT NULL,
    trade_date DATE NOT NULL,

    open_price DECIMAL(18,4),
    high_price DECIMAL(18,4),
    low_price DECIMAL(18,4),
    close_price DECIMAL(18,4),
    previous_close DECIMAL(18,4),

    total_traded_volume BIGINT UNSIGNED,
    total_traded_value DECIMAL(22,4),
    total_trades BIGINT UNSIGNED,

    price_source VARCHAR(100) DEFAULT 'NSE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(id),

    UNIQUE KEY uq_stock_daily (
        company_id,
        trade_date
    ),

    INDEX idx_stock_trade_date (trade_date),
    INDEX idx_stock_company_date (company_id, trade_date)
);

-- 3. HISTORICAL INDEX PRICES
CREATE TABLE IF NOT EXISTS index_prices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    index_symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50',
    trade_date DATE NOT NULL,

    open_value DECIMAL(18,4),
    high_value DECIMAL(18,4),
    low_value DECIMAL(18,4),
    close_value DECIMAL(18,4),

    data_source VARCHAR(100) DEFAULT 'NSE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_index_daily (
        index_symbol,
        trade_date
    ),

    INDEX idx_index_trade_date (trade_date)
);

-- 4. CORPORATE ACTIONS
CREATE TABLE IF NOT EXISTS corporate_actions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    company_id INT UNSIGNED NOT NULL,

    action_type ENUM(
        'DIVIDEND',
        'STOCK_SPLIT',
        'BONUS',
        'RIGHTS_ISSUE',
        'MERGER',
        'DEMERGER',
        'OTHER'
    ) NOT NULL,

    announcement_date DATE,
    ex_date DATE,
    record_date DATE,
    effective_date DATE,

    description TEXT,
    ratio VARCHAR(100),
    dividend_amount DECIMAL(18,4),

    source_name VARCHAR(150),
    source_reference VARCHAR(500),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (company_id) REFERENCES companies(id),

    INDEX idx_corporate_company_date (
        company_id,
        ex_date
    ),

    INDEX idx_corporate_action_type (action_type)
);
