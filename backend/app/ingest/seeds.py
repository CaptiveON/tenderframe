"""Domain seed data — the ONLY place domain terms appear outside catalog rows.

Adding a future domain (wider tax, tender help) = adding an entry here; no
pipeline code changes (BRIEF: domain-as-config).

M5 scope: full domestic VAT for SMEs — registration, schemes, rates, input
tax, returns, MTD. Sourced from HMRC manuals (recursively walked) + SME-facing
guides. search_queries stays empty on purpose: a broad VAT search pulls in
out-of-scope import/customs/marketplace guidance, which would make the system
answer questions it must abstain on. Out of scope (must abstain): customs/
import-export VAT, corporation tax, PAYE.
"""

SEEDS: dict[str, dict] = {
    "vat": {
        # hmrc_manual roots whose child_section_groups are walked recursively.
        # All domestic-VAT manuals; import/customs manuals deliberately excluded.
        "manual_roots": [
            "/hmrc-internal-manuals/vat-registration-manual",
            "/hmrc-internal-manuals/vat-input-tax",
            "/hmrc-internal-manuals/vat-flat-rate-scheme",
        ],
        # broad search disabled — see module docstring
        "search_queries": [],
        # SME-facing guides/answers, one per domestic-VAT area
        "pinned": [
            "/register-for-vat",              # registration
            "/how-vat-works",                 # rates / basics
            "/vat-rates",                     # rates
            "/vat-flat-rate-scheme",          # schemes: flat rate
            "/vat-cash-accounting-scheme",    # schemes: cash accounting
            "/vat-annual-accounting-scheme",  # schemes: annual accounting
            "/submit-vat-return",             # returns
            "/charge-reclaim-record-vat",     # input tax recovery + records/MTD
        ],
    },
}
