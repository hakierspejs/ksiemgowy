#!/usr/bin/env python

"""Downloads the most current uploaded financial report and compares it to
the one that can be generated based on the latest data. If they differ, uploads
a new one to the website."""

import contextlib
import datetime
import logging
import shutil
import socket
import subprocess
import time
import yaml


import ksiemgowy.current_report_builder
import ksiemgowy.models
from typing import Dict, Tuple, Generator, Optional


LOGGER = logging.getLogger("homepage_updater")
HOMEPAGE_REPO = "hakierspejs/homepage"
DUES_FILE_PATH = "_data/dues.yml"
GRAPHITE_HOST = ("graphite.hs-ldz.pl", 2003)


def serialize(
    dict_to_serialize: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
) -> str:
    """Serializes a given object, returning it in a format generated and
    expected by Ksiemgowy."""
    # return json.dumps(d, indent=2)
    return str(yaml.dump(dict_to_serialize))


def deserialize(
    serialized_string: str,
) -> ksiemgowy.current_report_builder.T_CURRENT_REPORT:
    """De-serializes a given string, returning it in a format generated and
    expected by Ksiemgowy."""
    # return json.loads(d)
    loaded = yaml.safe_load(serialized_string)
    return {
        "dues_total_lastmonth": loaded["dues_total_lastmonth"],
        "dues_last_updated": loaded["dues_last_updated"],
        "dues_num_subscribers": loaded["dues_num_subscribers"],
        "extra_monthly_reservations": loaded["extra_monthly_reservations"],
        "balance_so_far": loaded["balance_so_far"],
        "balances_by_account_labels": loaded["balances_by_account_labels"],
        "monthly": loaded["monthly"],
    }


def upload_value_to_graphite(
    host: Tuple[str, int], metric: str, value: str
) -> None:
    """Uploads a single metric to a Graphite server."""
    sock = socket.socket()
    try:
        sock.connect(host)
        now = int(time.time())
        buf = f"{metric} {value} {now}\n".encode()
        LOGGER.info("Sending %r to %r", buf, host)
        sock.send(buf)
        sock.close()
    except (ConnectionRefusedError, socket.timeout, TimeoutError) as err:
        LOGGER.exception(err)
    time.sleep(3.0)


def upload_to_graphite(
    host: Tuple[str, int],
    current_report: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
) -> None:
    """Uploads metrics to Graphite server."""
    upload_value_to_graphite(
        host,
        "hakierspejs.finanse.total_lastmonth",
        str(current_report["dues_total_lastmonth"]),
    )
    upload_value_to_graphite(
        host,
        "hakierspejs.finanse.num_subscribers",
        str(current_report["dues_num_subscribers"]),
    )


def get_remote_state_dues(
    remote_state_path: str,
) -> Optional[ksiemgowy.current_report_builder.T_CURRENT_REPORT]:
    """Reads remote state from a specified file, then de-serializes it
    and returns in a format that's similar to the one generated by
    Ksiemgowy."""
    try:
        with open(remote_state_path, encoding="utf8") as remote_state_file:
            ret = deserialize(remote_state_file.read())
        return ret
    except FileNotFoundError:
        return None


def ssh_agent_import_key_and_build_env_and_setup_git(
    deploy_key_path: str,
) -> Dict[str, str]:
    """Creates an SSH agent session and adds a specified key to it. Returns
    environment variables needed to use the SSH agent."""
    env = {}
    for line in subprocess.check_output(["ssh-agent", "-c"]).split(b"\n"):
        split = line.decode().split()
        if (
            len(split) == 3
            and split[0] == "setenv"
            and split[-1].endswith(";")
        ):
            env[split[1]] = split[2].rstrip(";")
    subprocess.check_call(["ssh-add", deploy_key_path], env=env)
    subprocess.check_call(["ssh-add", "-l"], env=env)
    return env


def set_up_git_identity(username: str, email: str, cwd: str) -> None:
    """Sets up git identity required in order to be able to commit: an e-mail
    and user name."""
    subprocess.check_call(["git", "config", "user.email", email], cwd=cwd)
    subprocess.check_call(["git", "config", "user.name", username], cwd=cwd)


@contextlib.contextmanager
def git_cloned(deploy_key_path: str) -> Generator[Dict[str, str], None, None]:
    """Sets up SSH authorization to a Git repository using SSH deploy keys,
    then clones the repository and sets up git identify for it. Acts as a
    context manager - once it exits, the source tree gets deleted.

    Yields enviroment variables needed to be able to commit and push to git."""
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


def update_git_remote_state(
    filepath: str,
    new_state: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
    env: Dict[str, str],
) -> None:
    """Updates remote state by writing to a file, creating a git commit and
    pushing it to the repository."""
    with open(filepath, "w", encoding="utf8") as remote_state_file:
        remote_state_file.write(serialize(new_state))
    subprocess.check_call(
        ["git", "commit", "-am", "dues: autoupdate"], cwd="homepage", env=env
    )
    subprocess.check_call(["git", "push"], cwd="homepage", env=env)


def do_states_differ(
    remote_state: Optional[ksiemgowy.current_report_builder.T_CURRENT_REPORT],
    current_report: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
) -> bool:
    """Returns true if current report differs from the remote one. Does not
    compare keys which are not in current report."""
    if remote_state is None:
        return True
    for k in current_report:
        if current_report.get(k) != remote_state.get(k):
            return True
    return False


def is_local_state_newer(
    remote_state: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
    current_report: ksiemgowy.current_report_builder.T_CURRENT_REPORT,
) -> bool:
    """Compares remote state and current report, using time criteria."""
    local_modified = datetime.datetime.strptime(
        current_report["dues_last_updated"], "%d-%m-%Y"
    )
    remote_modified = datetime.datetime.strptime(
        remote_state["dues_last_updated"], "%d-%m-%Y"
    )
    return local_modified > remote_modified


def maybe_update_dues(
    database: ksiemgowy.models.KsiemgowyDB, git_env: Dict[str, str]
) -> None:
    """Generates the current report, retrieves the one that's accessible online
    and if the current one is later, updates the remote state."""
    now = datetime.datetime.now()
    current_report = ksiemgowy.current_report_builder.get_current_report(
        now, database.list_expenses(), database.list_positive_transfers()
    )
    upload_to_graphite(GRAPHITE_HOST, current_report)
    remote_state_path = f"homepage/{DUES_FILE_PATH}"
    remote_state = get_remote_state_dues(remote_state_path)
    if remote_state is None:
        has_changed = True
    else:
        has_changed = do_states_differ(remote_state, current_report)

    if has_changed and (
        remote_state is None
        or is_local_state_newer(remote_state, current_report)
    ):
        if remote_state is None:
            remote_state = current_report
        else:
            remote_state.update(current_report)
        LOGGER.info("maybe_update_dues: updating dues")
        update_git_remote_state(remote_state_path, remote_state, git_env)
    LOGGER.info("maybe_update_dues: done")


def maybe_update(
    database: ksiemgowy.models.KsiemgowyDB, deploy_key_path: str
) -> None:
    """Submodule's entry point. Checks out the repository, operates on it and
    cleans up the checked out tree."""
    with git_cloned(deploy_key_path) as git_env:
        maybe_update_dues(database, git_env)
    """Submodule's entry point. Checks out the repository, operates on it and
    cleans up the checked out tree."""
    with git_cloned(deploy_key_path) as git_env:
        maybe_update_dues(database, git_env)
