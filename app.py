from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, UTC
import requests
from bs4 import BeautifulSoup
import os
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from sqlalchemy import inspect
import json
import tempfile
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# /// = relative path, //// = absolute path
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class KTCPlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(10), nullable=False)
    team = db.Column(db.String(10))
    value = db.Column(db.Integer)
    age = db.Column(db.Float)
    rookie = db.Column(db.String(5))
    rank = db.Column(db.Integer)
    trend = db.Column(db.String(10))
    tier = db.Column(db.String(10))
    position_rank = db.Column(db.String(10))
    league_format = db.Column(db.String(10), nullable=False)  # '1QB' or 'SF'
    is_redraft = db.Column(db.Boolean, nullable=False)
    tep = db.Column(db.Integer, nullable=False)
    last_updated = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    def to_dict(self):
        return {
            "Player Name": self.player_name,
            "Position": self.position,
            "Team": self.team,
            "Value": self.value,
            "Age": self.age,
            "Rookie": self.rookie,
            "Rank": self.rank,
            "Trend": self.trend,
            "Tier": self.tier,
            "Position Rank": self.position_rank
        }


def fetch_ktc_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        return None


def scrape_players(base_url, format_code, value_key, pos_rank_key, max_pages=10):
    all_elements = []

    for page_num in range(max_pages):
        url = base_url.format(page_num, format_code)
        page = fetch_ktc_page(url)
        if not page:
            continue
        soup = BeautifulSoup(page.content, "html.parser")
        player_elements = soup.find_all(class_="onePlayer")
        all_elements.extend(player_elements)

    players = []
    for player_element in all_elements:
        player_name_element = player_element.find(class_="player-name")
        player_position_element = player_element.find(class_="position")
        player_value_element = player_element.find(class_="value")
        player_age_element = player_element.find(class_="position hidden-xs")

        # Extract rank number
        rank_element = player_element.find(class_="rank-number")
        try:
            player_rank = int(rank_element.get_text(
                strip=True)) if rank_element else None
        except (ValueError, AttributeError):
            player_rank = None

        # Extract trend with direction
        trend_element = player_element.find(class_="trend")
        player_trend = None
        if trend_element:
            trend_value = trend_element.get_text(strip=True)
            if trend_element.contents and len(trend_element.contents) > 1:
                try:
                    trend_class = trend_element.contents[1].attrs.get("class", [""])[
                        0]
                    if trend_class == "trend-up":
                        player_trend = f"+{trend_value}" if trend_value else "+0"
                    elif trend_class == "trend-down":
                        player_trend = f"-{trend_value}" if trend_value else "-0"
                    else:
                        player_trend = "0"
                except (IndexError, AttributeError):
                    player_trend = "0"
            else:
                player_trend = "0"
        else:
            player_trend = "0"

        # Extract tier
        player_tier = None
        player_info_element = player_element.find(class_="player-info")
        if player_info_element and len(player_info_element.contents) > 1:
            try:
                player_tier = player_info_element.contents[1].get_text(
                    strip=True)
            except (IndexError, AttributeError):
                player_tier = None

        if not (player_name_element and player_position_element and player_value_element):
            continue

        player_name = player_name_element.get_text(strip=True)
        team_suffix = (
            player_name[-3:] if player_name[-3:] == 'RFA' else
            player_name[-4:] if len(player_name) >= 4 and player_name[-4] == 'R' else
            player_name[-2:] if player_name[-2:] == 'FA' else
            player_name[-3:] if player_name[-3:].isupper() else ""
        )
        player_name = player_name.replace(team_suffix, "").strip()
        player_position_rank = player_position_element.get_text(strip=True)
        player_position = player_position_rank[:2]
        try:
            player_value = int(player_value_element.get_text(strip=True))
        except Exception:
            player_value = 0

        # Always extract age regardless of league type
        player_age = None
        if player_age_element:
            player_age_text = player_age_element.get_text(strip=True)
            try:
                player_age = float(
                    player_age_text[:4]) if player_age_text else None
            except Exception:
                player_age = None

        # Always determine rookie status
        if team_suffix and team_suffix[0] == 'R':
            player_team = team_suffix[1:]
            player_rookie = "Yes"
        else:
            player_team = team_suffix
            player_rookie = "No"

        if player_position == "PI":  # Player Inactive
            player_info = {
                "Player Name": player_name,
                pos_rank_key: None,
                "Position": player_position,
                "Team": None,
                value_key: player_value,
                "Age": player_age,
                "Rookie": player_rookie,
                "Rank": player_rank,
                "Trend": player_trend,
                "Tier": player_tier
            }
        else:
            player_info = {
                "Player Name": player_name,
                pos_rank_key: player_position_rank,
                "Position": player_position,
                "Team": player_team,
                value_key: player_value,
                "Age": player_age,
                "Rookie": player_rookie,
                "Rank": player_rank,
                "Trend": player_trend,
                "Tier": player_tier
            }
        players.append(player_info)
    return players


def merge_redraft_values(players, base_url, format_code, value_key, pos_rank_key, max_pages=10):
    all_elements = []
    for page_num in range(max_pages):
        url = base_url.format(page_num, format_code)
        page = fetch_ktc_page(url)
        if not page:
            continue
        soup = BeautifulSoup(page.content, "html.parser")
        player_elements = soup.find_all(class_="onePlayer")
        all_elements.extend(player_elements)

    for player_element in all_elements:
        player_name_element = player_element.find(class_="player-name")
        player_position_element = player_element.find(class_="position")
        player_value_element = player_element.find(class_="value")

        # Extract rank number
        rank_element = player_element.find(class_="rank-number")
        try:
            redraft_rank = int(rank_element.get_text(
                strip=True)) if rank_element else None
        except (ValueError, AttributeError):
            redraft_rank = None

        # Extract trend with direction
        trend_element = player_element.find(class_="trend")
        redraft_trend = None
        if trend_element:
            trend_value = trend_element.get_text(strip=True)
            if trend_element.contents and len(trend_element.contents) > 1:
                try:
                    trend_class = trend_element.contents[1].attrs.get("class", [""])[
                        0]
                    if trend_class == "trend-up":
                        redraft_trend = f"+{trend_value}" if trend_value else "+0"
                    elif trend_class == "trend-down":
                        redraft_trend = f"-{trend_value}" if trend_value else "-0"
                    else:
                        redraft_trend = "0"
                except (IndexError, AttributeError):
                    redraft_trend = "0"
            else:
                redraft_trend = "0"
        else:
            redraft_trend = "0"

        # Extract tier
        redraft_tier = None
        player_info_element = player_element.find(class_="player-info")
        if player_info_element and len(player_info_element.contents) > 1:
            try:
                redraft_tier = player_info_element.contents[1].get_text(
                    strip=True)
            except (IndexError, AttributeError):
                redraft_tier = None

        if not (player_name_element and player_position_element and player_value_element):
            continue

        player_name = player_name_element.get_text(strip=True)
        team_suffix = (
            player_name[-3:] if player_name[-3:] == 'RFA' else
            player_name[-4:] if len(player_name) >= 4 and player_name[-4] == 'R' else
            player_name[-2:] if player_name[-2:] == 'FA' else
            player_name[-3:] if player_name[-3:].isupper() else ""
        )
        player_name = player_name.replace(team_suffix, "").strip()
        player_position_rank = player_position_element.get_text(strip=True)
        try:
            player_value = int(player_value_element.get_text(strip=True))
        except Exception:
            player_value = 0

        for player in players:
            if player["Player Name"] == player_name:
                player[pos_rank_key] = player_position_rank
                player[value_key] = player_value
                player["RdrftRank"] = redraft_rank
                player["RdrftTrend"] = redraft_trend
                player["RdrftTier"] = redraft_tier
                break
    return players


def scrape_ktc(is_redraft, league_format, tep=0):
    # Only scrape the format the user selected
    if league_format == '1QB':
        format_code = 1
        value_key = 'Value'
        pos_rank_key = 'Position Rank'
        base_url = "https://keeptradecut.com/dynasty-rankings?page={0}&filters=QB|WR|RB|TE&format={1}"
        # base_url = "https://keeptradecut.com/dynasty-rankings"
        players = scrape_players(
            base_url, format_code, value_key, pos_rank_key)
        if is_redraft:
            redraft_url = "https://keeptradecut.com/fantasy-rankings?page={0}&filters=QB|WR|RB|TE&format={1}"
            # redraft_url = "https://keeptradecut.com/fantasy-rankings"
            players = merge_redraft_values(
                players, redraft_url, 1, 'RdrftValue', 'RdrftPosition Rank')
    else:  # SF
        format_code = 0
        value_key = 'SFValue'
        pos_rank_key = 'SFPosition Rank'
        base_url = "https://keeptradecut.com/dynasty-rankings?page={0}&filters=QB|WR|RB|TE|RDP&format={1}"
        # base_url = "https://keeptradecut.com/dynasty-rankings"
        players = scrape_players(
            base_url, format_code, value_key, pos_rank_key)
        if is_redraft:
            redraft_url = "https://keeptradecut.com/fantasy-rankings?page={0}&filters=QB|WR|RB|TE&format={1}"
            # redraft_url = "https://keeptradecut.com/fantasy-rankings"
            players = merge_redraft_values(
                players, redraft_url, 2, 'SFRdrftValue', 'SFRdrftPosition Rank')
    return players


def tep_adjust(players, tep, value_key):
    # Adjusted multipliers to match KTC's actual TEP system
    s = 0.2
    if tep == 0:
        return players
    elif tep == 1:
        t_mult = 1.1
        r = 250
    elif tep == 2:
        t_mult = 1.2
        r = 350
    elif tep == 3:
        t_mult = 1.3
        r = 450
    else:
        print(f"Error: invalid TEP value -- {tep}")
        return players

    # Sort players by value to establish consistent ranking
    players = sorted(players, key=lambda x: x.get(value_key, 0), reverse=True)

    # Find max player value to use as cap
    max_player_val = max(player.get(value_key, 0) for player in players)

    # Apply TEP adjustment only to tight ends
    for rank, player in enumerate(players):
        if player.get("Position") == "TE":
            original_value = player.get(value_key, 0)
            # print(f"original_value: {original_value}")
            if original_value > 0:
                t = t_mult * original_value
                n = rank / (len(players) - 25) * r + s * r
                player[value_key] = min(max_player_val - 1, round(t + n, 2))

    # Re-sort players by adjusted values to maintain proper rankings
    return sorted(players, key=lambda x: x.get(value_key, 0), reverse=True)


def upload_json_to_s3(json_data, bucket_name, object_key):
    """
    Upload JSON data to an S3 bucket

    Parameters:
    json_data (dict): The JSON data to upload
    bucket_name (str): The name of the S3 bucket
    object_key (str): The S3 object key (path/filename.json)

    Returns:
    bool: True if upload was successful, False otherwise
    """
    try:
        s3_client = boto3.client('s3')

        # Create a temporary file to write JSON data
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(json_data, temp_file, indent=2, default=str)
            temp_file_path = temp_file.name

        print(f"Uploading JSON to s3://{bucket_name}/{object_key}...")
        s3_client.upload_file(temp_file_path, bucket_name, object_key)
        print(f"Successfully uploaded JSON to s3://{bucket_name}/{object_key}")

        # Clean up temporary file
        os.unlink(temp_file_path)
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


@app.route('/api/ktc/refresh', methods=['POST'])
def refresh_rankings():
    """Endpoint to fetch fresh data from KTC and store in database"""
    try:
        # Get parameters from query string only
        is_redraft = request.args.get('is_redraft', 'false').lower() in [
            'true', 't', 'yes', 'y', '1']
        league_format = request.args.get('league_format', '1QB').upper()
        tep = int(request.args.get('tep', '0'))

        # Validate parameters
        if league_format not in ['1QB', 'SF']:
            return jsonify({'error': 'Invalid league format. Must be 1QB or SF'}), 400
        if tep not in [0, 1, 2, 3]:
            return jsonify({'error': 'Invalid TEP value. Must be 0, 1, 2, or 3'}), 400

        # Scrape fresh data
        players = scrape_ktc(is_redraft, league_format, tep)
        print(f"Scraped {len(players)} players")

        # Apply TEP adjustments manually since KTC loads TEP values via JavaScript
        # which server-side scraping cannot capture
        if not is_redraft and tep > 0:
            value_key = 'Value' if league_format == '1QB' else 'SFValue'
            players = tep_adjust(players, tep, value_key)
            print(f"Applied TEP adjustments, now have {len(players)} players")

        # Create tables if they don't exist
        db.create_all()

        # Delete existing data for this configuration
        deleted_count = KTCPlayer.query.filter_by(
            league_format=league_format,
            is_redraft=is_redraft,
            tep=tep
        ).count()

        KTCPlayer.query.filter_by(
            league_format=league_format,
            is_redraft=is_redraft,
            tep=tep
        ).delete()
        print(f"Deleted {deleted_count} existing records")

        # Store new data
        added_count = 0
        for player in players:
            # Get the correct value based on format and redraft status
            if is_redraft:
                if league_format == '1QB':
                    value = player.get("RdrftValue", 0)
                    position_rank = player.get("RdrftPosition Rank")
                else:
                    value = player.get("SFRdrftValue", 0)
                    position_rank = player.get("SFRdrftPosition Rank")
            else:
                if league_format == '1QB':
                    value = player.get("Value", 0)
                    position_rank = player.get("Position Rank")
                else:
                    value = player.get("SFValue", 0)
                    position_rank = player.get("SFPosition Rank")

            # Skip players with no value to avoid bad data
            if value is None or value == 0:
                print(
                    f"Skipping player {player.get('Player Name', 'Unknown')} - no value")
                continue

            ktc_player = KTCPlayer(
                player_name=player["Player Name"],
                position=player["Position"],
                team=player.get("Team"),  # Use .get() since team can be None
                value=value,
                age=player.get("Age"),
                rookie=player.get("Rookie", "No"),
                rank=player.get("Rank"),
                trend=player.get("Trend", "0"),
                tier=player.get("Tier"),
                position_rank=position_rank,
                league_format=league_format,
                is_redraft=is_redraft,
                tep=tep
            )
            db.session.add(ktc_player)
            added_count += 1

        print(f"Adding {added_count} new records to database")

        # Add debugging before commit
        print(f"Database session has {len(db.session.new)} new objects")
        print(f"Database session has {len(db.session.dirty)} dirty objects")

        try:
            db.session.commit()
            print("Database commit successful")

            # Verify the commit worked
            verify_count = KTCPlayer.query.filter_by(
                league_format=league_format,
                is_redraft=is_redraft,
                tep=tep
            ).count()
            print(f"Verified: {verify_count} records now in database")

        except Exception as commit_error:
            print(f"Database commit failed: {commit_error}")
            db.session.rollback()
            raise commit_error

        # Upload JSON to S3 (same bucket as ktc-scrape.py)
        bucket_name = os.getenv('S3_BUCKET')
        print('bucket_name: ', bucket_name)

        if bucket_name:
            object_key = f"ktc_refresh_{league_format.lower()}_{'redraft' if is_redraft else 'dynasty'}_tep{tep}.json"
            json_data = {
                'message': 'Rankings refreshed successfully',
                'timestamp': datetime.now(UTC).isoformat(),
                'count': len(players),
                'parameters': {
                    'is_redraft': is_redraft,
                    'league_format': league_format,
                    'tep': tep
                },
                'players': players
            }
            upload_json_to_s3(json_data, bucket_name, object_key)

        return jsonify({
            'message': 'Rankings refreshed successfully',
            'timestamp': datetime.now(UTC).isoformat(),
            'count': len(players)
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error refreshing rankings: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ktc/rankings', methods=['GET'])
def get_rankings():
    """Endpoint to retrieve stored rankings with optional filtering"""
    try:
        # Get parameters from query string
        is_redraft = request.args.get('is_redraft', 'false').lower() in [
            'true', 't', 'yes', 'y', '1']
        league_format = request.args.get('league_format', '1QB').upper()
        tep = int(request.args.get('tep', '0'))

        # Validate parameters
        if league_format not in ['1QB', 'SF']:
            return jsonify({'error': 'Invalid league format. Must be 1QB or SF'}), 400
        if tep not in [0, 1, 2, 3]:
            return jsonify({'error': 'Invalid TEP value. Must be 0, 1, 2, or 3'}), 400

        # Query the database
        players = KTCPlayer.query.filter_by(
            league_format=league_format,
            is_redraft=is_redraft,
            tep=tep
        ).order_by(KTCPlayer.rank.asc()).all()

        if not players:
            return jsonify({'error': 'No rankings found for the specified parameters'}), 404

        # Get the timestamp from the most recent player
        last_updated = max(player.last_updated for player in players)

        # Upload JSON to S3 (same bucket as ktc-scrape.py)
        bucket_name = os.getenv('S3_BUCKET')
        print('bucket_name: ', bucket_name)
        if bucket_name:
            object_key = f"ktc_rankings_{league_format.lower()}_{'redraft' if is_redraft else 'dynasty'}_tep{tep}.json"
            json_data = {
                'timestamp': last_updated.isoformat(),
                'is_redraft': is_redraft,
                'league_format': league_format,
                'tep': tep,
                'players': [player.to_dict() for player in players]
            }
            upload_json_to_s3(json_data, bucket_name, object_key)

        return jsonify({
            'timestamp': last_updated.isoformat(),
            'is_redraft': is_redraft,
            'league_format': league_format,
            'tep': tep,
            'players': [player.to_dict() for player in players]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.cli.command("init_db")
def init_db():
    # Initialize the database
    db.create_all()
    print("Initialized the database.")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
