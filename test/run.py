#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2016 Blue Box, an IBM Company
# Copyright 2016 Paul Durivage <pmduriva at us.ibm.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import os
import sys
import time
import shlex
import datetime
import subprocess
import multiprocessing

from argparse import ArgumentParser
from contextlib import contextmanager


PLAYS_INITIAL = ['1-initial.yml']
PLAYS_PARALLEL = [
    '2-glance.yml',
    '3-nova.yml',
    '4-cinder.yml',
    '5-ceph.yml',
    '6-neutron.yml',
    '8-swift.yml',
    '9-heat.yml',
    '10-ceilometer.yml',
    '11-magnum.yml',
    '12-ironic.yml',
]
PLAYS_FINAL = ['13-openstack_base_and_network.yml']

TEST_PLAY = 'playbooks/tests/tasks/main.yml'
CLEANUP_PLAY = 'playbooks/tests/tasks/cleanup.yml'
UPGRADE_PLAY = 'upgrade.yml'

lock = multiprocessing.Lock()


@contextmanager
def timer(name=None):
    start = time.time()
    yield
    end = time.time()

    if name:
        timestamp = datetime.timedelta(seconds=int(end - start))
        with lock:
            print(
                "\nTask '%s' completed in %s (hh:mm:ss).\n" % (name, timestamp)
            )
            sys.stdout.flush()


def popen(exec_str, stderr=subprocess.STDOUT, stdout=subprocess.PIPE):
    return subprocess.Popen(
        exec_str, stderr=stderr, stdout=stdout, env=os.environ.copy()
    )


def ursula_single(playbook, args):
    exec_str = (
        'ursula {environment} {playbook} -u {login_user} --sudo {extra_args}'
    ).format(
        environment=args.env,
        playbook=playbook,
        login_user=args.login_user,
        extra_args=args.extra_ansible_args
    ).strip()

    if args.verbose:
        print("Executing: '%s'" % exec_str)
        sys.stdout.flush()

    process = popen(shlex.split(exec_str), stderr=None, stdout=None)
    stdout, stderr = process.communicate()

    if process.poll() is not 0:
        print('\nPlaybook %s exited with errors, exit code: '
              '%s\n' % (playbook, process.returncode), file=sys.stderr)
        sys.stderr.flush()

    return process.returncode


def ursula_parallel(process_name, playbook, args):
    exec_str = (
        'ursula {environment} {playbook} -u {login_user} --sudo {extra_args}'
    ).format(
        environment=args.env,
        playbook=playbook,
        login_user=args.login_user,
        extra_args=args.extra_ansible_args
    ).strip()

    if args.verbose:
        with lock:
            print("Executing: '%s'" % exec_str)
            sys.stdout.flush()

    with lock:
        print(
            "Running playbook '%s' in process %s." % (playbook, process_name)
        )
        sys.stdout.flush()

    logfile = '%s.log' % playbook.split('.')[0]
    process = popen(shlex.split(exec_str))

    stdout, stderr = process.communicate()

    f = open(logfile, 'wb')
    while True:
        f.wite(stdout)
        if process.poll() is not None:
            break
        time.sleep(5)
    f.close()

    if process.poll() is not 0:
        with lock:
            print("\nPlaybook '%s' exited with errors, exit code: "
                  "%s\n" % (playbook, process.returncode), file=sys.stderr)
            sys.stderr.flush()

    with lock:
        print(stdout)
        if args.verbose and process.returncode is 0:
            print("\nPlaybook '%s' complete.\n" % playbook)
        sys.stdout.flush()

    return process.returncode


def run_parallel(args):
    if args.verbose:
        print('Running playbooks in parallel.')
        sys.stdout.flush()

    num_procs = args.workers if args.workers else len(PLAYS_PARALLEL)
    pool = multiprocessing.Pool(processes=num_procs)
    results = []
    for idx, playbook in enumerate(PLAYS_PARALLEL):
        if args.verbose:
            print("Adding  '%s' to process pool." % playbook)
            sys.stdout.flush()

        result = pool.apply_async(ursula_parallel, args=[idx, playbook, args])
        results.append(result)

    if args.verbose:
        print('All playbooks added to process pool.')
        sys.stdout.flush()

    pool.close()

    if args.verbose:
        print('Waiting for processes to complete...')
        sys.stdout.flush()

    pool.join()

    results = [result.get(1) for result in results]
    if any(results):
        return 1
    else:
        return 0


def run_deploy(args):
    for play in PLAYS_INITIAL:
        with timer('serial play %s' % play):
            rc = ursula_single(play, args)
            if rc != 0:
                return rc

    with timer('parallel Ursula deploy'):
        rc = run_parallel(args)
        if rc != 0:
            return rc

    for play in PLAYS_FINAL:
        with timer('serial play %s' % play):
            rc = ursula_single(play, args)
            if rc != 0:
                return rc


def dispatch(args):
    if args.test:
        if args.verbose:
            print('Running test.')
        sys.exit(ursula_single(TEST_PLAY, args))
    elif args.cleanup:
        if args.verbose:
            print('Running cleanup.')
        sys.exit(ursula_single(CLEANUP_PLAY, args))
    elif args.upgrade:
        if args.verbose:
            print('Running upgrade.')
        sys.exit(ursula_single(UPGRADE_PLAY, args))
    elif args.deploy:
        if args.verbose:
            print('Running deploy.')
            sys.exit(run_deploy(args))


def parse_args():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test', action='store_true')
    group.add_argument('--deploy', action='store_true')
    group.add_argument('--cleanup', action='store_true')
    group.add_argument('--upgrade', action='store_true')
    parser.add_argument('--env', '--environment', default='envs/test')
    parser.add_argument('--login-user', default='ubuntu')
    parser.add_argument('-w', '--workers', type=int, default=0)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parser.add_argument('extra_ansible_args', nargs='?', default='')
    return parser.parse_args()


def main():
    args = parse_args()
    dispatch(args)


if __name__ == '__main__':
    with timer('main parallel test runner'):
        main()
