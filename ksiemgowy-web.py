#!/usr/bin/env python

import os

import flask

import ksiemgowy.public_state


PUBLIC_DB_URI = os.environ['PUBLIC_DB_URI']
app = flask.Flask(__name__)


@app.route('/liczba_placacych')
def liczba_placacych():
    state = ksiemgowy.public_state.PublicState(PUBLIC_DB_URI)
    observed_acc_numbers = set()
    observed_acc_owners = set()
    num_subscribers = 1  # because d33tah's transfers are invisible to system
    for action in state.list_mbank_actions():
        if (
            action["in_acc_no"] not in observed_acc_numbers
            and action["in_person"] not in observed_acc_owners
        ):
            num_subscribers += 1
            observed_acc_numbers.add(action["in_acc_no"])
            observed_acc_owners.add(action["in_person"])
    return str(num_subscribers)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
