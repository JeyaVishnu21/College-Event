-- Crowd Event Management System - Stage 2 Database Schema
-- Database: MySQL 8.x+ / MariaDB compatible
-- -------------------------------------------------------------

CREATE DATABASE IF NOT EXISTS `crowd_event_db` 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE `crowd_event_db`;

-- -------------------------------------------------------------
-- 1. Table: users
-- Stores administrator and organizer accounts.
-- Distinguishes user roles with strict ENUM constraint.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` ENUM('administrator', 'organizer') NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_users_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------
-- 2. Table: venues
-- Stores campus event locations managed by college administrator.
-- Allows a venue to host multiple events over time.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `venues` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `location` VARCHAR(255) NOT NULL,
    `capacity` INT NOT NULL DEFAULT 0,
    `status` ENUM('available', 'unavailable') NOT NULL DEFAULT 'available',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------
-- 2b. Table: fest
-- Stores event / festival series grouping (e.g. Legacy 2K26).
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `fest` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `start_date` DATE NULL,
    `end_date` DATE NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_fest_dates` (`start_date`, `end_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Compatibility VIEW for event_series
CREATE OR REPLACE VIEW `event_series` AS SELECT * FROM `fest`;

-- -------------------------------------------------------------
-- 3. Table: events
-- Stores event requests, requested schedules vs administrator's
-- final approved schedules, venue allocation, category, and fest.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `events` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `organizer_id` INT NOT NULL,
    `event_name` VARCHAR(150) NOT NULL,
    `description` TEXT NULL,
    `status` ENUM('pending', 'approved', 'rejected', 'completed', 'cancelled') NOT NULL DEFAULT 'pending',
    `requested_date` DATE NOT NULL,
    `requested_start_time` TIME NOT NULL,
    `requested_end_time` TIME NOT NULL,
    `approved_date` DATE NULL,
    `approved_start_time` TIME NULL,
    `approved_end_time` TIME NULL,
    `venue_id` INT NULL,
    `series_id` INT NULL,
    `category` VARCHAR(50) DEFAULT 'General',
    `expected_participants` INT NULL DEFAULT NULL,
    `rejection_reason` VARCHAR(255) NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_events_organizer` (`organizer_id`),
    INDEX `idx_events_venue_status` (`venue_id`, `status`),
    INDEX `idx_events_schedule` (`approved_date`, `approved_start_time`, `approved_end_time`),
    INDEX `idx_events_series` (`series_id`),
    INDEX `idx_events_category` (`category`),
    CONSTRAINT `fk_events_organizer` FOREIGN KEY (`organizer_id`) 
        REFERENCES `users` (`id`) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    CONSTRAINT `fk_events_venue` FOREIGN KEY (`venue_id`) 
        REFERENCES `venues` (`id`) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE,
    CONSTRAINT `fk_events_series` FOREIGN KEY (`series_id`) 
        REFERENCES `fest` (`id`) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------
-- 4. Table: images
-- Stores periodic event images uploaded during an active event.
-- An event can have multiple images.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `event_id` INT NOT NULL,
    `image_path` VARCHAR(255) NOT NULL,
    `uploaded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `processing_status` ENUM('pending', 'processing', 'completed', 'failed') NOT NULL DEFAULT 'pending',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_images_event` (`event_id`),
    INDEX `idx_images_status` (`processing_status`),
    CONSTRAINT `fk_images_event` FOREIGN KEY (`event_id`) 
        REFERENCES `events` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------
-- 5. Table: crowd_analyses
-- Stores numeric crowd count estimates for images.
-- image_id is UNIQUE: an image has 0 or 1 crowd analysis record.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `crowd_analyses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `image_id` INT NOT NULL UNIQUE,
    `predicted_count` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `processing_status` ENUM('pending', 'completed', 'failed') NOT NULL DEFAULT 'completed',
    `model_name` VARCHAR(50) NOT NULL DEFAULT 'CSRNet',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_crowd_analyses_timestamp` (`analysis_timestamp`),
    INDEX `idx_crowd_analyses_count` (`predicted_count`),
    CONSTRAINT `fk_crowd_analyses_image` FOREIGN KEY (`image_id`) 
        REFERENCES `images` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------
-- 6. Table: alerts
-- Stores notifications generated when crowd count exceeds
-- venue safe thresholds. Targetable to organizer and administrator.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `alerts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `event_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    `crowd_analysis_id` INT NULL,
    `detected_count` INT NOT NULL,
    `threshold` INT NOT NULL,
    `message` VARCHAR(255) NOT NULL,
    `status` ENUM('unread', 'read') NOT NULL DEFAULT 'unread',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_alerts_user_status` (`user_id`, `status`),
    INDEX `idx_alerts_event` (`event_id`),
    CONSTRAINT `fk_alerts_event` FOREIGN KEY (`event_id`) 
        REFERENCES `events` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
    CONSTRAINT `fk_alerts_user` FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
    CONSTRAINT `fk_alerts_analysis` FOREIGN KEY (`crowd_analysis_id`) 
        REFERENCES `crowd_analyses` (`id`) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
