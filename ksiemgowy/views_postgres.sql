CREATE VIEW mbank_actions_unpacked AS SELECT id,
        mbank_action ->> 'in_acc_no' AS in_acc_no,
        mbank_action ->> 'out_acc_no' AS out_acc_no,
        replace(mbank_action ->> 'amount_pln', ',', '.')::real AS amount_pln,
        mbank_action ->> 'in_person' AS in_person,
        mbank_action ->> 'in_desc' AS in_desc,
        mbank_action ->> 'balance' AS balance,
        to_timestamp(mbank_action ->> 'timestamp', 'YYYY-MM-DD HH24:MI') AS timestamp
    FROM mbank_actions;


CREATE VIEW members_ever as select m.in_acc_no,
	min(
        to_char(current_timestamp, 'J')::integer - to_char(timestamp, 'J')::integer
    )::integer days_since_last_payment,
	max(
        to_char(current_timestamp, 'J')::integer - to_char(timestamp,'J')::integer
    )::integer days_since_first_payment,
	avg(amount_pln) average_due,
	sum(amount_pln) total_paid,
	min(timestamp) first_paid,
	max(timestamp) last_paid,
	count(1) num_dues
    from mbank_actions_unpacked m
    group by m.in_acc_no
    order by days_since_last_payment asc
;

create view dues as select
    row_number() over (order by last_paid desc) lp,
        email,
        days_since_last_payment since_last,
    trunc(average_due::numeric, 2) average_due,
        trunc(total_paid::numeric,      2) total_paid,
        trunc(
        (total_paid/(case
            when days_since_first_payment < 30 then 
                30 
            else 
                days_since_first_payment 
            end))::numeric, 2
    ) daily,
        trunc(
        (days_since_first_payment * (total_paid/(case
            when days_since_first_payment < 30 then 
                30 
            else 
                days_since_first_payment
            end)) / (num_dues)
    )::numeric, 2) avg_mo,
        first_paid,
        last_paid,
        case
        when num_dues > 1 then
            (
                (to_char(current_timestamp, 'J')::integer - to_char(first_paid, 'J')::integer)
                / (num_dues-1)
            )::integer
        else 
            null 
        end 
        pay_interval,
        num_dues
    from members_ever m 
    left join in_acc_no_to_email e on m.in_acc_no=e.in_acc_no
    where days_since_last_payment < 90
    order by days_since_last_payment asc;
