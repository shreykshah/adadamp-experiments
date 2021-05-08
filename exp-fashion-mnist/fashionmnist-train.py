import os
import sys
from pathlib import Path
from pprint import pprint
import itertools
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime
from time import time
import yaml
import traceback
import sys
import json
from copy import copy

import numpy as np
from distributed import Client, as_completed
from distributed.scheduler import KilledWorker

DIR = Path(__file__).absolute().parent
sys.path.append(str(DIR.parent))

import train

def _write(data: List[Dict[str, Any]], filename: str) -> bool:
    df = pd.DataFrame(data)
    df.to_parquet(filename, index=False)
    return True

def _dummy(**kwargs):
    return [{"time": time(), **kwargs}], [{"train": True}]


def _get_unique(series: pd.Series) -> Any:
    assert series.nunique() == 1
    return series.unique()[0]


if __name__ == "__main__":

    DATA_DIR = (
        Path("/mnt")
        / "ws"
        / "home"
        / "sshah"
        / "adadamp-experiments"
        / "exp-fashion-mnist"
        / "_data"
        / datetime.now().isoformat()[:10]
    )
    if not DATA_DIR.exists():
        DATA_DIR.mkdir()
    else:
        d = datetime.now().isoformat()[:10] + "-v2"
        DATA_DIR = DATA_DIR.parent / d
        DATA_DIR.mkdir()
    print(f"DATA_DIR = {DATA_DIR}")
    x = input("Continue? y/n : ")
    assert x.lower() in ["y", "n"]
    if x.lower() == "n":
        sys.exit(1)

    epochs = 200
    n_runs = 1
    seed_start = 1000

    already_finished = [
        f.name
        for f in DATA_DIR.glob("*.parquet")
        if "epochs" in pd.read_parquet(f).columns
        and pd.read_parquet(f).epochs.max() >= epochs - 5
    ]

    with open("hyperparams.json", "r") as f:
        params = json.load(f)
    for damp, param in params.items():
        param["damper"] = damp

    print("n_runs =", n_runs)
    cont = input("Ok? y/n : ")
    if cont.lower() == "n":
        sys.exit(1)

    client = Client()

    def submit(seed, **kwargs):
        import train
        #assert train.__version__ == "0.1"

        import adadamp
        #assert adadamp.__version__ == "0.1.4"

        return train.main(epochs=epochs, verbose=False, init_seed=seed, random_state=seed, tuning=False, **kwargs)

    futures = []
    seeds = np.arange(seed_start, seed_start + n_runs)
    dampers = ["geodamp", "adagrad", "geodamplr", "radadamp"]
    assert set(dampers).issubset(set(params.keys()))

    for damper in dampers:
        kwargs = params[damper]
        futures.extend(client.map(submit, seeds, **kwargs))

    for k, future in enumerate(as_completed(futures)):
        try:
            data, train_data = future.result()
        except:  # KilledWorker:
            # This is likely a problem with my code rather than with the
            # Dask cluster.
            #
            # https://stackoverflow.com/questions/46691675/what-do-killedworker-exceptions-mean-in-dask
            print("-" * 20)
            for info in sys.exc_info():
                print(info)
        else:
            print(f"writing training {k}")
            _write(data, str(DATA_DIR / f"{k}-test.parquet"))
            _write(train_data, str(DATA_DIR / f"{k}-train.parquet"))