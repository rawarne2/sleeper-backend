import requests
import os
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import date, datetime
import csv
import sys
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import json
import re

# this is just the script to scrape and put in csv. app.py duplicates this logic.


def get_user_input():
    # Prompt for redraft league (boolean-like)
    while True:
        redraft_input = input(
            "Is your league a redraft league? Please enter 'True' or 'False': ").strip().lower()
        if redraft_input in ['true', 't', 'yes', 'y', '1']:
            is_redraft = True
            break
        elif redraft_input in ['false', 'f', 'no', 'n', '0']:
            is_redraft = False
            break
        else:
            print("Invalid input. Please enter 'True' or 'False'.")

    # Prompt for league format
    while True:
        format_input = input(
            "What is your league format? Please enter '1QB' or 'SF': ").strip().upper()
        if format_input in ['1QB', '1']:
            league_format = '1QB'
            break
        elif format_input in ['SF', 'SUPERFLEX', 'SUPER FLEX', 'S']:
            league_format = 'SF'
            break
        else:
            print("Invalid input. Please enter '1QB' or 'SF'.")

    # Prompt for TEP if not redraft
    tep = 0
    if not is_redraft:
        while True:
            tep_input = input(
                "Is there a Tight End Premium (TEP)? Please enter '0' for None, '1' for TE+, '2' for TE++, or '3' for TE+++: ").strip()
            if tep_input in ['0', '1', '2', '3']:
                tep = int(tep_input)
                break
            else:
                print("Invalid input. Please enter 0, 1, 2, or 3.")

    # Prompt for S3 upload - simplified to just yes/no
    while True:
        s3_upload_input = input(
            "Do you want to upload the CSV to S3? (yes/no): ").strip().lower()
        if s3_upload_input in ['yes', 'y', '1', 'true', 't']:
            s3_upload = True
            break
        elif s3_upload_input in ['no', 'n', '0', 'false', 'f']:
            s3_upload = False
            break
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")

    s3_bucket = os.getenv('S3_BUCKET')
    s3_key = "ktc.csv"

    return is_redraft, league_format, tep, s3_upload, s3_bucket, s3_key


def fetch_ktc_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"HTTP error while fetching {url}: {e}")
        sys.exit(1)


def extract_players_array(html_content):
    """Extract the playersArray from the JavaScript in the HTML source"""
    try:
        # Look for the playersArray definition in the script tags
        pattern = r'var playersArray = (\[.*?\]);'
        match = re.search(pattern, html_content, re.DOTALL)

        if not match:
            print("Could not find playersArray in HTML source")
            return []

        # Parse the JavaScript array as JSON
        players_json = match.group(1)
        players_array = json.loads(players_json)
        return players_array

    except (json.JSONDecodeError, AttributeError) as e:
        print(f"Error parsing playersArray: {e}")
        return []


def parse_dynasty_player(player_obj, league_format):
    """Parse a dynasty player object from the playersArray"""
    try:
        # Determine if this is 1QB or SF format
        is_1qb = league_format == '1QB'
        values = player_obj.get('oneQBValues', {}) if is_1qb else player_obj.get(
            'superflexValues', {})

        # Extract basic player info
        player_name = player_obj.get('playerName', '')
        position = player_obj.get('position', '')
        team = player_obj.get('team', '')
        age = player_obj.get('age')
        rookie = "Yes" if player_obj.get('rookie', False) else "No"

        # Extract values and rankings
        value = values.get('value', 0)
        rank = values.get('rank')

        # Extract trend
        overall_trend = values.get('overallTrend', 0)
        trend_str = f"+{overall_trend}" if overall_trend > 0 else str(
            overall_trend) if overall_trend < 0 else "0"

        # Extract tier
        tier = values.get('overallTier')
        tier_str = f"Tier {tier}" if tier else ""

        # Extract positional rank
        pos_rank = values.get('positionalRank')
        position_rank = f"{position}{pos_rank}" if pos_rank else ""

        return {
            "Player Name": player_name,
            "Position": position,
            "Team": team,
            "Value": value,
            "Age": age,
            "Rookie": rookie,
            "Rank": rank,
            "Trend": trend_str,
            "Tier": tier_str,
            "Position Rank": position_rank
        }

    except Exception as e:
        print(
            f"Error parsing dynasty player {player_obj.get('playerName', 'Unknown')}: {e}")
        return None


def parse_fantasy_player(player_obj, league_format):
    """Parse a fantasy/redraft player object from the playersArray"""
    try:
        # Determine if this is 1QB or SF format
        is_1qb = league_format == '1QB'
        values = player_obj.get('oneQBValues', {}) if is_1qb else player_obj.get(
            'superflexValues', {})

        # Extract basic player info
        player_name = player_obj.get('playerName', '')
        position = player_obj.get('position', '')
        team = player_obj.get('team', '')
        age = player_obj.get('age')
        rookie = "Yes" if player_obj.get('rookie', False) else "No"

        # Extract values and rankings
        value = values.get('value', 0)
        rank = values.get('rank')

        # Extract trend
        overall_trend = values.get('overallTrend', 0)
        trend_str = f"+{overall_trend}" if overall_trend > 0 else str(
            overall_trend) if overall_trend < 0 else "0"

        # Extract tier
        tier = values.get('overallTier')
        tier_str = f"Tier {tier}" if tier else ""

        # Extract positional rank
        pos_rank = values.get('positionalRank')
        position_rank = f"{position}{pos_rank}" if pos_rank else ""

        return {
            "Player Name": player_name,
            "Position": position,
            "Team": team,
            "RdrftValue": value,
            "Age": age,
            "Rookie": rookie,
            "RdrftRank": rank,
            "RdrftTrend": trend_str,
            "RdrftTier": tier_str,
            "RdrftPosition Rank": position_rank
        }

    except Exception as e:
        print(
            f"Error parsing fantasy player {player_obj.get('playerName', 'Unknown')}: {e}")
        return None


def scrape_players_from_array(url, league_format, is_redraft=False):
    """Scraping function that uses the playersArray from JavaScript source"""
    try:
        print(f"Fetching data from: {url}")
        response = fetch_ktc_page(url)

        # Extract playersArray from the HTML source
        players_array = extract_players_array(response.text)
        if not players_array:
            print("No players found in playersArray")
            return []

        print(f"Found {len(players_array)} players in playersArray")

        # Parse players based on whether it's dynasty or fantasy
        players = []
        for player_obj in players_array:
            if is_redraft:
                parsed_player = parse_fantasy_player(player_obj, league_format)
            else:
                parsed_player = parse_dynasty_player(player_obj, league_format)

            if parsed_player:
                players.append(parsed_player)

        print(f"Successfully parsed {len(players)} players")
        return players

    except Exception as e:
        print(f"Error in scrape_players_from_array: {e}")
        return []


def merge_dynasty_fantasy_data(dynasty_players, fantasy_players, league_format):
    """Merge dynasty and fantasy player data"""
    try:
        # Create a dictionary of fantasy players by name for quick lookup
        fantasy_dict = {player["Player Name"]                        : player for player in fantasy_players}

        # Add fantasy data to dynasty players
        merged_players = []
        for dynasty_player in dynasty_players:
            player_name = dynasty_player["Player Name"]

            # Find matching fantasy player
            fantasy_player = fantasy_dict.get(player_name)
            if fantasy_player:
                # Merge the data
                merged_player = dynasty_player.copy()

                # Add fantasy-specific fields - simplified field names
                merged_player["RdrftValue"] = fantasy_player.get("RdrftValue")
                merged_player["RdrftPosition Rank"] = fantasy_player.get(
                    "RdrftPosition Rank")

                merged_player["RdrftRank"] = fantasy_player.get("RdrftRank")
                merged_player["RdrftTrend"] = fantasy_player.get("RdrftTrend")
                merged_player["RdrftTier"] = fantasy_player.get("RdrftTier")

                merged_players.append(merged_player)
            else:
                # Include dynasty player even if no fantasy match
                merged_players.append(dynasty_player)

        print(
            f"Merged {len(merged_players)} players from dynasty and fantasy data")
        return merged_players

    except Exception as e:
        print(f"Error merging dynasty and fantasy data: {e}")
        return dynasty_players  # Return dynasty players as fallback


def scrape_ktc(is_redraft, league_format):
    """Main scraping function using the playersArray approach"""
    try:
        # Determine URLs based on league type
        if is_redraft:
            dynasty_url = "https://keeptradecut.com/dynasty-rankings"
            fantasy_url = "https://keeptradecut.com/fantasy-rankings"

            # First get dynasty data
            print(f"Scraping dynasty data for {league_format} format...")
            dynasty_players = scrape_players_from_array(
                dynasty_url, league_format, is_redraft=False)

            # Then get fantasy data
            print(f"Scraping fantasy data for {league_format} format...")
            fantasy_players = scrape_players_from_array(
                fantasy_url, league_format, is_redraft=True)

            # Merge the data
            players = merge_dynasty_fantasy_data(
                dynasty_players, fantasy_players, league_format)

        else:
            # Just get dynasty data
            dynasty_url = "https://keeptradecut.com/dynasty-rankings"
            print(f"Scraping dynasty data for {league_format} format...")
            players = scrape_players_from_array(
                dynasty_url, league_format, is_redraft=False)

        print(f"Total players after scraping: {len(players)}")
        return players

    except Exception as e:
        print(f"Error in scrape_ktc: {e}")
        return []


def upload_to_s3(file_path, bucket_name, object_key):
    """
    Upload a file to an S3 bucket

    Parameters:
    file_path (str): The path to the file to upload
    bucket_name (str): The name of the S3 bucket
    object_key (str): The S3 object key (path/filename.csv)

    Returns:
    bool: True if upload was successful, False otherwise
    """
    try:
        s3_client = boto3.client('s3')
        print(f"Uploading {file_path} to s3://{bucket_name}/{object_key}...")
        s3_client.upload_file(file_path, bucket_name, object_key)
        print(
            f"Successfully uploaded {file_path} to s3://{bucket_name}/{object_key}")
        return True
    except NoCredentialsError:
        print("Error: AWS credentials not found. Make sure you've configured your AWS credentials.")
        return False
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error uploading to S3: {e}")
        return False


def export_to_csv(players, league_format, tep, is_redraft, s3_upload=False, s3_bucket=None, s3_key=None):
    timestamp = f"Updated {date.today().strftime('%m/%d/%y')} at {datetime.now().strftime('%I:%M%p').lower()}"
    if is_redraft:
        header = [timestamp, "Rank", "Trend", "Tier",
                  "Position Rank", "Position", "Team", "RdrftValue", "Age", "Rookie"]
        value_cols = ["RdrftValue"]
        rows_data = [
            [player["Player Name"], player.get("RdrftRank"), player.get("RdrftTrend", "0"), player.get("RdrftTier"),
             player.get(
                 "RdrftPosition Rank"), player["Position"], player["Team"],
             player.get("RdrftValue", 0), player.get("Age"), player.get("Rookie")]
            for player in players if player.get("RdrftValue", 0) > 0
        ]
    else:
        header = [timestamp, "Rank", "Trend", "Tier",
                  "Position Rank", "Position", "Team", "Value", "Age", "Rookie"]
        value_cols = ["Value"]
        rows_data = [
            [player["Player Name"], player.get("Rank"), player.get("Trend", "0"), player.get("Tier"),
             player.get("Position Rank"), player["Position"], player["Team"],
             player.get("Value", 0), player.get("Age"), player.get("Rookie")]
            for player in players if player.get("Value", 0) > 0
        ]
    rows_data.insert(0, header)
    # TEP adjustments are no longer needed with the current scraping approach
    # The playersArray already contains the correct TEP-adjusted values

    # Remove call to make_unique and instead sort by value and then by rank
    # If two players have the same value, the one with better rank (lower number) will come first
    value_col = value_cols[0]
    value_idx = header.index(value_col)
    rank_idx = header.index("Rank")

    # Sort first by value (descending), then by rank (ascending) when values are equal
    rows_data = [header] + sorted(rows_data[1:],
                                  key=lambda x: (
                                      x[value_idx], -float(x[rank_idx]) if x[rank_idx] is not None else float('inf')),
                                  reverse=True)

    csv_filename = 'ktc.csv'
    with open(csv_filename, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerows(rows_data)
    print(
        f"Data exported to {csv_filename} on {date.today().strftime('%B %d, %Y')} successful.")

    # Upload to S3 if requested
    if s3_upload and s3_bucket and s3_key:
        upload_to_s3(csv_filename, s3_bucket, s3_key)


if __name__ == "__main__":
    is_redraft, league_format, tep, s3_upload, s3_bucket, s3_key = get_user_input()
    players = scrape_ktc(is_redraft, league_format)
    export_to_csv(players, league_format, tep, is_redraft,
                  s3_upload, s3_bucket, s3_key)
