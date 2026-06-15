"""Domain seed data — the ONLY place domain terms appear outside catalog rows.

Adding a future domain (wider tax, tender help) = adding an entry here; no
pipeline code changes (BRIEF: domain-as-config).

M2 scope: VAT registration manual + registration guides. The remaining
domestic-VAT roots (input tax, supply & consideration, flat rate, notices)
are appended at M5.
"""

SEEDS: dict[str, dict] = {
    "vat": {
        # hmrc_manual roots whose child_section_groups are walked recursively
        "manual_roots": [
            "/hmrc-internal-manuals/vat-registration-manual",
        ],
        # Search API queries (HMRC org filter applied in catalog.py).
        # Deliberately empty at M2: a broad "vat registration" query pulled in
        # 887 loosely-related docs including out-of-scope import/marketplace
        # VAT, which would defeat M4's abstention checks. M5 curates precise
        # per-topic queries (schemes, rates, input tax, returns, MTD).
        "search_queries": [],
        # explicit base_paths always included
        "pinned": [
            "/register-for-vat",
        ],
    },
}
