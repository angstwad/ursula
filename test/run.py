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
import shlex
import subprocess
import multiprocessing

from argparse import ArgumentParser


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


def get_login_user():
    login_user = os.environ.get('LOGIN_USER')
    if not login_user:
        print('\nEnv var LOGIN_USER not set!\n', file=sys.stderr)
        sys.exit(1)
    return login_user


def popen(exec_str, stderr=subprocess.STDOUT, stdout=subprocess.PIPE,
          wait=True):
    process = subprocess.Popen(exec_str, stderr=stderr, stdout=stdout)
    exitcode = None
    if wait:
        exitcode = process.wait()
    return process, exitcode


def ursula_single(playbook, args):
    login_user = get_login_user()
    exec_str = (
        'ursula {environment} {playbook} -u {login_user} --sudo {extra_args}'
    ).format(
        environment=args.env,
        playbook=playbook,
        login_user=login_user,
        extra_args=args.extra_ansible_args
    ).strip()

    if args.verbose:
        print("Executing: '%s'" % exec_str)

    process, exitcode = popen(shlex.split(exec_str), stderr=None, stdout=None)

    if exitcode is not 0:
        print('\nPlaybook %s exited with errors, exit code: '
              '%s\n' % (playbook, exitcode), file=sys.stderr)


def ursula_parallel(process_name, playbook, args):
    login_user = get_login_user()
    exec_str = (
        'ursula {environment} {playbook} -u {login_user} --sudo {extra_args}'
    ).format(
        environment=args.env,
        playbook=playbook,
        login_user=login_user,
        extra_args=args.extra_ansible_args
    ).strip()

    if args.verbose:
        with lock:
            print("Executing: '%s'" % exec_str)

    with lock:
        print("Running playbook '%s' in process %s." % (playbook, process_name))

    process, exitcode = popen(shlex.split(exec_str))
    if exitcode is not 0:
        with lock:
            print('\nPlaybook %s exited with errors, exit code: '
                  '%s\n' % (playbook, exitcode), file=sys.stderr)

    with lock:
        print(process.stdout.read())


def run_parallel(args):
    if args.verbose:
        print('Running playbooks in parallel.')

    num_procs = args.workers if args.workers else len(PLAYS_PARALLEL)
    pool = multiprocessing.Pool(processes=num_procs)
    for idx, playbook in enumerate(PLAYS_PARALLEL):
        if args.verbose:
            print("Adding  '%s' to process pool." % playbook)

        pool.apply_async(ursula_parallel, args=[idx, playbook, args])

    if args.verbose:
        print('All playbooks added to process pool.')

    pool.close()

    if args.verbose:
        print('Waiting for processes to complete...')
    pool.join()


def run_deploy(args):
    for play in PLAYS_INITIAL:
        ursula_single(play, args)

    run_parallel(args)

    for play in PLAYS_FINAL:
        ursula_single(play, args)


def dispatch(args):
    if args.test:
        if args.verbose:
            print('Running test.')
        ursula_single(TEST_PLAY, args.extra_ansible_args)
    elif args.cleanup:
        if args.verbose:
            print('Running cleanup.')
        ursula_single(CLEANUP_PLAY, args.extra_ansible_args)
    elif args.upgrade:
        if args.verbose:
            print('Running upgrade.')
        ursula_single(UPGRADE_PLAY, args.extra_ansible_args)
    elif args.deploy:
        if args.verbose:
            print('Running deploy.')
        run_deploy(args)


def parse_args():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test', action='store_true')
    group.add_argument('--deploy', action='store_true')
    group.add_argument('--cleanup', action='store_true')
    group.add_argument('--upgrade', action='store_true')
    parser.add_argument('--env', '--environment', default='envs/test')
    parser.add_argument('-w', '--workers', type=int, default=0)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parser.add_argument('extra_ansible_args', nargs='?', default='')
    return parser.parse_args()


def main():
    args = parse_args()
    dispatch(args)


if __name__ == '__main__':
    main()
