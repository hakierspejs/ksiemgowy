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
DUES_SEPARATOR = '\n\n{% comment %} END OF AUTOUPDATED PART {% endcomment %}'


def parse_last_updated(s):
    prefix = '{% assign dues_last_updated = "'
    line = [l for l in s.split('\n') if l.startswith(prefix)][0]
    date_s = line.split(prefix)[1].split('"')[0]
    return datetime.datetime.strptime(date_s, '%d-%m-%Y')


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
    last_updated_s = last_updated.strftime('%d-%m-%Y')
    return textwrap.dedent(f'''
        {{% assign dues_total_lastmonth = {total} %}}
        {{% assign dues_last_updated = "{last_updated_s}" %}}
        {{% assign dues_num_subscribers = {num_subscribers} %}}
    ''').strip(), last_updated


def get_remote_state():
    with open(f'homepage/{DUES_FILE_PATH}') as f:
        ret = f.read().split(DUES_SEPARATOR)
    return ret[0], ret[1], parse_last_updated(''.join(ret))


def ssh_agent_import_key_and_build_env_and_setup_git(deploy_key_path):
    env = {}
    for line in subprocess.check_output(['ssh-agent', '-c']).split(b'\n'):
        s = line.decode().split()
        if len(s) == 3 and s[0] == 'setenv' and s[-1].endswith(';'):
            env[s[1]] = s[2].rstrip(';')
    subprocess.check_call(['ssh-add', deploy_key_path], env=env)
    subprocess.check_call(['ssh-add', '-l'], env=env)
    return env


def set_up_git_identity(username, email, cwd):
    subprocess.check_call([
        'git', 'config', 'user.email', email
    ], cwd=cwd)
    subprocess.check_call([
        'git', 'config', 'user.name', username
    ], cwd=cwd)


@contextlib.contextmanager
def git_cloned(deploy_key_path):
    cwd = 'homepage'
    try:
        env = ssh_agent_import_key_and_build_env_and_setup_git(deploy_key_path)
        git_url = f'git@github.com:{HOMEPAGE_REPO}.git'
        env['GIT_SSH_COMMAND'] = ' '.join([
            'ssh', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null'
        ])
        subprocess.check_call(['git', 'clone', git_url, cwd], env=env)
        set_up_git_identity('ksiemgowy', 'd33tah+ksiemgowy@gmail.com', cwd)
        yield env
    finally:
        try:
            shutil.rmtree(cwd)
        except FileNotFoundError:
            pass


def update_remote_state(new_state, env):
    with open(f'homepage/{DUES_FILE_PATH}', 'w') as f:
        f.write(new_state)
    subprocess.check_call(
        ['git', 'commit', '-am', 'dues: autoupdate'], cwd='homepage', env=env
    )
    subprocess.check_call(
        ['git', 'push'], cwd='homepage', env=env
    )


def maybe_update(db, deploy_key_path):
    time.sleep(600.0)
    with git_cloned(deploy_key_path) as git_env:
        local_state, last_updated_local = get_local_state(db)
        remote_state, suffix, last_updated_remote = get_remote_state()
        is_newer = last_updated_local > last_updated_remote
        if remote_state != local_state and is_newer:
            new_state = ''.join([local_state, DUES_SEPARATOR, suffix])
            update_remote_state(new_state, git_env)


def main():
    PUBLIC_DB_URI = os.environ['PUBLIC_DB_URI']
    deploy_key_path = os.environ['DEPLOY_KEY_PATH']
    state = ksiemgowy.public_state.PublicState(PUBLIC_DB_URI)
    maybe_update(state, deploy_key_path)
    schedule.every().hour.do(maybe_update, state, deploy_key_path)
    while True:
        time.sleep(1.0)
        schedule.run_pending()


if __name__ == '__main__':
    main()
