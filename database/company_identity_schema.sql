
CREATE TABLE IF NOT EXISTS company_identifiers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    company_id INT UNSIGNED NOT NULL,
    identifier_type VARCHAR(30) NOT NULL,
    identifier_value VARCHAR(50) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE DEFAULT NULL,
    source_name VARCHAR(150) DEFAULT NULL,
    source_reference VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uq_company_identifier_period (
        company_id,
        identifier_type,
        identifier_value,
        valid_from
    ),

    KEY idx_identifier_lookup (
        identifier_type,
        identifier_value,
        valid_from,
        valid_to
    ),

    CONSTRAINT fk_company_identifiers_company
        FOREIGN KEY (company_id)
        REFERENCES companies(id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
