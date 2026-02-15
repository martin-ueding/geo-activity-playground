import json

import pandas as pd


def main() -> None:
    df = pd.read_excel("strava-csv-columns/mapping.ods")

    with open("geo_activity_playground/importers/strava-csv-mapping.json", "w") as f:
        json.dump(
            {
                de: en
                for de, en in zip(df["German"], df["English"])
                if de and de != "NaN"
            },
            f,
            indent=4,
            ensure_ascii=False,
        )


if __name__ == "__main__":
    main()
