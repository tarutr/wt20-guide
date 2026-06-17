import duckdb
import os
import pandas as pd
from supabase import create_client

# ── Date constants ──────────────────────────────────────────────────────────
DATE_FROM      = '2024-10-21'
DATE_PRE_WC_TO = '2026-06-11'
DATE_WC_FROM   = '2026-06-12'
DATE_WC_TO     = '2026-07-05'

# ── Teams ────────────────────────────────────────────────────────────────────
WT20_TEAMS = [
    'Australia', 'Bangladesh', 'England', 'India', 'Ireland',
    'New Zealand', 'Pakistan', 'Scotland', 'South Africa',
    'Sri Lanka', 'Netherlands', 'West Indies'
]

teams_sql = "('" + "','".join(WT20_TEAMS) + "')"

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRICKET_DB   = os.path.join(BASE_DIR, 'data', 'cricket.duckdb')
DASHBOARD_DB = os.path.join(BASE_DIR, 'data', 'dashboard.duckdb')

# ── Open connections ─────────────────────────────────────────────────────────
print("Opening cricket.duckdb...")
cricket = duckdb.connect(CRICKET_DB, read_only=True)

print("Creating dashboard.duckdb...")
if os.path.exists(DASHBOARD_DB):
    os.remove(DASHBOARD_DB)
dashboard = duckdb.connect(DASHBOARD_DB)

print("Setup complete.")

# ── Supabase connection ──────────────────────────────────────────────────────
print("Connecting to Supabase...")
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
response = supabase.table("players").select("database_id, nationality, bowling_type").execute()
player_ids = [row["database_id"] for row in response.data if row["database_id"]]
player_teams = {row["database_id"]: row["nationality"] for row in response.data if row["database_id"]}
player_bowling_types = {row["database_id"]: row["bowling_type"] for row in response.data if row["database_id"]}
print(f"Pulled {len(player_ids)} players from Supabase.")

# ── Shared SQL fragments ─────────────────────────────────────────────────────
player_ids_sql   = "('" + "','".join(player_ids) + "')"
player_teams_sql = ", ".join([f"('{pid}', '{team}')" for pid, team in player_teams.items()])
player_bowling_types_sql = ", ".join([f"('{pid}', '{bt}')" for pid, bt in player_bowling_types.items()])

# ── Table 1: team_matches ────────────────────────────────────────────────────
print("Building team_matches...")

team_matches = cricket.execute("""
WITH

match_teams AS (
    SELECT match_id, team_1 AS team FROM matches
    WHERE match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND gender = 'female'
      AND match_type IN ('T20', 'IT20')
      AND team_1 IN {teams_sql}
    UNION ALL
    SELECT match_id, team_2 AS team FROM matches
    WHERE match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND gender = 'female'
      AND match_type IN ('T20', 'IT20')
      AND team_2 IN {teams_sql}
),

innings_agg AS (
    SELECT
        i.match_id,
        i.innings_number,
        i.batting_team                                                          AS team,
        SUM(d.runs_total)                                                       AS runs_scored,
        COUNT(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 END)       AS balls_faced
    FROM deliveries d
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE i.super_over IS NOT TRUE
    GROUP BY i.match_id, i.innings_number, i.batting_team
),

wickets_agg AS (
    SELECT
        match_id,
        innings_number,
        COUNT(*) AS wickets
    FROM wickets
    GROUP BY match_id, innings_number
),

innings_meta AS (
    SELECT
        match_id,
        batting_team AS team,
        MIN(innings_number) AS innings_number
    FROM innings
    WHERE super_over IS NOT TRUE
    GROUP BY match_id, batting_team
)

SELECT
    m.match_id,
    m.match_date_1                                                              AS date,
    m.match_type,
    m.venue,
    m.event_name                                                                AS tournament,
    m.toss_winner,
    m.toss_decision,
    mt.team,
    CASE
        WHEN m.team_1 = mt.team THEN m.team_2
        ELSE m.team_1
    END                                                                         AS opponent,
    CASE
        WHEN im.innings_number = 0 THEN 'first'
        WHEN im.innings_number = 1 THEN 'second'
        ELSE NULL
    END                                                                         AS bat_or_chase,
    ia.runs_scored,
    COALESCE(wl.wickets, 0)                                                     AS wickets_lost,
    ia.balls_faced,
    ROUND(ia.runs_scored * 6.0 / NULLIF(ia.balls_faced, 0), 2)                AS run_rate,
    ia_opp.runs_scored                                                          AS runs_conceded,
    COALESCE(wt.wickets, 0)                                                     AS wickets_taken,
    ia_opp.balls_faced                                                          AS balls_bowled,
    ROUND(ia_opp.runs_scored * 6.0 / NULLIF(ia_opp.balls_faced, 0), 2)        AS bowling_run_rate,
    CASE
        WHEN m.winner = mt.team THEN 'win'
        WHEN m.winner IS NOT NULL AND m.winner != mt.team THEN 'loss'
        WHEN m.result_type = 'tie' THEN 'tie'
        WHEN m.result_type = 'no result' THEN 'no result'
    END                                                                         AS result,
    m.result_margin,
    m.result_margin_type
FROM match_teams mt
JOIN matches m ON m.match_id = mt.match_id
LEFT JOIN innings_meta im ON im.match_id = mt.match_id
                         AND im.team = mt.team
LEFT JOIN innings_agg ia ON ia.match_id = mt.match_id
                        AND ia.team = mt.team
LEFT JOIN innings_agg ia_opp ON ia_opp.match_id = mt.match_id
                             AND ia_opp.team != mt.team
LEFT JOIN wickets_agg wl ON wl.match_id = mt.match_id
                        AND wl.innings_number = im.innings_number
LEFT JOIN wickets_agg wt ON wt.match_id = mt.match_id
                        AND wt.innings_number != im.innings_number
ORDER BY m.match_date_1, m.match_id, mt.team
""".format(
    date_from=DATE_FROM,
    date_wc_to=DATE_WC_TO,
    teams_sql=teams_sql
)).df()

dashboard.execute("CREATE TABLE team_matches AS SELECT * FROM team_matches")
print(f"team_matches done — {len(team_matches)} rows.")

# ── Table 2: player_stats_pre_wc ─────────────────────────────────────────────
print("Building player_stats_pre_wc...")

player_stats_pre_wc = cricket.execute("""
WITH

players AS (
    SELECT pid AS player_id, team
    FROM (VALUES {player_teams_sql}) t(pid, team)
),

batting_basic AS (
    SELECT
        d.batter_id                                                             AS player_id,
        COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number))              AS innings_batted,
        SUM(d.runs_batter)                                                      AS runs,
        COUNT(CASE WHEN d.wides IS NULL THEN 1 END)                            AS balls_faced,
        MAX(ib.runs)                                                            AS highest_score
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    JOIN innings_batters ib ON ib.match_id = d.match_id
                           AND ib.innings_number = d.innings_number
                           AND ib.batter_id = d.batter_id
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

dismissals AS (
    SELECT
        w.player_out_id                                                         AS player_id,
        COUNT(*)                                                                AS dismissals
    FROM wickets w
    JOIN matches m ON m.match_id = w.match_id
    JOIN innings i ON i.match_id = w.match_id
                  AND i.innings_number = w.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND w.kind NOT IN ('retired hurt', 'retired out', 'retired not out')
      AND w.player_out_id IN {player_ids_sql}
    GROUP BY w.player_out_id
),

highest_score_notout AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        CASE WHEN ib.out = 'not out' THEN TRUE ELSE FALSE END                  AS highest_score_not_out
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    JOIN batting_basic bb ON bb.player_id = ib.batter_id
                         AND ib.runs = bb.highest_score
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.batter_id IN {player_ids_sql}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ib.batter_id ORDER BY m.match_date_1 DESC) = 1
),

fifties_plus AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        COUNT(*)                                                                AS fifties_plus
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.runs >= 50
      AND ib.batter_id IN {player_ids_sql}
    GROUP BY ib.batter_id
),

batting_advanced AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(CASE WHEN ball_seq <= 10 THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN ball_seq <= 10 THEN 1 END), 0), 2)        AS first_10_ball_sr,
        ROUND(COUNT(CASE WHEN d.wides IS NULL THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN (d.runs_batter = 4 OR d.runs_batter = 6)
                                AND d.is_not_boundary IS NOT TRUE THEN 1 END), 0), 2) AS balls_per_boundary,
        ROUND(SUM(CASE WHEN (d.runs_batter != 4 AND d.runs_batter != 6)
                            OR d.is_not_boundary IS TRUE THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND ((d.runs_batter != 4 AND d.runs_batter != 6)
                                OR d.is_not_boundary IS TRUE) THEN 1 END), 0), 2) AS non_boundary_sr,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0 AND d.wides IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS dot_pct
    FROM (
        SELECT
            d.*,
            ROW_NUMBER() OVER (
                PARTITION BY d.match_id, d.innings_number, d.batter_id
                ORDER BY d.over_number, d.ball_index
            ) AS ball_seq
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        JOIN innings i ON i.match_id = d.match_id
                      AND i.innings_number = d.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND d.wides IS NULL
          AND d.batter_id IN {player_ids_sql}
    ) d
    GROUP BY d.batter_id
),

sr_edge AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.window_relative_sr > 0
                         AND ib.balls_faced >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls_faced >= 6 THEN 1 END), 0), 4)   AS sr_edge
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.batter_id IN {player_ids_sql}
    GROUP BY ib.batter_id
),

most_common_position AS (
    SELECT
        batter_id                                                               AS player_id,
        batting_position                                                        AS most_common_position
    FROM (
        SELECT
            ib.batter_id,
            ib.batting_position,
            COUNT(*)                                                            AS pos_count,
            ROW_NUMBER() OVER (
                PARTITION BY ib.batter_id
                ORDER BY COUNT(*) DESC
            )                                                                   AS rn
        FROM innings_batters ib
        JOIN matches m ON m.match_id = ib.match_id
        JOIN innings i ON i.match_id = ib.match_id
                      AND i.innings_number = ib.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND ib.batter_id IN {player_ids_sql}
        GROUP BY ib.batter_id, ib.batting_position
    )
    WHERE rn = 1
),

powerplay_batting AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS powerplay_sr,
        ROUND(SUM(d.runs_batter) * 1.0 /
              NULLIF(COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number)), 0), 2) AS powerplay_avg
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.over_number BETWEEN 0 AND 5
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

death_batting AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS death_sr,
        ROUND(SUM(d.runs_batter) * 1.0 /
              NULLIF(COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number)), 0), 2) AS death_avg
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.over_number >= 15
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

positional_averages AS (
    SELECT
        mcp.player_id,
        ROUND(AVG(bb2.balls_faced), 2)                                          AS batting_position_avg_balls,
        ROUND(AVG(bb2.runs * 100.0 / NULLIF(bb2.balls_faced, 0)), 2)           AS batting_position_avg_sr
    FROM most_common_position mcp
    JOIN most_common_position mcp2 ON mcp2.most_common_position = mcp.most_common_position
    JOIN batting_basic bb2 ON bb2.player_id = mcp2.player_id
    GROUP BY mcp.player_id
),

bowling_basic AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number))              AS innings_bowled,
        SUM(d.runs_batter + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0))    AS runs_conceded,
        COUNT(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 END)       AS legal_balls,
        COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END)                          AS wickets
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    LEFT JOIN wickets w ON w.match_id = d.match_id
                       AND w.innings_number = d.innings_number
                       AND w.over_number = d.over_number
                       AND w.ball_index = d.ball_index
                       AND w.kind NOT IN ('run out','retired hurt','retired out',
                           'obstructing the field','handled the ball',
                           'hit the ball twice','timed out')
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),

three_wkt_hauls AS (
    SELECT
        ib.bowler_id                                                            AS player_id,
        COUNT(*)                                                                AS three_wicket_hauls
    FROM innings_bowlers ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.wickets >= 3
      AND ib.bowler_id IN {player_ids_sql}
    GROUP BY ib.bowler_id
),

bowling_advanced AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0
                         AND d.wides IS NULL
                         AND d.noballs IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND d.noballs IS NULL THEN 1 END), 0), 2)      AS bowling_dot_pct,
        ROUND(SUM(CASE WHEN d.runs_batter IN (4, 6)
                            AND d.is_not_boundary IS NOT TRUE
                       THEN d.runs_batter ELSE 0 END) * 6.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND d.noballs IS NULL THEN 1 END), 0), 2)      AS boundary_runs_per_over
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),

bowling_edge AS (
    SELECT
        ib.bowler_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.team_relative_economy < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS econ_edge,
        ROUND(COUNT(CASE WHEN ib.team_relative_sr < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS wicket_edge
    FROM innings_bowlers ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.bowler_id IN {player_ids_sql}
    GROUP BY ib.bowler_id
),

batting_percentiles AS (
    SELECT
        player_id,
        ROUND(PERCENT_RANK() OVER (ORDER BY first_10_ball_sr) * 100, 2)        AS first_10_sr_percentile,
        ROUND(PERCENT_RANK() OVER (ORDER BY powerplay_sr) * 100, 2)            AS powerplay_sr_percentile,
        ROUND(PERCENT_RANK() OVER (ORDER BY powerplay_avg) * 100, 2)           AS powerplay_avg_percentile,
        ROUND(PERCENT_RANK() OVER (ORDER BY death_sr) * 100, 2)                AS death_sr_percentile,
        ROUND(PERCENT_RANK() OVER (ORDER BY death_avg) * 100, 2)               AS death_avg_percentile
    FROM (
        SELECT
            bb.player_id,
            ba.first_10_ball_sr,
            pp.powerplay_sr,
            pp.powerplay_avg,
            db.death_sr,
            db.death_avg
        FROM batting_basic bb
        LEFT JOIN batting_advanced ba ON ba.player_id = bb.player_id
        LEFT JOIN powerplay_batting pp ON pp.player_id = bb.player_id
        LEFT JOIN death_batting db ON db.player_id = bb.player_id
    )
),

bowling_percentiles AS (
    SELECT
        player_id,
        ROUND(PERCENT_RANK() OVER (ORDER BY economy ASC) * 100, 2)             AS economy_percentile,
        ROUND(PERCENT_RANK() OVER (ORDER BY bowling_sr ASC) * 100, 2)          AS bowling_sr_percentile
    FROM (
        SELECT
            player_id,
            ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2)             AS economy,
            ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2)                   AS bowling_sr
        FROM bowling_basic
        WHERE wickets >= 10 OR legal_balls >= 30
    )
),

top7_wickets_cte AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END)                          AS top7_wickets
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    JOIN innings_batters ib ON ib.match_id = d.match_id
                           AND ib.innings_number = d.innings_number
                           AND ib.batter_id = d.batter_id
                           AND ib.batting_position BETWEEN 1 AND 7
    LEFT JOIN wickets w ON w.match_id = d.match_id
                       AND w.innings_number = d.innings_number
                       AND w.over_number = d.over_number
                       AND w.ball_index = d.ball_index
                       AND w.kind NOT IN ('run out','retired hurt','retired out',
                           'obstructing the field','handled the ball',
                           'hit the ball twice','timed out')
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),
team_runs_rank AS (
    SELECT
        p.player_id,
        RANK() OVER (PARTITION BY p.team ORDER BY COALESCE(bb.runs, 0) DESC)   AS team_runs_rank
    FROM players p
    LEFT JOIN batting_basic bb ON bb.player_id = p.player_id
),

team_wickets_rank AS (
    SELECT
        p.player_id,
        RANK() OVER (PARTITION BY p.team ORDER BY COALESCE(bw.wickets, 0) DESC) AS team_wickets_rank
    FROM players p
    LEFT JOIN bowling_basic bw ON bw.player_id = p.player_id
)

SELECT
    p.player_id,
    bb.innings_batted,
    bb.runs,
    bb.balls_faced,
    ROUND(bb.runs * 1.0 / NULLIF(di.dismissals, 0), 2)                        AS batting_average,
    ROUND(bb.runs * 100.0 / NULLIF(bb.balls_faced, 0), 2)                     AS batting_sr,
    bb.highest_score,
    hs.highest_score_not_out,
    fp.fifties_plus,
    ba.first_10_ball_sr,
    ba.balls_per_boundary,
    ba.non_boundary_sr,
    ba.dot_pct,
    se.sr_edge,
    mcp.most_common_position,
    pp.powerplay_sr,
    pp.powerplay_avg,
    db.death_sr,
    db.death_avg,
    pa.batting_position_avg_sr,
    pa.batting_position_avg_balls,
    bpc.first_10_sr_percentile,
    bpc.powerplay_sr_percentile,
    bpc.powerplay_avg_percentile,
    bpc.death_sr_percentile,
    bpc.death_avg_percentile,
    tr.team_runs_rank,
    bw.innings_bowled,
    bw.runs_conceded,
    bw.wickets,
    ROUND(bw.runs_conceded * 6.0 / NULLIF(bw.legal_balls, 0), 2)              AS economy,
    ROUND(bw.runs_conceded * 1.0 / NULLIF(bw.wickets, 0), 2)                  AS bowling_average,
    ROUND(bw.legal_balls * 1.0 / NULLIF(bw.wickets, 0), 2)                    AS bowling_sr,
    tw.three_wicket_hauls,
    bwa.bowling_dot_pct,
    bwa.boundary_runs_per_over,
    be.econ_edge,
    be.wicket_edge,
    wpc.bowling_sr_percentile,
    wpc.economy_percentile,
    wr.team_wickets_rank,
    t7.top7_wickets
FROM players p
LEFT JOIN batting_basic bb ON bb.player_id = p.player_id
LEFT JOIN dismissals di ON di.player_id = p.player_id
LEFT JOIN highest_score_notout hs ON hs.player_id = p.player_id
LEFT JOIN fifties_plus fp ON fp.player_id = p.player_id
LEFT JOIN batting_advanced ba ON ba.player_id = p.player_id
LEFT JOIN sr_edge se ON se.player_id = p.player_id
LEFT JOIN most_common_position mcp ON mcp.player_id = p.player_id
LEFT JOIN powerplay_batting pp ON pp.player_id = p.player_id
LEFT JOIN death_batting db ON db.player_id = p.player_id
LEFT JOIN positional_averages pa ON pa.player_id = p.player_id
LEFT JOIN batting_percentiles bpc ON bpc.player_id = p.player_id
LEFT JOIN team_runs_rank tr ON tr.player_id = p.player_id
LEFT JOIN bowling_basic bw ON bw.player_id = p.player_id
LEFT JOIN three_wkt_hauls tw ON tw.player_id = p.player_id
LEFT JOIN bowling_advanced bwa ON bwa.player_id = p.player_id
LEFT JOIN bowling_edge be ON be.player_id = p.player_id
LEFT JOIN bowling_percentiles wpc ON wpc.player_id = p.player_id
LEFT JOIN team_wickets_rank wr ON wr.player_id = p.player_id
LEFT JOIN top7_wickets_cte t7 ON t7.player_id = p.player_id
""".format(
    date_from=DATE_FROM,
    date_pre_wc_to=DATE_PRE_WC_TO,
    player_ids_sql=player_ids_sql,
    player_teams_sql=player_teams_sql
)).df()

dashboard.execute("CREATE TABLE player_stats_pre_wc AS SELECT * FROM player_stats_pre_wc")
print(f"player_stats_pre_wc done — {len(player_stats_pre_wc)} rows.")

# ── Table 3: player_stats_wc ─────────────────────────────────────────────────
print("Building player_stats_wc...")

player_stats_wc = cricket.execute("""
WITH

players AS (
    SELECT pid AS player_id, team
    FROM (VALUES {player_teams_sql}) t(pid, team)
),

batting_basic AS (
    SELECT
        d.batter_id                                                             AS player_id,
        COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number))              AS innings_batted,
        SUM(d.runs_batter)                                                      AS runs,
        COUNT(CASE WHEN d.wides IS NULL THEN 1 END)                            AS balls_faced,
        MAX(ib.runs)                                                            AS highest_score
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    JOIN innings_batters ib ON ib.match_id = d.match_id
                           AND ib.innings_number = d.innings_number
                           AND ib.batter_id = d.batter_id
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

dismissals AS (
    SELECT
        w.player_out_id                                                         AS player_id,
        COUNT(*)                                                                AS dismissals
    FROM wickets w
    JOIN matches m ON m.match_id = w.match_id
    JOIN innings i ON i.match_id = w.match_id
                  AND i.innings_number = w.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND w.kind NOT IN ('retired hurt', 'retired out', 'retired not out')
      AND w.player_out_id IN {player_ids_sql}
    GROUP BY w.player_out_id
),

highest_score_notout AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        CASE WHEN ib.out = 'not out' THEN TRUE ELSE FALSE END                  AS highest_score_not_out
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    JOIN batting_basic bb ON bb.player_id = ib.batter_id
                         AND ib.runs = bb.highest_score
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.batter_id IN {player_ids_sql}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ib.batter_id ORDER BY m.match_date_1 DESC) = 1
),

fifties_plus AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        COUNT(*)                                                                AS fifties_plus
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.runs >= 50
      AND ib.batter_id IN {player_ids_sql}
    GROUP BY ib.batter_id
),

batting_advanced AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(CASE WHEN ball_seq <= 10 THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN ball_seq <= 10 THEN 1 END), 0), 2)        AS first_10_ball_sr,
        ROUND(COUNT(CASE WHEN d.wides IS NULL THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN (d.runs_batter = 4 OR d.runs_batter = 6)
                                AND d.is_not_boundary IS NOT TRUE THEN 1 END), 0), 2) AS balls_per_boundary,
        ROUND(SUM(CASE WHEN (d.runs_batter != 4 AND d.runs_batter != 6)
                            OR d.is_not_boundary IS TRUE THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND ((d.runs_batter != 4 AND d.runs_batter != 6)
                                OR d.is_not_boundary IS TRUE) THEN 1 END), 0), 2) AS non_boundary_sr,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0 AND d.wides IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS dot_pct
    FROM (
        SELECT
            d.*,
            ROW_NUMBER() OVER (
                PARTITION BY d.match_id, d.innings_number, d.batter_id
                ORDER BY d.over_number, d.ball_index
            ) AS ball_seq
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        JOIN innings i ON i.match_id = d.match_id
                      AND i.innings_number = d.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND d.wides IS NULL
          AND d.batter_id IN {player_ids_sql}
    ) d
    GROUP BY d.batter_id
),

sr_edge AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.window_relative_sr > 0
                         AND ib.balls_faced >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls_faced >= 6 THEN 1 END), 0), 4)   AS sr_edge
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.batter_id IN {player_ids_sql}
    GROUP BY ib.batter_id
),

most_common_position AS (
    SELECT
        batter_id                                                               AS player_id,
        batting_position                                                        AS most_common_position
    FROM (
        SELECT
            ib.batter_id,
            ib.batting_position,
            COUNT(*)                                                            AS pos_count,
            ROW_NUMBER() OVER (
                PARTITION BY ib.batter_id
                ORDER BY COUNT(*) DESC
            )                                                                   AS rn
        FROM innings_batters ib
        JOIN matches m ON m.match_id = ib.match_id
        JOIN innings i ON i.match_id = ib.match_id
                      AND i.innings_number = ib.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND ib.batter_id IN {player_ids_sql}
        GROUP BY ib.batter_id, ib.batting_position
    )
    WHERE rn = 1
),

powerplay_batting AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS powerplay_sr,
        ROUND(SUM(d.runs_batter) * 1.0 /
              NULLIF(COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number)), 0), 2) AS powerplay_avg
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.over_number BETWEEN 0 AND 5
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

death_batting AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS death_sr,
        ROUND(SUM(d.runs_batter) * 1.0 /
              NULLIF(COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number)), 0), 2) AS death_avg
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.over_number >= 15
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

bowling_basic AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        COUNT(DISTINCT CONCAT(d.match_id, '_', d.innings_number))              AS innings_bowled,
        SUM(d.runs_batter + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0))    AS runs_conceded,
        COUNT(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 END)       AS legal_balls,
        COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END)                          AS wickets
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    LEFT JOIN wickets w ON w.match_id = d.match_id
                       AND w.innings_number = d.innings_number
                       AND w.over_number = d.over_number
                       AND w.ball_index = d.ball_index
                       AND w.kind NOT IN ('run out','retired hurt','retired out',
                           'obstructing the field','handled the ball',
                           'hit the ball twice','timed out')
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),

three_wkt_hauls AS (
    SELECT
        ib.bowler_id                                                            AS player_id,
        COUNT(*)                                                                AS three_wicket_hauls
    FROM innings_bowlers ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.wickets >= 3
      AND ib.bowler_id IN {player_ids_sql}
    GROUP BY ib.bowler_id
),

bowling_advanced AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0
                         AND d.wides IS NULL
                         AND d.noballs IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND d.noballs IS NULL THEN 1 END), 0), 2)      AS bowling_dot_pct,
        ROUND(SUM(CASE WHEN d.runs_batter IN (4, 6)
                            AND d.is_not_boundary IS NOT TRUE
                       THEN d.runs_batter ELSE 0 END) * 6.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND d.noballs IS NULL THEN 1 END), 0), 2)      AS boundary_runs_per_over
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),

top7_wickets_cte AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END)                          AS top7_wickets
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    JOIN innings_batters ib ON ib.match_id = d.match_id
                           AND ib.innings_number = d.innings_number
                           AND ib.batter_id = d.batter_id
                           AND ib.batting_position BETWEEN 1 AND 7
    LEFT JOIN wickets w ON w.match_id = d.match_id
                       AND w.innings_number = d.innings_number
                       AND w.over_number = d.over_number
                       AND w.ball_index = d.ball_index
                       AND w.kind NOT IN ('run out','retired hurt','retired out',
                           'obstructing the field','handled the ball',
                           'hit the ball twice','timed out')
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),
bowling_edge AS (
    SELECT
        ib.bowler_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.team_relative_economy < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS econ_edge,
        ROUND(COUNT(CASE WHEN ib.team_relative_sr < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS wicket_edge
    FROM innings_bowlers ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.bowler_id IN {player_ids_sql}
    GROUP BY ib.bowler_id
)

SELECT
    p.player_id,
    bb.innings_batted,
    bb.runs,
    bb.balls_faced,
    ROUND(bb.runs * 1.0 / NULLIF(di.dismissals, 0), 2)                        AS batting_average,
    ROUND(bb.runs * 100.0 / NULLIF(bb.balls_faced, 0), 2)                     AS batting_sr,
    bb.highest_score,
    hs.highest_score_not_out,
    fp.fifties_plus,
    ba.first_10_ball_sr,
    ba.balls_per_boundary,
    ba.non_boundary_sr,
    ba.dot_pct,
    se.sr_edge,
    mcp.most_common_position,
    pp.powerplay_sr,
    pp.powerplay_avg,
    db.death_sr,
    db.death_avg,
    bw.innings_bowled,
    bw.runs_conceded,
    bw.wickets,
    ROUND(bw.runs_conceded * 6.0 / NULLIF(bw.legal_balls, 0), 2)              AS economy,
    ROUND(bw.runs_conceded * 1.0 / NULLIF(bw.wickets, 0), 2)                  AS bowling_average,
    ROUND(bw.legal_balls * 1.0 / NULLIF(bw.wickets, 0), 2)                    AS bowling_sr,
    tw.three_wicket_hauls,
    bwa.bowling_dot_pct,
    bwa.boundary_runs_per_over,
    be.econ_edge,
    be.wicket_edge,
    t7.top7_wickets
FROM players p
LEFT JOIN batting_basic bb ON bb.player_id = p.player_id
LEFT JOIN dismissals di ON di.player_id = p.player_id
LEFT JOIN highest_score_notout hs ON hs.player_id = p.player_id
LEFT JOIN fifties_plus fp ON fp.player_id = p.player_id
LEFT JOIN batting_advanced ba ON ba.player_id = p.player_id
LEFT JOIN sr_edge se ON se.player_id = p.player_id
LEFT JOIN most_common_position mcp ON mcp.player_id = p.player_id
LEFT JOIN powerplay_batting pp ON pp.player_id = p.player_id
LEFT JOIN death_batting db ON db.player_id = p.player_id
LEFT JOIN bowling_basic bw ON bw.player_id = p.player_id
LEFT JOIN three_wkt_hauls tw ON tw.player_id = p.player_id
LEFT JOIN bowling_advanced bwa ON bwa.player_id = p.player_id
LEFT JOIN bowling_edge be ON be.player_id = p.player_id
LEFT JOIN top7_wickets_cte t7 ON t7.player_id = p.player_id
""".format(
    date_from=DATE_WC_FROM,
    date_wc_to=DATE_WC_TO,
    player_ids_sql=player_ids_sql,
    player_teams_sql=player_teams_sql
)).df()

dashboard.execute("CREATE TABLE player_stats_wc AS SELECT * FROM player_stats_wc")
print(f"player_stats_wc done — {len(player_stats_wc)} rows.")


# ── Table 4: player_graph_data ───────────────────────────────────────────────
print("Building player_graph_data...")

player_graph_data = cricket.execute("""
WITH

players AS (
    SELECT pid AS player_id, bowling_type
    FROM (VALUES {player_bowling_types_sql}) t(pid, bowling_type)
),

batting_sr AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS radar_batting_sr,
        ROUND(SUM(CASE WHEN (d.runs_batter != 4 AND d.runs_batter != 6)
                            OR d.is_not_boundary IS TRUE THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND ((d.runs_batter != 4 AND d.runs_batter != 6)
                                OR d.is_not_boundary IS TRUE) THEN 1 END), 0), 2) AS radar_nbsr,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0 AND d.wides IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL THEN 1 END), 0), 2)       AS radar_dot_pct
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.batter_id IN {player_ids_sql}
    GROUP BY d.batter_id
),

first_10_sr AS (
    SELECT
        d.batter_id                                                             AS player_id,
        ROUND(SUM(CASE WHEN ball_seq <= 10 THEN d.runs_batter ELSE 0 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN ball_seq <= 10 THEN 1 END), 0), 2)        AS radar_first_10_sr
    FROM (
        SELECT
            d.*,
            ROW_NUMBER() OVER (
                PARTITION BY d.match_id, d.innings_number, d.batter_id
                ORDER BY d.over_number, d.ball_index
            ) AS ball_seq
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        JOIN innings i ON i.match_id = d.match_id
                      AND i.innings_number = d.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND d.wides IS NULL
          AND d.batter_id IN {player_ids_sql}
    ) d
    GROUP BY d.batter_id
),

sr_edge AS (
    SELECT
        ib.batter_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.window_relative_sr > 0
                         AND ib.balls_faced >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls_faced >= 6 THEN 1 END), 0), 4)   AS radar_sr_edge
    FROM innings_batters ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.batter_id IN {player_ids_sql}
    GROUP BY ib.batter_id
),

most_common_position AS (
    SELECT
        batter_id                                                               AS player_id,
        batting_position                                                        AS most_common_position
    FROM (
        SELECT
            ib.batter_id,
            ib.batting_position,
            COUNT(*)                                                            AS pos_count,
            ROW_NUMBER() OVER (
                PARTITION BY ib.batter_id
                ORDER BY COUNT(*) DESC
            )                                                                   AS rn
        FROM innings_batters ib
        JOIN matches m ON m.match_id = ib.match_id
        JOIN innings i ON i.match_id = ib.match_id
                      AND i.innings_number = ib.innings_number
        WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
          AND m.gender = 'female'
          AND m.match_type IN ('T20', 'IT20')
          AND i.super_over IS NOT TRUE
          AND ib.batter_id IN {player_ids_sql}
        GROUP BY ib.batter_id, ib.batting_position
    )
    WHERE rn = 1
),

bowling_metrics AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        ROUND(SUM(d.runs_batter + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 END), 0), 2) AS radar_economy,
        ROUND(COUNT(CASE WHEN d.runs_batter = 0
                         AND d.wides IS NULL
                         AND d.noballs IS NULL THEN 1 END) * 100.0 /
              NULLIF(COUNT(CASE WHEN d.wides IS NULL
                                AND d.noballs IS NULL THEN 1 END), 0), 2)      AS radar_dot_pct_bowl
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
),

bowling_edge AS (
    SELECT
        ib.bowler_id                                                            AS player_id,
        ROUND(COUNT(CASE WHEN ib.team_relative_economy < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS radar_econ_edge,
        ROUND(COUNT(CASE WHEN ib.team_relative_sr < 0
                         AND ib.balls >= 6 THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN ib.balls >= 6 THEN 1 END), 0), 4)         AS radar_wicket_edge
    FROM innings_bowlers ib
    JOIN matches m ON m.match_id = ib.match_id
    JOIN innings i ON i.match_id = ib.match_id
                  AND i.innings_number = ib.innings_number
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND ib.bowler_id IN {player_ids_sql}
    GROUP BY ib.bowler_id
),

important_wickets AS (
    SELECT
        d.bowler_id                                                             AS player_id,
        ROUND(COUNT(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 END) * 1.0 /
              NULLIF(COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END), 0), 2)    AS top7_bowling_sr,
        COUNT(CASE WHEN w.kind IS NOT NULL THEN 1 END)                          AS top7_wickets
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    JOIN innings i ON i.match_id = d.match_id
                  AND i.innings_number = d.innings_number
    JOIN innings_batters ib ON ib.match_id = d.match_id
                           AND ib.innings_number = d.innings_number
                           AND ib.batter_id = d.batter_id
                           AND ib.batting_position BETWEEN 1 AND 7
    LEFT JOIN wickets w ON w.match_id = d.match_id
                       AND w.innings_number = d.innings_number
                       AND w.over_number = d.over_number
                       AND w.ball_index = d.ball_index
                       AND w.kind NOT IN ('run out','retired hurt','retired out',
                           'obstructing the field','handled the ball',
                           'hit the ball twice','timed out')
    WHERE m.match_date_1 BETWEEN '{date_from}' AND '{date_pre_wc_to}'
      AND m.gender = 'female'
      AND m.match_type IN ('T20', 'IT20')
      AND i.super_over IS NOT TRUE
      AND d.bowler_id IN {player_ids_sql}
    GROUP BY d.bowler_id
)

SELECT
    p.player_id,
    p.bowling_type,
    mcp.most_common_position,
    bs.radar_batting_sr,
    bs.radar_nbsr,
    bs.radar_dot_pct,
    f.radar_first_10_sr,
    se.radar_sr_edge,
    bm.radar_economy,
    bm.radar_dot_pct_bowl,
    be.radar_econ_edge,
    be.radar_wicket_edge,
    iw.top7_bowling_sr,
    iw.top7_wickets
FROM players p
LEFT JOIN batting_sr bs ON bs.player_id = p.player_id
LEFT JOIN first_10_sr f ON f.player_id = p.player_id
LEFT JOIN sr_edge se ON se.player_id = p.player_id
LEFT JOIN most_common_position mcp ON mcp.player_id = p.player_id
LEFT JOIN bowling_metrics bm ON bm.player_id = p.player_id
LEFT JOIN bowling_edge be ON be.player_id = p.player_id
LEFT JOIN important_wickets iw ON iw.player_id = p.player_id
""".format(
    date_from=DATE_FROM,
    date_pre_wc_to=DATE_PRE_WC_TO,
    player_ids_sql=player_ids_sql,
    player_bowling_types_sql=player_bowling_types_sql
)).df()

dashboard.execute("CREATE TABLE player_graph_data AS SELECT * FROM player_graph_data")
print(f"player_graph_data done — {len(player_graph_data)} rows.")

cricket.close()
dashboard.close()
print("Done.")
