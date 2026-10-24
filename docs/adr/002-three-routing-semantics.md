# ADR 002: benchmark, navigation and exit-rooted analysis

Accepted 2026-10-24. Preserve the kit's exact anchor-based graph, connector penalties and free outside node for benchmark answers. The labeled train/dev dataset includes 137 A-to-B routes and 43 tours using outside.

Human navigation uses outside=none, validates furniture intersections and withholds unsupported geometry. It never turns the free benchmark outside node into a first-person route. Walking metres measure horizontal validated segments; floor transitions are separately announced. Exit-rooted impact uses outside=free to measure access to any exit, with separate general, step-free and width-profile results. Its distance changes include graph penalties and must not be described as physical walking distance.

Verification: fw eval differential; tests/test_insights.py; fw eval walkability --split dev --pairs 4. Route availability and route validity are reported separately.
