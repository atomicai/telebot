import os
from pathlib import Path

import dotenv
from envyaml import EnvYAML
from loguru import logger

from src.etc.pattern import singleton


@singleton
class IConfig:
    DEFAULT_UMAP = dict(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine")

    DEFAULT_PCA = dict()

    DEFAULT_HDBSCAN = dict()

    DEFAULT_KMEANS = dict()

    def __init__(self):
        logger.info(
            f"IConfig | path to `config.yaml` = [{str(Path(os.getcwd()) / 'config.yaml')}]"
        )
        config = dict(EnvYAML(Path(os.getcwd()) / "config.yaml"))
        logger.info(
            f"/CONFIGURING | From config.yaml loaded K=[{config.keys()}] value(s)"
        )
        for k, v in config.items():
            if k.startswith("_"):
                continue
            setattr(self, k, v)
            logger.info(f"/CONFIGURING | {k}=[{v}]")
        dotenv.load_dotenv()


Config = IConfig()


__all__ = ["Config"]
