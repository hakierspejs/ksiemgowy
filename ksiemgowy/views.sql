CREATE VIEW positive_actions_unpacked as select id, json_extract(positive_action, '$.sender_acc_no') as sender_acc_no, json_extract(positive_action, '$.out_acc_no') as out_acc_no, cast(replace(json_extract(positive_action, '$.amount_pln'), ',', '.') as real) as amount_pln, json_extract(positive_action, '$.in_person') as in_person, json_extract(positive_action, '$.in_desc') as in_desc, json_extract(positive_action, '$.balance') as balance, date(json_extract(positive_action, '$.timestamp')) as timestamp from positive_actions
CREATE VIEW previous_actions as select m.*, (select timestamp from positive_actions_unpacked m2 where m.sender_acc_no=m2.sender_acc_no and m.timestamp>m2.timestamp order by timestamp desc limit 1 ) as previous_timestamp from positive_actions_unpacked m
CREATE VIEW forgot_to_pay as select sender_acc_no, min(julianday() - julianday(timestamp)) days_since_last_payment , avg(amount_pln) average_due from positive_actions_unpacked group by sender_acc_no having days_since_last_payment <40 and days_since_last_payment > 30 order by  days_since_last_payment desc
CREATE VIEW suma_wplat_od_nieaktywnych_czlonkow as select (select sum(amount_pln) from positive_actions_unpacked) - (select sum(paid) from members) suma;
CREATE VIEW members as select * from members_ever where days_since_last_payment < 33 order by  days_since_last_payment asc
CREATE VIEW members_ever as select m.sender_acc_no, cast(min(julianday() - julianday(timestamp)) as integer) days_since_last_payment, cast(max(julianday() - julianday(timestamp)) as integer) days_since_first_payment, avg(amount_pln) average_due, sum(amount_pln) total_paid, min(timestamp) first_paid, max(timestamp) last_paid, count(1) num_dues from positive_actions_unpacked m group by m.sender_acc_no order by  days_since_last_payment asc
