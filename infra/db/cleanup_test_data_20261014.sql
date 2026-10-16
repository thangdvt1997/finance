-- Dọn dữ liệu thử (QA/lab/smoke) 2026-10-14. Sao lưu vào schema archive (hậu tố _cleanup_20261014) rồi xoá, trong 1 transaction.
-- GIỮ: mt5:99000001 (demo), master:admin, master:qa-final-* (phiên QA đang chạy), sổ cái bất biến (audit_log, paper_*, tr_*).
BEGIN;
CREATE SCHEMA IF NOT EXISTS archive;
CREATE TEMP TABLE _qa_users AS SELECT user_id FROM portal_users
  WHERE login_key IN ('mt5:98596106','mt5:99596106','mt5:100596106','master:cs-e4d28a') AND created_at < now() - interval '12 hours';
CREATE TEMP TABLE _qa_acc AS SELECT account_id FROM mt_accounts
  WHERE account_id IN ('mt5:98596106','mt5:99596106','mt5:100596106');
-- sao lưu
CREATE TABLE archive.portal_users_cleanup_20261014 AS SELECT * FROM portal_users WHERE user_id IN (SELECT user_id FROM _qa_users);
CREATE TABLE archive.mt_accounts_cleanup_20261014 AS SELECT * FROM mt_accounts WHERE account_id IN (SELECT account_id FROM _qa_acc);
CREATE TABLE archive.user_accounts_cleanup_20261014 AS SELECT * FROM user_accounts WHERE user_id IN (SELECT user_id FROM _qa_users);
CREATE TABLE archive.portal_sessions_cleanup_20261014 AS SELECT * FROM portal_sessions WHERE user_id IN (SELECT user_id FROM _qa_users);
CREATE TABLE archive.view_as_grants_cleanup_20261014 AS SELECT * FROM view_as_grants WHERE created_at < now() - interval '12 hours';
CREATE TABLE archive.account_tags_cleanup_20261014 AS SELECT * FROM account_tags WHERE account_id IN (SELECT account_id FROM _qa_acc);
CREATE TABLE archive.account_groups_cleanup_20261014 AS SELECT * FROM account_groups WHERE name LIKE 'qa %';
CREATE TABLE archive.incidents_cleanup_20261014 AS SELECT * FROM incidents WHERE opened_at < now() - interval '12 hours' AND (key ~* 'qa-' OR title ~* 'qa-' OR detail ~* '\(QA\)|QA giao' );
CREATE TABLE archive.incident_events_cleanup_20261014 AS SELECT * FROM incident_events WHERE incident_id IN (SELECT incident_id FROM archive.incidents_cleanup_20261014);
CREATE TABLE archive.user_notifications_cleanup_20261014 AS SELECT * FROM user_notifications WHERE title ~* 'qa-' AND ts < now() - interval '12 hours';
CREATE TABLE archive.alert_rule_events_cleanup_20261014 AS SELECT * FROM alert_rule_events WHERE rule_name IN ('smoke-fire');
CREATE TABLE archive.bars_lab_cleanup_20261014 AS SELECT * FROM bars WHERE source IN ('qa','mt4:demo-mt4-01','mt5:demo-mt5-01');
CREATE TABLE archive.quotes_lab_cleanup_20261014 AS SELECT * FROM quotes WHERE source IN ('qa','mt4:demo-mt4-01','mt5:demo-mt5-01');
CREATE TABLE archive.alerts_test_cleanup_20261014 AS SELECT * FROM alerts
  WHERE ts < now() - interval '12 hours' AND (title ~* '(qa-[0-9a-f]{4,}|^QA alert|demo-mt[45]-01|smoke)' OR title ~* '^\[MÔ PHỎNG\] smoke');
-- xoá (con trước cha)
DELETE FROM incident_events WHERE incident_id IN (SELECT incident_id FROM archive.incidents_cleanup_20261014);
DELETE FROM incidents WHERE incident_id IN (SELECT incident_id FROM archive.incidents_cleanup_20261014);
DELETE FROM user_notifications WHERE id IN (SELECT id FROM archive.user_notifications_cleanup_20261014);
DELETE FROM alert_rule_events WHERE id IN (SELECT id FROM archive.alert_rule_events_cleanup_20261014);
DELETE FROM view_as_grants WHERE created_at < now() - interval '12 hours';
DELETE FROM account_tags WHERE account_id IN (SELECT account_id FROM _qa_acc);
DELETE FROM account_group_members WHERE account_id IN (SELECT account_id FROM _qa_acc) OR group_id IN (SELECT group_id FROM account_groups WHERE name LIKE 'qa %');
DELETE FROM account_groups WHERE name LIKE 'qa %';
DELETE FROM user_accounts WHERE user_id IN (SELECT user_id FROM _qa_users);
DELETE FROM portal_sessions WHERE user_id IN (SELECT user_id FROM _qa_users);
DELETE FROM mt_accounts WHERE account_id IN (SELECT account_id FROM _qa_acc);
DELETE FROM portal_users WHERE user_id IN (SELECT user_id FROM _qa_users);
DELETE FROM bars WHERE source IN ('qa','mt4:demo-mt4-01','mt5:demo-mt5-01');
DELETE FROM quotes WHERE source IN ('qa','mt4:demo-mt4-01','mt5:demo-mt5-01');
DELETE FROM alerts WHERE id IN (SELECT id FROM archive.alerts_test_cleanup_20261014);
SELECT 'archived' k, relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname='archive' AND relname LIKE '%cleanup_20261014' ORDER BY 2;
COMMIT;
