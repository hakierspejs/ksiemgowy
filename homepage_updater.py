#!/usr/bin/env python

import contextlib
import datetime
import os
import shutil
import logging
import subprocess
import textwrap
import time
import socket
import dateutil.rrule

import schedule

import ksiemgowy.public_state

LOGGER = logging.getLogger("homepage_updater")
HOMEPAGE_REPO = "hakierspejs/homepage"
DUES_FILE_PATH = "_includes/dues.txt"
MEETUP_FILE_PATH = "_includes/next_meeting.txt"
DUES_SEPARATOR = "\n\n{% comment %} END OF AUTOUPDATED PART {% endcomment %}"


def upload_to_graphite(h, metric, value):
    s = socket.socket()
    try:
        s.connect(h)
        now = int(time.time())
        buf = f"{metric} {value} {now}\n".encode()
        LOGGER.info("Sending %r to %r", buf, h)
        s.send(buf)
        s.close()
    except (ConnectionRefusedError, socket.timeout) as e:
        LOGGER.exception(e)
    time.sleep(3.0)


def parse_last_updated(s):
    prefix = '{% assign dues_last_updated = "'
    line = [l for l in s.split("\n") if l.startswith(prefix)][0]
    date_s = line.split(prefix)[1].split('"')[0]
    return datetime.datetime.strptime(date_s, "%d-%m-%Y")


def get_local_state_dues(db):
    now = datetime.datetime.now()
    month_ago = now - datetime.timedelta(days=31)
    total = 200
    num_subscribers = 1
    last_updated = None
    total_ever = 0
    observed_acc_numbers = set()
    observed_acc_owners = set()
    first_200pln_d33tah_due_date = datetime.datetime(year=2020, month=6, day=7)
    for action in db.list_mbank_actions():
        total_ever += action.amount_pln
        if action.timestamp < month_ago:
            continue
        elif last_updated is None or action.timestamp > last_updated:
            last_updated = action.timestamp
        if (
            action.in_acc_no not in observed_acc_numbers
            and action.in_person not in observed_acc_owners
        ):
            num_subscribers += 1
            observed_acc_numbers.add(action.in_acc_no)
            observed_acc_owners.add(action.in_person)
        total += action.amount_pln
    total_ever += sum(
        [
            200
            for _ in dateutil.rrule.rrule(
                dateutil.rrule.MONTHLY, dtstart=first_200pln_d33tah_due_date, until=now
            )
        ]
    )
    last_updated_s = last_updated.strftime("%d-%m-%Y")
    h = ("graphite.hs-ldz.pl", 2003)
    upload_to_graphite(h, "hakierspejs.finanse.total_lastmonth", total)
    upload_to_graphite(h, "hakierspejs.finanse.num_subscribers", num_subscribers)
    return (
        textwrap.dedent(
            f"""
        {{% assign dues_total_lastmonth = {total} %}}
        {{% assign dues_last_updated = "{last_updated_s}" %}}
        {{% assign dues_num_subscribers = {num_subscribers} %}}
        {{% assign dues_so_far = {total_ever} %}}
    """
        ).strip(),
        last_updated,
    )


def get_remote_state_dues():
    with open(f"homepage/{DUES_FILE_PATH}") as f:
        ret = f.read().split(DUES_SEPARATOR)
    return ret[0], ret[1], parse_last_updated("".join(ret))


def ssh_agent_import_key_and_build_env_and_setup_git(deploy_key_path):
    env = {}
    for line in subprocess.check_output(["ssh-agent", "-c"]).split(b"\n"):
        s = line.decode().split()
        if len(s) == 3 and s[0] == "setenv" and s[-1].endswith(";"):
            env[s[1]] = s[2].rstrip(";")
    subprocess.check_call(["ssh-add", deploy_key_path], env=env)
    subprocess.check_call(["ssh-add", "-l"], env=env)
    return env


def set_up_git_identity(username, email, cwd):
    subprocess.check_call(["git", "config", "user.email", email], cwd=cwd)
    subprocess.check_call(["git", "config", "user.name", username], cwd=cwd)


@contextlib.contextmanager
def git_cloned(deploy_key_path):
    cwd = "homepage"
    try:
        env = ssh_agent_import_key_and_build_env_and_setup_git(deploy_key_path)
        git_url = f"git@github.com:{HOMEPAGE_REPO}.git"
        env["GIT_SSH_COMMAND"] = " ".join(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ]
        )
        subprocess.check_call(["git", "clone", git_url, cwd], env=env)
        set_up_git_identity("ksiemgowy", "d33tah+ksiemgowy@gmail.com", cwd)
        yield env
    finally:
        try:
            shutil.rmtree(cwd)
        except FileNotFoundError:
            pass


def update_remote_state(filepath, new_state, env):
    with open(filepath, "w") as f:
        f.write(new_state)
    subprocess.check_call(
        ["git", "commit", "-am", "dues: autoupdate"], cwd="homepage", env=env
    )
    subprocess.check_call(["git", "push"], cwd="homepage", env=env)


def maybe_update_dues(db, git_env):
    local_state, last_updated_local = get_local_state_dues(db)
    remote_state, suffix, last_updated_remote = get_remote_state_dues()
    is_newer = last_updated_local > last_updated_remote
    if remote_state != local_state and is_newer:
        new_state = "".join([local_state, DUES_SEPARATOR, suffix])
        update_remote_state(f"homepage/{DUES_FILE_PATH}", new_state, git_env)


def maybe_update(db, deploy_key_path):
    time.sleep(600.0)
    with git_cloned(deploy_key_path) as git_env:
        maybe_update_dues(db, git_env)


def main():
    PUBLIC_DB_URI = os.environ["PUBLIC_DB_URI"]
    deploy_key_path = os.environ["DEPLOY_KEY_PATH"]
    state = ksiemgowy.public_state.PublicState(PUBLIC_DB_URI)
    maybe_update(state, deploy_key_path)
    schedule.every().hour.do(maybe_update, state, deploy_key_path)
    while True:
        time.sleep(1.0)
        schedule.run_pending()


if __name__ == "__main__":
    main()
