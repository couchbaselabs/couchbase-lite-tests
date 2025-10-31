from pathlib import Path

import click
import requests

from environment.aws.common.io import download_progress_bar


class CBLLibraryDownloader:
    def __init__(self, project: str, file: str, version: str, build: int = 0):
        self.__project = project
        self.__file = file
        self.__version = version
        self.__build = build

    def download(self, location: Path) -> None:
        """
        Download the CBL library from the latest builds server.
        """
        if self.__build == 0:
            download_url = f"https://releases.service.couchbase.com/builds/releases/mobile/{self.__project}/{self.__version}/{self.__file}"
        else:
            download_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{self.__project}/{self.__version}/{self.__build}/{self.__file}"

        click.echo(f"Downloading CBL from {download_url}")
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        download_progress_bar(response, location)
        click.echo("Done")
