-- Crowd Event Management System - Stage 2 Seed Data
-- Database: crowd_event_db
-- -------------------------------------------------------------

USE `crowd_event_db`;

-- Temporarily disable foreign key checks for clean idempotent re-seeding
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE `alerts`;
TRUNCATE TABLE `crowd_analyses`;
TRUNCATE TABLE `images`;
TRUNCATE TABLE `events`;
TRUNCATE TABLE `venues`;
TRUNCATE TABLE `users`;
SET FOREIGN_KEY_CHECKS = 1;

-- -------------------------------------------------------------
-- 1. Insert Users
-- Roles: 1 administrator, 2 organizers
-- Seed test credentials:
--   admin@college.edu           -> Password: Admin@123
--   john.organizer@college.edu  -> Password: Organizer@123
--   sarah.organizer@college.edu -> Password: Organizer@123
-- -------------------------------------------------------------
INSERT INTO `users` (`id`, `name`, `email`, `password_hash`, `role`, `created_at`) VALUES
(1, 'Admin Administrator', 'admin@college.edu', 'scrypt:32768:8:1$ZBmmI8ijTMZRLXlI$cbf08c9aa2acc3a4add71fb87d23c3e684ce186b0b6f3edf33e855a82ae2b830ece2fe59ba8c40c3b0a12de4682ba4d63843e3b8cf93fd1c3a4a392b2f6d10c4', 'administrator', NOW()),
(2, 'John Organizer', 'john.organizer@college.edu', 'scrypt:32768:8:1$4auFVvoYXxD8QYso$4bf9c94177d8483b526a4a438c80a6e8c3176efceb41890fea4f58ac70396549f5c783b92ad8d551c570a0eae8899fb0ad2444c3b59f0f9bbbc6a90da482b97b', 'organizer', NOW()),
(3, 'Sarah Organizer', 'sarah.organizer@college.edu', 'scrypt:32768:8:1$4auFVvoYXxD8QYso$4bf9c94177d8483b526a4a438c80a6e8c3176efceb41890fea4f58ac70396549f5c783b92ad8d551c570a0eae8899fb0ad2444c3b59f0f9bbbc6a90da482b97b', 'organizer', NOW());

-- -------------------------------------------------------------
-- 2. Insert Venues
-- 3 college venues that administrator maintains
-- -------------------------------------------------------------
INSERT INTO `venues` (`id`, `name`, `location`, `capacity`, `status`, `created_at`) VALUES
(1, 'Main Auditorium', 'Block A, 1st Floor', 1000, 'available', NOW()),
(2, 'Seminar Hall', 'Block B, 2nd Floor', 250, 'available', NOW()),
(3, 'Open Ground', 'Campus Central Grounds', 3000, 'available', NOW());

-- -------------------------------------------------------------
-- 3. Insert Events
-- Event 1: Approved & Currently Active (today, 08:00 to 22:00)
-- Event 2: Pending request for next week
-- -------------------------------------------------------------
INSERT INTO `events` (
    `id`, `organizer_id`, `event_name`, `description`, `status`,
    `requested_date`, `requested_start_time`, `requested_end_time`,
    `approved_date`, `approved_start_time`, `approved_end_time`,
    `venue_id`, `created_at`
) VALUES
(
    1, 2, 'TechFest Annual Symposium 2026', 
    'Flagship college technical conference with keynotes, project exhibitions, and robotics show.', 
    'approved',
    CURRENT_DATE(), '08:00:00', '20:00:00',
    CURRENT_DATE(), '08:00:00', '22:00:00',
    1, NOW()
),
(
    2, 3, 'Cultural Dance & Music Night', 
    'Annual intra-college cultural competition showcasing traditional dance and band performances.', 
    'pending',
    DATE_ADD(CURRENT_DATE(), INTERVAL 7 DAY), '18:00:00', '22:00:00',
    NULL, NULL, NULL,
    3, NOW()
);

-- -------------------------------------------------------------
-- 4. Insert Images for Event 1
-- Images 1-4: successfully processed with crowd analyses.
-- Image 5: pending/processing image with NO crowd analysis yet
-- (proves 0 or 1 relationship between image and analysis).
-- -------------------------------------------------------------
INSERT INTO `images` (`id`, `event_id`, `image_path`, `uploaded_at`, `processing_status`, `created_at`) VALUES
(1, 1, 'uploads/events/1/techfest_img_001.jpg', DATE_SUB(NOW(), INTERVAL 90 MINUTE), 'completed', DATE_SUB(NOW(), INTERVAL 90 MINUTE)),
(2, 1, 'uploads/events/1/techfest_img_002.jpg', DATE_SUB(NOW(), INTERVAL 60 MINUTE), 'completed', DATE_SUB(NOW(), INTERVAL 60 MINUTE)),
(3, 1, 'uploads/events/1/techfest_img_003.jpg', DATE_SUB(NOW(), INTERVAL 30 MINUTE), 'completed', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
(4, 1, 'uploads/events/1/techfest_img_004.jpg', DATE_SUB(NOW(), INTERVAL 5 MINUTE), 'completed', DATE_SUB(NOW(), INTERVAL 5 MINUTE)),
(5, 1, 'uploads/events/1/techfest_img_005.jpg', NOW(), 'pending', NOW());

-- -------------------------------------------------------------
-- 5. Insert Crowd Analyses for Images
-- Image 1 -> 320
-- Image 2 -> 510
-- Image 3 -> 760 (Peak / Maximum crowd count for Event 1)
-- Image 4 -> 640 (Latest crowd count for Event 1 at Main Auditorium)
-- -------------------------------------------------------------
INSERT INTO `crowd_analyses` (
    `id`, `image_id`, `predicted_count`, `analysis_timestamp`,
    `processing_status`, `model_name`, `created_at`
) VALUES
(1, 1, 320, DATE_SUB(NOW(), INTERVAL 88 MINUTE), 'completed', 'CSRNet', DATE_SUB(NOW(), INTERVAL 88 MINUTE)),
(2, 2, 510, DATE_SUB(NOW(), INTERVAL 58 MINUTE), 'completed', 'CSRNet', DATE_SUB(NOW(), INTERVAL 58 MINUTE)),
(3, 3, 760, DATE_SUB(NOW(), INTERVAL 28 MINUTE), 'completed', 'CSRNet', DATE_SUB(NOW(), INTERVAL 28 MINUTE)),
(4, 4, 640, DATE_SUB(NOW(), INTERVAL 3 MINUTE), 'completed', 'CSRNet', DATE_SUB(NOW(), INTERVAL 3 MINUTE));

-- -------------------------------------------------------------
-- 6. Insert Sample Alerts
-- Triggered when peak crowd (760) exceeded safe threshold (700)
-- Sent to both Management (user 1) and Organizer (user 2)
-- -------------------------------------------------------------
INSERT INTO `alerts` (
    `id`, `event_id`, `user_id`, `crowd_analysis_id`,
    `detected_count`, `threshold`, `message`, `status`, `created_at`
) VALUES
(
    1, 1, 1, 3, 760, 700,
    'High Crowd Warning: Main Auditorium density reached 760 attendees, exceeding safe threshold of 700.',
    'unread', DATE_SUB(NOW(), INTERVAL 27 MINUTE)
),
(
    2, 1, 2, 3, 760, 700,
    'High Crowd Warning: Main Auditorium density reached 760 attendees, exceeding safe threshold of 700.',
    'unread', DATE_SUB(NOW(), INTERVAL 27 MINUTE)
);
