import os
import re
import json
from . import api
from . import ops
from . import context
from . import weave_server

import pytest


def test_logfile_created(fresh_server_logfile):

    with context.local_http_client():
        # run this to kick off a server
        assert api.use(ops.Number.__add__(3, 9)) == 12

        # check that the log file was created
        assert os.path.exists(weave_server.default_log_filename)

        with open(weave_server.default_log_filename, "r") as f:
            content = f.read()

        # check that it has a record of executing one call
        assert "execute" in content and "200" in content


def test_logfile_captures_error(fresh_server_logfile):
    # run this to kick off a server

    with context.local_http_client():
        with pytest.raises(json.JSONDecodeError):
            api.use(ops.Number.__add__(3, "a"))

        # check that the log file was created
        assert os.path.exists(weave_server.default_log_filename)

        with open(weave_server.default_log_filename, "r") as f:
            content = f.read()

        # check that it has a record of executing one call
        assert "execute" in content and "500" in content


def test_log_2_app_instances_different_threads(fresh_server_logfile):
    # kick off two http servers

    with context.local_http_client():
        with context.local_http_client():
            with pytest.raises(json.JSONDecodeError):
                # this one is run by server 2
                api.use(ops.Number.__add__(3, "a"))

        # this one is run by server 1
        assert api.use(ops.Number.__add__(3, 9)) == 12

    # check that the log file was created
    assert os.path.exists(weave_server.default_log_filename)

    with open(weave_server.default_log_filename, "r") as f:
        content = f.read()

    # check that it has a record of executing one call
    assert "execute" in content and "500" in content and "200" in content
    threads = re.findall(r"\(Thread (.+)\)", content)

    assert len(threads) == 3
    assert threads[-2] != threads[-1]


def test_capture_server_logs_captures_server_logs(fresh_server_logfile, capsys):
    context.capture_weave_server_logs()

    with context.local_http_client():
        # run this to kick off a server
        assert api.use(ops.Number.__add__(3, 9)) == 12

        # check that the log file was created
        assert os.path.exists(weave_server.default_log_filename)

        with open(weave_server.default_log_filename, "r") as f:
            content = f.read()

        # check that it has a record of executing one call
        assert "execute" in content and "200" in content

        # check that the same stuff appears in the captured stream logs
        capresult = capsys.readouterr()
        stderr = capresult.err
        assert "execute" in stderr and "200" in stderr
