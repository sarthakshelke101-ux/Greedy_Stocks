
USE greedy_stocks;

CREATE TABLE IF NOT EXISTS index_constituent_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    index_symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50',
    report_month DATE NOT NULL,

    symbol VARCHAR(30) NOT NULL,
    security_name VARCHAR(255) NOT NULL,
    industry VARCHAR(255) NULL,

    equity_capital DECIMAL(24, 4) NULL,
    index_market_cap DECIMAL(24, 8) NULL,
    weightage DECIMAL(12, 8) NULL,

    beta DECIMAL(12, 8) NULL,
    r2 DECIMAL(12, 8) NULL,
    volatility DECIMAL(16, 8) NULL,
    monthly_return DECIMAL(16, 8) NULL,
    avg_impact_cost DECIMAL(16, 8) NULL,

    source_archive VARCHAR(255) NOT NULL,
    source_csv VARCHAR(255) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uq_snapshot_month_symbol (
        index_symbol,
        report_month,
        symbol
    ),

    KEY idx_snapshot_symbol_month (
        symbol,
        report_month
    ),

    KEY idx_snapshot_month (
        report_month
    )

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
