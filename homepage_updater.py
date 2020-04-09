#!/usr/bin/env python

import contextlib
import datetime
import os
import shutil
import subprocess
import textwrap
import time

import schedule

import ksiemgowy.public_state

HOMEPAGE_REPO = 'hakierspejs/homepage'
DUES_FILE_PATH = '_includes/dues.txt'
PUBLIC_DB_URI = os.environ['PUBLIC_DB_URI']
DUES_SEPARATOR = '\n\n{% comment %} END OF AUTOUPDATED PART {% endcomment %}'


def get_local_state(db):
    now = datetime.datetime.now()
    month_ago = now - datetime.timedelta(days=31)
    total = 200
    num_subscribers = 1
    last_updated = None
    for action in db.list_mbank_actions():
        if action['timestamp'] < month_ago:
            continue
        if last_updated is None:
            last_updated = action['timestamp']
        num_subscribers += 1
        total += action['amount_pln']
    last_updated = '09-04-2020'
    return textwrap.dedent(f'''
        {{% assign dues_total_lastmonth = {total} %}}
        {{% assign dues_last_updated = "{last_updated}" %}}
        {{% assign dues_num_subscribers = {num_subscribers} %}}
    ''').strip()


def get_remote_state():
    with open(f'homepage/{DUES_FILE_PATH}') as f:
        return f.read().split(DUES_SEPARATOR)


@contextlib.contextmanager
def git_cloned():
    try:
        git_url = f'git@github.com:{HOMEPAGE_REPO}.git'
        subprocess.check_call(['git', 'clone', git_url])
        yield
    finally:
        try:
            shutil.rmtree('homepage')
        except FileNotFoundError:
            pass


def update_remote_state(new_state):
    with open(f'homepage/{DUES_FILE_PATH}', 'w') as f:
        f.write(new_state)
    subprocess.check_call(
        ['git', 'commit', '-am', 'dues: autoupdate'], cwd='homepage'
    )
    subprocess.check_call(
        ['git', 'push'], cwd='homepage'
    )


def maybe_update(db):
    with git_cloned():
        local_state = get_local_state(db)
        remote_state, suffix = get_remote_state()
        if remote_state != local_state:
            new_state = ''.join([local_state, DUES_SEPARATOR, suffix])
            update_remote_state(new_state)


def main():
    PUBLIC_DB_URI = os.environ['PUBLIC_DB_URI']
    state = ksiemgowy.public_state.PublicState(PUBLIC_DB_URI)
    maybe_update(state)
    schedule.every().day.do(maybe_update, state)
    while True:
        time.sleep(1.0)
        schedule.run_pending()


if __name__ == '__main__':
    main()
