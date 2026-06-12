import duckdb
import json
import os
from supabase import create_client
from datetime import date, datetime

# ── Date constants ──────────────────────────────────────────────────────────
DATE_FROM      = '2024-10-21'
DATE_PRE_WC_TO = '2026-06-11'
DATE_WC_FROM   = '2026-06-12'
DATE_WC_TO     = '2026-07-05'

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DB = os.path.join(BASE_DIR, 'data', 'dashboard.duckdb')
OUTPUT_JSON  = os.path.join(BASE_DIR, 'site', 'data.json')

# ── Open connections ─────────────────────────────────────────────────────────
print("Opening dashboard.duckdb...")
db = duckdb.connect(DASHBOARD_DB, read_only=True)

print("Connecting to Supabase...")
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

print("Setup complete.")

# ── Pull Supabase data needed for badge calculations ─────────────────────────
print("Pulling Supabase data...")

teams_raw   = supabase.table("teams").select("*").execute().data
players_raw = supabase.table("players").select("*").execute().data
badges_raw  = supabase.table("badges").select("*").execute().data

# Build lookup dicts
badge_name_to_id = {b["name"]: b["id"] for b in badges_raw}
player_by_id     = {p["database_id"]: p for p in players_raw}
team_by_name = {}
for t in teams_raw:
    team_by_name[t["name"]] = t
    team_by_name[t["database_name"]] = t

# ── Badge assignment calculation ─────────────────────────────────────────────
print("Checking badge assignments...")

existing = supabase.table("badge_assignments").select("id").execute().data

if len(existing) == 0:
    print("No assignments found — calculating...")
    assignments = []

    # ── Load dashboard data ──────────────────────────────────────────────────
    team_matches = db.execute(f"""
        SELECT team, result, date, runs_scored, wickets_taken, bat_or_chase
        FROM team_matches
        WHERE date BETWEEN '{DATE_FROM}' AND '{DATE_PRE_WC_TO}'
        ORDER BY date
    """).df()

    player_stats = db.execute("SELECT * FROM player_stats_pre_wc").df()

    # ── Team badges ──────────────────────────────────────────────────────────

    # Serial Winners — manual flag
    for t in teams_raw:
        if t.get("serial_winners_flag"):
            assignments.append({
                "entity_type": "team",
                "entity_id": t["id"],
                "badge_id": badge_name_to_id["Serial Winners"]
            })

    # Age badges — Veterans, Peaking, Rookies
    team_ages = {}
    for p in players_raw:
        team = p.get("nationality")
        age  = p.get("age")
        if team and age:
            try:
                team_ages.setdefault(team, []).append(float(age))
            except (ValueError, TypeError):
                continue

    for team_name, ages in team_ages.items():
        sorted_ages = sorted(ages)
        n = len(sorted_ages)
        median_age = (sorted_ages[n // 2] if n % 2 != 0
                      else (sorted_ages[n // 2 - 1] + sorted_ages[n // 2]) / 2)
        t = team_by_name.get(team_name)
        if not t:
            continue
        if median_age > 30:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Veterans"]})
        elif 26 <= median_age <= 29:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Peaking"]})
        elif median_age < 25:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Rookies"]})

    # Accumulators — top 3 teams by average runs scored
    avg_runs = (
        team_matches.groupby("team")["runs_scored"]
        .mean()
        .sort_values(ascending=False)
        .head(3)
        .index.tolist()
    )
    for team_name in avg_runs:
        t = team_by_name.get(team_name)
        if t:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Accumulators"]})

    # Chasers — top 3 teams by win ratio batting second (min 5 chases)
    chases = team_matches[team_matches["bat_or_chase"] == "second"].copy()
    chase_wins = (
        chases.groupby("team")
        .apply(lambda x: x[x["result"] == "win"].shape[0] / x.shape[0] if x.shape[0] >= 5 else None)
        .dropna()
        .sort_values(ascending=False)
        .head(3)
        .index.tolist()
    )
    for team_name in chase_wins:
        t = team_by_name.get(team_name)
        if t:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Chasers"]})

    # Wicket-takers — top 3 teams by average wickets taken
    avg_wickets = (
        team_matches.groupby("team")["wickets_taken"]
        .mean()
        .sort_values(ascending=False)
        .head(3)
        .index.tolist()
    )
    for team_name in avg_wickets:
        t = team_by_name.get(team_name)
        if t:
            assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Wicket-takers"]})

    # In Form — at least 7 wins in last 10 games
    for team_name in team_matches["team"].unique():
        last_10 = team_matches[team_matches["team"] == team_name].tail(10)
        wins = last_10[last_10["result"] == "win"].shape[0]
        if wins >= 7:
            t = team_by_name.get(team_name)
            if t:
                assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["In Form"]})

    # Out of Form — fewer than 3 wins in last 10 games
    for team_name in team_matches["team"].unique():
        last_10 = team_matches[team_matches["team"] == team_name].tail(10)
        wins = last_10[last_10["result"] == "win"].shape[0]
        if wins < 3:
            t = team_by_name.get(team_name)
            if t:
                assignments.append({"entity_type": "team", "entity_id": t["id"], "badge_id": badge_name_to_id["Out of Form"]})

    # ── Player badges ────────────────────────────────────────────────────────

    BATTER_ROLES = {"Top Order Bat", "Middle Order Bat", "Finisher", "Wicket Keeper"}
    BOWLER_ROLES = {"Pacer", "Spinner"}
    AR_ROLES     = {"All-Rounder"}

    for _, row in player_stats.iterrows():
        pid  = row["player_id"]
        p    = player_by_id.get(pid)
        if not p:
            continue
        role    = p.get("role", "")
        is_bat  = role in BATTER_ROLES
        is_bowl = role in BOWLER_ROLES
        is_ar   = role in AR_ROLES
        eid     = p["id"]

        def val(col):
            v = row.get(col)
            try:
                import math
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return None
            except Exception:
                pass
            return v

        # Anchor — above avg balls faced AND below avg SR at their position
        if (is_bat or is_ar):
            avg_balls = val("batting_position_avg_balls")
            avg_sr    = val("batting_position_avg_sr")
            balls     = val("balls_faced")
            sr        = val("batting_sr")
            if all(v is not None for v in [avg_balls, avg_sr, balls, sr]):
                if balls > avg_balls and sr < avg_sr:
                    assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Anchor"]})

        # Fast Starter — top 10 percentile first 10-ball SR
        if (is_bat or is_ar):
            v = val("first_10_sr_percentile")
            if v is not None and v >= 90:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Fast Starter"]})

        # Slow Starter — bottom 10 percentile first 10-ball SR
        if (is_bat or is_ar):
            v = val("first_10_sr_percentile")
            if v is not None and v <= 10:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Slow Starter"]})

        # Powerplay Specialist — top 10 percentile SR AND avg in overs 1-6
        if (is_bat or is_ar):
            pp_sr  = val("powerplay_sr_percentile")
            pp_avg = val("powerplay_avg_percentile")
            if pp_sr is not None and pp_avg is not None and pp_sr >= 90 and pp_avg >= 90:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Powerplay Specialist"]})

        # Finisher — top 10 percentile SR AND avg in overs 16-20
        if (is_bat or is_ar):
            d_sr  = val("death_sr_percentile")
            d_avg = val("death_avg_percentile")
            if d_sr is not None and d_avg is not None and d_sr >= 90 and d_avg >= 90:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Finisher"]})

        # Speed Demon — manual flag
        if (is_bowl or is_ar) and p.get("speed_demon_flag"):
            assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Speed Demon"]})

        # Wicket Threat — bottom 10 percentile bowling SR (lower = takes wickets faster)
        if (is_bowl or is_ar):
            v = val("bowling_sr_percentile")
            if v is not None and v <= 10:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Wicket Threat"]})

        # Stingy — bottom 10 percentile economy (lower = more economical)
        if (is_bowl or is_ar):
            v = val("economy_percentile")
            if v is not None and v <= 10:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Stingy"]})

        # Expensive — top 10 percentile economy (higher = more expensive)
        if (is_bowl or is_ar):
            v = val("economy_percentile")
            if v is not None and v >= 90:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Expensive"]})

        # Serial Winner — manual flag
        if p.get("serial_winner_flag"):
            assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Serial Winner"]})

        # Key Player — rank 1 in team for runs OR wickets
        runs_rank    = val("team_runs_rank")
        wickets_rank = val("team_wickets_rank")
        if runs_rank == 1 or wickets_rank == 1:
            assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Key Player"]})

        # Key All-Rounder — top 3 runs AND wickets on team
        if is_ar and runs_rank is not None and wickets_rank is not None:
            if runs_rank <= 3 and wickets_rank <= 3:
                assignments.append({"entity_type": "player", "entity_id": eid, "badge_id": badge_name_to_id["Key All-Rounder"]})

    # ── Write assignments to Supabase ────────────────────────────────────────
    if assignments:
        supabase.table("badge_assignments").insert(assignments).execute()
        print(f"Wrote {len(assignments)} badge assignments to Supabase.")
    else:
        print("No badge assignments calculated.")

else:
    print(f"Found {len(existing)} existing badge assignments — skipping calculation.")


# ── Build teams array ────────────────────────────────────────────────────────
print("Building teams array...")

# Load all team matches for form guide and record
all_team_matches = db.execute(f"""
    SELECT team, result, date
    FROM team_matches
    ORDER BY date
""").df()

# Load badge assignments from Supabase
badge_assignments_raw = supabase.table("badge_assignments").select("*").execute().data
badge_by_id = {b["id"]: b for b in badges_raw}

# Build team badge lookup: team supabase id -> list of badge objects
team_badges = {}
for a in badge_assignments_raw:
    if a["entity_type"] == "team":
        tid = a["entity_id"]
        badge = badge_by_id.get(a["badge_id"])
        if badge:
            team_badges.setdefault(tid, []).append({
                "name": badge["name"],
                "badge_id": badge["id"]
            })

# Build player supabase id lookup
player_by_supabase_id = {p["id"]: p for p in players_raw}

teams_array = []

for t in teams_raw:
    team_name = t["database_name"]
    tid       = t["id"]

    # Match record (pre-WC + WC full window)
    tm = all_team_matches[all_team_matches["team"] == team_name]
    record = {
        "played":    int(len(tm)),
        "wins":      int((tm["result"] == "win").sum()),
        "losses":    int((tm["result"] == "loss").sum()),
        "ties":      int((tm["result"] == "tie").sum()),
        "no_result": int((tm["result"] == "no result").sum())
    }

    # Form guide — last 5 results
    form = []
    for _, row in tm.tail(5).iterrows():
        form.append({
            "result": row["result"],
            "date":   str(row["date"])
        })

    # Star player
    star_player = None
    if t.get("star_player_id"):
        sp = player_by_supabase_id.get(t["star_player_id"])
        if sp:
            star_player = {
                "id":        sp["id"],
                "name":      sp["name"],
                "photo_url": t.get("star_player_image_url"),
                "reasoning": t.get("star_player_reasoning")
            }

    teams_array.append({
        "id":                   tid,
        "name":                 team_name,
        "captain":              t.get("captain"),
        "captain_id":           t.get("captain_id"),
        "head_coach":           t.get("head_coach"),
        "team_brief":           t.get("team_brief"),
        "flag_url":             t.get("flag_url"),
        "t20_wc_titles":        t.get("t20_wc_titles"),
        "odi_wc_titles":        t.get("odi_wc_titles"),
        "acknowledgements":     t.get("acknowledgements"),
        "record":               record,
        "form":                 form,
        "star_player":          star_player,
        "badges":               team_badges.get(tid, [])
    })

print(f"Teams array built — {len(teams_array)} teams.")


# ── Build players array ──────────────────────────────────────────────────────
print("Building players array...")

# Load all player stats tables
pre_wc = db.execute("SELECT * FROM player_stats_pre_wc").df()
wc     = db.execute("SELECT * FROM player_stats_wc").df()
graph  = db.execute("SELECT * FROM player_graph_data").df()

# Index by player_id
pre_wc_by_id = {row["player_id"]: row for _, row in pre_wc.iterrows()}
wc_by_id     = {row["player_id"]: row for _, row in wc.iterrows()}
graph_by_id  = {row["player_id"]: row for _, row in graph.iterrows()}

# Build player badge lookup: player supabase id -> list of badge objects
player_badges = {}
for a in badge_assignments_raw:
    if a["entity_type"] == "player":
        pid = a["entity_id"]
        badge = badge_by_id.get(a["badge_id"])
        if badge:
            player_badges.setdefault(pid, []).append({
                "name": badge["name"],
                "badge_id": badge["id"]
            })

def clean(v):
    """Convert NaN/NaT to None for JSON serialisation."""
    import math
    import pandas as pd
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    if hasattr(v, 'item'):
        return v.item()
    return v

def stats_row(row):
    """Convert a dataframe row to a clean dict."""
    return {k: clean(v) for k, v in row.items() if k != "player_id"}

players_array = []

for p in players_raw:
    pid = p.get("database_id")
    sid = p.get("id")

    pre = pre_wc_by_id.get(pid)
    wc_row = wc_by_id.get(pid)
    gr  = graph_by_id.get(pid)

    players_array.append({
        "id":              sid,
        "database_id":     pid,
        "name":            p.get("name"),
        "role":            p.get("role"),
        "nationality":     p.get("nationality"),
        "age":             p.get("age"),
        "batting_hand":    p.get("batting_hand"),
        "bowling_hand":    p.get("bowling_hand"),
        "bowling_type":    p.get("bowling_type"),
        "photo_url":       p.get("photo_url"),
        "t20_wc_titles":   p.get("t20_wc_titles"),
        "odi_wc_titles":   p.get("odi_wc_titles"),
        "wpl_titles":      p.get("wpl_titles"),
        "hundred_titles":  p.get("hundred_titles"),
        "wbbl_titles":     p.get("wbbl_titles"),
        "acknowledgements": p.get("acknowledgements"),
        "pre_wc_stats":    stats_row(pre) if pre is not None else None,
        "wc_stats":        stats_row(wc_row) if wc_row is not None else None,
        "graph_data":      stats_row(gr) if gr is not None else None,
        "badges":          player_badges.get(sid, [])
    })

print(f"Players array built — {len(players_array)} players.")


# ── Write data.json ──────────────────────────────────────────────────────────
print("Writing data.json...")

output = {
    "teams":   teams_array,
    "players": players_array
}

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

with open(OUTPUT_JSON, 'w') as f:
    json.dump(output, f, default=str)

size_kb = os.path.getsize(OUTPUT_JSON) / 1024
print(f"data.json written — {size_kb:.1f} KB.")

db.close()
print("Done.")
