import os
from pathlib import Path

import dotenv
import yaml
from dotmap import DotMap
from src.etc.pattern import singleton


def override_with_env(dotmap_obj: DotMap, prefix: str = ""):

    for key, value in dotmap_obj.items():
        env_var_name = (prefix + "_" if prefix else "") + key.upper()

        if isinstance(value, DotMap):
            override_with_env(value, env_var_name)
        else:
            env_val = os.getenv(env_var_name)
            if env_val is not None:
                dotmap_obj[key] = env_val


@singleton
class IConfig:
    DEFAULT_UMAP = dict(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine")

    DEFAULT_PCA = dict()

    DEFAULT_HDBSCAN = dict()

    DEFAULT_KMEANS = dict()

    def __init__(self):

        config_path = Path(__file__).parent.parent.parent / "config.yaml"
        try:
            with open(config_path, "r", encoding="utf-8") as fp:
                raw_config = yaml.safe_load(fp)
                config = DotMap(raw_config or {})
        except FileNotFoundError:
            config = DotMap()

        dotenv.load_dotenv()
        override_with_env(config)

        for k, v in config.items():
            setattr(self, k, v)


Config = IConfig()
__all__ = ["Config"]