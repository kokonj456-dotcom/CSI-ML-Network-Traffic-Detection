CREATE TABLE IF NOT EXISTS capture_files (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    original_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    sha256 BINARY(32) NOT NULL UNIQUE,
    imported_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS traffic_flows (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    capture_file_id BIGINT UNSIGNED NULL,
    first_frame BIGINT UNSIGNED NULL,
    source_type ENUM('live_capture','pcap','central_test') NOT NULL,
    interface_name VARCHAR(255) NULL,
    started_at DATETIME(6) NOT NULL,
    ended_at DATETIME(6) NOT NULL,
    src_ip VARBINARY(16) NULL,
    dst_ip VARBINARY(16) NULL,
    src_port SMALLINT UNSIGNED NULL,
    dst_port SMALLINT UNSIGNED NULL,
    transport_protocol VARCHAR(16) NOT NULL,
    service_group VARCHAR(32) NULL,
    connection_state VARCHAR(32) NULL,
    packets_forward BIGINT UNSIGNED NOT NULL,
    packets_backward BIGINT UNSIGNED NOT NULL,
    bytes_forward BIGINT UNSIGNED NOT NULL,
    bytes_backward BIGINT UNSIGNED NOT NULL,
    FOREIGN KEY (capture_file_id) REFERENCES capture_files(id),
    UNIQUE KEY uq_capture_flow (capture_file_id, first_frame),
    INDEX idx_flow_time (started_at, id),
    INDEX idx_flow_src_time (src_ip, started_at),
    INDEX idx_flow_dst_time (dst_ip, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS flow_protocol_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    flow_id BIGINT UNSIGNED NOT NULL,
    observed_at DATETIME(6) NOT NULL,
    protocol VARCHAR(16) NOT NULL,
    frame_number BIGINT UNSIGNED NULL,
    details_json JSON NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES traffic_flows(id),
    INDEX idx_event_flow_time (flow_id, observed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS predictions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    flow_id BIGINT UNSIGNED NOT NULL,
    model_id VARCHAR(191) NOT NULL,
    scored_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    status ENUM('scored','not_scored') NOT NULL,
    binary_score DOUBLE NULL,
    threshold_used DOUBLE NULL,
    is_flagged BOOLEAN NULL,
    category_id SMALLINT UNSIGNED NULL,
    category_score DOUBLE NULL,
    inputs_json JSON NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES traffic_flows(id),
    UNIQUE KEY uq_flow_model (flow_id, model_id),
    INDEX idx_prediction_flow_time (flow_id, scored_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    prediction_id BIGINT UNSIGNED NOT NULL UNIQUE,
    opened_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    status ENUM('new','acknowledged','resolved') NOT NULL DEFAULT 'new',
    acknowledged_at DATETIME(6) NULL,
    resolved_at DATETIME(6) NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id),
    INDEX idx_alert_status_time (status, opened_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS false_positive_feedback (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    alert_id BIGINT UNSIGNED NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    evidence_note TEXT NULL,
    reported_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'approved',
    review_note TEXT NULL,
    reviewed_at DATETIME(6) NULL,
    FOREIGN KEY (alert_id) REFERENCES alerts(id),
    INDEX idx_feedback_status_time (status, reported_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
