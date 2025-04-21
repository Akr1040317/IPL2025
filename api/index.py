# api/index.py

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
import os
import json

import firebase_admin
from firebase_admin import credentials, firestore

# ──────────────────────────────────────────────────────────────────────────────
# App & Firebase init
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

sa = json.loads(os.environ["FIREBASE_SA_KEY"])
cred = credentials.Certificate(sa)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ──────────────────────────────────────────────────────────────────────────────
# Helper functions (all unchanged)
# ──────────────────────────────────────────────────────────────────────────────
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
                    continue
            except ValueError:
                continue

            venue_section = date_time_section.find("div", class_="y_Y0B") if date_time_section else None
            venue = venue_section.get_text(strip=True) if venue_section else ""
            location = venue_section.find("div", class_="otuuQ").find("p").find("span").get_text(strip=True) if venue_section else ""
            match_number = match.find("div", class_="cONiu").get_text(strip=True) if match.find("div", class_="cONiu") else ""
            teams_container = match.find("div", class_="C81t6")
            if not teams_container:
                continue
            team_sections = teams_container.find_all("div", class_="U5fiW")
            teams = []
            for team in team_sections:
                team_name_elem = team.find("div", class_="WkFo7")
                if not team_name_elem:
                    continue
                team_name = get_full_team_name(team_name_elem.get_text(strip=True))
                score_section = team.find("div", class_="hPK5L")
                score = score_section.find("div", class_="n7m6x").get_text(strip=True) if score_section and score_section.find("div", class_="n7m6x") else "0"
                overs = score_section.find("div", class_="WbVlv").get_text(strip=True) if score_section and score_section.find("div", class_="WbVlv") else "0.0 ov"
                teams.append({"team": team_name, "score": score, "overs": overs})

            if len(teams) != 2:
                continue

            outcome = match.find("div", class_="bmG9a").get_text(strip=True) if match.find("div", class_="bmG9a") else ""
            matches.append({
                "date_time": date_time_text,
                "venue": venue,
                "location": location,
                "match_number": match_number,
                "teams": teams,
                "outcome": outcome
            })
        except Exception:
            continue

    # build standings
    teams_stats = {}
    def init_team(n):
        if n not in teams_stats:
            teams_stats[n] = {
                "matches": 0, "wins": 0, "losses": 0, "no_result": 0,
                "runs_scored": 0, "overs_faced": 0.0,
                "runs_conceded": 0, "overs_bowled": 0.0,
                "recent_form": []
            }

    for m in matches:
        t1 = m["teams"][0]; t2 = m["teams"][1]
        init_team(t1["team"]); init_team(t2["team"])
        try:
            r1, bo1, bl1 = process_innings(t1)
            r2, bo2, bl2 = process_innings(t2)
        except:
            continue

        teams_stats[t1["team"]]["matches"] += 1
        teams_stats[t1["team"]]["runs_scored"] += r1
        teams_stats[t1["team"]]["overs_faced"] += bo1
        teams_stats[t1["team"]]["runs_conceded"] += r2
        teams_stats[t1["team"]]["overs_bowled"] += bl2

        teams_stats[t2["team"]]["matches"] += 1
        teams_stats[t2["team"]]["runs_scored"] += r2
        teams_stats[t2["team"]]["overs_faced"] += bo2
        teams_stats[t2["team"]]["runs_conceded"] += r1
        teams_stats[t2["team"]]["overs_bowled"] += bl1

        outcome = m["outcome"]
        super_over = re.search(r"(.+?) tied with (.+?) \((.+?) win Super Over", outcome)
        if super_over:
            winner = get_full_team_name(super_over.group(3).strip())
        else:
            winner = get_full_team_name(outcome.split("beat")[0].strip()) if "beat" in outcome else None

        if winner == t1["team"]:
            teams_stats[t1["team"]]["wins"] += 1
            teams_stats[t1["team"]]["recent_form"].append("W")
            teams_stats[t2["team"]]["losses"] += 1
            teams_stats[t2["team"]]["recent_form"].append("L")
        elif winner == t2["team"]:
            teams_stats[t2["team"]]["wins"] += 1
            teams_stats[t2["team"]]["recent_form"].append("W")
            teams_stats[t1["team"]]["losses"] += 1
            teams_stats[t1["team"]]["recent_form"].append("L")
        else:
            teams_stats[t1["team"]]["no_result"] += 1
            teams_stats[t2["team"]]["no_result"] += 1
            teams_stats[t1["team"]]["recent_form"].append("NR")
            teams_stats[t2["team"]]["recent_form"].append("NR")

    standings = []
    for team, s in teams_stats.items():
        nrr = 0.0
        if s["overs_faced"] and s["overs_bowled"]:
            nrr = (s["runs_scored"]/s["overs_faced"]) - (s["runs_conceded"]/s["overs_bowled"])
        standings.append({
            "POS": 0,
            "TEAM": team,
            "P": s["matches"],
            "W": s["wins"],
            "L": s["losses"],
            "NR": s["no_result"],
            "NRR": round(nrr,3),
            "FOR": f"{s['runs_scored']}/{decimal_to_overs(s['overs_faced'])}",
            "AGAINST": f"{s['runs_conceded']}/{decimal_to_overs(s['overs_bowled'])}",
            "PTS": s["wins"]*2,
            "RECENT_FORM": " ".join(s["recent_form"][-5:])
        })

    standings.sort(key=lambda x: (x["PTS"], x["NRR"]), reverse=True)
    for i, row in enumerate(standings, start=1):
        row["POS"] = i

    matches_list = []
    for m in matches:
        matches_list.append({
            "Date_Time": m["date_time"],
            "Venue": m["venue"],
            "Location": m["location"],
            "Match": m["match_number"],
            "Team_1": f"{m['teams'][0]['team']} - {m['teams'][0]['score']} ({m['teams'][0]['overs']})",
            "Team_2": f"{m['teams'][1]['team']} - {m['teams'][1]['score']} ({m['teams'][1]['overs']})",
            "Result": m["outcome"]
        })

    return standings, matches_list

def compute_probabilities(upcoming_matches, standings, matches):
    G = nx.DiGraph()
    for t in standings:
        G.add_node(t["TEAM"])
    for m in matches:
        out = m["Result"]
        t1 = get_full_team_name(m["Team_1"].split(" - ")[0])
        t2 = get_full_team_name(m["Team_2"].split(" - ")[0])
        if not out: continue
        so = re.search(r"(.+?) tied with (.+?) \((.+?) win Super Over", out)
        winner = get_full_team_name(so.group(3).strip()) if so else get_full_team_name(out.split("beat")[0].strip()) if "beat" in out else None
        loser = t1 if winner==t2 else t2
        if winner and loser:
            G.add_edge(winner, loser, weight=1.0)

    for m in upcoming_matches:
        t1 = get_full_team_name(m["Team_1"])
        t2 = get_full_team_name(m["Team_2"])
        # head-to-head
        h2h = m.get("head_to_head", {"played":0,"team1_wins":0,"team2_wins":0})
        if h2h["played"]>0:
            h2h_score = (h2h["team1_wins"] - h2h["team2_wins"]) / h2h["played"]
        else:
            h2h_score = 0
        # form & NRR
        s1 = next((x for x in standings if x["TEAM"].lower()==t1.lower()),None)
        s2 = next((x for x in standings if x["TEAM"].lower()==t2.lower()),None)
        def form_val(f):
            pts=0
            for i,r in enumerate(f.split()):
                w=1 - (i*0.1)
                pts += w if r=="W" else -w if r=="L" else 0
            return pts/ max(len(f.split()),1)
        f_score = (form_val(s1["RECENT_FORM"]) - form_val(s2["RECENT_FORM"])) if s1 and s2 else 0
        nrr_score = np.tanh((s1["NRR"] - s2["NRR"])/2) if s1 and s2 else 0
        # strength of schedule
        try:
            d1 = set(nx.descendants(G,t1))|{t1}
            d2 = set(nx.descendants(G,t2))|{t2}
            if t2 in d1 and t1 not in d2:
                sos=0.3
            elif t1 in d2 and t2 not in d1:
                sos=-0.3
            else:
                avg1 = sum(nx.shortest_path_length(G,t1,o,weight='weight') for o in d1 if o!=t1)/max(1,len(d1)-1)
                avg2 = sum(nx.shortest_path_length(G,t2,o,weight='weight') for o in d2 if o!=t2)/max(1,len(d2)-1)
                sos=(avg2-avg1)/max(1,avg1+avg2)
        except:
            sos=0
        # last year performance
        perf = m.get("last_year_performance",{})
        p1,p2 = perf.get(t1,{"win_pct":50}), perf.get(t2,{"win_pct":50})
        perf_score = (p1["win_pct"]-p2["win_pct"])/100

        weights = {"h2h":0.4,"form":0.2,"nrr":0.1,"sos":0.1,"performance":0.2}
        total = weights["h2h"]*h2h_score + weights["form"]*f_score + weights["nrr"]*nrr_score + weights["sos"]*sos + weights["performance"]*perf_score
        prob1 = 1/(1+np.exp(-total*3))
        prob1 = max(0.05, min(0.95, prob1))
        m["Probability"] = {"Team_1": round(prob1*100,2), "Team_2": round((1-prob1)*100,2)}

    return upcoming_matches

def fetch_upcoming_matches(since=None):
    url = "https://timesofindia.indiatimes.com/sports/cricket/ipl/schedule"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code!=200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    elems = soup.find_all("a", class_=lambda x: x and all(c in x.split() for c in ["ejgS5","GsXWY"]))
    upcoming = []

    abbr = {"CSK":"csk","MI":"mi","RCB":"rcb","KKR":"kkr","SRH":"srh","DC":"dc","PBKS":"pbks","RR":"rr","GT":"gt","LSG":"lsg"}

    for m in elems:
        try:
            dt_sec = m.find("div",class_="ieLQJ")
            dt = dt_sec.find("div").get_text(strip=True) if dt_sec else ""
            md = date_parser.parse(dt).replace(tzinfo=None)
            if since and md<=since: continue

            venue = dt_sec.find("div",class_="y_Y0B").find("div",class_="otuuQ").find("span").get_text(strip=True) if dt_sec else ""
            num = m.find("div",class_="B2Exg").find("div",class_="cONiu").get_text(strip=True)
            teams = []
            for t in m.find("div",class_="B2Exg").find("div",class_="C81t6").find_all("div",class_="U5fiW"):
                n = t.find("div",class_="WkFo7").get_text(strip=True)
                if n=="TBC": raise AttributeError
                teams.append(n)

            h2h={"played":0,"team1_wins":0,"team2_wins":0}
            last_perf={}
            href=m.get("href")
            if href:
                inner = requests.get(f"https://timesofindia.indiatimes.com{href}",headers=headers)
                if inner.status_code==200:
                    ss=BeautifulSoup(inner.text,"html.parser").find("div",class_="cQWcQ")
                    if ss:
                        h2s=ss.find("div",class_="tVu1k")
                        if h2s:
                            for item in h2s.find_all("div",class_="OAk24"):
                                txt=item.get_text(strip=True).lower()
                                val=int(re.search(r"\d+",txt).group())
                                if "played" in txt: h2h["played"]=val
                                elif abbr.get(teams[0],teams[0].lower()) in txt: h2h["team1_wins"]=val
                                elif abbr.get(teams[1],teams[1].lower()) in txt: h2h["team2_wins"]=val

                        perf_sec=ss.find("div",class_="t66hp")
                        if perf_sec:
                            for row in perf_sec.find_all("div",class_="U5ktS")[1:]:
                                tn=row.find("div",class_="CCcyO").find("span").get_text(strip=True)
                                tn_full=get_full_team_name(tn)
                                stats=row.find("div",class_="vtQ9d")
                                p=int(stats.find("strong",class_="_donp").text) if stats.find("strong",class_="_donp") else 0
                                w=int(stats.find("strong",class_="PqVJY").text) if stats.find("strong",class_="PqVJY") else 0
                                pct=float(stats.find("strong",class_="OngzT").text.replace("%","")) if stats.find("strong",class_="OngzT") else 50
                                last_perf[tn_full]={"played":p,"won":w,"win_pct":pct}
        except Exception:
            continue

        row={
            "Date_Time": dt,
            "Venue": venue,
            "Location": venue,
            "Match": num,
            "Team_1": teams[0],
            "Team_2": teams[1],
            "Result": "",
            "head_to_head": h2h,
            "last_year_performance": last_perf
        }
        upcoming.append(row)

    # need full past for probabilities
    past = fetch_ipl_data()[1]
    return compute_probabilities(upcoming, fetch_ipl_data()[0], past)

def refresh_if_needed():
    try:
        md_doc = db.collection("iplCache").document("metadata").get()
        md = md_doc.to_dict() if md_doc.exists else {}
        last_past = md.get("lastPastMatch", datetime(2000,1,1))
        last_future = md.get("lastFutureMatch", datetime(2000,1,1))
        if isinstance(last_past, datetime) and last_past.tzinfo: last_past=last_past.replace(tzinfo=None)
        if isinstance(last_future, datetime) and last_future.tzinfo: last_future=last_future.replace(tzinfo=None)
        last_upd = md.get("lastUpdated", datetime(2000,1,1))
        if isinstance(last_upd, datetime) and last_upd.tzinfo: last_upd=last_upd.replace(tzinfo=None)
        force = (datetime.now() - last_upd) > timedelta(hours=24)

        new_standings, new_past = fetch_ipl_data(since=None if force else last_past)
        new_upcoming = fetch_upcoming_matches(since=None if force else last_future)

        def mx(lst,key):
            dates=[]
            for i in lst:
                try:
                    d=date_parser.parse(i[key])
                    if d.tzinfo: d=d.replace(tzinfo=None)
                    dates.append(d)
                except:
                    pass
            return max(dates) if dates else datetime(2000,1,1)

        npast=mx(new_past,"Date_Time")
        nup=mx(new_upcoming,"Date_Time")

        upd=False
        # past incremental
        for m in new_past:
            mid=hashlib.md5(f"{m['Date_Time']}_{m['Team_1']}_{m['Team_2']}".encode()).hexdigest()
            if not db.collection("iplCache").document("matches").collection("pastMatches").document(mid).get().exists:
                db.collection("iplCache").document("matches").collection("pastMatches").document(mid).set(m)
                upd=True

        for m in new_upcoming:
            mid=hashlib.md5(f"{m['Date_Time']}_{m['Team_1']}_{m['Team_2']}".encode()).hexdigest()
            try:
                d=date_parser.parse(m["Date_Time"]).replace(tzinfo=None)
                if d < datetime.now() or m.get("Result"):
                    db.collection("iplCache").document("matches").collection("pastMatches").document(mid).set(m)
                    db.collection("iplCache").document("matches").collection("upcomingMatches").document(mid).delete()
                    upd=True
                else:
                    if not db.collection("iplCache").document("matches").collection("upcomingMatches").document(mid).get().exists:
                        db.collection("iplCache").document("matches").collection("upcomingMatches").document(mid).set(m)
                        upd=True
            except:
                pass

        if (new_standings and upd) or force:
            db.collection("iplCache").document("standings").set({"teams": new_standings})

        if upd or force:
            db.collection("iplCache").document("metadata").set({
                "lastPastMatch": npast,
                "lastFutureMatch": nup,
                "lastUpdated": firestore.SERVER_TIMESTAMP
            }, merge=True)

        # return fresh data
        past_cached=[d.to_dict() for d in db.collection("iplCache").document("matches").collection("pastMatches").stream()]
        up_cached=[d.to_dict() for d in db.collection("iplCache").document("matches").collection("upcomingMatches").stream()]
        # sort
        past_cached.sort(key=lambda x: date_parser.parse(x["Date_Time"]), reverse=True)
        up_cached.sort(key=lambda x: date_parser.parse(x["Date_Time"]))
        standings_doc=db.collection("iplCache").document("standings").get()
        teams=standings_doc.to_dict().get("teams",[]) if standings_doc.exists else []
        return teams, past_cached, up_cached

    except Exception as e:
        logging.exception("Error in refresh_if_needed")
        raise

# ──────────────────────────────────────────────────────────────────────────────
# New endpoint: full refresh
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/refresh", methods=["GET"])
def refresh():
    try:
        # re‐scrape & push into Firestore
        refresh_if_needed()

        # now read back the metadata doc
        md = db.collection("iplCache").document("metadata").get().to_dict() or {}
        ts = md.get("lastUpdated")
        # convert Firestore Timestamp -> ISO string
        last_updated = ts.isoformat() if hasattr(ts, "isoformat") else None

        return jsonify({
            "status": "ok",
            "lastUpdated": last_updated
        }), 200
    except Exception as e:
        logging.exception("💥 Refresh failed")
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────────────────────────────────────
# Fast read endpoints, no scraping on each call
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/api/metadata", methods=["GET"])
def metadata():
    """Tell client when we last ran our cron/refresh."""
    md = db.collection("iplCache").document("metadata").get().to_dict() or {}
    ts = md.get("lastUpdated")
    last_updated = ts.isoformat() if hasattr(ts, "isoformat") else None
    return jsonify({ "lastUpdated": last_updated }), 200

@app.route("/api/standings", methods=["GET"])
def get_standings():
    doc = db.collection("iplCache").document("standings").get()
    teams = doc.to_dict().get("teams", []) if doc.exists else []
    return jsonify(teams), 200

@app.route("/api/matches", methods=["GET"])
def get_matches():
    past = [d.to_dict() for d in db.collection("iplCache")
                                 .document("matches")
                                 .collection("pastMatches")
                                 .stream()]
    past.sort(key=lambda x: date_parser.parse(x["Date_Time"]), reverse=True)
    return jsonify(past), 200

@app.route("/api/upcoming-matches", methods=["GET"])
def get_upcoming_matches():
    up = [d.to_dict() for d in db.collection("iplCache")
                               .document("matches")
                               .collection("upcomingMatches")
                               .stream()]
    up.sort(key=lambda x: date_parser.parse(x["Date_Time"]))
    return jsonify(up), 200

# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5001)
