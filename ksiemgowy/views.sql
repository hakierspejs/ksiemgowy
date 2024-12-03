DROP VIEW IF EXISTS previous_actions;
DROP VIEW IF EXISTS forgot_to_pay;
DROP VIEW IF EXISTS suma_wplat_od_nieaktywnych_czlonkow;
DROP VIEW IF EXISTS members;
DROP VIEW IF EXISTS members_ever;

CREATE VIEW previous_actions as select m.*, (select timestamp from bank_actions m2 where m.sender_acc_no=m2.sender_acc_no and m.timestamp>m2.timestamp order by timestamp desc limit 1 ) as previous_timestamp from bank_actions m;
CREATE VIEW forgot_to_pay as select sender_acc_no, min(julianday() - julianday(timestamp)) days_since_last_payment , avg(amount_pln) average_due from bank_actions group by sender_acc_no having days_since_last_payment <40 and days_since_last_payment > 30 order by  days_since_last_payment desc;
CREATE VIEW suma_wplat_od_nieaktywnych_czlonkow as select (select sum(amount_pln) from bank_actions) - (select sum(paid) from members) suma;
CREATE VIEW members as select * from members_ever where days_since_last_payment < 33 order by  days_since_last_payment asc;
CREATE VIEW members_ever as select m.sender_acc_no, cast(min(julianday() - julianday(timestamp)) as integer) days_since_last_payment, cast(max(julianday() - julianday(timestamp)) as integer) days_since_first_payment, avg(amount_pln) average_due, sum(amount_pln) total_paid, min(timestamp) first_paid, max(timestamp) last_paid, count(1) num_dues from bank_actions m group by m.sender_acc_no order by  days_since_last_payment asc;
