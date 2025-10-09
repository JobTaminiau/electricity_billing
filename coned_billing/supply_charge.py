"""
Supply charges are set by zone and service class and type. We retrieve the lookup table from
https://www.coned.com/en/accounts-billing/your-bill/rate-calculators/market-supply-charge
to get the relevant supply charges.
"""
import tempfile
import requests
import pandas as pd
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


URL = "https://cdne-dcxprod-east-rtcalc.azureedge.net/marketsupplycharges/LDS_APPND.CSV?sp=r&st=2023-10-11T20:42:07Z&se=2025-10-12T04:42:07Z&spr=https&sv=2022-11-02&sr=c&sig=EHduEN%2BRaNl7hReL85bq0W6JIQTD05snlrff6yKGiho%3D"

# at the moment, we're only looking at residential, small commercial and large commercial
target_codes = ['1', '2', '001', '002', '001   ', '002   ', '009CNV']

DATE_FROM = 20250101
DATE_TO = 20251006

# Create a session with retry logic
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=2,  # Wait 2, 4, 8 seconds between retries
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# Add headers to look more like a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    # Download the CSV with retry logic
    print("Downloading CSV file...")
    response = session.get(URL, headers=headers, timeout=30)
    response.raise_for_status()
    print("Download successful!")

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as temp_file:
        temp_file.write(response.text)
        temp_file_path = temp_file.name

    try:
        # Read the CSV with pandas
        df = pd.read_csv(temp_file_path)
        df_filtered = df[df['SC AND'].isin(target_codes)].copy()

        # Convert FROM DT to numeric if it isn't already
        df_filtered['FROM DT '] = pd.to_numeric(df_filtered['FROM DT '], errors='coerce')

        # Filter for 2025 and later

        df_filtered = df_filtered[df_filtered['FROM DT '] >= 20250000].copy()

        # Select only Zone J columns
        zone_j_columns = ['SC AND', 'FROM DT ', ' TO  DT ', 'TRIP',
                          'ALL HOURS.4', 'ALL HOURS.5',  # LT and HT ALL HOURS for Zone J
                          'ON PEAK  .4', 'ON PEAK  .5',  # LT and HT ON PEAK for Zone J
                          'OFF PEAK .4', 'OFF PEAK .5']  # LT and HT OFF PEAK for Zone J

        df_zone_j = df_filtered[zone_j_columns].copy()

        # Rename columns for clarity
        df_zone_j.columns = ['SC_TYPE', 'FROM_DATE', 'TO_DATE', 'TRIP',
                             'ALL_HOURS_LT', 'ALL_HOURS_HT',
                             'ON_PEAK_LT', 'ON_PEAK_HT',
                             'OFF_PEAK_LT', 'OFF_PEAK_HT']

        for sc_type in df_zone_j['SC_TYPE'].unique():
            df_type = df_zone_j[df_zone_j['SC_TYPE'] == sc_type]

            # Calculate average supply charges for 2025
            avg_all_hours_lt = df_type['ALL_HOURS_LT'].mean()
            avg_all_hours_ht = df_type['ALL_HOURS_HT'].mean()
            avg_on_peak_lt = df_type['ON_PEAK_LT'].mean()
            avg_on_peak_ht = df_type['ON_PEAK_HT'].mean()
            avg_off_peak_lt = df_type['OFF_PEAK_LT'].mean()
            avg_off_peak_ht = df_type['OFF_PEAK_HT'].mean()

            print(f"\n{'=' * 60}")
            print(f"Service Class Type: {sc_type}")
            print(f"{'=' * 60}")
            print(f"Number of billing periods: {len(df_type)}")
            print(f"\nAverage Supply Charges ($/kWh):")
            print(f"  ALL HOURS - Low Tension:  ${avg_all_hours_lt:.6f}")
            print(f"  ALL HOURS - High Tension: ${avg_all_hours_ht:.6f}")
            print(f"  ON PEAK - Low Tension:    ${avg_on_peak_lt:.6f}")
            print(f"  ON PEAK - High Tension:   ${avg_on_peak_ht:.6f}")
            print(f"  OFF PEAK - Low Tension:   ${avg_off_peak_lt:.6f}")
            print(f"  OFF PEAK - High Tension:  ${avg_off_peak_ht:.6f}")

    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)

except requests.exceptions.RequestException as e:
    print(f"Error downloading file: {e}")
    print("\nTip: If the download keeps failing, you can save the CSV locally")
    print("and modify the script to read from the local file instead.")