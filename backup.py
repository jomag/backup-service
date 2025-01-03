#!/bin/env python3
from typing import List, Optional
import subprocess
import tomllib
import os

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

    print("Running command: ", cmd)
    res = subprocess.run(
        cmd,
        capture_output=False,
        text=True,
        env=env,
    )

    if res.returncode != 0:
        raise ResticError(f"Failed running restic command '{command}'", res.stdout, res.stderr, res.returncode)

class Repository:
    def __init__(
        self,
        name: str,
        description: str,
        method: str = "local",
        path: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        user: Optional[str] = None,
        identity_file: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.method = method
        self.path = path
        self.password = password
        self.host = host
        self.user = user
        self.identity_file = identity_file

    def get_password(self):
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
        restic(self.get_url(), self.get_password(), cmd, identity_file=self.identity_file)

    def initialize(self):
        """Initialize repo if not already initialized"""
        self._restic("init")

    def check(self):
        """Run health-check on repository"""
        self._restic("check")
         
class Operation:
    def __init__(
        self,
        directory: str,
        description: str,
        repos: List[str]
    ):
        self.directory = directory
        self.description = description
        self.repos = repos

def read_config(path: str):
    with open(path, "rb") as f:
        data = tomllib.load(f)

    if "repo" in data:
        for name, repo in data["repo"].items():
            print(name, repo)

    if "backup" in data:
        for name, backup in data["backup"].items():
            print(name, backup)

    print(data) 
    

def cmd_backup(ops: List[Operation], repos: List[Repository]):
    for repo in repos:
        try:
            repo.check()
        except ResticError:
            print("Health check of repo failed. Try initializing.")
            repo.initialize()
            repo.check()

def cmd_initialize(repos: List[Repository]):
    success = []
    fails = []
    for repo in repos:
        try:
            repo.initialize()
            success.append(repo.name)
        except ResticError:
            fails.append(repo.name)
    print(f"Successfully initialized {len(success)} repositories:", ", ".join(success))
    print(f"Failed to initialize {len(fails)} repositories:", ", ".join(fails))
            
            

def cmd_health_check(repos: List[Repository]):
    pass

read_config("backup.toml")


#cmd_initialize(repositories)
# cmd_backup(operations, repositories)

