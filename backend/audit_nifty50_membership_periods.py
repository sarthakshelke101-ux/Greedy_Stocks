
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = (
    ROOT / "database" / "processed" / "constituents"
)

SNAPSHOT_FILE = (
    DATA_DIR / "nifty50_constituent_snapshots.csv"
)

EVENT_FILE = (
    DATA_DIR / "nifty50_membership_events_reconciled.csv"
)

OUTPUT_FILE = (
    DATA_DIR / "nifty50_membership_observation_audit_v2.csv"
)


def main():

    snapshots = pd.read_csv(
        SNAPSHOT_FILE,
        dtype=str,
        keep_default_na=False,
    )

    events = pd.read_csv(
        EVENT_FILE,
        dtype=str,
        keep_default_na=False,
    )

    snapshots["report_month"] = pd.PeriodIndex(
        snapshots["report_month"],
        freq="M",
    )

    all_months = sorted(
        snapshots["report_month"].unique()
    )

    if len(all_months) != 19:
        raise ValueError(
            f"Expected 19 months, found {len(all_months)}"
        )

    if snapshots.duplicated(
        ["report_month", "Security Symbol"]
    ).any():
        raise ValueError(
            "Duplicate symbol/month observations found."
        )

    records = []

    for symbol, group in snapshots.groupby(
        "Security Symbol"
    ):

        observed_months = sorted(
            group["report_month"].unique()
        )

        first_month = observed_months[0]
        last_month = observed_months[-1]

        expected_internal_months = [
            month
            for month in all_months
            if first_month <= month <= last_month
        ]

        internal_missing_months = [
            str(month)
            for month in expected_internal_months
            if month not in observed_months
        ]

        related_events = events[
            (events["old_symbol"] == symbol)
            | (events["new_symbol"] == symbol)
        ]

        event_details = []

        for event in related_events.itertuples(index=False):

            event_details.append(
                f"{event.event_date}: "
                f"{event.old_symbol}->{event.new_symbol} "
                f"({event.event_type})"
            )

        records.append({

            "symbol": symbol,

            "security_name": group.iloc[-1][
                "Security Name"
            ],

            "first_observed_month": str(first_month),

            "last_observed_month": str(last_month),

            "observed_month_count": len(
                observed_months
            ),

            "internal_missing_month_count": len(
                internal_missing_months
            ),

            "internal_missing_months": ", ".join(
                internal_missing_months
            ),

            "related_event_count": len(
                related_events
            ),

            "related_events": " | ".join(
                event_details
            ),

            "observation_status": (
                "CONTIGUOUS"
                if not internal_missing_months
                else "INTERNAL_GAP_REQUIRES_REVIEW"
            ),

            "start_date_status": (
                "OBSERVATION_BOUNDARY_ONLY"
            ),

            "end_date_status": (
                "OBSERVATION_BOUNDARY_ONLY"
            ),

        })

    result = pd.DataFrame(records)

    result = result.sort_values(
        "symbol"
    ).reset_index(drop=True)

    if len(result) != 54:
        raise ValueError(
            f"Expected 54 instruments, found {len(result)}"
        )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("=" * 70)
    print("NIFTY 50 MEMBERSHIP AUDIT V2")
    print("=" * 70)

    print("Historical instruments:", len(result))

    print(
        "Instruments with internal gaps:",
        (
            result["internal_missing_month_count"] > 0
        ).sum()
    )

    print(
        "Contiguous observation histories:",
        (
            result["observation_status"] == "CONTIGUOUS"
        ).sum()
    )

    print("\nINTERNAL GAPS")

    gaps = result[
        result["internal_missing_month_count"] > 0
    ]

    if gaps.empty:
        print("No internal observation gaps found.")
    else:
        print(
            gaps[
                [
                    "symbol",
                    "first_observed_month",
                    "last_observed_month",
                    "internal_missing_months",
                ]
            ].to_string(index=False)
        )

    print("\nTATA MOTORS")

    print(
        result[
            result["symbol"].isin(
                ["TATAMOTORS", "TMPV"]
            )
        ][
            [
                "symbol",
                "first_observed_month",
                "last_observed_month",
                "observed_month_count",
                "related_events",
            ]
        ].to_string(index=False)
    )

    print("\nSaved:", OUTPUT_FILE)

    print("\nAUDIT V2 COMPLETE")


if __name__ == "__main__":
    main()
