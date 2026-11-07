"""Hand-authored expected IDs for the fixed sample, independent of SearchService."""
ACTIVE_IDS = [
    "asg-csc10004-lab", "asg-csc10004-project", "asg-csc10005-lab", "asg-csc10005-project",
    "asg-ct-proposal", "asg-db-sql", "asg-english", "asg-network", "asg-overdue", "asg-update",
    "class-csc10004", "evt-beach", "evt-cancel", "evt-debate", "evt-delete", "evt-end-midnight",
    "evt-future-reg", "evt-green", "evt-missing-both", "evt-missing-end", "evt-missing-start",
    "evt-next-midnight", "evt-overlap", "evt-reg-after", "evt-reg-before", "evt-reg-exact",
    "evt-speaking", "evt-today", "exam-csc10005", "fee-english", "fee-hk1", "fee-installment",
    "fee-mixed", "personal-study", "sample-cross-field", "sample-description-only",
    "sample-literal", "sample-title-only",
]
EXAMPLES = (
    ("All six types, active, in ID order", {"sort": "id", "limit": 100}, ACTIVE_IDS),
    ("CSC10004 assignments due on the fixed day", {
        "filters": {"course": "CSC10004", "types": ["assignment"],
                    "deadline_within": ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]},
        "sort": "id"}, ["asg-csc10004-lab"]),
    ("Vietnamese text and five-point events", {
        "keyword": "tình nguyện", "filters": {"types": ["event"], "min_training_points": 5,
                                               "max_training_points": 5}, "sort": "id"},
     ["sample-description-only"]),
    ("Terms across title and description", {"keyword": "tình nguyện", "sort": "id"},
     ["sample-cross-field", "sample-description-only", "sample-title-only"]),
    ("Literal punctuation", {"keyword": "50%_! O'Reilly \\"}, ["sample-literal"]),
    ("Cancelled status", {"filters": {"statuses": ["cancelled"]}, "sort": "id"},
     ["asg-cancelled", "evt-cancelled"]),
    ("Stable course page", {"filters": {"course": "CSC10004"}, "sort": "id", "limit": 2, "offset": 1},
     ["asg-csc10004-project", "asg-overdue"]),
    ("No match", {"keyword": "quantum pineapple"}, []),
)
