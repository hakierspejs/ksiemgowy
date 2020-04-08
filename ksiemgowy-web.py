#!/usr/bin/env python

import os

import flask

import ksiemgowy.public_state


PUBLIC_DB_URI = os.environ['PUBLIC_DB_URI']
app = flask.Flask(__name__)


@app.route('/liczba_placacych')
def liczba_placacych():
    state = ksiemgowy.public_state.PublicState(PUBLIC_DB_URI)
    return str(len(list(state.list_mbank_actions())))


if __name__ == '__main__':
    app.run(host='0.0.0.0')
