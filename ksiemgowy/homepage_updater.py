#!/usr/bin/env python

import collections
import contextlib
import datetime
import logging
import shutil
import socket
import subprocess
import time
import yaml

from yaml.representer import Representer

import ksiemgowy.current_report_builder


yaml.add_representer(collections.defaultdict, Representer.represent_dict)


LOGGER = logging.getLogger("homepage_updater")
HOMEPAGE_REPO = "hakierspejs/homepage"
DUES_FILE_PATH = "_data/dues.yml"
MEETUP_FILE_PATH = "_includes/next_meeting.txt"


def serialize(d):
    # return json.dumps(d, indent=2)
    return yaml.dump(d)


def deserialize(d):
    # return json.loads(d)
    return yaml.safe_load(d)


def upload_value_to_graphite(h, metric, value):
    s = socket.socket()
    try:
        s.connect(h)
        now = int(time.time())
        buf = f"{metric} {value} {now}\n".encode()
        LOGGER.info("Sending %r to %r", buf, h)
        s.send(buf)
        s.close()
    except (ConnectionRefusedError, socket.timeout, TimeoutError) as e:
        LOGGER.exception(e)
    time.sleep(3.0)


def upload_to_graphite(d):
    h = ("graphite.hs-ldz.pl", 2003)
    upload_value_to_graphite(
        h, "hakierspejs.finanse.total_lastmonth", d["dues_total_lastmonth"]
    )
    upload_value_to_graphite(
        h, "hakierspejs.finanse.num_subscribers", d["dues_num_subscribers"]
    )


def get_remote_state_dues():
    try:
        with open(f"homepage/{DUES_FILE_PATH}") as f:
            ret = deserialize(f.read())
        return ret
    except FileNotFoundError:
        return {}


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
        f.write(serialize(new_state))
    subprocess.check_call(
        ["git", "commit", "-am", "dues: autoupdate"], cwd="homepage", env=env
    )
    subprocess.check_call(["git", "push"], cwd="homepage", env=env)


def do_states_differ(remote_state, current_report):
    for k in current_report:
        if current_report.get(k) != remote_state.get(k):
            return True
    return False


def is_newer(remote_state, current_report):
    local_modified = datetime.datetime.strptime(
        current_report["dues_last_updated"], "%d-%m-%Y"
    )
    remote_modified = datetime.datetime.strptime(
        remote_state["dues_last_updated"], "%d-%m-%Y"
    )
    return local_modified > remote_modified


def maybe_update_dues(db, git_env):
    now = datetime.datetime.now()
    current_report = ksiemgowy.current_report_builder.get_current_report(
        now, db.list_expenses(), db.list_mbank_actions()
    )
    upload_to_graphite(current_report)
    remote_state = get_remote_state_dues()
    has_changed = do_states_differ(remote_state, current_report)
    if has_changed and is_newer(remote_state, current_report):
        LOGGER.info("maybe_update_dues: updating dues")
        remote_state.update(current_report)
        update_remote_state(
            f"homepage/{DUES_FILE_PATH}", remote_state, git_env
        )
    LOGGER.info("maybe_update_dues: done")


def maybe_update(db, deploy_key_path):
    with git_cloned(deploy_key_path) as git_env:
        maybe_update_dues(db, git_env)
