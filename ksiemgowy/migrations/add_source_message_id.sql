-- Run once on an existing database without source_message_id,
-- before starting the updated application. New databases already
-- get this column from the SQLAlchemy table definition.
ALTER TABLE bank_actions ADD COLUMN source_message_id VARCHAR;
