#!/bin/env python3
from typing import List, Optional
import subprocess
import tomllib
import os
import argparse
import sys

from pydantic import BaseModel, ConfigDict
from colorama import Fore, Style
from dotenv import load_dotenv

def print_status(text):
    print(f"{Fore.YELLOW}{text}{Style.RESET_ALL}")

def print_success(text):
    print(f"{Fore.GREEN}{text}{Style.RESET_ALL}")

def print_error(text):
    print(f"{Fore.RED}{text}{Style.RESET_ALL}")

def fatal_error(message: str, help: Optional[str] = None):
    print_error(message)
    print()
    if help:
        print(help)
    sys.exit(1)

class ResticError(Exception):
    def __init__(self, message, output, error, retval):
        super().__init__(message)
        self.output = output
        self.error = error
        self.retval = retval

class RepositoryError(Exception):
    pass

def restic(
    url: str,
    password: str,
    command: str,
    args: Optional[List[str]] = None,
    identity_file: Optional[str] = None
):
    if args is None:
        args = []
        
    cmd = ["restic", "-r", url, command, *args]
        
    env = os.environ.copy()
    env["RESTIC_PASSWORD"] = password

    if identity_file:
        cmd.extend(["-o", f'sftp.args=-i {identity_file}'])

    try:
        res = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            env=env,
        )
        if res.returncode != 0:
            raise ResticError(
                f"Failed running restic command '{command}'",
                res.stdout,
                res.stderr,
                res.returncode,
            )
    except FileNotFoundError:
        fatal_error("Restic command not found", "Make sure restic is available")

class Repository(BaseModel):
    name: str
    description: str
    method: str = "local"
    path: Optional[str] = None
    password: Optional[str] = None
    password_env: Optional[str] = None
    host: Optional[str] = None
    user: Optional[str] = None
    identity_file: Optional[str] = None

    class Config:
        extra = 'forbid'

    def get_password(self):
        if self.password is not None:
            return self.password
        if self.password_env is not None:
            try:
                return os.environ[self.password_env]
            except KeyError:
                fatal_error(f"Failed to find password env variable with name {self.password_env}")
        return self.password or "123"

    def get_url(self):
        if self.method == "local":
            if not self.path:
                raise RepositoryError(f"No path set for local repository '{self.name}'")
            return self.path
        elif self.method == "sftp":
            if not self.path:
                raise RepositoryError(f"No path set for SFTP repository '{self.name}'")
            if not self.host:
                raise RepositoryError(f"No host set for SFTP repository '{self.name}'")
            if self.user:
                return f"sftp:{self.user}@{self.host}:{self.path}"
            else:
                return f"sftp:{self.host}:{self.path}"
        else:
            raise RepositoryError(f"Unsupported repository access method: '{self.method}'")

    def _restic(self, cmd: str, args: Optional[List[str]] = None):
        restic(self.get_url(), self.get_password(), cmd, args, identity_file=self.identity_file)

    def initialize(self):
        """Initialize repo if not already initialized"""
        self._restic("init")

    def check(self):
        """Run health-check on repository"""
        self._restic("check")

    def backup(self, paths: List[str], host: Optional[str]=None):
        args = [*paths]
        if host:
            args.extend(["--host", host])
        self._restic("backup", args)
         
class Operation(BaseModel):
    host: Optional[str] = None
    path: str
    description: str
    repos: List[str]
    
    class Config:
        extra = 'forbid'


def read_config(path: str):
    with open(path, "rb") as f:
        data = tomllib.load(f)

    repos: List[Repository] = []
    backups: List[Operation] = []

    if "repo" in data:
        for name, cfg in data["repo"].items():
            repos.append(Repository(name=name, **cfg))

    if "backup" in data:
        for name, cfg in data["backup"].items():
            backups.append(Operation(**cfg))

    return repos, backups 
    

def cmd_backup(args):
    repos, backups = read_config(args.config)

    backups_by_host = {}

    for b in backups:
        if b.host in backups_by_host:
            backups_by_host[b.host].append(b)
        else:
            backups_by_host[b.host] = [b]

    for repo in repos:
        for host in backups_by_host:
            repo_backups = [b for b in backups_by_host[host] if repo.name in b.repos]
            paths = [b.path for b in repo_backups]
            print_status(f"Backup as host '{host}' to {repo.name}:")
            for p in paths:
                print_status(f" - {p}")
            repo.backup(paths, host=host)

def cmd_init(args):
    repos, _ = read_config(args.config)

    success = []
    fails = []
    for repo in repos:
        print_status(f"Initializing {repo.method} repository '{repo.name}'")
        try:
            repo.initialize()
            success.append(repo.name)
        except ResticError:
            fails.append(repo.name)
            
    if len(success) > 0:
        print_success(f"Successfully initialized {len(success)} repositories:")
        for r in success:
            print(f" - {r}")
        print()

    if len(fails) > 0:
        print_error(f"Failed to initialize {len(fails)} repositories:")
        for r in fails:
            print(f" - {r}")
        print()

def cmd_check(repos: List[Repository]):
    repos, _ = read_config(args.config)

    for repo in repos:
        print_status(f"Run health check for {repo.method} repository '{repo.name}'")
        repo.check()

load_dotenv()

parser = argparse.ArgumentParser(prog="Backup Service")
subparsers = parser.add_subparsers(help="command", required=True)

parser_init = subparsers.add_parser("init", help="Initialize repositories")
parser_init.add_argument("-c", "--config", help="Config file", required=True)
parser_init.set_defaults(func=cmd_init)

parser_check = subparsers.add_parser("check", help="Run health checks on repositories")
parser_check.add_argument("-c", "--config", help="Config file", required=True)
parser_check.set_defaults(func=cmd_check)

parser_backup = subparsers.add_parser("backup", help="Perform backup")
parser_backup.add_argument("-c", "--config", help="Config file", required=True)
parser_backup.set_defaults(func=cmd_backup)

args = parser.parse_args()
args.func(args)
