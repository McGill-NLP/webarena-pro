/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-11.8.6-MariaDB, for debian-linux-gnu (aarch64)
--
-- Host: localhost    Database: firefly
-- ------------------------------------------------------
-- Server version	11.8.6-MariaDB-ubu2404

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `2fa_tokens`
--

DROP TABLE IF EXISTS `2fa_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `2fa_tokens` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(10) unsigned NOT NULL,
  `expires_at` datetime NOT NULL,
  `token` varchar(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `2fa_tokens_token_unique` (`token`),
  KEY `2fa_tokens_user_id_foreign` (`user_id`),
  CONSTRAINT `2fa_tokens_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `2fa_tokens`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `2fa_tokens` WRITE;
/*!40000 ALTER TABLE `2fa_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `2fa_tokens` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `account_balances`
--

DROP TABLE IF EXISTS `account_balances`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `account_balances` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `title` varchar(100) DEFAULT NULL,
  `account_id` int(10) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `date` date DEFAULT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `transaction_journal_id` int(10) unsigned DEFAULT NULL,
  `balance` decimal(32,12) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_account_currency` (`account_id`,`transaction_currency_id`,`transaction_journal_id`,`date`,`title`),
  KEY `account_balances_transaction_journal_id_foreign` (`transaction_journal_id`),
  KEY `account_balances_transaction_currency_id_foreign` (`transaction_currency_id`),
  CONSTRAINT `account_balances_account_id_foreign` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `account_balances_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `account_balances_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `account_balances`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `account_balances` WRITE;
/*!40000 ALTER TABLE `account_balances` DISABLE KEYS */;
/*!40000 ALTER TABLE `account_balances` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `account_meta`
--

DROP TABLE IF EXISTS `account_meta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `account_meta` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `account_id` int(10) unsigned NOT NULL,
  `name` varchar(191) NOT NULL,
  `data` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `account_meta_account_id_index` (`account_id`),
  CONSTRAINT `account_meta_account_id_foreign` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=41 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `account_meta`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `account_meta` WRITE;
/*!40000 ALTER TABLE `account_meta` DISABLE KEYS */;
INSERT INTO `account_meta` VALUES
(1,'2026-03-05 23:02:04','2026-03-05 23:02:04',1,'account_role','\"defaultAsset\"'),
(2,'2026-03-05 23:02:04','2026-03-05 23:02:04',1,'currency_id','\"1\"'),
(3,'2026-03-05 23:02:04','2026-03-05 23:02:04',2,'account_role','\"savingAsset\"'),
(4,'2026-03-05 23:02:04','2026-03-05 23:02:04',2,'currency_id','\"1\"'),
(5,'2026-03-05 23:02:04','2026-03-05 23:02:04',3,'account_role','\"cashWalletAsset\"'),
(6,'2026-03-05 23:02:04','2026-03-05 23:02:04',3,'currency_id','\"1\"'),
(7,'2026-03-05 23:23:30','2026-03-05 23:23:30',4,'BIC','\"\"'),
(8,'2026-03-05 23:23:30','2026-03-05 23:23:30',4,'account_number','\"\"'),
(9,'2026-03-05 23:23:30','2026-03-05 23:23:30',5,'BIC','\"\"'),
(10,'2026-03-05 23:23:30','2026-03-05 23:23:30',5,'account_number','\"\"'),
(11,'2026-03-05 23:23:30','2026-03-05 23:23:30',6,'BIC','\"\"'),
(12,'2026-03-05 23:23:30','2026-03-05 23:23:30',6,'account_number','\"\"'),
(13,'2026-03-05 23:23:31','2026-03-05 23:23:31',7,'BIC','\"\"'),
(14,'2026-03-05 23:23:31','2026-03-05 23:23:31',7,'account_number','\"\"'),
(15,'2026-03-05 23:23:31','2026-03-05 23:23:31',8,'BIC','\"\"'),
(16,'2026-03-05 23:23:31','2026-03-05 23:23:31',8,'account_number','\"\"'),
(17,'2026-03-05 23:23:31','2026-03-05 23:23:31',9,'BIC','\"\"'),
(18,'2026-03-05 23:23:31','2026-03-05 23:23:31',9,'account_number','\"\"'),
(19,'2026-03-05 23:23:31','2026-03-05 23:23:31',10,'BIC','\"\"'),
(20,'2026-03-05 23:23:31','2026-03-05 23:23:31',10,'account_number','\"\"'),
(21,'2026-03-05 23:23:31','2026-03-05 23:23:31',11,'BIC','\"\"'),
(22,'2026-03-05 23:23:31','2026-03-05 23:23:31',11,'account_number','\"\"'),
(23,'2026-03-05 23:23:31','2026-03-05 23:23:31',12,'BIC','\"\"'),
(24,'2026-03-05 23:23:31','2026-03-05 23:23:31',12,'account_number','\"\"'),
(25,'2026-03-05 23:30:40','2026-03-05 23:30:40',13,'BIC','\"\"'),
(26,'2026-03-05 23:30:40','2026-03-05 23:30:40',13,'account_number','\"\"'),
(27,'2026-03-05 23:30:40','2026-03-05 23:30:40',14,'BIC','\"\"'),
(28,'2026-03-05 23:30:40','2026-03-05 23:30:40',14,'account_number','\"\"'),
(29,'2026-03-05 23:30:40','2026-03-05 23:30:40',15,'BIC','\"\"'),
(30,'2026-03-05 23:30:40','2026-03-05 23:30:40',15,'account_number','\"\"'),
(31,'2026-03-05 23:30:40','2026-03-05 23:30:40',16,'BIC','\"\"'),
(32,'2026-03-05 23:30:40','2026-03-05 23:30:40',16,'account_number','\"\"'),
(33,'2026-03-05 23:30:40','2026-03-05 23:30:40',17,'BIC','\"\"'),
(34,'2026-03-05 23:30:40','2026-03-05 23:30:40',17,'account_number','\"\"'),
(35,'2026-03-05 23:30:41','2026-03-05 23:30:41',18,'BIC','\"\"'),
(36,'2026-03-05 23:30:41','2026-03-05 23:30:41',18,'account_number','\"\"'),
(37,'2026-03-05 23:30:41','2026-03-05 23:30:41',19,'BIC','\"\"'),
(38,'2026-03-05 23:30:41','2026-03-05 23:30:41',19,'account_number','\"\"'),
(39,'2026-03-05 23:30:41','2026-03-05 23:30:41',20,'BIC','\"\"'),
(40,'2026-03-05 23:30:41','2026-03-05 23:30:41',20,'account_number','\"\"');
/*!40000 ALTER TABLE `account_meta` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `account_piggy_bank`
--

DROP TABLE IF EXISTS `account_piggy_bank`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `account_piggy_bank` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `account_id` int(10) unsigned NOT NULL,
  `piggy_bank_id` int(10) unsigned NOT NULL,
  `current_amount` decimal(32,12) NOT NULL DEFAULT 0.000000000000,
  `native_current_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_piggy_save` (`account_id`,`piggy_bank_id`),
  KEY `account_piggy_bank_piggy_bank_id_foreign` (`piggy_bank_id`),
  CONSTRAINT `account_piggy_bank_account_id_foreign` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `account_piggy_bank_piggy_bank_id_foreign` FOREIGN KEY (`piggy_bank_id`) REFERENCES `piggy_banks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `account_piggy_bank`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `account_piggy_bank` WRITE;
/*!40000 ALTER TABLE `account_piggy_bank` DISABLE KEYS */;
/*!40000 ALTER TABLE `account_piggy_bank` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `account_types`
--

DROP TABLE IF EXISTS `account_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `account_types` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `type` varchar(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `account_types_type_unique` (`type`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `account_types`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `account_types` WRITE;
/*!40000 ALTER TABLE `account_types` DISABLE KEYS */;
INSERT INTO `account_types` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26','Asset account'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26','Beneficiary account'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26','Cash account'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26','Credit card'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26','Debt'),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26','Default account'),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26','Expense account'),
(8,'2026-03-05 22:12:26','2026-03-05 22:12:26','Import account'),
(9,'2026-03-05 22:12:26','2026-03-05 22:12:26','Initial balance account'),
(10,'2026-03-05 22:12:26','2026-03-05 22:12:26','Liability credit account'),
(11,'2026-03-05 22:12:26','2026-03-05 22:12:26','Loan'),
(12,'2026-03-05 22:12:26','2026-03-05 22:12:26','Mortgage'),
(13,'2026-03-05 22:12:26','2026-03-05 22:12:26','Reconciliation account'),
(14,'2026-03-05 22:12:26','2026-03-05 22:12:26','Revenue account');
/*!40000 ALTER TABLE `account_types` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `accounts`
--

DROP TABLE IF EXISTS `accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `accounts` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `account_type_id` int(10) unsigned NOT NULL,
  `name` varchar(1024) NOT NULL,
  `virtual_balance` decimal(32,12) DEFAULT NULL,
  `iban` varchar(255) DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `encrypted` tinyint(1) NOT NULL DEFAULT 0,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `native_virtual_balance` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `accounts_user_id_index` (`user_id`),
  KEY `accounts_user_group_id_index` (`user_group_id`),
  KEY `accounts_account_type_id_index` (`account_type_id`),
  CONSTRAINT `accounts_account_type_id_foreign` FOREIGN KEY (`account_type_id`) REFERENCES `account_types` (`id`) ON DELETE CASCADE,
  CONSTRAINT `accounts_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `accounts_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `accounts`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `accounts` WRITE;
/*!40000 ALTER TABLE `accounts` DISABLE KEYS */;
INSERT INTO `accounts` VALUES
(1,'2026-03-05 23:02:04','2026-03-05 23:02:37',NULL,1,1,1,'BMO',0.000000000000,NULL,1,0,1,NULL),
(2,'2026-03-05 23:02:04','2026-03-05 23:02:37',NULL,1,1,1,'BMO savings account',0.000000000000,NULL,1,0,2,NULL),
(3,'2026-03-05 23:02:04','2026-03-05 23:02:04',NULL,1,1,1,'Cash wallet',0.000000000000,NULL,1,0,3,NULL),
(4,'2026-03-05 23:23:30','2026-03-05 23:30:41',NULL,1,1,14,'Adobe',NULL,NULL,1,0,0,NULL),
(5,'2026-03-05 23:23:30','2026-03-05 23:30:41',NULL,1,1,14,'KPN Phone Provider',NULL,NULL,1,0,0,NULL),
(6,'2026-03-05 23:23:30','2026-03-05 23:30:41',NULL,1,1,14,'Taxes and Revenues Government service',NULL,NULL,1,0,0,NULL),
(7,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'Alibaba',NULL,NULL,1,0,0,NULL),
(8,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'amazon.com',NULL,NULL,1,0,0,NULL),
(9,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'iCentre Mac Store',NULL,NULL,1,0,0,NULL),
(10,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'Jumper Pet Food Store',NULL,NULL,1,0,0,NULL),
(11,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'Cafe Central',NULL,NULL,1,0,0,NULL),
(12,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,1,1,7,'Student Loan Organization',NULL,NULL,1,0,0,NULL),
(13,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,7,'Baker Bob',NULL,NULL,1,0,0,NULL),
(14,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,7,'Buy and Large',NULL,NULL,1,0,0,NULL),
(15,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,7,'Halfords Car Parts',NULL,NULL,1,0,0,NULL),
(16,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,7,'McDonalds',NULL,NULL,1,0,0,NULL),
(17,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,7,'SuperMarket',NULL,NULL,1,0,0,NULL),
(18,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,'XS4All ISP',NULL,NULL,1,0,0,NULL),
(19,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,'The Water Company',NULL,NULL,1,0,0,NULL),
(20,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,'Shell',NULL,NULL,1,0,0,NULL);
/*!40000 ALTER TABLE `accounts` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `attachments`
--

DROP TABLE IF EXISTS `attachments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `attachments` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `attachable_id` int(10) unsigned NOT NULL,
  `attachable_type` varchar(255) NOT NULL,
  `md5` varchar(128) NOT NULL,
  `filename` varchar(1024) NOT NULL,
  `title` varchar(1024) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `mime` varchar(1024) NOT NULL,
  `size` int(10) unsigned NOT NULL,
  `uploaded` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `attachments_user_id_foreign` (`user_id`),
  KEY `attachments_to_ugi` (`user_group_id`),
  CONSTRAINT `attachments_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `attachments_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attachments`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `attachments` WRITE;
/*!40000 ALTER TABLE `attachments` DISABLE KEYS */;
/*!40000 ALTER TABLE `attachments` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `audit_log_entries`
--

DROP TABLE IF EXISTS `audit_log_entries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_log_entries` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `auditable_id` int(10) unsigned NOT NULL,
  `auditable_type` varchar(191) NOT NULL,
  `changer_id` int(10) unsigned NOT NULL,
  `changer_type` varchar(191) NOT NULL,
  `action` varchar(255) NOT NULL,
  `before` text DEFAULT NULL,
  `after` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_log_entries`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `audit_log_entries` WRITE;
/*!40000 ALTER TABLE `audit_log_entries` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_log_entries` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `auto_budgets`
--

DROP TABLE IF EXISTS `auto_budgets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `auto_budgets` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `budget_id` int(10) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `auto_budget_type` tinyint(3) unsigned NOT NULL DEFAULT 1,
  `amount` decimal(32,12) NOT NULL,
  `period` varchar(50) NOT NULL,
  `native_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `auto_budgets_transaction_currency_id_foreign` (`transaction_currency_id`),
  KEY `auto_budgets_budget_id_foreign` (`budget_id`),
  CONSTRAINT `auto_budgets_budget_id_foreign` FOREIGN KEY (`budget_id`) REFERENCES `budgets` (`id`) ON DELETE CASCADE,
  CONSTRAINT `auto_budgets_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auto_budgets`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `auto_budgets` WRITE;
/*!40000 ALTER TABLE `auto_budgets` DISABLE KEYS */;
/*!40000 ALTER TABLE `auto_budgets` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `available_budgets`
--

DROP TABLE IF EXISTS `available_budgets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `available_budgets` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `amount` decimal(32,12) NOT NULL,
  `start_date` date NOT NULL,
  `start_date_tz` varchar(50) DEFAULT NULL,
  `end_date` date NOT NULL,
  `end_date_tz` varchar(50) DEFAULT NULL,
  `native_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `available_budgets_transaction_currency_id_foreign` (`transaction_currency_id`),
  KEY `available_budgets_user_id_foreign` (`user_id`),
  KEY `available_budgets_to_ugi` (`user_group_id`),
  CONSTRAINT `available_budgets_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `available_budgets_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `available_budgets_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `available_budgets`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `available_budgets` WRITE;
/*!40000 ALTER TABLE `available_budgets` DISABLE KEYS */;
/*!40000 ALTER TABLE `available_budgets` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `bills`
--

DROP TABLE IF EXISTS `bills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `bills` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned DEFAULT NULL,
  `name` varchar(1024) NOT NULL,
  `match` varchar(1024) NOT NULL,
  `amount_min` decimal(32,12) NOT NULL,
  `amount_max` decimal(32,12) NOT NULL,
  `date` date NOT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `end_date_tz` varchar(50) DEFAULT NULL,
  `extension_date` date DEFAULT NULL,
  `extension_date_tz` varchar(50) DEFAULT NULL,
  `repeat_freq` varchar(30) NOT NULL,
  `skip` smallint(5) unsigned NOT NULL DEFAULT 0,
  `automatch` tinyint(1) NOT NULL DEFAULT 1,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `name_encrypted` tinyint(1) NOT NULL DEFAULT 0,
  `match_encrypted` tinyint(1) NOT NULL DEFAULT 0,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `native_amount_min` decimal(32,12) DEFAULT NULL,
  `native_amount_max` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `bills_user_id_foreign` (`user_id`),
  KEY `bills_transaction_currency_id_foreign` (`transaction_currency_id`),
  KEY `bills_to_ugi` (`user_group_id`),
  CONSTRAINT `bills_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `bills_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE SET NULL,
  CONSTRAINT `bills_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bills`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `bills` WRITE;
/*!40000 ALTER TABLE `bills` DISABLE KEYS */;
/*!40000 ALTER TABLE `bills` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `budget_limits`
--

DROP TABLE IF EXISTS `budget_limits`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `budget_limits` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `budget_id` int(10) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned DEFAULT NULL,
  `start_date` date NOT NULL,
  `start_date_tz` varchar(50) DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `end_date_tz` varchar(50) DEFAULT NULL,
  `amount` decimal(32,12) NOT NULL,
  `period` varchar(12) DEFAULT NULL,
  `generated` tinyint(1) NOT NULL DEFAULT 0,
  `native_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `budget_limits_budget_id_foreign` (`budget_id`),
  KEY `budget_limits_transaction_currency_id_foreign` (`transaction_currency_id`),
  CONSTRAINT `budget_limits_budget_id_foreign` FOREIGN KEY (`budget_id`) REFERENCES `budgets` (`id`) ON DELETE CASCADE,
  CONSTRAINT `budget_limits_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `budget_limits`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `budget_limits` WRITE;
/*!40000 ALTER TABLE `budget_limits` DISABLE KEYS */;
/*!40000 ALTER TABLE `budget_limits` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `budget_transaction`
--

DROP TABLE IF EXISTS `budget_transaction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `budget_transaction` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `budget_id` int(10) unsigned NOT NULL,
  `transaction_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `budget_transaction_budget_id_foreign` (`budget_id`),
  KEY `budget_transaction_transaction_id_foreign` (`transaction_id`),
  CONSTRAINT `budget_transaction_budget_id_foreign` FOREIGN KEY (`budget_id`) REFERENCES `budgets` (`id`) ON DELETE CASCADE,
  CONSTRAINT `budget_transaction_transaction_id_foreign` FOREIGN KEY (`transaction_id`) REFERENCES `transactions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `budget_transaction`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `budget_transaction` WRITE;
/*!40000 ALTER TABLE `budget_transaction` DISABLE KEYS */;
/*!40000 ALTER TABLE `budget_transaction` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `budget_transaction_journal`
--

DROP TABLE IF EXISTS `budget_transaction_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `budget_transaction_journal` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `budget_id` int(10) unsigned NOT NULL,
  `budget_limit_id` int(10) unsigned DEFAULT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `budget_transaction_journal_budget_id_foreign` (`budget_id`),
  KEY `budget_transaction_journal_transaction_journal_id_foreign` (`transaction_journal_id`),
  KEY `budget_id_foreign` (`budget_limit_id`),
  CONSTRAINT `budget_id_foreign` FOREIGN KEY (`budget_limit_id`) REFERENCES `budget_limits` (`id`) ON DELETE SET NULL,
  CONSTRAINT `budget_transaction_journal_budget_id_foreign` FOREIGN KEY (`budget_id`) REFERENCES `budgets` (`id`) ON DELETE CASCADE,
  CONSTRAINT `budget_transaction_journal_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `budget_transaction_journal`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `budget_transaction_journal` WRITE;
/*!40000 ALTER TABLE `budget_transaction_journal` DISABLE KEYS */;
INSERT INTO `budget_transaction_journal` VALUES
(1,1,NULL,10),
(2,3,NULL,11),
(3,3,NULL,12),
(4,1,NULL,13),
(5,2,NULL,14),
(6,1,NULL,15),
(7,2,NULL,16),
(8,2,NULL,17),
(9,2,NULL,18),
(10,1,NULL,19),
(11,4,NULL,20),
(12,1,NULL,21),
(13,3,NULL,22),
(14,3,NULL,23);
/*!40000 ALTER TABLE `budget_transaction_journal` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `budgets`
--

DROP TABLE IF EXISTS `budgets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `budgets` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `name` varchar(1024) NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `encrypted` tinyint(1) NOT NULL DEFAULT 0,
  `order` mediumint(8) unsigned NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `budgets_user_id_index` (`user_id`),
  KEY `budgets_user_group_id_index` (`user_group_id`),
  CONSTRAINT `budgets_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `budgets_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `budgets`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `budgets` WRITE;
/*!40000 ALTER TABLE `budgets` DISABLE KEYS */;
INSERT INTO `budgets` VALUES
(1,'2026-03-05 23:27:42','2026-03-05 23:27:42',NULL,1,1,'Groceries',1,0,1),
(2,'2026-03-05 23:28:23','2026-03-05 23:28:23',NULL,1,1,'Bills',1,0,2),
(3,'2026-03-05 23:28:28','2026-03-05 23:28:28',NULL,1,1,'Car',1,0,3),
(4,'2026-03-05 23:28:43','2026-03-05 23:28:43',NULL,1,1,'Going out',1,0,4);
/*!40000 ALTER TABLE `budgets` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `categories`
--

DROP TABLE IF EXISTS `categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `categories` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `name` varchar(1024) NOT NULL,
  `encrypted` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `categories_user_id_index` (`user_id`),
  KEY `categories_user_group_id_index` (`user_group_id`),
  CONSTRAINT `categories_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `categories_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `categories`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `categories` WRITE;
/*!40000 ALTER TABLE `categories` DISABLE KEYS */;
INSERT INTO `categories` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,'Reimbursements',0),
(2,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,'Internet',0),
(3,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,'Electronics',0),
(4,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,'Cats',0),
(5,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,'Drinks',0),
(6,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,'Student loans',0),
(7,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,'Daily Groceries',0),
(8,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,'Car',0),
(9,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,'Junk food',0),
(10,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,'House',0),
(11,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,'Going out',0);
/*!40000 ALTER TABLE `categories` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `category_transaction`
--

DROP TABLE IF EXISTS `category_transaction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `category_transaction` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `category_id` int(10) unsigned NOT NULL,
  `transaction_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `category_transaction_category_id_foreign` (`category_id`),
  KEY `category_transaction_transaction_id_foreign` (`transaction_id`),
  CONSTRAINT `category_transaction_category_id_foreign` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`) ON DELETE CASCADE,
  CONSTRAINT `category_transaction_transaction_id_foreign` FOREIGN KEY (`transaction_id`) REFERENCES `transactions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `category_transaction`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `category_transaction` WRITE;
/*!40000 ALTER TABLE `category_transaction` DISABLE KEYS */;
/*!40000 ALTER TABLE `category_transaction` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `category_transaction_journal`
--

DROP TABLE IF EXISTS `category_transaction_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `category_transaction_journal` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `category_id` int(10) unsigned NOT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `category_transaction_journal_category_id_foreign` (`category_id`),
  KEY `category_transaction_journal_transaction_journal_id_index` (`transaction_journal_id`),
  CONSTRAINT `category_transaction_journal_category_id_foreign` FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`) ON DELETE CASCADE,
  CONSTRAINT `category_transaction_journal_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `category_transaction_journal`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `category_transaction_journal` WRITE;
/*!40000 ALTER TABLE `category_transaction_journal` DISABLE KEYS */;
INSERT INTO `category_transaction_journal` VALUES
(1,1,1),
(2,1,2),
(3,1,3),
(4,2,4),
(5,2,5),
(6,3,6),
(7,4,7),
(8,5,8),
(9,6,9),
(10,7,10),
(11,8,11),
(12,8,12),
(13,9,13),
(14,6,14),
(15,7,15),
(16,2,16),
(17,6,17),
(18,10,18),
(19,7,19),
(20,11,20),
(21,7,21),
(22,8,22),
(23,8,23);
/*!40000 ALTER TABLE `category_transaction_journal` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `configuration`
--

DROP TABLE IF EXISTS `configuration`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `configuration` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `name` varchar(50) NOT NULL,
  `data` text NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=55 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `configuration`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `configuration` WRITE;
/*!40000 ALTER TABLE `configuration` DISABLE KEYS */;
INSERT INTO `configuration` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'db_version','1'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_accounts','true'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_attachments','true'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_bills','true'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_budgets','true'),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_categories','true'),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_piggy_banks','true'),
(8,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_preferences','true'),
(9,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_tags','true'),
(10,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_transaction_journals','true'),
(11,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_transactions','true'),
(12,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'is_decrypted_journal_links','true'),
(13,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_transaction_identifier','true'),
(14,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_migrated_to_groups','true'),
(15,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_account_currencies','true'),
(16,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_transfer_currencies','true'),
(17,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_other_currencies','true'),
(18,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_migrate_notes','true'),
(19,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_migrate_attachments','true'),
(20,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_bills_to_rules','true'),
(21,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_bl_currency','true'),
(22,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_cc_liabilities','true'),
(23,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_back_to_journals','true'),
(24,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'480_rename_account_meta','true'),
(25,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'481_migrate_recurrence_meta','true'),
(26,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'500_migrate_tag_locations','true'),
(27,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'560_upgrade_liabilities','true'),
(28,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'600_upgrade_liabilities','true'),
(29,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'550_budget_limit_periods','true'),
(30,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'610_migrate_rule_actions','true'),
(31,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'610_correct_balances','true'),
(32,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'use_running_balance','true'),
(33,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'610_upgrade_currency_prefs','true'),
(34,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'620_make_multi_piggies','true'),
(35,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'620_pc_amounts','true'),
(36,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'enable_exchange_rates','false'),
(37,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'640_upgrade_webhooks','true'),
(38,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'oauth_private_key','\"eyJpdiI6InE1cGkzT2hEb2RTNjdydHc5VzhxVlE9PSIsInZhbHVlIjoiNkkxeENCUmtEUXhaZUtBVkltVCs3WkNXdmM0SmEySzRZdHE2d0VVbFhKckp6LzBqZ0pjanVXaXZ5ejE5NWdXbzNWZWRqRWs5U0owS0NCc01IcGdrVExLZWcwSkt6dll4Q0k0MDR5SVVQTXVPMEwwRXc3VnBRNVFXS09EMWRvT08yYUV1M0tOQitmMkdYSUpuRk5IOTlwSWpWUWhYdmcyWG85YklFY1U2MVFyN0ZveWNLWXc4Y2oyTHRuOGRvYjBsNHJUOGpVYVppam1FSXY0VE5jOG5PMFlJUHQxK1I0R3Qyb2lSVlB0RC9KNi8wNi90MnVwOFpiQ3NKSzZZT2pMaDBqdnovMzd3aGMrdEMvVUFvR25sU3FPa25ZMjRRZXpFRS92clVadUNKdkY2a0UwQXN2N0gxTmI2TkljYnBsaTY5UERpb2tKaWFrUW5WUkYvYTkrUy85cnViNklzckRST2tOa2xkZmZneWQwQlRjZERCTkVOSENNZS8yWWprTkNMN3czZXR0d1c4OGFLZkEzZmpCSTlJNGpxQ1RHNXNreVp6OEwzWHZJQVZ1Yk5WQ0ZTaGJCdzJ5ZzY2eHgwL0JCY2dQNXRlaWJqVlUwZTdHZEZwNnIwWFBtbGd5NGRJZ3FxYytzZ0JHaGk1dDVkT2NsS3RXZVhVM2dVTjNna05uTlBNdEN3L0NhdWkxYWRCQ0lTcE9FTGx6ZWVid0phOTRTWTV1OHRpa01pRGZtQ21tTkRZdm5EZVhHU1ZqOGhaalFIOVpPYXI3Qmh4TU1NUnFDN3crVDJNOFdHWGlVdlpPZCtDemYzWDdud2hQRDVabFNtOU84aGJXMTFsaU5MRklHRENMMzR5MHMyN0FURGV2U1RIVU9pMkRGbkVGdTFsOGdZSklaaWU5Y1hHN3VGQUtxUWdzTXZnbUVOR1ZycXVFbERoZFA2Wi8wZWRUeGNmdHhCOUdMd1c5NVhJVGxEZ3J4L2U4ZWVHUjFCN1dYNm1OeThOOVJNOEJDcGh1VjhOM1M3OE4rUWhnZmVIZU10QklnMmNVOC96M3J2TjNYcHFMSHR6aHkxN2tSMndkZ0k1UHorenY3SUtsUXh4MTBwb0YwSDBrOXRMakFBSUl6NURJN210RGJ0eW1HbGRCRndNKzVqOGhGb3lOa2ZMQlFmUXNGM3BxU0E1MnZMWlY1SG11VDFYV09aQ0E5V2I5MThHWk0rNkJCRUdwUFNsdDRXclU5ZXd3b2lEelBsTmJ1aC9uVXBYYzB3bXVhVzRnb3JSMndpNFg5WmlYRTlmZWx1MU5LNXR0eDVvcTBBNlk2bzhYRkxjTGo4NHEwSGZsL3VTV3lkSDgrR2xVTDZ6TkZsRzZtNUoxbS9zN01VL1BGVXU0Rkd5WmU1djFYK3JzYXlrcVZLazNPdC9NYVhmSU1PUTZmTStpdXQxWmdlMmY0V1FxOXB3WFN0djdhTW40a2xDNFZuSkhKcXhzTzVuNS83UEphYmNTOHI3MTNhakkxRlZDcjhwc21VSTdrZ213TWVJTU81enZYMzVvM0Z2VHZFaHF3MzlxaFU1ZmtXRGllWlFjSWFPcGdvdlZKWGhXeW12emVyRGFWcjNyRGh6YUxKT3JFaFEraFR1cmR0dEtDK2VTUUNJWC9VZ1E5NHZFUks3NlYvNkRxWmh0QWxEMVVmNExaalZ4RTNSU1cwa05ZNUduT3dyZzl4UHRsbWdraTRucWVtTHQ0L0RHaTEzZHRTTi9YQTF5V1ZMVU9BS3RTbXVDVFRKUThCTStSd0JscC9nQW5MNDE5VzcrWlFIMGYxR1Y0WTlJVmlDNVFNZVlSZkRlYnpoODc5ZEZURUkvcVV0ZEFMR3pNWng2dXZnVnVIaVlIS1ZlNXltYXZibVVSbWx3ZlM3RVo2WmthVFE1MTk2bTdvQkg5aUNUSEZrT2wyeTNVZ0U2bzhmRUpvVHJ5VnY1WHBjc0FrNTQ0N2hWelZXTWdiWnpmVURKdlBHK3J5U29EbW5QcmhmRzJYYlFaR2hIQmFYOG1XUGs0Z1dydHg0bFpJdFpRWmlyZnVKcnB5SnpzVTJXcjdLSFlUNkhmZEhMYStPb3NMYXZUVmRsVmc4emF4bk5IUjlrOTZhOUNmSlJUR21rdU9uOHpzdGFabFZhR1lTcHk0M1Q0US9YZ3UybE44T2U3UGE1OGg3Z09WRXlDUGdqejREakU3RHBUTUl0ZWxpQjVvQldFRWxvS01uSmNVSFB0SWxBRW9kbGdacitCd3Y3VDlYdnpNUUc2OENzMUlOYy9Wa2YyckJsSVRYbFpvamlxMm5LMmdXTFZFNDh4UEdMRDNrV2tEbStCUFdOcWIrbFpKZmJFaHpYbXFtSDE0c2dFVzNJQUV0TVpNVXp1ZHhxdjYzUFhGcUdhU0pSbzZ6N1YxTmYvRFpoYUg2L0ZUVmVwbE5TUTBMK1FBWktEakJmeWluME04RUpjd0kyVXNhem9FT1Bmd0Q3UU12NDcwM3NPMzlQVk90N1RDSFZhZ2JBRXRPb0FmV0J4MzhBZkNsaWpzTmtiT1N6L203SGJSRE1kMzM1K3V0bnZBVDBhZTd4L1lWTStYM1BnNkQxT3VPQ3JkTUVOSHJ6QWVmNFJiNUtsSTN1b2dTQ3hqSU9yV3Zia2tRNkwvMG5wUzNwL1RibkVDU1FSOVdhQWZhWHpRbUlvUHVQVTZFYnNOeGtpekxHb3NRdGtIdCtiV1AvaE9nZHM3bG5XMVZiMkhpdEUzSFVMcjV1QUFONFdZWm1JaG5zcFlTa3dVNzdhS1p5VDcrZlpxNmMrRG1ibFNoa0l0anBQS1JTb2UxMFRrSk4zQU1CVmY0SERqNTNmczhPdExldmdvYmo1cTVqL2xtRlVmWVZLa01RWWx2SC9qcjJrRytQYnU5RThTdFdsZlY0Si9uYnFTWWNqMnNXeGxRSm55a3hSak5Ic3FvVXlvc0hqZmNvc0oxVGUwVDV4SDk5bEtxVHBReEsyQmxHZ1dnU2IwZE5tZzR1VG8vMjFHLytpNjBxSURSeUUrTmpQS1cxR3lFZmROTzBobDVPY1Y3Y3JJWEcvQXJ5UFBnTm52dDl1MVJycVFFWGkveEs5NHI3UHFsT2svZGtmOWVYeDJyczE2elJUbnE4MnJ1RzBqTnRzMisvRk5HTHN1U2ZKNDBsdXVpV01rQjFjOENCRnFLT3NmNW1Xa3NaaUpjTGdzRCtZRmtCQnU0cjlLR2FScU1sbHhZdHZoZS9mdlM2NnZwN1paTGN3eklPc2dDSHl6aU5kQmQ2VVNYUUU3bmxKL0lHZGtHRVpxYWpMa0tmVVpFZFRQTmdBUW0zTmMwbGt3bXhOV0NrbGE2MlFNYTVjRzZWRkZvdVlPS1hmSE1zOGVuZzBLVXVFS3p1RVpSWnpNQ0FqQkZGdHVyalJvQmU1SnUrdUhDVnJtTERYTTRPMlo1MGpqK3p3RGo3R2JJQ054aSt1V1RMc3lrL3Ztdy9qUmdhWlpOM1h6clE0UHdkZDJPNFlvbkROaDloWS9kQi9rZlBZZUpsU1JKUUNvbHYzWnREOTE1amIvZjBSc1F4bTdqWjE2RFBMZ2VRNnNUUEowbjJhaG1IeXdES3lHTFB1ZFlXSzBvem9jaXl1NksrZFg4cDcyUGMvZWpHaklHOG9Sc3FoOExVVWwzZjN4YWgvcDVCcmVoRDd2Q0VTWTRtU0NPTmNWWlBiQWRCa2o2Qmo3S3ExZlNrbUJoRmdqQ3pRMVRTdFdFTm5RL2xiS2I3WmJPeUg0SEV3WlN3MHlIZ1hLWTk1dS9XTHp1VVlDand2WkF4WFJCNEUwcEo1dFptL0c0c1paL001cFRQbjdvcm1zZEpFMWVvWmVCL1E2YzJMMGFpbTBUcUFaY1YwQWNvYkpjbkNjamZvTjY5Zm5XNkJzQUR3VVZ0UjBJc1FCVjlJV2VyM2pVZ3RINE9XNithZkhtWUFlVjVyTko3NE1QYUxNT1lCRWJHZ2VwUXd4S0Q0WG5JcWN3eUpHNDlySHQzLzR3V0doZFpKRERqKzV4RHMydktNWnE2Q3dlbm1GMlhDVWRzTTlqanNmbGxUdjIrby8wMmh0NGhlY1MyM1pXUHdJdm42YXdDRTc5aHN0TDJSNU9pTXlCVmZvN0RtWHFWcHY2ZWg4NTRCZFlVZWxJNENWTmlDd2NhdlF3WTFFOTN5OTNJdDZsZmxrOW4yNlJNaEtIZHNPU3BhaUJ2SS8vYXpLUVZUMlJHL1F4Z0xUNy9QYUsrY3RIdWoreXRlR2h1TUdUL2ErWDFKSmx3SUx2R3A1ZEVIMWhIS3NWcXF1OVhuQTVPYTZ6dEljNEp2Ty9iTDgvMERhUjJqVTBUSWsweFpGMjdvZWIyYUIyeFR4REVLaEtONUswM1NvcWNaVE92SzRYNmRDazVBNWRDREN1OHdEUjVwUjRpSlVYelBsMlFtdnFSdHZZeWVXZWFtMmdJTGY2VWpJbHp3cFN5N0JTT3BYYnpZRlZhTnhscGVENWw0cy9jWEJSRThVTi9sZWtFODZFTFRZclJvaEJnTzBaSldiWENzc3plZ0lQUVgyckZ3ZVBvRVZ4MHZyM3FYZmhBQmY3dlRrUmpGOWlJOUpFU0NpbEtTWVAzSHhXR3ZoOUk4c0FLRzF6QVgwc3AydGRjekl0T0RmdXp1aFN0S2g4bm14M0dTOUJzUy9XekZnMWxRY0NPcTJ6SkFnQTdHanFENVphVlBxNkh0Tm5pR3B5VlhlYU9CdTI0SDNFRksrZ2dMUEFUUWt3S1YrQTRJSHhIbGk1ZzBmeVJhNUNzS1d3U2J2MHF5K2xuL2hVMmgxYWJtcUJBVHFoVnlCNUEzOGVkQ21UZlJtckYrOVBSSUtueXovcFJVWTc1QTJqWVBSandyemQzTVJxMHNURGtOOHFSUVRxc3huVjhuL1doY3BOY1BMOFU3cnlvejMyTEh4bGJnRHVERHhNdHFOckd6UmU4ZUZ1NkN3eENwcE9sL3p2ci85VlhyT2JYcVJTbGFVeUFiQm5UQklmcGF2TGhOUjNuR1NIcGUvbVNDTHR6bWZEL2dFMjZPTTZ4MldDT2JBblR0TkZZR2VVTnFJNVZqYjBNZzlPT0NYRkxRK0NSY1pkNkR1enpnQnhROXhZL2cxZmFNNzlUVHlSWVFrZkVjSDdEemVUYXc0bDRIWnhkanMzRXNYZ0dvdS95d1FGQnRHOTliTlJ4OW5rTTQyVTQ0eWU4anFMZC9Ma2RoTzV6RzNmOW51U2ZUOUUvcnZuUHJmQytsT0dZQXdldmd6OEh0OXNmZXl1SDFGZkNibXI5THduLzhCVkNwbkFUMkpTVkV4T3RMenQrc09vOGg2S0R3MkNRUTdiM25iS1VZZDhlTXZqRzdZRkd1aFppTmFPVzBYcDZnaWt6L20vZHB0UXhsZGlFa05mdHJiaHo5MGxUQW5Ta3lXcVk5VkIwcC9NcmpUVFEvWmZYYlgvTjlYV3RUNk44T1hOdGVUcU9HOFVoWWVURHRHanM4MGFWVzBWY1pYZ3NjNFp5YzgwT1pQYldKaEUrbnJqcDZvVDNsTzliSXBKSlBsRG9FVVhpOVZKbitteUlVRVczQ0NZWERKNVNRQldwTHU1REVMc0ZlNXYwNStmUkpodmlwYnRteDVwQ3FNZW8vVFNwcng4a1lucWcxbGZ6M0tqTmc1ZzNSamVuRDA0dzVNQkp5WkVEU3pML001dUZ0Z2VhYzB5UlhZQVFJWkxRM2s2ak9NajdGdXEzM0ZnWUZLSVg0aVVaUTcrWHZJSktWSFlKN3UzTTF5bzJXcnhUK3RCZGMwd0JlbTZMTlZqdHlmUkpFOVZwd3ZNZktWZDdodlRCVzdIb3FDL2pXSTdQY3o5eEJIaDA0VEl1WWtWWFQzQzlHRVpmYnh4dW5NODNPTHJIZFdtMnpObW5KNjZQMD0iLCJtYWMiOiI5YTNjYmQ4MjZjMzQwMWRhNTc4MmExMDI2ZDZhMjU4OGZmMDc0MTk2MjNlMDhjOTliM2QyNThjNTE2ZjkyOTkzIiwidGFnIjoiIn0=\"'),
(39,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'oauth_public_key','\"eyJpdiI6InBCRjVUek1tRUhCQ1p5NkVsVEFyWEE9PSIsInZhbHVlIjoieHh1djB6Zit1QzdkWmoxdzdwTUJTNWRKdXNrVUwxcWwwb1FZVTh1eDNWaUdESWZ1RmdjRXNnWDB1YjJRb09yT0xOOWhDdmZEYTQ5czlPSXNsMG5IemRDWmxrSEIzbXU5VE5xUGtXV1hXQWpRd0dieUtBRmNKTGZPNXh6aW1JZkh5OFZhSWFSYUZxVG1FSk5qRHVHcjFzOGlDU1NBbExBcDkxYVBtM0JWZklqZDFGZS9pUmpKZjhURDZnY0JxMlFzWEg3TlFjeVprK0ZuZDNtWVJWdUltbHcyMlF1elhEdTkvdTQ2QnlCSVRGSkdxTzVLRjdzcTMrckNpY29kWWpVV21ZR3dTTTQ3L1d3YjNOd1BFNHZxaVZIZUROcFZKd0I2M0RMV1duT3dDN2cyRk5jbVFTeDFzeHlTaGNQd3NLWmpRaEFKU2dsTzhvVTNUSG5Fc1Z3a3UzdFdySnlMdFJKTEZxQjRtR2dwRGY4TVMxTitwMFpOaVFLWXJUeVlUUHllZmtnRlNEQXJaN0NxN2d0V05mWXAwN2YyUGJteHQ4Mm5Jd0FDQVVSbFRPc0c2akhQS1JyRFR0ZXVCZHQyVmpLYkNmMkpnN3c5TlBId0lNTStZVk9BaVRjaWJwdC9xcVJNWDl6MzlhZkNxUHkwcVpibUFOL2RDVkM4VHZ3RUZCUlEvTWhDdDNqNm1SUEJKSUFvc2FEZkI0bWVmUXE0NTVsVi9kRnNmN0RpMGtlblE0dDlrVnh2STZBWVFSUlJFNllXaEJOaEI3VFAyVGpBKy9jSERGS1ByQnBycHpQbEZlblFmN1FDVkdERW5iK0JuVTVUWjFrMEs3UkhIc3E2VXpRbjFzMDYvVjNLSmhGLzRTSjE2ZWVEOEVGQ0QrLzlwOTlqMzRMMm5EbUU5U3B2amtwVHZRUndybFF3ZzZsV08rQmVyS0o5czhFL014TlhhcmdRZTYwVHd1eVgyci9tQlpkbnc0bTZLYW41TmJRc3duZW5JKzJsWmVOS1BhTkovY3BBSGgvb3V5azVnTzVLWms2VjVsS3lOb2s0QkJEYnVQeEtQeFJuMDBvd2pNenZibkhHSjJvSjlDbXBHN3RDU0ltYzczWVc3anJFR3B3QWdpUWlibWtPTFJHdE9oNzNrMFRwZUl1ejZqNHByTG5xRk5acFpGaW1ZNjJzTFM1eTNwbWs4c21Hd2h6ZXdtcWRDVlczdWg0dzViSWlBRVZUVmhsQXFvWEsvNDZBNzdJK1crVWJtWGlFa1VzYkxIVUlzWlN1bUN3ODVIc0NVclVIUEJER2NKdE5idG4wZklXMWx1UlpJUXVMMHdSS2JkLzJ2cWRiWjJ0TlUzMUZsWWhTQlNCelJTYmw2QnJ1K1MxRlJMaFk2cGxWcDNhbXpvaDc5OVRydVppUkNlQUZraEdBeXpmTHRxSU94b3VCK05UdndCcGRhV2VndDM1NGI5Q29sWU8zY1g2NzFBPT0iLCJtYWMiOiI5YTBlYThmYzY0OTAwMjNiMjc3MDU2MmI1ZmVmNzAxZTI1NjZhYTMxYmVlZmVmYjIzNTZjY2Q5YzU2ZDk3YjZmIiwidGFnIjoiIn0=\"'),
(40,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'utc','false'),
(41,'2026-03-05 22:12:27','2026-03-05 22:12:27',NULL,'allow_webhooks','false'),
(42,'2026-03-05 22:12:27','2026-03-05 22:12:27',NULL,'ff3_build_time','1772606967'),
(43,'2026-03-05 22:12:28','2026-03-05 22:12:28',NULL,'installation_id','\"04764dfb-0151-4749-b336-670fb589c79b\"'),
(44,'2026-03-05 22:13:01','2026-03-05 22:13:01',NULL,'is_demo_site','false'),
(45,'2026-03-05 22:13:01','2026-03-05 22:13:01',NULL,'single_user_mode','true'),
(46,'2026-03-05 22:30:27','2026-03-05 22:30:27',NULL,'notification_user_new_reg','true'),
(47,'2026-03-05 22:30:27','2026-03-05 22:30:27',NULL,'notification_admin_new_reg','true'),
(48,'2026-03-05 22:30:27','2026-03-05 22:30:27',NULL,'slack_webhook_url','\"\"'),
(49,'2026-03-05 22:30:27','2026-03-05 22:30:27',NULL,'pushover_app_token','\"\"'),
(50,'2026-03-05 22:30:27','2026-03-05 22:30:27',NULL,'pushover_user_token','\"\"'),
(51,'2026-03-05 23:02:05','2026-03-05 23:02:05',NULL,'permission_update_check','-1'),
(52,'2026-03-05 23:02:05','2026-03-05 23:02:05',NULL,'last_update_warning','1772748125'),
(53,'2026-03-05 23:09:32','2026-03-05 23:09:32',NULL,'valid_url_protocols','\"http,https,ftp,ftps,mailto\"'),
(54,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,'enable_batch_processing','false');
/*!40000 ALTER TABLE `configuration` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `currency_exchange_rates`
--

DROP TABLE IF EXISTS `currency_exchange_rates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `currency_exchange_rates` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `from_currency_id` int(10) unsigned NOT NULL,
  `to_currency_id` int(10) unsigned NOT NULL,
  `date` date NOT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `rate` decimal(32,12) NOT NULL,
  `user_rate` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `currency_exchange_rates_user_id_foreign` (`user_id`),
  KEY `currency_exchange_rates_from_currency_id_foreign` (`from_currency_id`),
  KEY `currency_exchange_rates_to_currency_id_foreign` (`to_currency_id`),
  KEY `cer_to_ugi` (`user_group_id`),
  CONSTRAINT `cer_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `currency_exchange_rates_from_currency_id_foreign` FOREIGN KEY (`from_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `currency_exchange_rates_to_currency_id_foreign` FOREIGN KEY (`to_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `currency_exchange_rates_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `currency_exchange_rates`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `currency_exchange_rates` WRITE;
/*!40000 ALTER TABLE `currency_exchange_rates` DISABLE KEYS */;
INSERT INTO `currency_exchange_rates` VALUES
(1,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,1,'2025-04-15',NULL,1.000000000000,NULL),
(2,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,2,'2025-04-15',NULL,410.797980000000,NULL),
(3,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,3,'2025-04-15',NULL,0.860032610000,NULL),
(4,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,4,'2025-04-15',NULL,46.867455000000,NULL),
(5,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,5,'2025-04-15',NULL,4.280209800000,NULL),
(6,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,6,'2025-04-15',NULL,43.180054000000,NULL),
(7,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,7,'2025-04-15',NULL,7.459100000000,NULL),
(8,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,11,'2025-04-15',NULL,7.464833600000,NULL),
(9,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,12,'2025-04-15',NULL,1.134904400000,NULL),
(10,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,13,'2025-04-15',NULL,6.645851800000,NULL),
(11,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,14,'2025-04-15',NULL,1.575105000000,NULL),
(12,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,15,'2025-04-15',NULL,22.805278000000,NULL),
(13,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,21,'2025-04-15',NULL,19070.382000000000,NULL),
(14,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,22,'2025-04-15',NULL,1.787202000000,NULL),
(15,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,23,'2025-04-15',NULL,1.919107800000,NULL),
(16,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,24,'2025-04-15',NULL,57.874172000000,NULL),
(17,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,25,'2025-04-15',NULL,10.549438000000,NULL),
(18,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,26,'2025-04-15',NULL,21.444356000000,NULL),
(19,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,27,'2025-04-15',NULL,162.471950000000,NULL),
(20,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,28,'2025-04-15',NULL,8.284997700000,NULL),
(21,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,30,'2025-04-15',NULL,93.344230000000,NULL),
(22,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,31,'2025-04-15',NULL,97.572815000000,NULL),
(23,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,32,'2025-04-15',NULL,4.180178600000,NULL),
(24,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,33,'2025-04-15',NULL,0.926831260000,NULL),
(25,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,34,'2025-04-15',NULL,7.534500000000,NULL),
(26,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,8,'2025-04-15',NULL,145.105320000000,NULL),
(27,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,9,'2025-04-15',NULL,11.980824000000,NULL),
(28,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,10,'2025-04-15',NULL,11.088090000000,NULL),
(29,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,35,'2025-04-15',NULL,8.804632200000,NULL),
(30,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,1,36,'2025-04-15',NULL,25.092213000000,NULL);
/*!40000 ALTER TABLE `currency_exchange_rates` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `failed_jobs`
--

DROP TABLE IF EXISTS `failed_jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `failed_jobs` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `uuid` varchar(191) NOT NULL,
  `connection` text NOT NULL,
  `queue` text NOT NULL,
  `payload` longtext NOT NULL,
  `exception` longtext NOT NULL,
  `failed_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `failed_jobs_uuid_unique` (`uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `failed_jobs`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `failed_jobs` WRITE;
/*!40000 ALTER TABLE `failed_jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `failed_jobs` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `group_journals`
--

DROP TABLE IF EXISTS `group_journals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `group_journals` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `transaction_group_id` int(10) unsigned NOT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_in_group` (`transaction_group_id`,`transaction_journal_id`),
  KEY `group_journals_transaction_journal_id_foreign` (`transaction_journal_id`),
  CONSTRAINT `group_journals_transaction_group_id_foreign` FOREIGN KEY (`transaction_group_id`) REFERENCES `transaction_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `group_journals_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `group_journals`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `group_journals` WRITE;
/*!40000 ALTER TABLE `group_journals` DISABLE KEYS */;
/*!40000 ALTER TABLE `group_journals` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `group_memberships`
--

DROP TABLE IF EXISTS `group_memberships`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `group_memberships` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned NOT NULL,
  `user_role_id` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `group_memberships_user_id_user_group_id_user_role_id_unique` (`user_id`,`user_group_id`,`user_role_id`),
  KEY `group_memberships_user_group_id_foreign` (`user_group_id`),
  KEY `group_memberships_user_role_id_foreign` (`user_role_id`),
  CONSTRAINT `group_memberships_user_group_id_foreign` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `group_memberships_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `group_memberships_user_role_id_foreign` FOREIGN KEY (`user_role_id`) REFERENCES `user_roles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `group_memberships`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `group_memberships` WRITE;
/*!40000 ALTER TABLE `group_memberships` DISABLE KEYS */;
INSERT INTO `group_memberships` VALUES
(1,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,1,1,21);
/*!40000 ALTER TABLE `group_memberships` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `invited_users`
--

DROP TABLE IF EXISTS `invited_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `invited_users` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `email` varchar(255) NOT NULL,
  `invite_code` varchar(64) NOT NULL,
  `expires` datetime NOT NULL,
  `expires_tz` varchar(50) DEFAULT NULL,
  `redeemed` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `invited_users_user_id_foreign` (`user_id`),
  CONSTRAINT `invited_users_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `invited_users`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `invited_users` WRITE;
/*!40000 ALTER TABLE `invited_users` DISABLE KEYS */;
/*!40000 ALTER TABLE `invited_users` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `jobs` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `queue` varchar(191) NOT NULL,
  `payload` longtext NOT NULL,
  `attempts` tinyint(3) unsigned NOT NULL,
  `reserved_at` int(10) unsigned DEFAULT NULL,
  `available_at` int(10) unsigned NOT NULL,
  `created_at` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `jobs_queue_index` (`queue`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `jobs`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `jobs` WRITE;
/*!40000 ALTER TABLE `jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `jobs` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `journal_links`
--

DROP TABLE IF EXISTS `journal_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `journal_links` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `link_type_id` int(10) unsigned NOT NULL,
  `source_id` int(10) unsigned NOT NULL,
  `destination_id` int(10) unsigned NOT NULL,
  `comment` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `journal_links_link_type_id_source_id_destination_id_unique` (`link_type_id`,`source_id`,`destination_id`),
  KEY `journal_links_source_id_foreign` (`source_id`),
  KEY `journal_links_destination_id_foreign` (`destination_id`),
  CONSTRAINT `journal_links_destination_id_foreign` FOREIGN KEY (`destination_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE,
  CONSTRAINT `journal_links_link_type_id_foreign` FOREIGN KEY (`link_type_id`) REFERENCES `link_types` (`id`) ON DELETE CASCADE,
  CONSTRAINT `journal_links_source_id_foreign` FOREIGN KEY (`source_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `journal_links`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `journal_links` WRITE;
/*!40000 ALTER TABLE `journal_links` DISABLE KEYS */;
/*!40000 ALTER TABLE `journal_links` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `journal_meta`
--

DROP TABLE IF EXISTS `journal_meta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `journal_meta` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  `name` varchar(255) NOT NULL,
  `data` text NOT NULL,
  `hash` varchar(64) NOT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `journal_meta_transaction_journal_id_index` (`transaction_journal_id`),
  KEY `journal_meta_data_index` (`data`(768)),
  KEY `journal_meta_name_index` (`name`),
  CONSTRAINT `journal_meta_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `journal_meta`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `journal_meta` WRITE;
/*!40000 ALTER TABLE `journal_meta` DISABLE KEYS */;
INSERT INTO `journal_meta` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',1,'import_hash_v2','\"dcf2e87d82ad4eefccc39f91879e5933836a02b4edcf98704729ea2245fd00ea\"','b242f71b054c863d2b67608baf7443c1116f3ce2d1eab30143fb0473828584bd',NULL),
(2,'2026-03-05 23:23:30','2026-03-05 23:23:30',2,'import_hash_v2','\"5757f0c0b69b9d76e697c28efbbde40cc1513ee106ca40f213174c18889dc6f9\"','96bf821babed2b956df55fb6d6962249392b9a3b1b3b4f9bd40153da694d3696',NULL),
(3,'2026-03-05 23:23:30','2026-03-05 23:23:30',3,'import_hash_v2','\"dc72dbc4381ceefd2eb865f0518713031e98598f48217a506379787f0da71a8c\"','632ebd9bed77cc2f06dba5078263fc2457d5226d2f5abb2e1597a9f48cdaf0f7',NULL),
(4,'2026-03-05 23:23:31','2026-03-05 23:23:31',4,'import_hash_v2','\"b0e17eca3ffdf800d1a200d7ef0fb72dcbd8e9a0e432792200766d3ffb6588fd\"','3a6f860bc756f6b976c26b75b6b054522f4aff831980912fab6dff9ceff3fdf3',NULL),
(5,'2026-03-05 23:23:31','2026-03-05 23:23:31',5,'import_hash_v2','\"024601cf219a6fbe941676814d85aefc03dfd2367bae6570c3426c8ce2731278\"','7ff0b53875d4d9ab3b16228d18e43abb511fa16bed3bbd54f2aa8619c3574422',NULL),
(6,'2026-03-05 23:23:31','2026-03-05 23:23:31',6,'import_hash_v2','\"6aa38141534083c01182001cbe4f989f1474ce74c7d1354ac786528a89e173ba\"','848a8e1ed38b3652718f283390c9140acc7bed1502771b6016f7d6b842d18f72',NULL),
(7,'2026-03-05 23:23:31','2026-03-05 23:23:31',7,'import_hash_v2','\"08abbd147facb802c042cc05aab634c1b42d46e919ae14d964cf3201fe2b6838\"','2cd847e6f79dcef28d9ecce43ce25cbeea08a17125ca6c27e0d9c45f6164a116',NULL),
(8,'2026-03-05 23:23:31','2026-03-05 23:23:31',8,'import_hash_v2','\"5121f0983ed0b1138d7f978e4d62c2e9af19eb67cfd795941dfd23493dd47a35\"','0c19f1f2552d3c43a62337f46c762e1226e9db8139b9d9ca72f9e6efadda70e7',NULL),
(9,'2026-03-05 23:23:31','2026-03-05 23:23:31',9,'import_hash_v2','\"8e149cc8a7b25a8b462a0383fd9ff78f9228cd81b344b6d9f1d73c08df00874d\"','0cba0f296196b2eab7e0350a581eec578c7319cca666d8226bf21c71bd5987ee',NULL),
(10,'2026-03-05 23:30:40','2026-03-05 23:30:40',10,'import_hash_v2','\"d4f54f62bd47c0d6a96f9ff626a070770ec5d32a2b2d4328fdb9a328e2fd3240\"','7c92da2ef19e9f521d7d5c415dad4246cd9b0b59c671eef0239cbd6cf637e0cc',NULL),
(11,'2026-03-05 23:30:40','2026-03-05 23:30:40',11,'import_hash_v2','\"071b28c50002fe4147e7b7fff8e302c69899334b80b0baaa528806fbd4a21ee3\"','bd1f368347dc7fe730724f5626e95320f57c52f7760a1c0e639d1b31f7041163',NULL),
(12,'2026-03-05 23:30:40','2026-03-05 23:30:40',12,'import_hash_v2','\"e81326c4153c8ae6a5016826b7d715ac05a91e3a7aa667125e073ac3d9bdf1b8\"','882088f50a1d2c147259aed8092081181e14b7046590867398e31ff158010500',NULL),
(13,'2026-03-05 23:30:40','2026-03-05 23:30:40',13,'import_hash_v2','\"bf2af176bf58741449f3d9496ff72eefe781e03bad81f0fc39d85b72bece4966\"','eb4597a43e33a43769d4ae9de5933fc54660669a8a4460b607c5e10d975aaf03',NULL),
(14,'2026-03-05 23:30:40','2026-03-05 23:30:40',14,'import_hash_v2','\"0014fbce57658008f470ed3b3485c1caf3d82abde71bbaaaf6acb91dc11b8bca\"','0485ccbed126d74df9d1ee4a9802a25a641223bc4b04f3fe957e985df94073ff',NULL),
(15,'2026-03-05 23:30:40','2026-03-05 23:30:40',15,'import_hash_v2','\"b30bf48224875b78028cb4daf4753a4865315bb908112323c686af1f6468ea38\"','1ac9af7ed1696f98677be632e714231a9d822e779a981c4281ac0f379ecadce8',NULL),
(16,'2026-03-05 23:30:41','2026-03-05 23:30:41',16,'import_hash_v2','\"4703a7654031070e167351dca10fe2866df07d00eb38a5b87c94a4ae2f2b415c\"','04009ea6d299ac9e705af3fe544c8f1df8c14e259f83477f4c234448fae528d3',NULL),
(17,'2026-03-05 23:30:41','2026-03-05 23:30:41',17,'import_hash_v2','\"86dd4b7b23cca4692e6c6abb47f72e5b8ff40a0f005d3b277165b43927213060\"','d27a13b3434b4df775b12fb703e0489268d546c5b60a52fe5d3bfc8bd9b6891d',NULL),
(18,'2026-03-05 23:30:41','2026-03-05 23:30:41',18,'import_hash_v2','\"cb98cd97ec0c919abaa7c16d1194155cd7da3dcf42ec5b6800e00ff1cf8c0638\"','2b8a7995a43e0d56b08a6327b10a9252d2eca3b90e21eafe2b47dc1f22ef73b3',NULL),
(19,'2026-03-05 23:30:41','2026-03-05 23:30:41',19,'import_hash_v2','\"9b7b8dea6d785f1899451c03b10ef25b480752b5f558034f1d747bbf390eb720\"','9bb8f7e53af3a4be0b94adb4ae0705b2259936aec94f60a5dc1edafc353676a7',NULL),
(20,'2026-03-05 23:30:41','2026-03-05 23:30:41',20,'import_hash_v2','\"b6da52c1ef4c06da284e583da576887e61355d8972292b9efc178b03e429f975\"','19f51c0b15a7c11bfdcbe32008d782f027c43e4a1af249db40773c4f9d8fc5f1',NULL),
(21,'2026-03-05 23:30:41','2026-03-05 23:30:41',21,'import_hash_v2','\"83c58c5607dfadbafdb901c6e1531db464cd0a1a81cd44dd109a53f7f8ba4f22\"','cbaf7e4618d0985053e1e83d8887ddc9793e11551757cba78dc19b07652c18d4',NULL),
(22,'2026-03-05 23:30:41','2026-03-05 23:30:41',22,'import_hash_v2','\"6006414b6ca440aea10bc69b2aea8b598a29e6930dcbd1adc928cede7bf6562a\"','f27a2b488685b421b25b8ac3f1eca6e4b37e4237384b0efbdd73a694c419de85',NULL),
(23,'2026-03-05 23:30:41','2026-03-05 23:30:41',23,'import_hash_v2','\"c31d4911b8a07b022e7c1ff3b0a46a085c73cc3f63b8284ef6a1ae2e570af6e1\"','cdc77f641fd359b0c92a072f69107a9ad53e424aa8c90c1889972c478ad82a47',NULL);
/*!40000 ALTER TABLE `journal_meta` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `link_types`
--

DROP TABLE IF EXISTS `link_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `link_types` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `name` varchar(191) NOT NULL,
  `outward` varchar(191) NOT NULL,
  `inward` varchar(191) NOT NULL,
  `editable` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `link_types_name_outward_inward_unique` (`name`,`outward`,`inward`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `link_types`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `link_types` WRITE;
/*!40000 ALTER TABLE `link_types` DISABLE KEYS */;
INSERT INTO `link_types` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Related','relates to','relates to',0),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Refund','(partially) refunds','is (partially) refunded by',0),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Paid','(partially) pays for','is (partially) paid for by',0),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Reimbursement','(partially) reimburses','is (partially) reimbursed by',0);
/*!40000 ALTER TABLE `link_types` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `locations`
--

DROP TABLE IF EXISTS `locations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `locations` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `locatable_id` int(10) unsigned NOT NULL,
  `locatable_type` varchar(255) NOT NULL,
  `latitude` decimal(12,8) DEFAULT NULL,
  `longitude` decimal(12,8) DEFAULT NULL,
  `zoom_level` smallint(5) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `locations`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `locations` WRITE;
/*!40000 ALTER TABLE `locations` DISABLE KEYS */;
/*!40000 ALTER TABLE `locations` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `migrations`
--

DROP TABLE IF EXISTS `migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `migrations` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `migration` varchar(191) NOT NULL,
  `batch` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=61 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `migrations`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `migrations` WRITE;
/*!40000 ALTER TABLE `migrations` DISABLE KEYS */;
INSERT INTO `migrations` VALUES
(1,'2016_06_16_000000_create_support_tables',1),
(2,'2016_06_16_000001_create_users_table',1),
(3,'2016_06_16_000002_create_main_tables',1),
(4,'2016_08_25_091522_changes_for_3101',1),
(5,'2016_09_12_121359_fix_nullables',1),
(6,'2016_10_09_150037_expand_transactions_table',1),
(7,'2016_10_22_075804_changes_for_v410',1),
(8,'2016_11_24_210552_changes_for_v420',1),
(9,'2016_12_22_150431_changes_for_v430',1),
(10,'2016_12_28_203205_changes_for_v431',1),
(11,'2017_04_13_163623_changes_for_v440',1),
(12,'2017_06_02_105232_changes_for_v450',1),
(13,'2017_08_20_062014_changes_for_v470',1),
(14,'2017_11_04_170844_changes_for_v470a',1),
(15,'2018_01_01_000001_create_oauth_auth_codes_table',1),
(16,'2018_01_01_000002_create_oauth_access_tokens_table',1),
(17,'2018_01_01_000003_create_oauth_refresh_tokens_table',1),
(18,'2018_01_01_000004_create_oauth_clients_table',1),
(19,'2018_01_01_000005_create_oauth_personal_access_clients_table',1),
(20,'2018_03_19_141348_changes_for_v472',1),
(21,'2018_04_07_210913_changes_for_v473',1),
(22,'2018_04_29_174524_changes_for_v474',1),
(23,'2018_06_08_200526_changes_for_v475',1),
(24,'2018_09_05_195147_changes_for_v477',1),
(25,'2018_11_06_172532_changes_for_v479',1),
(26,'2019_01_28_193833_changes_for_v4710',1),
(27,'2019_02_05_055516_changes_for_v4711',1),
(28,'2019_02_11_170529_changes_for_v4712',1),
(29,'2019_03_11_223700_fix_ldap_configuration',1),
(30,'2019_03_22_183214_changes_for_v480',1),
(31,'2019_11_30_000000_create_2fa_token_table',1),
(32,'2019_12_28_191351_make_locations_table',1),
(33,'2020_03_13_201950_changes_for_v520',1),
(34,'2020_06_07_063612_changes_for_v530',1),
(35,'2020_06_30_202620_changes_for_v530a',1),
(36,'2020_07_24_162820_changes_for_v540',1),
(37,'2020_11_12_070604_changes_for_v550',1),
(38,'2021_03_12_061213_changes_for_v550b2',1),
(39,'2021_05_09_064644_add_ldap_columns_to_users_table',1),
(40,'2021_05_13_053836_extend_currency_info',1),
(41,'2021_07_05_193044_drop_tele_table',1),
(42,'2021_08_28_073733_user_groups',1),
(43,'2021_12_27_000001_create_local_personal_access_tokens_table',1),
(44,'2022_08_21_104626_add_user_groups',1),
(45,'2022_09_18_123911_create_notifications_table',1),
(46,'2022_10_01_074908_invited_users',1),
(47,'2022_10_01_210238_audit_log_entries',1),
(48,'2023_08_11_192521_upgrade_og_table',1),
(49,'2023_10_21_113213_add_currency_pivot_tables',1),
(50,'2024_03_03_174645_add_indices',1),
(51,'2024_04_01_174351_expand_preferences_table',1),
(52,'2024_05_12_060551_create_account_balance_table',1),
(53,'2024_07_28_145631_add_running_balance',1),
(54,'2024_11_05_062108_add_date_tz_columns',1),
(55,'2024_11_30_075826_multi_piggy',1),
(56,'2024_12_19_061003_add_native_amount_column',1),
(57,'2025_07_10_065736_rename_tag_mode',1),
(58,'2025_08_19_180459_create_webhook_details_tables',1),
(59,'2025_09_25_175248_create_period_statistics',1),
(60,'2026_01_28_201901_migrations_01_2026',1);
/*!40000 ALTER TABLE `migrations` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `notes`
--

DROP TABLE IF EXISTS `notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `notes` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `noteable_id` int(10) unsigned NOT NULL,
  `noteable_type` varchar(191) NOT NULL,
  `title` varchar(191) DEFAULT NULL,
  `text` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notes`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `notes` WRITE;
/*!40000 ALTER TABLE `notes` DISABLE KEYS */;
/*!40000 ALTER TABLE `notes` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `notifications` (
  `id` char(36) NOT NULL,
  `type` varchar(191) NOT NULL,
  `notifiable_type` varchar(191) NOT NULL,
  `notifiable_id` bigint(20) unsigned NOT NULL,
  `data` text NOT NULL,
  `read_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `notifications_notifiable_type_notifiable_id_index` (`notifiable_type`,`notifiable_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
/*!40000 ALTER TABLE `notifications` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `oauth_access_tokens`
--

DROP TABLE IF EXISTS `oauth_access_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_access_tokens` (
  `id` varchar(100) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `client_id` int(11) NOT NULL,
  `name` varchar(191) DEFAULT NULL,
  `scopes` text DEFAULT NULL,
  `revoked` tinyint(1) NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `oauth_access_tokens_user_id_index` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_access_tokens`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `oauth_access_tokens` WRITE;
/*!40000 ALTER TABLE `oauth_access_tokens` DISABLE KEYS */;
INSERT INTO `oauth_access_tokens` VALUES
('2f1aa8ce1a863daeddf6717626fdc6cd491fffe34d6d0242945868aa4dc27dd90f65cba67ffea19f',1,2,NULL,'[]',0,'2026-03-05 22:41:14','2026-03-05 22:41:14','2026-03-19 22:41:14'),
('521f8ef5d5e44b7ae556b2f5858cbbf1b9e2a1089a4409780ba12bb3558fda6c791a3aa3a833bbdc',1,2,NULL,'[]',0,'2026-03-05 23:02:26','2026-03-05 23:02:26','2026-03-19 23:02:26'),
('8b9316b8cd0fa8a55b25d9bc54cf429b34b5f3f38176113676325c0c2b60b8219dfeb9d5dd1e6d4e',1,2,NULL,'[]',0,'2026-03-05 23:31:26','2026-03-05 23:31:26','2026-03-19 23:31:26'),
('ba900d09ca0b7c3cb1a08ceb98b4db75af836a9019bcf4d0b6c878ae1c81a38ab29f49d3f028d4a8',1,2,NULL,'[]',0,'2026-03-05 23:17:02','2026-03-05 23:17:02','2026-03-19 23:17:02'),
('e38e527dff4d5a5e5ae97bdcf50d9b968fb496463951687b0b57caa76d10b57c0aded8415418bb62',1,2,NULL,'[]',0,'2026-03-05 23:29:36','2026-03-05 23:29:36','2026-03-19 23:29:36');
/*!40000 ALTER TABLE `oauth_access_tokens` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `oauth_auth_codes`
--

DROP TABLE IF EXISTS `oauth_auth_codes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_auth_codes` (
  `id` varchar(100) NOT NULL,
  `user_id` int(11) NOT NULL,
  `client_id` int(11) NOT NULL,
  `scopes` text DEFAULT NULL,
  `revoked` tinyint(1) NOT NULL,
  `expires_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_auth_codes`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `oauth_auth_codes` WRITE;
/*!40000 ALTER TABLE `oauth_auth_codes` DISABLE KEYS */;
INSERT INTO `oauth_auth_codes` VALUES
('1fba287c73d801a898cf6e2261c99d8121631335cb954276357b2ee4ecc78b3b16c2eed6ed8bc22e',1,2,'[]',1,'2026-03-05 23:39:36'),
('3e09a8250ccf9239e09e6f94497e684e95d2de39a980a14ab5c266b81b79340e7a9a62262b1f4e60',1,2,'[]',1,'2026-03-05 23:41:25'),
('640c1d9145dc3669384ceda6efc0882a8e5a73d7b392d2d358b3cf731a51cd63be3ad5b01e822192',1,2,'[]',1,'2026-03-05 22:51:13'),
('96448ab1d210d50ec7006588423c9dea5e55019507c8593dce9bbc3351879c72c104c4df56788790',1,2,'[]',1,'2026-03-05 23:27:01'),
('dc2aed51fc9b03b2306ba43b75ae0696a5829a8e6ec904ddcf9600d12ac680d0a7264e7dc96d0309',1,2,'[]',1,'2026-03-05 23:12:26');
/*!40000 ALTER TABLE `oauth_auth_codes` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `oauth_clients`
--

DROP TABLE IF EXISTS `oauth_clients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_clients` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `name` varchar(191) NOT NULL,
  `secret` varchar(100) DEFAULT NULL,
  `redirect` text NOT NULL,
  `personal_access_client` tinyint(1) NOT NULL,
  `password_client` tinyint(1) NOT NULL,
  `revoked` tinyint(1) NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `provider` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `oauth_clients_user_id_index` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_clients`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `oauth_clients` WRITE;
/*!40000 ALTER TABLE `oauth_clients` DISABLE KEYS */;
INSERT INTO `oauth_clients` VALUES
(1,NULL,'FireflyIII Personal Access Grant Client','upy2Xvzi81JYYTTXesIwhGoQF4s2LIWLsXQyw3T1','http://localhost',1,0,0,'2026-03-05 22:39:01','2026-03-05 22:39:01',NULL),
(2,1,'importer',NULL,'http://localhost:81/callback',0,0,0,'2026-03-05 22:40:44','2026-03-05 22:40:44',NULL);
/*!40000 ALTER TABLE `oauth_clients` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `oauth_personal_access_clients`
--

DROP TABLE IF EXISTS `oauth_personal_access_clients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_personal_access_clients` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `client_id` int(11) NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `oauth_personal_access_clients_client_id_index` (`client_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_personal_access_clients`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `oauth_personal_access_clients` WRITE;
/*!40000 ALTER TABLE `oauth_personal_access_clients` DISABLE KEYS */;
INSERT INTO `oauth_personal_access_clients` VALUES
(1,1,'2026-03-05 22:39:01','2026-03-05 22:39:01');
/*!40000 ALTER TABLE `oauth_personal_access_clients` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `oauth_refresh_tokens`
--

DROP TABLE IF EXISTS `oauth_refresh_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `oauth_refresh_tokens` (
  `id` varchar(100) NOT NULL,
  `access_token_id` varchar(100) NOT NULL,
  `revoked` tinyint(1) NOT NULL,
  `expires_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `oauth_refresh_tokens_access_token_id_index` (`access_token_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `oauth_refresh_tokens`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `oauth_refresh_tokens` WRITE;
/*!40000 ALTER TABLE `oauth_refresh_tokens` DISABLE KEYS */;
INSERT INTO `oauth_refresh_tokens` VALUES
('1c3ff91a8ce251709c9038cf769dab8013c1386c72bbcb294904067552bc15f4f2180c422de35f46','8b9316b8cd0fa8a55b25d9bc54cf429b34b5f3f38176113676325c0c2b60b8219dfeb9d5dd1e6d4e',0,'2027-03-05 23:31:26'),
('7b75b2d5229646e27a0b47628f7a5ede5d8b6ea4e71390a8484a3ce956f5b9e9321143260e82f790','ba900d09ca0b7c3cb1a08ceb98b4db75af836a9019bcf4d0b6c878ae1c81a38ab29f49d3f028d4a8',0,'2027-03-05 23:17:02'),
('b26712cd5f6b7077d8b08a17c7977c27f5b1663a242727d49ff04861638937d8053c1e1f457569d3','e38e527dff4d5a5e5ae97bdcf50d9b968fb496463951687b0b57caa76d10b57c0aded8415418bb62',0,'2027-03-05 23:29:36'),
('e6e3884222a54e62e20488fc84fc67e7315b5a22070c1de9451047321caf6e3762ddc423d733d567','521f8ef5d5e44b7ae556b2f5858cbbf1b9e2a1089a4409780ba12bb3558fda6c791a3aa3a833bbdc',0,'2027-03-05 23:02:26'),
('ee4b4021e4f780c5495fb2e29347ba42de5ea2d04db691b909bd998e4b1eaff1738248641e2bd191','2f1aa8ce1a863daeddf6717626fdc6cd491fffe34d6d0242945868aa4dc27dd90f65cba67ffea19f',0,'2027-03-05 22:41:14');
/*!40000 ALTER TABLE `oauth_refresh_tokens` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `object_groupables`
--

DROP TABLE IF EXISTS `object_groupables`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `object_groupables` (
  `object_group_id` int(11) NOT NULL,
  `object_groupable_id` int(10) unsigned NOT NULL,
  `object_groupable_type` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `object_groupables`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `object_groupables` WRITE;
/*!40000 ALTER TABLE `object_groupables` DISABLE KEYS */;
/*!40000 ALTER TABLE `object_groupables` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `object_groups`
--

DROP TABLE IF EXISTS `object_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `object_groups` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `order` mediumint(8) unsigned NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `object_groups_user_id_foreign` (`user_id`),
  KEY `object_groups_to_ugi` (`user_group_id`),
  CONSTRAINT `object_groups_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `object_groups_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `object_groups`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `object_groups` WRITE;
/*!40000 ALTER TABLE `object_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `object_groups` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `password_resets`
--

DROP TABLE IF EXISTS `password_resets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_resets` (
  `email` varchar(191) NOT NULL,
  `token` varchar(191) NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  KEY `password_resets_email_index` (`email`),
  KEY `password_resets_token_index` (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `password_resets`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `password_resets` WRITE;
/*!40000 ALTER TABLE `password_resets` DISABLE KEYS */;
/*!40000 ALTER TABLE `password_resets` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `period_statistics`
--

DROP TABLE IF EXISTS `period_statistics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `period_statistics` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `user_group_id` bigint(20) unsigned NOT NULL,
  `primary_statable_id` int(10) unsigned DEFAULT NULL,
  `primary_statable_type` varchar(255) DEFAULT NULL,
  `secondary_statable_id` int(10) unsigned DEFAULT NULL,
  `secondary_statable_type` varchar(255) DEFAULT NULL,
  `tertiary_statable_id` int(10) unsigned DEFAULT NULL,
  `tertiary_statable_type` varchar(255) DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `start` datetime DEFAULT NULL,
  `start_tz` varchar(50) DEFAULT NULL,
  `end` datetime DEFAULT NULL,
  `end_tz` varchar(50) DEFAULT NULL,
  `type` varchar(255) NOT NULL,
  `count` int(10) unsigned NOT NULL DEFAULT 0,
  `amount` decimal(32,12) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `period_statistics_transaction_currency_id_foreign` (`transaction_currency_id`),
  KEY `period_statistics_user_group_id_foreign` (`user_group_id`),
  CONSTRAINT `period_statistics_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `period_statistics_user_group_id_foreign` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `period_statistics`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `period_statistics` WRITE;
/*!40000 ALTER TABLE `period_statistics` DISABLE KEYS */;
INSERT INTO `period_statistics` VALUES
(1,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2026-03-01 00:00:00','Europe/Amsterdam','2026-03-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(2,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2026-02-01 00:00:00','Europe/Amsterdam','2026-02-28 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(3,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2026-01-01 00:00:00','Europe/Amsterdam','2026-01-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(4,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-12-01 00:00:00','Europe/Amsterdam','2025-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(5,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-11-01 00:00:00','Europe/Amsterdam','2025-11-30 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(6,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-10-01 00:00:00','Europe/Amsterdam','2025-10-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(7,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-09-01 00:00:00','Europe/Amsterdam','2025-09-30 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(8,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-08-01 00:00:00','Europe/Amsterdam','2025-08-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(9,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-07-01 00:00:00','Europe/Amsterdam','2025-07-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(10,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-06-01 00:00:00','Europe/Amsterdam','2025-06-30 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(11,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-05-01 00:00:00','Europe/Amsterdam','2025-05-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(12,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-04-01 00:00:00','Europe/Amsterdam','2025-04-30 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(13,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-03-01 00:00:00','Europe/Amsterdam','2025-03-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(14,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2025-01-01 00:00:00','Europe/Amsterdam','2025-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(15,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2024-01-01 00:00:00','Europe/Amsterdam','2024-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(16,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2023-01-01 00:00:00','Europe/Amsterdam','2023-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(17,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2022-01-01 00:00:00','Europe/Amsterdam','2022-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(18,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2021-01-01 00:00:00','Europe/Amsterdam','2021-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000),
(19,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,NULL,NULL,NULL,NULL,NULL,1,'2020-01-01 00:00:00','Europe/Amsterdam','2020-12-31 23:59:59','Europe/Amsterdam','all_withdrawal',0,0.000000000000);
/*!40000 ALTER TABLE `period_statistics` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `permission_role`
--

DROP TABLE IF EXISTS `permission_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `permission_role` (
  `permission_id` int(10) unsigned NOT NULL,
  `role_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`permission_id`,`role_id`),
  KEY `permission_role_role_id_foreign` (`role_id`),
  CONSTRAINT `permission_role_permission_id_foreign` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `permission_role_role_id_foreign` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permission_role`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `permission_role` WRITE;
/*!40000 ALTER TABLE `permission_role` DISABLE KEYS */;
/*!40000 ALTER TABLE `permission_role` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `name` varchar(191) NOT NULL,
  `display_name` varchar(191) DEFAULT NULL,
  `description` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `permissions_name_unique` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permissions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `permissions` WRITE;
/*!40000 ALTER TABLE `permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `permissions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `personal_access_tokens`
--

DROP TABLE IF EXISTS `personal_access_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `personal_access_tokens` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `tokenable_type` varchar(191) NOT NULL,
  `tokenable_id` bigint(20) unsigned NOT NULL,
  `name` varchar(191) NOT NULL,
  `token` varchar(64) NOT NULL,
  `abilities` text DEFAULT NULL,
  `last_used_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `personal_access_tokens_token_unique` (`token`),
  KEY `personal_access_tokens_tokenable_type_tokenable_id_index` (`tokenable_type`,`tokenable_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `personal_access_tokens`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `personal_access_tokens` WRITE;
/*!40000 ALTER TABLE `personal_access_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `personal_access_tokens` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `piggy_bank_events`
--

DROP TABLE IF EXISTS `piggy_bank_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `piggy_bank_events` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `piggy_bank_id` int(10) unsigned NOT NULL,
  `transaction_journal_id` int(10) unsigned DEFAULT NULL,
  `date` date NOT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `amount` decimal(32,12) NOT NULL,
  `native_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `piggy_bank_events_piggy_bank_id_foreign` (`piggy_bank_id`),
  KEY `piggy_bank_events_transaction_journal_id_foreign` (`transaction_journal_id`),
  CONSTRAINT `piggy_bank_events_piggy_bank_id_foreign` FOREIGN KEY (`piggy_bank_id`) REFERENCES `piggy_banks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `piggy_bank_events_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `piggy_bank_events`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `piggy_bank_events` WRITE;
/*!40000 ALTER TABLE `piggy_bank_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `piggy_bank_events` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `piggy_bank_repetitions`
--

DROP TABLE IF EXISTS `piggy_bank_repetitions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `piggy_bank_repetitions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `piggy_bank_id` int(10) unsigned NOT NULL,
  `start_date` date DEFAULT NULL,
  `start_date_tz` varchar(50) DEFAULT NULL,
  `target_date` date DEFAULT NULL,
  `target_date_tz` varchar(50) DEFAULT NULL,
  `current_amount` decimal(32,12) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `piggy_bank_repetitions_piggy_bank_id_foreign` (`piggy_bank_id`),
  CONSTRAINT `piggy_bank_repetitions_piggy_bank_id_foreign` FOREIGN KEY (`piggy_bank_id`) REFERENCES `piggy_banks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `piggy_bank_repetitions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `piggy_bank_repetitions` WRITE;
/*!40000 ALTER TABLE `piggy_bank_repetitions` DISABLE KEYS */;
/*!40000 ALTER TABLE `piggy_bank_repetitions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `piggy_banks`
--

DROP TABLE IF EXISTS `piggy_banks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `piggy_banks` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `account_id` int(10) unsigned DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned DEFAULT NULL,
  `name` varchar(1024) NOT NULL,
  `target_amount` decimal(32,12) NOT NULL,
  `start_date` date DEFAULT NULL,
  `start_date_tz` varchar(50) DEFAULT NULL,
  `target_date` date DEFAULT NULL,
  `target_date_tz` varchar(50) DEFAULT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 0,
  `encrypted` tinyint(1) NOT NULL DEFAULT 1,
  `native_target_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `unique_currency` (`transaction_currency_id`),
  KEY `piggy_banks_account_id_foreign` (`account_id`),
  CONSTRAINT `piggy_banks_account_id_foreign` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE SET NULL,
  CONSTRAINT `unique_currency` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `piggy_banks`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `piggy_banks` WRITE;
/*!40000 ALTER TABLE `piggy_banks` DISABLE KEYS */;
/*!40000 ALTER TABLE `piggy_banks` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `preferences`
--

DROP TABLE IF EXISTS `preferences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `preferences` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `name` varchar(1024) NOT NULL,
  `data` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `preferences_user_id_foreign` (`user_id`),
  KEY `preferences_to_ugi` (`user_group_id`),
  CONSTRAINT `preferences_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `preferences_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `preferences`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `preferences` WRITE;
/*!40000 ALTER TABLE `preferences` DISABLE KEYS */;
INSERT INTO `preferences` VALUES
(1,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'viewRange','\"1M\"'),
(2,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'language','\"en_US\"'),
(3,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'locale','\"equal\"'),
(4,'2026-03-05 22:30:28','2026-03-05 23:30:41',1,NULL,'lastActivity','\"0.93103500 1772749841\"'),
(5,'2026-03-05 22:30:28','2026-03-05 22:37:40',1,NULL,'anonymous','false'),
(6,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'list-length','10'),
(7,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'darkMode','\"browser\"'),
(8,'2026-03-05 22:30:28','2026-03-05 22:30:28',1,NULL,'convert_to_primary','false'),
(9,'2026-03-05 22:30:37','2026-03-05 22:30:37',1,NULL,'listPageSize','50'),
(10,'2026-03-05 22:31:41','2026-03-05 22:31:41',1,NULL,'shown_demo_piggy-banks_index','false'),
(11,'2026-03-05 22:31:45','2026-03-05 23:02:06',1,NULL,'shown_demo_index','true'),
(12,'2026-03-05 22:39:01','2026-03-05 22:39:01',1,NULL,'mfa_recovery','[]'),
(13,'2026-03-05 22:39:01','2026-03-05 22:39:01',1,NULL,'access_token','\"c4d8e29d8caf1f0b572e744ae7f37cef\"'),
(14,'2026-03-05 22:41:14','2026-03-05 22:41:14',1,NULL,'slack_webhook_url','\"\"'),
(15,'2026-03-05 22:41:14','2026-03-05 22:41:14',1,NULL,'pushover_app_token','\"\"'),
(16,'2026-03-05 22:41:14','2026-03-05 22:41:14',1,NULL,'pushover_user_token','\"\"'),
(17,'2026-03-05 23:02:04','2026-03-05 23:02:04',1,NULL,'frontpageAccounts','[1,2,3]'),
(18,'2026-03-05 23:02:04','2026-03-05 23:02:04',1,NULL,'transaction_journal_optional_fields','{\"interest_date\":true,\"book_date\":false,\"process_date\":false,\"due_date\":false,\"payment_date\":false,\"invoice_date\":false,\"internal_reference\":false,\"notes\":true,\"attachments\":true}'),
(19,'2026-03-05 23:24:50','2026-03-05 23:27:44',1,NULL,'shown_demo_budgets_index','true'),
(20,'2026-03-05 23:29:50','2026-03-05 23:29:50',1,NULL,'customFiscalYear','false');
/*!40000 ALTER TABLE `preferences` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `recurrences`
--

DROP TABLE IF EXISTS `recurrences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `recurrences` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `transaction_type_id` int(10) unsigned NOT NULL,
  `title` varchar(1024) NOT NULL,
  `description` text NOT NULL,
  `first_date` date NOT NULL,
  `first_date_tz` varchar(50) DEFAULT NULL,
  `repeat_until` date DEFAULT NULL,
  `repeat_until_tz` varchar(50) DEFAULT NULL,
  `latest_date` date DEFAULT NULL,
  `latest_date_tz` varchar(50) DEFAULT NULL,
  `repetitions` smallint(5) unsigned NOT NULL,
  `apply_rules` tinyint(1) NOT NULL DEFAULT 1,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `recurrences_user_id_foreign` (`user_id`),
  KEY `recurrences_transaction_type_id_foreign` (`transaction_type_id`),
  KEY `recurrences_to_ugi` (`user_group_id`),
  CONSTRAINT `recurrences_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `recurrences_transaction_type_id_foreign` FOREIGN KEY (`transaction_type_id`) REFERENCES `transaction_types` (`id`) ON DELETE CASCADE,
  CONSTRAINT `recurrences_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `recurrences`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `recurrences` WRITE;
/*!40000 ALTER TABLE `recurrences` DISABLE KEYS */;
/*!40000 ALTER TABLE `recurrences` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `recurrences_meta`
--

DROP TABLE IF EXISTS `recurrences_meta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `recurrences_meta` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `recurrence_id` int(10) unsigned NOT NULL,
  `name` varchar(50) NOT NULL,
  `value` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `recurrences_meta_recurrence_id_foreign` (`recurrence_id`),
  CONSTRAINT `recurrences_meta_recurrence_id_foreign` FOREIGN KEY (`recurrence_id`) REFERENCES `recurrences` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `recurrences_meta`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `recurrences_meta` WRITE;
/*!40000 ALTER TABLE `recurrences_meta` DISABLE KEYS */;
/*!40000 ALTER TABLE `recurrences_meta` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `recurrences_repetitions`
--

DROP TABLE IF EXISTS `recurrences_repetitions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `recurrences_repetitions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `recurrence_id` int(10) unsigned NOT NULL,
  `repetition_type` varchar(50) NOT NULL,
  `repetition_moment` varchar(50) NOT NULL,
  `repetition_skip` smallint(5) unsigned NOT NULL,
  `weekend` smallint(5) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `recurrences_repetitions_recurrence_id_foreign` (`recurrence_id`),
  CONSTRAINT `recurrences_repetitions_recurrence_id_foreign` FOREIGN KEY (`recurrence_id`) REFERENCES `recurrences` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `recurrences_repetitions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `recurrences_repetitions` WRITE;
/*!40000 ALTER TABLE `recurrences_repetitions` DISABLE KEYS */;
/*!40000 ALTER TABLE `recurrences_repetitions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `recurrences_transactions`
--

DROP TABLE IF EXISTS `recurrences_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `recurrences_transactions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `recurrence_id` int(10) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `transaction_type_id` int(10) unsigned DEFAULT NULL,
  `foreign_currency_id` int(10) unsigned DEFAULT NULL,
  `source_id` int(10) unsigned NOT NULL,
  `destination_id` int(10) unsigned NOT NULL,
  `amount` decimal(32,12) NOT NULL,
  `foreign_amount` decimal(32,12) DEFAULT NULL,
  `description` varchar(1024) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `recurrences_transactions_recurrence_id_foreign` (`recurrence_id`),
  KEY `recurrences_transactions_transaction_currency_id_foreign` (`transaction_currency_id`),
  KEY `recurrences_transactions_foreign_currency_id_foreign` (`foreign_currency_id`),
  KEY `recurrences_transactions_source_id_foreign` (`source_id`),
  KEY `recurrences_transactions_destination_id_foreign` (`destination_id`),
  KEY `type_foreign` (`transaction_type_id`),
  CONSTRAINT `recurrences_transactions_destination_id_foreign` FOREIGN KEY (`destination_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `recurrences_transactions_foreign_currency_id_foreign` FOREIGN KEY (`foreign_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE SET NULL,
  CONSTRAINT `recurrences_transactions_recurrence_id_foreign` FOREIGN KEY (`recurrence_id`) REFERENCES `recurrences` (`id`) ON DELETE CASCADE,
  CONSTRAINT `recurrences_transactions_source_id_foreign` FOREIGN KEY (`source_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `recurrences_transactions_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `type_foreign` FOREIGN KEY (`transaction_type_id`) REFERENCES `transaction_types` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `recurrences_transactions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `recurrences_transactions` WRITE;
/*!40000 ALTER TABLE `recurrences_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `recurrences_transactions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `role_user`
--

DROP TABLE IF EXISTS `role_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_user` (
  `user_id` int(10) unsigned NOT NULL,
  `role_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_user_role_id_foreign` (`role_id`),
  CONSTRAINT `role_user_role_id_foreign` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `role_user_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_user`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `role_user` WRITE;
/*!40000 ALTER TABLE `role_user` DISABLE KEYS */;
INSERT INTO `role_user` VALUES
(1,1);
/*!40000 ALTER TABLE `role_user` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `name` varchar(191) NOT NULL,
  `display_name` varchar(191) DEFAULT NULL,
  `description` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `roles_name_unique` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26','owner','Site Owner','User runs this instance of FF3'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26','demo','Demo User','User is a demo user');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `rt_meta`
--

DROP TABLE IF EXISTS `rt_meta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `rt_meta` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `rt_id` int(10) unsigned NOT NULL,
  `name` varchar(50) NOT NULL,
  `value` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `rt_meta_rt_id_foreign` (`rt_id`),
  CONSTRAINT `rt_meta_rt_id_foreign` FOREIGN KEY (`rt_id`) REFERENCES `recurrences_transactions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rt_meta`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `rt_meta` WRITE;
/*!40000 ALTER TABLE `rt_meta` DISABLE KEYS */;
/*!40000 ALTER TABLE `rt_meta` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `rule_actions`
--

DROP TABLE IF EXISTS `rule_actions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `rule_actions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `rule_id` int(10) unsigned NOT NULL,
  `action_type` varchar(50) NOT NULL,
  `action_value` varchar(255) NOT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `stop_processing` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `rule_actions_rule_id_foreign` (`rule_id`),
  CONSTRAINT `rule_actions_rule_id_foreign` FOREIGN KEY (`rule_id`) REFERENCES `rules` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rule_actions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `rule_actions` WRITE;
/*!40000 ALTER TABLE `rule_actions` DISABLE KEYS */;
/*!40000 ALTER TABLE `rule_actions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `rule_groups`
--

DROP TABLE IF EXISTS `rule_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `rule_groups` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `stop_processing` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `rule_groups_user_id_foreign` (`user_id`),
  KEY `rule_groups_to_ugi` (`user_group_id`),
  CONSTRAINT `rule_groups_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `rule_groups_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rule_groups`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `rule_groups` WRITE;
/*!40000 ALTER TABLE `rule_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `rule_groups` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `rule_triggers`
--

DROP TABLE IF EXISTS `rule_triggers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `rule_triggers` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `rule_id` int(10) unsigned NOT NULL,
  `trigger_type` varchar(50) NOT NULL,
  `trigger_value` varchar(255) NOT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `stop_processing` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `rule_triggers_rule_id_foreign` (`rule_id`),
  CONSTRAINT `rule_triggers_rule_id_foreign` FOREIGN KEY (`rule_id`) REFERENCES `rules` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rule_triggers`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `rule_triggers` WRITE;
/*!40000 ALTER TABLE `rule_triggers` DISABLE KEYS */;
/*!40000 ALTER TABLE `rule_triggers` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `rules`
--

DROP TABLE IF EXISTS `rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `rules` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `rule_group_id` int(10) unsigned NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `stop_processing` tinyint(1) NOT NULL DEFAULT 0,
  `strict` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `rules_user_id_foreign` (`user_id`),
  KEY `rules_rule_group_id_foreign` (`rule_group_id`),
  KEY `rules_to_ugi` (`user_group_id`),
  CONSTRAINT `rules_rule_group_id_foreign` FOREIGN KEY (`rule_group_id`) REFERENCES `rule_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `rules_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `rules_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rules`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `rules` WRITE;
/*!40000 ALTER TABLE `rules` DISABLE KEYS */;
/*!40000 ALTER TABLE `rules` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `sessions`
--

DROP TABLE IF EXISTS `sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `sessions` (
  `id` varchar(191) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` text DEFAULT NULL,
  `payload` text NOT NULL,
  `last_activity` int(11) NOT NULL,
  UNIQUE KEY `sessions_id_unique` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sessions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `sessions` WRITE;
/*!40000 ALTER TABLE `sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `sessions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `tag_transaction_journal`
--

DROP TABLE IF EXISTS `tag_transaction_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tag_transaction_journal` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `tag_id` int(10) unsigned NOT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `tag_transaction_journal_tag_id_transaction_journal_id_unique` (`tag_id`,`transaction_journal_id`),
  KEY `idx_ttj_journal_tag` (`transaction_journal_id`,`tag_id`),
  CONSTRAINT `tag_transaction_journal_tag_id_foreign` FOREIGN KEY (`tag_id`) REFERENCES `tags` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tag_transaction_journal_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tag_transaction_journal`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `tag_transaction_journal` WRITE;
/*!40000 ALTER TABLE `tag_transaction_journal` DISABLE KEYS */;
INSERT INTO `tag_transaction_journal` VALUES
(1,1,1),
(2,1,2),
(3,1,3),
(4,1,4),
(5,1,5),
(6,1,6),
(7,1,7),
(8,1,8),
(9,1,9),
(10,2,10),
(11,2,11),
(12,2,12),
(13,2,13),
(14,2,14),
(15,2,15),
(16,2,16),
(17,2,17),
(18,2,18),
(19,2,19),
(20,2,20),
(21,2,21),
(22,2,22),
(23,2,23);
/*!40000 ALTER TABLE `tag_transaction_journal` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `tags`
--

DROP TABLE IF EXISTS `tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `tags` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `tag` varchar(1024) NOT NULL,
  `tag_mode` varchar(1024) NOT NULL,
  `date` date DEFAULT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `latitude` decimal(12,8) DEFAULT NULL,
  `longitude` decimal(12,8) DEFAULT NULL,
  `zoomLevel` smallint(5) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `tags_user_id_foreign` (`user_id`),
  KEY `tags_to_ugi` (`user_group_id`),
  CONSTRAINT `tags_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `tags_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tags`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `tags` WRITE;
/*!40000 ALTER TABLE `tags` DISABLE KEYS */;
INSERT INTO `tags` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,'Data Import on 2026-03-05 @ 23:23','nothing','2026-03-05',NULL,'',NULL,NULL,NULL),
(2,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,'Data Import on 2026-03-05 @ 23:30','nothing','2026-03-05',NULL,'',NULL,NULL,NULL);
/*!40000 ALTER TABLE `tags` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_currencies`
--

DROP TABLE IF EXISTS `transaction_currencies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_currencies` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT 0,
  `code` varchar(51) NOT NULL,
  `name` varchar(255) NOT NULL,
  `symbol` varchar(51) NOT NULL,
  `decimal_places` smallint(5) unsigned NOT NULL DEFAULT 2,
  PRIMARY KEY (`id`),
  UNIQUE KEY `transaction_currencies_code_unique` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_currencies`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_currencies` WRITE;
/*!40000 ALTER TABLE `transaction_currencies` DISABLE KEYS */;
INSERT INTO `transaction_currencies` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 23:02:04',NULL,1,'EUR','Euro','€',2),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'HUF','Hungarian forint','Ft',2),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'GBP','British Pound','£',2),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'UAH','Ukrainian hryvnia','₴',2),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'PLN','Polish złoty','zł',2),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'TRY','Turkish lira','₺',2),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'DKK','Dansk krone','kr.',2),
(8,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'ISK','Íslensk króna','kr.',2),
(9,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'NOK','Norsk krone','kr.',2),
(10,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'SEK','Svensk krona','kr.',2),
(11,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'RON','Romanian leu','lei',2),
(12,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'USD','US Dollar','$',2),
(13,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'BRL','Brazilian real','R$',2),
(14,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'CAD','Canadian dollar','C$',2),
(15,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'MXN','Mexican peso','MX$',2),
(16,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'PEN','Peruvian Sol','S/',2),
(17,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'ARS','Argentinian Peso','$',2),
(18,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'COP','Colombian Peso','$',2),
(19,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'CLP','Chilean Peso','$',2),
(20,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'UYU','Uruguayan Peso','$',2),
(21,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'IDR','Indonesian rupiah','Rp',2),
(22,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'AUD','Australian dollar','A$',2),
(23,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'NZD','New Zealand dollar','NZ$',2),
(24,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'EGP','Egyptian pound','E£',2),
(25,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'MAD','Moroccan dirham','DH',2),
(26,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'ZAR','South African rand','R',2),
(27,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'JPY','Japanese yen','¥',0),
(28,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'CNY','Chinese yuan','¥',2),
(29,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'KRW','South Korean won','₩',2),
(30,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'RUB','Russian ruble','₽',2),
(31,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'INR','Indian rupee','₹',2),
(32,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'ILS','Israeli new shekel','₪',2),
(33,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'CHF','Swiss franc','CHF',2),
(34,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'HRK','Croatian kuna','kn',2),
(35,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'HKD','Hong Kong dollar','HK$',2),
(36,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'CZK','Czech koruna','Kč',2),
(37,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'KZT','Kazakhstani tenge','₸',2),
(38,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'SAR','Saudi Riyal','SAR',2),
(39,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'RSD','Serbian Dinar','RSD',2),
(40,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'TWD','New Taiwan Dollar','NT$',0),
(41,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,0,'THB','Thai baht','฿',2);
/*!40000 ALTER TABLE `transaction_currencies` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_currency_user`
--

DROP TABLE IF EXISTS `transaction_currency_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_currency_user` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `user_default` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_combo` (`user_id`,`transaction_currency_id`),
  KEY `transaction_currency_user_transaction_currency_id_foreign` (`transaction_currency_id`),
  CONSTRAINT `transaction_currency_user_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transaction_currency_user_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_currency_user`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_currency_user` WRITE;
/*!40000 ALTER TABLE `transaction_currency_user` DISABLE KEYS */;
/*!40000 ALTER TABLE `transaction_currency_user` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_currency_user_group`
--

DROP TABLE IF EXISTS `transaction_currency_user_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_currency_user_group` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `user_group_id` bigint(20) unsigned NOT NULL,
  `transaction_currency_id` int(10) unsigned NOT NULL,
  `group_default` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_combo_ug` (`user_group_id`,`transaction_currency_id`),
  KEY `transaction_currency_user_group_transaction_currency_id_foreign` (`transaction_currency_id`),
  CONSTRAINT `transaction_currency_user_group_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transaction_currency_user_group_user_group_id_foreign` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_currency_user_group`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_currency_user_group` WRITE;
/*!40000 ALTER TABLE `transaction_currency_user_group` DISABLE KEYS */;
INSERT INTO `transaction_currency_user_group` VALUES
(2,'2026-03-05 23:02:04','2026-03-05 23:02:04',1,1,1);
/*!40000 ALTER TABLE `transaction_currency_user_group` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_groups`
--

DROP TABLE IF EXISTS `transaction_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_groups` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `title` varchar(1024) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `transaction_groups_user_id_index` (`user_id`),
  KEY `transaction_groups_user_group_id_index` (`user_group_id`),
  CONSTRAINT `transaction_groups_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `transaction_groups_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_groups`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_groups` WRITE;
/*!40000 ALTER TABLE `transaction_groups` DISABLE KEYS */;
INSERT INTO `transaction_groups` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,NULL),
(2,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,NULL),
(3,'2026-03-05 23:23:30','2026-03-05 23:23:31',NULL,1,1,NULL),
(4,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(5,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(6,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(7,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(8,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(9,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,NULL),
(10,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,NULL),
(11,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,NULL),
(12,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,NULL),
(13,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,NULL),
(14,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,NULL),
(15,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,1,1,NULL),
(16,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(17,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(18,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(19,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(20,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(21,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(22,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL),
(23,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,NULL);
/*!40000 ALTER TABLE `transaction_groups` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_journals`
--

DROP TABLE IF EXISTS `transaction_journals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_journals` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `transaction_type_id` int(10) unsigned NOT NULL,
  `transaction_group_id` int(10) unsigned DEFAULT NULL,
  `bill_id` int(10) unsigned DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned DEFAULT NULL,
  `description` varchar(1024) NOT NULL,
  `date` datetime NOT NULL,
  `date_tz` varchar(50) DEFAULT NULL,
  `interest_date` date DEFAULT NULL,
  `book_date` date DEFAULT NULL,
  `process_date` date DEFAULT NULL,
  `order` int(10) unsigned NOT NULL DEFAULT 0,
  `tag_count` int(10) unsigned NOT NULL,
  `encrypted` tinyint(1) NOT NULL DEFAULT 1,
  `completed` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `transaction_journals_user_id_index` (`user_id`),
  KEY `transaction_journals_user_group_id_index` (`user_group_id`),
  KEY `transaction_journals_date_index` (`date`),
  KEY `transaction_journals_transaction_group_id_index` (`transaction_group_id`),
  KEY `transaction_journals_transaction_type_id_index` (`transaction_type_id`),
  KEY `transaction_journals_transaction_currency_id_index` (`transaction_currency_id`),
  KEY `transaction_journals_bill_id_index` (`bill_id`),
  KEY `idx_tj_deleted` (`deleted_at`),
  CONSTRAINT `transaction_journals_bill_id_foreign` FOREIGN KEY (`bill_id`) REFERENCES `bills` (`id`) ON DELETE SET NULL,
  CONSTRAINT `transaction_journals_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `transaction_journals_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transaction_journals_transaction_group_id_foreign` FOREIGN KEY (`transaction_group_id`) REFERENCES `transaction_groups` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transaction_journals_transaction_type_id_foreign` FOREIGN KEY (`transaction_type_id`) REFERENCES `transaction_types` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transaction_journals_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_journals`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_journals` WRITE;
/*!40000 ALTER TABLE `transaction_journals` DISABLE KEYS */;
INSERT INTO `transaction_journals` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,1,1,NULL,1,'Money back from internet subscription','2016-10-10 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(2,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,1,1,1,2,NULL,1,'Discount from new service subscription','2016-11-11 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(3,'2026-03-05 23:23:30','2026-03-05 23:23:31',NULL,1,1,1,3,NULL,1,'Tax break for 2016','2016-12-12 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(4,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,4,NULL,1,'Bought some weird Chinese stuff','2016-02-12 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(5,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,5,NULL,1,'Bought some books','2016-02-24 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(6,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,6,NULL,1,'Apple brand batteries for Magic Mouse','2016-04-20 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(7,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,7,NULL,1,'Expensive pet food','2016-05-09 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(8,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,8,NULL,1,'Drinks with friends','2016-07-14 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(9,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,1,1,7,9,NULL,1,'Paid back third part','2016-09-10 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(10,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,10,NULL,1,'Bread','2016-03-11 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(11,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,11,NULL,1,'Car parts','2016-03-22 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(12,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,12,NULL,1,'Oil for car','2016-04-10 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(13,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,13,NULL,1,'McBurger with fries','2016-05-18 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(14,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,14,NULL,1,'Paid back first part of one million of student loans','2016-06-08 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(15,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,1,1,7,15,NULL,1,'Did some groceries','2016-06-16 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(16,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,16,NULL,1,'Forgot a bill','2016-07-07 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(17,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,17,NULL,1,'Paid back the second part','2016-08-06 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(18,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,18,NULL,1,'Water bill','2016-08-12 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(19,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,19,NULL,1,'Did some groceries','2016-09-05 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(20,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,20,NULL,1,'Drinks with friends','2016-11-04 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(21,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,21,NULL,1,'Did some groceries','2016-11-08 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(22,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,22,NULL,1,'Got gas for the car','2016-12-03 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1),
(23,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,1,1,7,23,NULL,1,'Got gas for the car','2016-12-06 00:00:00','Europe/Amsterdam',NULL,NULL,NULL,0,0,1,1);
/*!40000 ALTER TABLE `transaction_journals` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transaction_types`
--

DROP TABLE IF EXISTS `transaction_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transaction_types` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `type` varchar(50) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `transaction_types_type_unique` (`type`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transaction_types`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transaction_types` WRITE;
/*!40000 ALTER TABLE `transaction_types` DISABLE KEYS */;
INSERT INTO `transaction_types` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Deposit'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Invalid'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Liability credit'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Opening balance'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Reconciliation'),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Transfer'),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'Withdrawal');
/*!40000 ALTER TABLE `transaction_types` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `transactions`
--

DROP TABLE IF EXISTS `transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `transactions` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `reconciled` tinyint(1) NOT NULL DEFAULT 0,
  `account_id` int(10) unsigned NOT NULL,
  `transaction_journal_id` int(10) unsigned NOT NULL,
  `description` varchar(1024) DEFAULT NULL,
  `transaction_currency_id` int(10) unsigned DEFAULT NULL,
  `amount` decimal(32,12) NOT NULL,
  `balance_before` decimal(32,12) DEFAULT NULL,
  `balance_after` decimal(32,12) DEFAULT NULL,
  `balance_dirty` tinyint(1) NOT NULL DEFAULT 1,
  `foreign_amount` decimal(32,12) DEFAULT NULL,
  `foreign_currency_id` int(10) unsigned DEFAULT NULL,
  `identifier` smallint(5) unsigned NOT NULL DEFAULT 0,
  `native_amount` decimal(32,12) DEFAULT NULL,
  `native_foreign_amount` decimal(32,12) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `transactions_account_id_index` (`account_id`),
  KEY `transactions_transaction_journal_id_index` (`transaction_journal_id`),
  KEY `transactions_transaction_currency_id_index` (`transaction_currency_id`),
  KEY `transactions_foreign_currency_id_index` (`foreign_currency_id`),
  KEY `idx_tx_journal_amount` (`transaction_journal_id`,`amount`),
  CONSTRAINT `transactions_account_id_foreign` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `transactions_foreign_currency_id_foreign` FOREIGN KEY (`foreign_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE SET NULL,
  CONSTRAINT `transactions_transaction_currency_id_foreign` FOREIGN KEY (`transaction_currency_id`) REFERENCES `transaction_currencies` (`id`) ON DELETE SET NULL,
  CONSTRAINT `transactions_transaction_journal_id_foreign` FOREIGN KEY (`transaction_journal_id`) REFERENCES `transaction_journals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `transactions`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `transactions` WRITE;
/*!40000 ALTER TABLE `transactions` DISABLE KEYS */;
INSERT INTO `transactions` VALUES
(1,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,0,4,1,NULL,1,-120.000000000000,0.000000000000,-120.000000000000,0,NULL,NULL,0,NULL,NULL),
(2,'2026-03-05 23:23:30','2026-03-05 23:30:41',NULL,0,1,1,NULL,1,120.000000000000,-989.830000000000,-869.830000000000,0,NULL,NULL,0,NULL,NULL),
(3,'2026-03-05 23:23:30','2026-03-05 23:23:30',NULL,0,5,2,NULL,1,-180.000000000000,0.000000000000,-180.000000000000,0,NULL,NULL,0,NULL,NULL),
(4,'2026-03-05 23:23:30','2026-03-05 23:30:41',NULL,0,1,2,NULL,1,180.000000000000,-915.260000000000,-735.260000000000,0,NULL,NULL,0,NULL,NULL),
(5,'2026-03-05 23:23:30','2026-03-05 23:23:31',NULL,0,6,3,NULL,1,-200.000000000000,0.000000000000,-200.000000000000,0,NULL,NULL,0,NULL,NULL),
(6,'2026-03-05 23:23:30','2026-03-05 23:23:31',NULL,0,2,3,NULL,1,200.000000000000,0.000000000000,200.000000000000,0,NULL,NULL,0,NULL,NULL),
(7,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,1,4,NULL,1,-15.000000000000,0.000000000000,-15.000000000000,0,NULL,NULL,0,NULL,NULL),
(8,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,7,4,NULL,1,15.000000000000,0.000000000000,15.000000000000,0,NULL,NULL,0,NULL,NULL),
(9,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,1,5,NULL,1,-110.000000000000,-15.000000000000,-125.000000000000,0,NULL,NULL,0,NULL,NULL),
(10,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,8,5,NULL,1,110.000000000000,0.000000000000,110.000000000000,0,NULL,NULL,0,NULL,NULL),
(11,'2026-03-05 23:23:31','2026-03-05 23:30:40',NULL,0,1,6,NULL,1,-34.000000000000,-193.400000000000,-227.400000000000,0,NULL,NULL,0,NULL,NULL),
(12,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,9,6,NULL,1,34.000000000000,0.000000000000,34.000000000000,0,NULL,NULL,0,NULL,NULL),
(13,'2026-03-05 23:23:31','2026-03-05 23:30:40',NULL,0,1,7,NULL,1,-30.000000000000,-227.400000000000,-257.400000000000,0,NULL,NULL,0,NULL,NULL),
(14,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,10,7,NULL,1,30.000000000000,0.000000000000,30.000000000000,0,NULL,NULL,0,NULL,NULL),
(15,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,0,1,8,NULL,1,-34.230000000000,-530.300000000000,-564.530000000000,0,NULL,NULL,0,NULL,NULL),
(16,'2026-03-05 23:23:31','2026-03-05 23:23:31',NULL,0,11,8,NULL,1,34.230000000000,0.000000000000,34.230000000000,0,NULL,NULL,0,NULL,NULL),
(17,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,0,1,9,NULL,1,-200.000000000000,-789.830000000000,-989.830000000000,0,NULL,NULL,0,NULL,NULL),
(18,'2026-03-05 23:23:31','2026-03-05 23:30:41',NULL,0,12,9,NULL,1,200.000000000000,400.000000000000,600.000000000000,0,NULL,NULL,0,NULL,NULL),
(19,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,1,10,NULL,1,-3.400000000000,-125.000000000000,-128.400000000000,0,NULL,NULL,0,NULL,NULL),
(20,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,13,10,NULL,1,3.400000000000,0.000000000000,3.400000000000,0,NULL,NULL,0,NULL,NULL),
(21,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,1,11,NULL,1,-45.000000000000,-128.400000000000,-173.400000000000,0,NULL,NULL,0,NULL,NULL),
(22,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,14,11,NULL,1,45.000000000000,0.000000000000,45.000000000000,0,NULL,NULL,0,NULL,NULL),
(23,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,1,12,NULL,1,-20.000000000000,-173.400000000000,-193.400000000000,0,NULL,NULL,0,NULL,NULL),
(24,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,15,12,NULL,1,20.000000000000,0.000000000000,20.000000000000,0,NULL,NULL,0,NULL,NULL),
(25,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,1,13,NULL,1,-8.000000000000,-257.400000000000,-265.400000000000,0,NULL,NULL,0,NULL,NULL),
(26,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,16,13,NULL,1,8.000000000000,0.000000000000,8.000000000000,0,NULL,NULL,0,NULL,NULL),
(27,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,1,14,NULL,1,-200.000000000000,-265.400000000000,-465.400000000000,0,NULL,NULL,0,NULL,NULL),
(28,'2026-03-05 23:30:40','2026-03-05 23:30:40',NULL,0,12,14,NULL,1,200.000000000000,0.000000000000,200.000000000000,0,NULL,NULL,0,NULL,NULL),
(29,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,0,1,15,NULL,1,-14.900000000000,-465.400000000000,-480.300000000000,0,NULL,NULL,0,NULL,NULL),
(30,'2026-03-05 23:30:40','2026-03-05 23:30:41',NULL,0,17,15,NULL,1,14.900000000000,0.000000000000,14.900000000000,0,NULL,NULL,0,NULL,NULL),
(31,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,16,NULL,1,-50.000000000000,-480.300000000000,-530.300000000000,0,NULL,NULL,0,NULL,NULL),
(32,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,18,16,NULL,1,50.000000000000,0.000000000000,50.000000000000,0,NULL,NULL,0,NULL,NULL),
(33,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,17,NULL,1,-200.000000000000,-564.530000000000,-764.530000000000,0,NULL,NULL,0,NULL,NULL),
(34,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,12,17,NULL,1,200.000000000000,200.000000000000,400.000000000000,0,NULL,NULL,0,NULL,NULL),
(35,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,18,NULL,1,-10.000000000000,-764.530000000000,-774.530000000000,0,NULL,NULL,0,NULL,NULL),
(36,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,19,18,NULL,1,10.000000000000,0.000000000000,10.000000000000,0,NULL,NULL,0,NULL,NULL),
(37,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,19,NULL,1,-15.300000000000,-774.530000000000,-789.830000000000,0,NULL,NULL,0,NULL,NULL),
(38,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,17,19,NULL,1,15.300000000000,14.900000000000,30.200000000000,0,NULL,NULL,0,NULL,NULL),
(39,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,20,NULL,1,-31.100000000000,-869.830000000000,-900.930000000000,0,NULL,NULL,0,NULL,NULL),
(40,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,11,20,NULL,1,31.100000000000,34.230000000000,65.330000000000,0,NULL,NULL,0,NULL,NULL),
(41,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,21,NULL,1,-14.330000000000,-900.930000000000,-915.260000000000,0,NULL,NULL,0,NULL,NULL),
(42,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,17,21,NULL,1,14.330000000000,30.200000000000,44.530000000000,0,NULL,NULL,0,NULL,NULL),
(43,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,22,NULL,1,-30.100000000000,-735.260000000000,-765.360000000000,0,NULL,NULL,0,NULL,NULL),
(44,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,20,22,NULL,1,30.100000000000,0.000000000000,30.100000000000,0,NULL,NULL,0,NULL,NULL),
(45,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,1,23,NULL,1,-22.910000000000,-765.360000000000,-788.270000000000,0,NULL,NULL,0,NULL,NULL),
(46,'2026-03-05 23:30:41','2026-03-05 23:30:41',NULL,0,20,23,NULL,1,22.910000000000,30.100000000000,53.010000000000,0,NULL,NULL,0,NULL,NULL);
/*!40000 ALTER TABLE `transactions` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `user_groups`
--

DROP TABLE IF EXISTS `user_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_groups` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_groups_title_unique` (`title`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_groups`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `user_groups` WRITE;
/*!40000 ALTER TABLE `user_groups` DISABLE KEYS */;
INSERT INTO `user_groups` VALUES
(1,'2026-03-05 22:30:28','2026-03-05 22:30:28',NULL,'test@example.com');
/*!40000 ALTER TABLE `user_groups` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_roles_title_unique` (`title`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
INSERT INTO `user_roles` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'ro'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_trx'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_meta'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_budgets'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_piggies'),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_subscriptions'),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_rules'),
(8,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_recurring'),
(9,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_webhooks'),
(10,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'read_currencies'),
(11,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_budgets'),
(12,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_piggies'),
(13,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_subscriptions'),
(14,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_rules'),
(15,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_recurring'),
(16,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_webhooks'),
(17,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'mng_currencies'),
(18,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'view_reports'),
(19,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'view_memberships'),
(20,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'full'),
(21,'2026-03-05 22:12:26','2026-03-05 22:12:26',NULL,'owner');
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `objectguid` char(36) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `email` varchar(255) NOT NULL,
  `password` varchar(60) NOT NULL,
  `remember_token` varchar(100) DEFAULT NULL,
  `reset` varchar(32) DEFAULT NULL,
  `blocked` tinyint(3) unsigned NOT NULL DEFAULT 0,
  `blocked_code` varchar(25) DEFAULT NULL,
  `mfa_secret` varchar(50) DEFAULT NULL,
  `domain` varchar(191) DEFAULT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `type_user_group_id` (`user_group_id`),
  CONSTRAINT `type_user_group_id` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES
(1,NULL,'2026-03-05 22:30:27','2026-03-05 22:30:28','test@example.com','$2y$10$uyBxNWTJDNvN23.xggu2QeEinwAziJb9i7huq49MTk/oTE9YZ4RVO',NULL,NULL,0,NULL,NULL,NULL,1);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_attempts`
--

DROP TABLE IF EXISTS `webhook_attempts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_attempts` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `webhook_message_id` int(10) unsigned NOT NULL,
  `status_code` smallint(5) unsigned NOT NULL DEFAULT 0,
  `logs` longtext DEFAULT NULL,
  `response` longtext DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `webhook_attempts_webhook_message_id_foreign` (`webhook_message_id`),
  CONSTRAINT `webhook_attempts_webhook_message_id_foreign` FOREIGN KEY (`webhook_message_id`) REFERENCES `webhook_messages` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_attempts`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_attempts` WRITE;
/*!40000 ALTER TABLE `webhook_attempts` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_attempts` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_deliveries`
--

DROP TABLE IF EXISTS `webhook_deliveries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_deliveries` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `key` smallint(5) unsigned NOT NULL,
  `title` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_deliveries_key_title_unique` (`key`,`title`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_deliveries`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_deliveries` WRITE;
/*!40000 ALTER TABLE `webhook_deliveries` DISABLE KEYS */;
INSERT INTO `webhook_deliveries` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',300,'JSON');
/*!40000 ALTER TABLE `webhook_deliveries` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_messages`
--

DROP TABLE IF EXISTS `webhook_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_messages` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `sent` tinyint(1) NOT NULL DEFAULT 0,
  `errored` tinyint(1) NOT NULL DEFAULT 0,
  `webhook_id` int(10) unsigned NOT NULL,
  `uuid` varchar(64) NOT NULL,
  `message` longtext NOT NULL,
  PRIMARY KEY (`id`),
  KEY `webhook_messages_webhook_id_foreign` (`webhook_id`),
  CONSTRAINT `webhook_messages_webhook_id_foreign` FOREIGN KEY (`webhook_id`) REFERENCES `webhooks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_messages`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_messages` WRITE;
/*!40000 ALTER TABLE `webhook_messages` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_messages` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_responses`
--

DROP TABLE IF EXISTS `webhook_responses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_responses` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `key` smallint(5) unsigned NOT NULL,
  `title` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_responses_key_title_unique` (`key`,`title`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_responses`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_responses` WRITE;
/*!40000 ALTER TABLE `webhook_responses` DISABLE KEYS */;
INSERT INTO `webhook_responses` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',200,'TRANSACTIONS'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',210,'ACCOUNTS'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',230,'BUDGET'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',240,'RELEVANT'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',220,'NONE');
/*!40000 ALTER TABLE `webhook_responses` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_triggers`
--

DROP TABLE IF EXISTS `webhook_triggers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_triggers` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `key` smallint(5) unsigned NOT NULL,
  `title` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_triggers_key_title_unique` (`key`,`title`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_triggers`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_triggers` WRITE;
/*!40000 ALTER TABLE `webhook_triggers` DISABLE KEYS */;
INSERT INTO `webhook_triggers` VALUES
(1,'2026-03-05 22:12:26','2026-03-05 22:12:26',50,'ANY'),
(2,'2026-03-05 22:12:26','2026-03-05 22:12:26',100,'STORE_TRANSACTION'),
(3,'2026-03-05 22:12:26','2026-03-05 22:12:26',110,'UPDATE_TRANSACTION'),
(4,'2026-03-05 22:12:26','2026-03-05 22:12:26',120,'DESTROY_TRANSACTION'),
(5,'2026-03-05 22:12:26','2026-03-05 22:12:26',200,'STORE_BUDGET'),
(6,'2026-03-05 22:12:26','2026-03-05 22:12:26',210,'UPDATE_BUDGET'),
(7,'2026-03-05 22:12:26','2026-03-05 22:12:26',220,'DESTROY_BUDGET'),
(8,'2026-03-05 22:12:26','2026-03-05 22:12:26',230,'STORE_UPDATE_BUDGET_LIMIT');
/*!40000 ALTER TABLE `webhook_triggers` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_webhook_delivery`
--

DROP TABLE IF EXISTS `webhook_webhook_delivery`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_webhook_delivery` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `webhook_id` int(10) unsigned NOT NULL,
  `webhook_delivery_id` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_webhook_delivery_webhook_id_webhook_delivery_id_unique` (`webhook_id`,`webhook_delivery_id`),
  KEY `link_to_delivery` (`webhook_delivery_id`),
  CONSTRAINT `link_to_delivery` FOREIGN KEY (`webhook_delivery_id`) REFERENCES `webhook_deliveries` (`id`) ON DELETE CASCADE,
  CONSTRAINT `webhook_webhook_delivery_webhook_id_foreign` FOREIGN KEY (`webhook_id`) REFERENCES `webhooks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_webhook_delivery`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_webhook_delivery` WRITE;
/*!40000 ALTER TABLE `webhook_webhook_delivery` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_webhook_delivery` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_webhook_response`
--

DROP TABLE IF EXISTS `webhook_webhook_response`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_webhook_response` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `webhook_id` int(10) unsigned NOT NULL,
  `webhook_response_id` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_webhook_response_webhook_id_webhook_response_id_unique` (`webhook_id`,`webhook_response_id`),
  KEY `link_to_response` (`webhook_response_id`),
  CONSTRAINT `link_to_response` FOREIGN KEY (`webhook_response_id`) REFERENCES `webhook_responses` (`id`) ON DELETE CASCADE,
  CONSTRAINT `webhook_webhook_response_webhook_id_foreign` FOREIGN KEY (`webhook_id`) REFERENCES `webhooks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_webhook_response`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_webhook_response` WRITE;
/*!40000 ALTER TABLE `webhook_webhook_response` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_webhook_response` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhook_webhook_trigger`
--

DROP TABLE IF EXISTS `webhook_webhook_trigger`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_webhook_trigger` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `webhook_id` int(10) unsigned NOT NULL,
  `webhook_trigger_id` bigint(20) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `webhook_webhook_trigger_webhook_id_webhook_trigger_id_unique` (`webhook_id`,`webhook_trigger_id`),
  KEY `link_to_trigger` (`webhook_trigger_id`),
  CONSTRAINT `link_to_trigger` FOREIGN KEY (`webhook_trigger_id`) REFERENCES `webhook_triggers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `webhook_webhook_trigger_webhook_id_foreign` FOREIGN KEY (`webhook_id`) REFERENCES `webhooks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_webhook_trigger`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhook_webhook_trigger` WRITE;
/*!40000 ALTER TABLE `webhook_webhook_trigger` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_webhook_trigger` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;

--
-- Table structure for table `webhooks`
--

DROP TABLE IF EXISTS `webhooks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhooks` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT NULL,
  `user_id` int(10) unsigned NOT NULL,
  `user_group_id` bigint(20) unsigned DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `secret` varchar(32) NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `trigger` smallint(5) unsigned NOT NULL,
  `response` smallint(5) unsigned NOT NULL,
  `delivery` smallint(5) unsigned NOT NULL,
  `url` varchar(1024) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `webhooks_user_id_foreign` (`user_id`),
  KEY `webhooks_title_index` (`title`),
  KEY `webhooks_secret_index` (`secret`),
  KEY `webhooks_to_ugi` (`user_group_id`),
  CONSTRAINT `webhooks_to_ugi` FOREIGN KEY (`user_group_id`) REFERENCES `user_groups` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `webhooks_user_id_foreign` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhooks`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `webhooks` WRITE;
/*!40000 ALTER TABLE `webhooks` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhooks` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-03-05 22:45:25
