import pathlib
from typing import Callable

import pandas as pd


def cache_parquet(
    loader: Callable[[pathlib.Path], pd.DataFrame]
) -> Callable[[pathlib.Path], pd.DataFrame]:
    def wrapped(path: pathlib.Path) -> pd.DataFrame:
        cache_path = (
            pathlib.Path.cwd() / "Cache" / loader.__name__ / f"{hash(path)}.parquet"
        )
        cache_path.parent.mkdir(exist_ok=True, parents=True)
        if cache_path.exists() and cache_path.stat().st_mtime > path.stat().st_mtime:
            return pd.read_parquet(cache_path)
        else:
            df = loader(path)
            df.to_parquet(cache_path)
            # Ensure that the file can be loaded again.
            pd.read_parquet(cache_path)
            return df

    return wrapped
