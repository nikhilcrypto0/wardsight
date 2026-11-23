"""Ward sizes derived from the planter, so tests do not hardcode numbers that change with the plan."""

from wardsight.planter import EXTRA_COUNTS, GROUP_COUNTS

DEV_CHARTS = sum(GROUP_COUNTS["dev"].values()) + sum(EXTRA_COUNTS.values())
ALL_CHARTS = DEV_CHARTS + sum(GROUP_COUNTS["heldout"].values())
FLAGGED_GROUPS = ("missing", "unsupported", "unspecified", "conflicting")
DEV_FLAGS = sum(n for g, n in {**GROUP_COUNTS["dev"], **EXTRA_COUNTS}.items() if g in FLAGGED_GROUPS)
