from pathlib import Path

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
            split_filename = self.__file.split(".")
            filename = f"{split_filename[0]}_{self.__version}.{split_filename[1]}"
            download_url = f"https://releases.service.couchbase.com/builds/releases/mobile/{self.__project}/{self.__version}/{filename}"
            print(f"Downloading CBL from {download_url}")
        else:
            split_filename = self.__file.split(".")
            filename = f"{split_filename[0]}_{self.__version}-{self.__build}.{split_filename[1]}"
            download_url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{self.__project}/{self.__version}/{self.__build}/{filename}"
            print(f"Downloading CBL from {download_url}")

        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        download_progress_bar(response, location)
        print("Done")
