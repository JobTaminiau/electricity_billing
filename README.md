# coned-billing

Estimate monthly bills from an hourly load curve using Consolidated Edison tariffs.

## Required contents

The CSV file entered into the model must contain the following columns:

1. "ts" - timezone-aware timestamp (YYYY-MM-DD HH:MM±HH:MM)
2. "kw" - interval demand (kW)
