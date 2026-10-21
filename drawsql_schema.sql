-- ============================================================================
-- Crowd Event Management System - DDL Schema for DrawSQL (drawsql.app)
-- Dialect: MySQL
-- Order: Parent tables created first to ensure foreign key resolution
-- ============================================================================

-- -------------------------------------------------------------
-- 1. Table: users
-- -------------------------------------------------------------
CREATE TABLE `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` ENUM('administrator', 'organizer') NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------
-- 2. Table: venues
-- -------------------------------------------------------------
CREATE TABLE `venues` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `location` VARCHAR(255) NOT NULL,
    `capacity` INT NOT NULL DEFAULT 0,
    `status` ENUM('available', 'unavailable') NOT NULL DEFAULT 'available',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------
-- 3. Table: fest
-- -------------------------------------------------------------
CREATE TABLE `fest` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `start_date` DATE NULL,
    `end_date` DATE NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------
-- 4. Table: events
-- -------------------------------------------------------------
CREATE TABLE `events` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `organizer_id` INT NOT NULL,
    `venue_id` INT NULL,
    `series_id` INT NULL,
    `event_name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `status` ENUM('pending', 'approved', 'rejected', 'completed', 'cancelled') NOT NULL DEFAULT 'pending',
    `requested_date` DATE NOT NULL,
    `requested_start_time` TIME NOT NULL,
    `requested_end_time` TIME NOT NULL,
    `approved_date` DATE NULL,
    `approved_start_time` TIME NULL,
    `approved_end_time` TIME NULL,
    `category` VARCHAR(50) DEFAULT 'General',
    `rejection_reason` VARCHAR(255) NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_events_organizer` FOREIGN KEY (`organizer_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT `fk_events_venue` FOREIGN KEY (`venue_id`) REFERENCES `venues` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT `fk_events_series` FOREIGN KEY (`series_id`) REFERENCES `fest` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
);

-- -------------------------------------------------------------
-- 5. Table: images
-- -------------------------------------------------------------
CREATE TABLE `images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `event_id` INT NOT NULL,
    `image_path` VARCHAR(255) NOT NULL,
    `uploaded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `processing_status` ENUM('pending', 'processing', 'completed', 'failed') NOT NULL DEFAULT 'pending',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_images_event` FOREIGN KEY (`event_id`) REFERENCES `events` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
);

-- -------------------------------------------------------------
-- 6. Table: crowd_analyses
-- -------------------------------------------------------------
CREATE TABLE `crowd_analyses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `image_id` INT NOT NULL UNIQUE,
    `predicted_count` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `processing_status` ENUM('pending', 'completed', 'failed') NOT NULL DEFAULT 'completed',
    `model_name` VARCHAR(50) NOT NULL DEFAULT 'CSRNet',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_crowd_analyses_image` FOREIGN KEY (`image_id`) REFERENCES `images` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
);

-- -------------------------------------------------------------
-- 7. Table: alerts
-- -------------------------------------------------------------
CREATE TABLE `alerts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `event_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    `crowd_analysis_id` INT NULL,
    `detected_count` INT NOT NULL,
    `threshold` INT NOT NULL,
    `message` VARCHAR(255) NOT NULL,
    `status` ENUM('unread', 'read') NOT NULL DEFAULT 'unread',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_alerts_event` FOREIGN KEY (`event_id`) REFERENCES `events` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_alerts_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_alerts_analysis` FOREIGN KEY (`crowd_analysis_id`) REFERENCES `crowd_analyses` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
);
