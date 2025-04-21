from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import networkx as nx
import numpy as np
from fuzzywuzzy import process, fuzz
from datetime import datetime, timedelta
from dateutil import parser as date_parser
import hashlib
import logging

import firebase_admin
from firebase_admin import credentials, firestore

# Set up logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# -------------------------------
# Helper Functions
# -------------------------------

def overs_to_decimal(overs_str):
    overs_str = overs_str.replace(" ov", "").strip()
    if "." in overs_str:
        whole, balls = overs_str.split(".")
        try:
            whole = int(whole)
            balls = int(balls)
        except ValueError:
            return float(overs_str)
        return whole + (balls / 6)
    else:
        return float(overs_str)

def decimal_to_overs(decimal_overs):
    whole = int(decimal_overs)
    balls = round((decimal_overs - whole) * 6)
    if balls == 6:
        whole += 1
        balls = 0
    return f"{whole}.{balls}"

def process_innings(team_info):
    score_str = team_info["score"].strip()
    actual_overs = overs_to_decimal(team_info["overs"])
    if "/" in score_str:
        runs_str, wickets_str = score_str.split("/")
        runs = int(runs_str.strip())
        wickets = wickets_str.strip()
        if wickets == "10":
            batting_overs = 20.0
            bowling_overs = 20.0
        else:
            batting_overs = actual_overs
            bowling_overs = actual_overs
    else:
        runs = int(score_str)
        batting_overs = 20.0
        bowling_overs = 20.0
    return runs, batting_overs, bowling_overs

team_abbr_map = {
    "CSK": "Chennai Super Kings", "MI": "Mumbai Indians", "RCB": "Royal Challengers Bengaluru",
    "KKR": "Kolkata Knight Riders", "SRH": "Sunrisers Hyderabad", "DC": "Delhi Capitals",
    "PBKS": "Punjab Kings", "RR": "Rajasthan Royals", "GT": "Gujarat Titans", "LSG": "Lucknow Super Giants",
    "Chennai Super Kings": "Chennai Super Kings", "Mumbai Indians": "Mumbai Indians",
    "Royal Challengers Bengaluru": "Royal Challengers Bengaluru", "Kolkata Knight Riders": "Kolkata Knight Riders",
    "Sunrisers Hyderabad": "Sunrisers Hyderabad", "Delhi Capitals": "Delhi Capitals",
    "Punjab Kings": "Punjab Kings", "Rajasthan Royals": "Rajasthan Royals",
    "Gujarat Titans": "Gujarat Titans", "Lucknow Super Giants": "Lucknow Super Giants",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Kings XI Punjab": "Punjab Kings",
    "Delhi Daredevils": "Delhi Capitals",
    "Deccan Chargers": "Sunrisers Hyderabad",
    "Gujarat": "Gujarat Titans",
    "Lucknow": "Lucknow Super Giants",
    "Punjab": "Punjab Kings",
    "Rajasthan": "Rajasthan Royals",
    "Hyderabad": "Sunrisers Hyderabad",
    "Delhi": "Delhi Capitals",
    "Kolkata": "Kolkata Knight Riders",
    "Mumbai": "Mumbai Indians",
    "Chennai": "Chennai Super Kings",
    "Titans": "Gujarat Titans",
    "Super Giants": "Lucknow Super Giants",
    "Royals": "Rajasthan Royals",
    "Knights": "Kolkata Knight Riders",
    "Capitals": "Delhi Capitals",
    "Kings": "Punjab Kings",
    "Sunrisers": "Sunrisers Hyderabad",
    "Guj Titans": "Gujarat Titans",
    "Lucknow SG": "Lucknow Super Giants",
    "Punjab K": "Punjab Kings",
    "Raj Royals": "Rajasthan Royals",
    "Sunrisers Hyd": "Sunrisers Hyderabad",
    "Delhi C": "Delhi Capitals",
    "Kolkata KR": "Kolkata Knight Riders",
    "Mumbai I": "Mumbai Indians",
    "Chennai SK": "Chennai Super Kings",
    "TATA Gujarat Titans": "Gujarat Titans",
    "LSG Lucknow": "Lucknow Super Giants",
    "PK": "Punjab Kings",
    "RR Royals": "Rajasthan Royals"
}

canonical_teams = [
    "Chennai Super Kings", "Mumbai Indians", "Royal Challengers Bengaluru",
    "Kolkata Knight Riders", "Sunrisers Hyderabad", "Delhi Capitals",
    "Punjab Kings", "Rajasthan Royals", "Gujarat Titans", "Lucknow Super Giants"
]

def get_full_team_name(name):
    if not name:
        return name
    cleaned_name = name.strip().lower()
    for key, value in team_abbr_map.items():
        if cleaned_name == key.lower():
            return value
    match, score = process.extractOne(cleaned_name, canonical_teams, scorer=fuzz.token_sort_ratio)
    if score > 80:
        logging.info(f"Fuzzy matched '{name}' to '{match}' (score: {score})")
        return match
    logging.warning(f"No match found for team name: '{name}'")
    return name

def refresh_if_needed():
    try:
        # Retrieve metadata
        metadata_doc = db.collection("iplCache").document("metadata").get()
        metadata = metadata_doc.to_dict() if metadata_doc.exists else {}

        # Get last-seen timestamps (default to a very old date)
        last_past = metadata.get("lastPastMatch", datetime(2000, 1, 1))
        last_future = metadata.get("lastFutureMatch", datetime(2000, 1, 1))

        # Normalize timestamps to naive datetime
        if isinstance(last_past, datetime) and last_past.tzinfo:
            last_past = last_past.replace(tzinfo=None)
        if isinstance(last_future, datetime) and last_future.tzinfo:
            last_future = last_future.replace(tzinfo=None)

        # Check if cache is older than 24 hours
        last_updated = metadata.get("lastUpdated", datetime(2000, 1, 1))
        if isinstance(last_updated, datetime) and last_updated.tzinfo:
            last_updated = last_updated.replace(tzinfo=None)
        force_refresh = (datetime.now() - last_updated) > timedelta(hours=24)

        # Scrape new data only after the last known timestamps or if forcing refresh
        new_standings, new_past_matches = fetch_ipl_data(since=last_past if not force_refresh else None)
        new_upcoming_matches = fetch_upcoming_matches(since=last_future if not force_refresh else None)

        # Calculate newest timestamps
        def max_date(lst, key):
            if not lst:
                return datetime(2000, 1, 1)
            dates = []
            for item in lst:
                try:
                    date = date_parser.parse(item[key])
                    if date.tzinfo:
                        date = date.replace(tzinfo=None)
                    dates.append(date)
                except (ValueError, TypeError):
                    continue
            return max(dates) if dates else datetime(2000, 1, 1)

        newest_past = max_date(new_past_matches, "Date_Time")
        newest_future = max_date(new_upcoming_matches, "Date_Time")

        # Update Firestore incrementally
        updates_made = False

        # Update past matches
        for match in new_past_matches:
            match_id = hashlib.md5(f"{match['Date_Time']}_{match['Team_1']}_{match['Team_2']}".encode()).hexdigest()
            existing = db.collection("iplCache").document("matches").collection("pastMatches").document(match_id).get()
            if not existing.exists:
                db.collection("iplCache").document("matches").collection("pastMatches").document(match_id).set(match)
                updates_made = True
                logging.info(f"Added new past match: {match['Match']}")

        # Update upcoming matches and move completed matches to past
        for match in new_upcoming_matches:
            match_id = hashlib.md5(f"{match['Date_Time']}_{match['Team_1']}_{match['Team_2']}".encode()).hexdigest()
            try:
                match_date = date_parser.parse(match["Date_Time"]).replace(tzinfo=None)
                if match_date < datetime.now() or match.get("Result"):
                    # Move to past matches
                    db.collection("iplCache").document("matches").collection("pastMatches").document(match_id).set(match)
                    db.collection("iplCache").document("matches").collection("upcomingMatches").document(match_id).delete()
                    updates_made = True
                    logging.info(f"Moved match to past: {match['Match']}")
                else:
                    existing = db.collection("iplCache").document("matches").collection("upcomingMatches").document(match_id).get()
                    if not existing.exists:
                        db.collection("iplCache").document("matches").collection("upcomingMatches").document(match_id).set(match)
                        updates_made = True
                        logging.info(f"Added new upcoming match: {match['Match']}")
            except ValueError:
                logging.warning(f"Invalid date for match: {match['Match']}")
                continue

        # Update standings if new matches were added or forcing refresh
        if (new_standings and updates_made) or force_refresh:
            db.collection("iplCache").document("standings").set({"teams": new_standings})
            logging.info("Updated standings")

        # Update metadata if new data was added
        if updates_made or new_standings or new_past_matches or new_upcoming_matches or force_refresh:
            metadata_updates = {
                "lastPastMatch": newest_past,
                "lastFutureMatch": newest_future,
                "lastUpdated": firestore.SERVER_TIMESTAMP
            }
            db.collection("iplCache").document("metadata").set(metadata_updates, merge=True)
            logging.info("Updated metadata")

        # Retrieve all cached data for return
        past_matches = [doc.to_dict() for doc in db.collection("iplCache").document("matches").collection("pastMatches").stream()]
        upcoming_matches = [doc.to_dict() for doc in db.collection("iplCache").document("matches").collection("upcomingMatches").stream()]
        
        # Sort past matches in chronological order
        # Sort past matches in reverse chronological order (most recent first)
        past_matches = sorted(
            past_matches,
            key=lambda x: date_parser.parse(x["Date_Time"]).replace(tzinfo=None) if x.get("Date_Time") else datetime(2000, 1, 1),
            reverse=True
        )
        
        # Sort upcoming matches in chronological order
        upcoming_matches = sorted(
            upcoming_matches,
            key=lambda x: date_parser.parse(x["Date_Time"]).replace(tzinfo=None) if x.get("Date_Time") else datetime(2000, 1, 1)
        )
        
        standings_doc = db.collection("iplCache").document("standings").get()
        standings = standings_doc.to_dict().get("teams", []) if standings_doc.exists else []

        return standings, past_matches, upcoming_matches
    except Exception as e:
        logging.error(f"Error in refresh_if_needed: {e}", exc_info=True)
        raise

# -------------------------------
# Compute Win Probabilities
# -------------------------------

def compute_probabilities(upcoming_matches, standings, matches):
    G = nx.DiGraph()
    team_nodes = set()
    
    for team in standings:
        team_nodes.add(team["TEAM"])
        G.add_node(team["TEAM"])
    
    for match in matches:
        outcome = match["Result"]
        team1 = get_full_team_name(match["Team_1"].split(" - ")[0])
        team2 = get_full_team_name(match["Team_2"].split(" - ")[0])
        if not outcome:
            continue
        super_over_match = re.search(r"(.+?) tied with (.+?) \((.+?) win Super Over.*?\)", outcome)
        if super_over_match:
            winner = get_full_team_name(super_over_match.group(3).strip())
            loser = team1 if winner == team2 else team2
            G.add_edge(winner, loser, weight=1.0)
        else:
            try:
                winner = get_full_team_name(outcome.split("beat")[0].strip())
                loser = team1 if winner == team2 else team2
                G.add_edge(winner, loser, weight=1.0)
            except:
                continue
    
    for match in upcoming_matches:
        team1 = get_full_team_name(match["Team_1"])
        team2 = get_full_team_name(match["Team_2"])
        
        logging.info(f"Computing probabilities for {team1} vs {team2}")
        logging.info(f"Head-to-Head: {match.get('head_to_head')}")
        
        h2h_score = 0
        form_score = 0
        nrr_score = 0
        sos_score = 0
        performance_score = 0
        
        # Head-to-Head
        h2h_data = match.get("head_to_head", {"played": 0, "team1_wins": 0, "team2_wins": 0})
        played = h2h_data["played"]
        if played > 0:
            team1_win_pct = h2h_data["team1_wins"] / played
            team2_win_pct = h2h_data["team2_wins"] / played
            h2h_score = team1_win_pct - team2_win_pct
            logging.info(f"H2H Score: {h2h_score:.3f} (Team1: {team1_win_pct:.3f}, Team2: {team2_win_pct:.3f})")
        else:
            logging.info("No H2H data")
        
        # Recent Form and NRR
        team1_stats = next((s for s in standings if s["TEAM"].lower() == team1.lower()), None)
        team2_stats = next((s for s in standings if s["TEAM"].lower() == team2.lower()), None)
        if team1_stats and team2_stats:
            logging.info(f"Team1 Stats: {team1_stats}")
            logging.info(f"Team2 Stats: {team2_stats}")
            def form_value(form):
                if not form:
                    return 0
                points = 0
                for i, result in enumerate(form.split()):
                    weight = 1.0 - (i * 0.1)
                    if result == "W":
                        points += weight
                    elif result == "L":
                        points -= weight
                return points / max(len(form.split()), 1)
            
            team1_form = min(max(form_value(team1_stats["RECENT_FORM"]), -1), 1)
            team2_form = min(max(form_value(team2_stats["RECENT_FORM"]), -1), 1)
            form_score = team1_form - team2_form
            logging.info(f"Form Score: {form_score:.3f} (Team1: {team1_form:.3f}, Team2: {team2_form:.3f})")
            
            nrr_diff = team1_stats["NRR"] - team2_stats["NRR"]
            nrr_score = np.tanh(nrr_diff / 2)  # Normalize to [-1, 1]
            logging.info(f"NRR Score: {nrr_score:.3f} (Team1 NRR: {team1_stats['NRR']}, Team2 NRR: {team2_stats['NRR']})")
        else:
            logging.warning(f"Standings data missing for {team1} or {team2}")
            logging.warning(f"Available standings teams: {[s['TEAM'] for s in standings]}")
        
        # Strength of Schedule
        try:
            team1_reachable = set(nx.descendants(G, team1)).union({team1})
            team2_reachable = set(nx.descendants(G, team2)).union({team2})
            if team2 in team1_reachable and team1 not in team2_reachable:
                sos_score = 0.3
            elif team1 in team2_reachable and team2 not in team1_reachable:
                sos_score = -0.3
            else:
                team1_strength = sum(nx.shortest_path_length(G, team1, other, weight='weight') 
                                   for other in team1_reachable if other != team1) / max(1, len(team1_reachable) - 1)
                team2_strength = sum(nx.shortest_path_length(G, team2, other, weight='weight') 
                                   for other in team2_reachable if other != team2) / max(1, len(team2_reachable) - 1)
                sos_score = (team2_strength - team1_strength) / max(1, team1_strength + team2_strength)
            logging.info(f"SoS Score: {sos_score:.3f}")
        except nx.NetworkXError as e:
            sos_score = 0
            logging.warning(f"SoS calculation failed: {str(e)}")
        
        # Last Year Performance
        perf_data = match.get("last_year_performance", {})
        team1_perf = perf_data.get(team1, {"played": 0, "win_pct": 50})
        team2_perf = perf_data.get(team2, {"played": 0, "win_pct": 50})
        performance_score = (team1_perf["win_pct"] - team2_perf["win_pct"]) / 100
        logging.info(f"Performance Score: {performance_score:.3f} (Team1: {team1_perf['win_pct']}%, Team2: {team2_perf['win_pct']}%)")
        
        # Combine scores with weights
        weights = {
            "h2h": 0.4,  # Increased weight for matchup-specific data
            "form": 0.2,
            "nrr": 0.1,  # Reduced weight for NRR
            "sos": 0.1,
            "performance": 0.2
        }
        
        total_score = (
            weights["h2h"] * h2h_score +
            weights["form"] * form_score +
            weights["nrr"] * nrr_score +
            weights["sos"] * sos_score +
            weights["performance"] * performance_score
        )
        logging.info(f"Total Score: {total_score:.3f}")
        
        # Convert to probability with less sensitive sigmoid
        base_prob = 1 / (1 + np.exp(-total_score * 3))
        team1_prob = max(0.05, min(0.95, base_prob))
        team2_prob = 1 - team1_prob
        logging.info(f"Probabilities: Team1: {team1_prob*100:.2f}%, Team2: {team2_prob*100:.2f}%")
        
        match["Probability"] = {
            "Team_1": float(round(team1_prob * 100, 2)),
            "Team_2": float(round(team2_prob * 100, 2))
        }
    
    return upcoming_matches

# -------------------------------
# Fetch Upcoming Matches
# -------------------------------

def fetch_upcoming_matches(since=None):
    url = "https://timesofindia.indiatimes.com/sports/cricket/ipl/schedule"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logging.error(f"Failed to retrieve upcoming matches page: Status code {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    match_elements = soup.find_all("a", class_=lambda x: x and all(cls in x.split() for cls in ["ejgS5", "GsXWY"]))
    upcoming_matches = []

    team_abbr_to_lower = {
        "CSK": "csk", "MI": "mi", "RCB": "rcb", "KKR": "kkr", "SRH": "srh",
        "DC": "dc", "PBKS": "pbks", "RR": "rr", "GT": "gt", "LSG": "lsg"
    }

    for match in match_elements:
        try:
            date_time_section = match.find("div", class_="ieLQJ")
            date_time_text = date_time_section.find("div").get_text(strip=True) if date_time_section else ""
            try:
                match_date = date_parser.parse(date_time_text)
                if match_date.tzinfo:
                    match_date = match_date.replace(tzinfo=None)
                if since and match_date <= since:
                    logging.info(f"Skipping match before {since}: {date_time_text}")
                    continue
            except ValueError:
                logging.warning(f"Invalid date format: {date_time_text}")
                continue

            venue_section = date_time_section.find("div", class_="y_Y0B") if date_time_section else None
            location = venue_section.find("div", class_="otuuQ").find("p").find("span").get_text(strip=True) if venue_section else ""
            match_number_section = match.find("div", class_="B2Exg")
            match_number = match_number_section.find("div", class_="cONiu").get_text(strip=True) if match_number_section else ""
            teams_container = match_number_section.find("div", class_="C81t6") if match_number_section else None
            teams = []
            if teams_container:
                team_sections = teams_container.find_all("div", class_="U5fiW")
                for team in team_sections:
                    team_name = team.find("div", class_="WkFo7")
                    if team_name:
                        team_name_text = team_name.get_text(strip=True)
                        if team_name_text == "TBC":
                            raise AttributeError("Skipping match with TBC teams")
                        teams.append({"team": team_name_text})

            if len(teams) != 2:
                logging.warning(f"Skipping match with incorrect team count: {teams}")
                continue

            match_center_href = match.get("href", "")
            head_to_head = {"played": 0, "team1_wins": 0, "team2_wins": 0}
            last_year_performance = {}
            
            if match_center_href:
                full_url = f"https://timesofindia.indiatimes.com{match_center_href}"
                try:
                    match_response = requests.get(full_url, headers=headers)
                    if match_response.status_code == 200:
                        match_soup = BeautifulSoup(match_response.text, "html.parser")
                        stats_container = match_soup.find("div", class_="cQWcQ")
                        if stats_container:
                            h2h_section = stats_container.find("div", class_="tVu1k")
                            if h2h_section:
                                h2h_items = h2h_section.find_all("div", class_="OAk24")
                                team1_abbr = team_abbr_to_lower.get(teams[0]["team"], teams[0]["team"].lower())
                                team2_abbr = team_abbr_to_lower.get(teams[1]["team"], teams[1]["team"].lower())
                                
                                for item in h2h_items:
                                    text = item.get_text(strip=True).lower()
                                    value_match = re.search(r'\d+', text)
                                    if not value_match:
                                        continue
                                    value = int(value_match.group())
                                    
                                    if "matches" in text or "played" in text:
                                        head_to_head["played"] = value
                                    elif team1_abbr in text and ("won" in text or "win" in text):
                                        head_to_head["team1_wins"] = value
                                    elif team2_abbr in text and ("won" in text or "win" in text):
                                        head_to_head["team2_wins"] = value
                                
                                logging.info(f"Scraped H2H for {teams[0]['team']} vs {teams[1]['team']}: {head_to_head}")
                            
                            perf_section = stats_container.find("div", class_="t66hp")
                            if perf_section:
                                perf_rows = perf_section.find_all("div", class_="U5ktS")[1:]
                                for row in perf_rows:
                                    team_span = row.find("div", class_="CCcyO").find("span")
                                    if not team_span:
                                        continue
                                    team_name = team_span.get_text(strip=True)
                                    team_name_full = get_full_team_name(team_name)
                                    stats = row.find("div", class_="vtQ9d")
                                    if stats:
                                        played = int(stats.find("strong", class_="_donp").text) if stats.find("strong", class_="_donp") else 0
                                        won = int(stats.find("strong", class_="PqVJY").text) if stats.find("strong", class_="PqVJY") else 0
                                        win_pct = float(stats.find("strong", class_="OngzT").text.replace("%", "")) if stats.find("strong", class_="OngzT") else 50
                                        last_year_performance[team_name_full] = {
                                            "played": played,
                                            "won": won,
                                            "win_pct": win_pct
                                        }
                                logging.info(f"Scraped Last Year Performance: {last_year_performance}")
                    else:
                        logging.error(f"Failed to fetch match center: Status code {match_response.status_code}")
                except Exception as e:
                    logging.error(f"Error fetching match data for {teams[0]['team']} vs {teams[1]['team']}: {e}")

            match_info = {
                "date_time": date_time_text,
                "venue": location,
                "location": location,
                "match_number": match_number,
                "teams": teams,
                "head_to_head": head_to_head,
                "last_year_performance": last_year_performance
            }
            upcoming_matches.append(match_info)
        except AttributeError as e:
            logging.warning(f"Skipping match due to parsing error: {e}")
            continue
        except Exception as e:
            logging.error(f"Unexpected error parsing match: {e}")
            continue

    # Process upcoming matches
    standings, past_matches = fetch_ipl_data()  # Fetch all past matches for standings
    upcoming_matches_list = []
    for match in upcoming_matches:
        team1_display = f"{match['teams'][0]['team']}"
        team2_display = f"{match['teams'][1]['team']}"
        row = {
            "Date_Time": match["date_time"],
            "Venue": match["venue"],
            "Location": match["location"],
            "Match": match["match_number"],
            "Team_1": team1_display,
            "Team_2": team2_display,
            "Result": "",
            "head_to_head": match["head_to_head"],
            "last_year_performance": match["last_year_performance"]
        }
        upcoming_matches_list.append(row)

    upcoming_matches_list = compute_probabilities(upcoming_matches_list, standings, past_matches)
    logging.info(f"Parsed {len(upcoming_matches_list)} upcoming matches")
    return upcoming_matches_list

# -------------------------------
# Data Fetching and Processing (Past Matches)
# -------------------------------

def fetch_ipl_data(since=None):
    url = "https://timesofindia.indiatimes.com/sports/cricket/ipl/results"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to retrieve page: Status code {response.status_code}")
    except Exception as e:
        logging.error(f"Error fetching IPL results page: {e}")
        return [], []

    soup = BeautifulSoup(response.text, "html.parser")
    match_elements = soup.find_all("a", class_="ejgS5 DuVhK ra0fi")
    matches = []

    for match in match_elements:
        try:
            date_time_section = match.find("div", class_="ieLQJ")
            date_time_text = date_time_section.find("div").get_text(strip=True) if date_time_section else ""
            try:
                match_date = date_parser.parse(date_time_text)
                if match_date.tzinfo:
                    match_date = match_date.replace(tzinfo=None)
                if since and match_date <= since:
                    logging.info(f"Skipping match before {since}: {date_time_text}")
                    continue
            except ValueError:
                logging.warning(f"Invalid date format: {date_time_text}")
                continue

            venue_section = date_time_section.find("div", class_="y_Y0B") if date_time_section else None
            venue = venue_section.get_text(strip=True) if venue_section else ""
            location = venue_section.find("div", class_="otuuQ").find("p").find("span").get_text(strip=True) if venue_section else ""
            match_number = match.find("div", class_="cONiu").get_text(strip=True) if match.find("div", class_="cONiu") else ""
            teams_container = match.find("div", class_="C81t6")
            if not teams_container:
                logging.warning("Skipping match: No teams container found")
                continue
            team_sections = teams_container.find_all("div", class_="U5fiW")
            teams = []
            for team in team_sections:
                team_name_elem = team.find("div", class_="WkFo7")
                if not team_name_elem:
                    logging.warning("Skipping team: No team name found")
                    continue
                team_name = team_name_elem.get_text(strip=True)
                team_name = get_full_team_name(team_name)
                score_section = team.find("div", class_="hPK5L")
                score = score_section.find("div", class_="n7m6x").get_text(strip=True) if score_section and score_section.find("div", class_="n7m6x") else "0"
                overs = score_section.find("div", class_="WbVlv").get_text(strip=True) if score_section and score_section.find("div", class_="WbVlv") else "0.0 ov"
                teams.append({"team": team_name, "score": score, "overs": overs})
            if len(teams) != 2:
                logging.warning(f"Skipping match: Incorrect team count {len(teams)}")
                continue
            outcome = match.find("div", class_="bmG9a").get_text(strip=True) if match.find("div", class_="bmG9a") else ""
            match_info = {
                "date_time": date_time_text,
                "venue": venue,
                "location": location,
                "match_number": match_number,
                "teams": teams,
                "outcome": outcome
            }
            matches.append(match_info)
        except Exception as e:
            logging.error(f"Error parsing match: {e}")
            continue

    teams_stats = {}
    def init_team(team_name):
        if team_name not in teams_stats:
            teams_stats[team_name] = {
                "matches": 0, "wins": 0, "losses": 0, "no_result": 0,
                "runs_scored": 0, "overs_faced": 0.0,
                "runs_conceded": 0, "overs_bowled": 0.0,
                "recent_form": []
            }

    for match in matches:
        team1_info = match["teams"][0]
        team2_info = match["teams"][1]
        t1_name = team1_info["team"]
        t2_name = team2_info["team"]
        init_team(t1_name)
        init_team(t2_name)
        try:
            runs1, batting_overs1, bowling_overs1 = process_innings(team1_info)
            runs2, batting_overs2, bowling_overs2 = process_innings(team2_info)
        except Exception as e:
            logging.error(f"Error processing innings for {t1_name} vs {t2_name}: {e}")
            continue

        teams_stats[t1_name]["matches"] += 1
        teams_stats[t1_name]["runs_scored"] += runs1
        teams_stats[t1_name]["overs_faced"] += batting_overs1
        teams_stats[t1_name]["runs_conceded"] += runs2
        teams_stats[t1_name]["overs_bowled"] += bowling_overs2
        teams_stats[t2_name]["matches"] += 1
        teams_stats[t2_name]["runs_scored"] += runs2
        teams_stats[t2_name]["overs_faced"] += batting_overs2
        teams_stats[t2_name]["runs_conceded"] += runs1
        teams_stats[t2_name]["overs_bowled"] += bowling_overs1

        outcome = match["outcome"]
        super_over_match = re.search(r"(.+?) tied with (.+?) \((.+?) win Super Over.*?\)", outcome)
        if super_over_match:
            winner = get_full_team_name(super_over_match.group(3).strip())
            if winner == t1_name:
                teams_stats[t1_name]["wins"] += 1
                teams_stats[t1_name]["recent_form"].append("W")
                teams_stats[t2_name]["losses"] += 1
                teams_stats[t2_name]["recent_form"].append("L")
            elif winner == t2_name:
                teams_stats[t2_name]["wins"] += 1
                teams_stats[t2_name]["recent_form"].append("W")
                teams_stats[t1_name]["losses"] += 1
                teams_stats[t1_name]["recent_form"].append("L")
        else:
            try:
                winner = get_full_team_name(outcome.split("beat")[0].strip())
                if winner == t1_name:
                    teams_stats[t1_name]["wins"] += 1
                    teams_stats[t1_name]["recent_form"].append("W")
                    teams_stats[t2_name]["losses"] += 1
                    teams_stats[t2_name]["recent_form"].append("L")
                elif winner == t2_name:
                    teams_stats[t2_name]["wins"] += 1
                    teams_stats[t2_name]["recent_form"].append("W")
                    teams_stats[t1_name]["losses"] += 1
                    teams_stats[t1_name]["recent_form"].append("L")
                else:
                    teams_stats[t1_name]["no_result"] += 1
                    teams_stats[t2_name]["no_result"] += 1
                    teams_stats[t1_name]["recent_form"].append("NR")
                    teams_stats[t2_name]["recent_form"].append("NR")
            except Exception:
                teams_stats[t1_name]["no_result"] += 1
                teams_stats[t2_name]["no_result"] += 1
                teams_stats[t1_name]["recent_form"].append("NR")
                teams_stats[t2_name]["recent_form"].append("NR")

    for team, stats in teams_stats.items():
        if stats["overs_faced"] > 0 and stats["overs_bowled"] > 0:
            batting_rate = stats["runs_scored"] / stats["overs_faced"]
            bowling_rate = stats["runs_conceded"] / stats["overs_bowled"]
            nrr = batting_rate - bowling_rate
        else:
            nrr = 0.0
        stats["nrr"] = round(nrr, 3)
        stats["points"] = stats["wins"] * 2

    standings = []
    for team, stats in teams_stats.items():
        row = {
            "POS": 0,
            "TEAM": team,
            "P": stats["matches"],
            "W": stats["wins"],
            "L": stats["losses"],
            "NR": stats["no_result"],
            "NRR": stats["nrr"],
            "FOR": f"{stats['runs_scored']}/{decimal_to_overs(stats['overs_faced'])}",
            "AGAINST": f"{stats['runs_conceded']}/{decimal_to_overs(stats['overs_bowled'])}",
            "PTS": stats["points"],
            "RECENT_FORM": " ".join(stats["recent_form"][-5:])
        }
        standings.append(row)

    standings = sorted(standings, key=lambda x: (x["PTS"], x["NRR"]), reverse=True)
    for i, row in enumerate(standings, start=1):
        row["POS"] = i

    matches_list = []
    for match in matches:
        team1_display = f"{match['teams'][0]['team']} - {match['teams'][0]['score']} ({match['teams'][0]['overs']})"
        team2_display = f"{match['teams'][1]['team']} - {match['teams'][1]['score']} ({match['teams'][1]['overs']})"
        row = {
            "Date_Time": match["date_time"],
            "Venue": match["venue"],
            "Location": match["location"],
            "Match": match["match_number"],
            "Team_1": team1_display,
            "Team_2": team2_display,
            "Result": match["outcome"]
        }
        matches_list.append(row)

    logging.info(f"Parsed {len(matches_list)} past matches")
    return standings, matches_list

# -------------------------------
# API Endpoints
# -------------------------------

@app.route("/api/standings", methods=["GET"])
def get_standings():
    try:
        standings, _, _ = refresh_if_needed()
        cleaned = []
        for row in standings:
            new_row = {}
            for k, v in row.items():
                if hasattr(v, "item"):
                    new_row[k] = v.item()
                else:
                    new_row[k] = v
            cleaned.append(new_row)
        return jsonify(cleaned)
    except Exception as e:
        logging.error(f"Error in get_standings: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/matches", methods=["GET"])
def get_matches():
    try:
        _, past_matches, _ = refresh_if_needed()
        return jsonify(past_matches)
    except Exception as e:
        logging.error(f"Error in get_matches: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/upcoming-matches", methods=["GET"])
def get_upcoming_matches():
    try:
        _, _, upcoming = refresh_if_needed()
        return jsonify(upcoming)
    except Exception as e:
        logging.error(f"Error in get_upcoming_matches: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)