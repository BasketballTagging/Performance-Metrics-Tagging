import streamlit as st
import pandas as pd
from datetime import datetime, date
from collections import defaultdict
import base64
import io
import re

st.set_page_config(page_title="StFx Mens Basketball Tagger", layout="wide")

# ---------------------------
# Session State & Utilities
# ---------------------------
def init_state():
    st.session_state.setdefault("plays", [])                 # list[str]
    st.session_state.setdefault("log", [])                   # list[dict]
    st.session_state.setdefault("selected_play", None)       # str | None
    st.session_state.setdefault("selected_player", None)     # str | None
    st.session_state.setdefault("opponent", "")
    st.session_state.setdefault("game_date", date.today())
    st.session_state.setdefault("quarter", "")
    st.session_state.setdefault("new_play", "")

    # roster: list of dicts: {"name": str, "img_url": str|None, "img_bytes": bytes|None}
    st.session_state.setdefault("players", [])
    st.session_state.setdefault("new_player_name", "")
    st.session_state.setdefault("new_player_img_url", "")
    st.session_state.setdefault("__exports_ready", False)

def safe_filename(s: str) -> str:
    s = s.strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-\.]", "", s)
    return s

def points_from_result(result: str) -> int:
    return {"Made 2": 2, "Made 3": 3, "Missed 2": 0, "Missed 3": 0, "Foul": 0}.get(result, 0)

def add_log(play: str, result: str, player: str):
    st.session_state["log"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "opponent": st.session_state["opponent"],
        "game_date": str(st.session_state["game_date"]),
        "quarter": st.session_state["quarter"],
        "player": player,
        "play": play,
        "result": result,
        "points": points_from_result(result),
    })

def compute_metrics(log_df: pd.DataFrame, group_col: str = "play", label: str = "Play") -> pd.DataFrame:
    """
    Generic metrics by group_col (either 'play' or 'player').
    """
    if log_df.empty:
        return pd.DataFrame(columns=[label, "Attempts", "Points", "PPP", "Frequency", "Success Rate"])

    attempts = log_df.groupby(group_col).size().rename("Attempts")
    points = log_df.groupby(group_col)["points"].sum().rename("Points")
    metrics = pd.concat([attempts, points], axis=1).reset_index().rename(columns={group_col: label})
    metrics["PPP"] = metrics["Points"] / metrics["Attempts"]

    total_attempts = metrics["Attempts"].sum()
    metrics["Frequency"] = metrics["Attempts"] / (total_attempts if total_attempts else 1)

    made_mask = log_df["result"].isin(["Made 2", "Made 3"])
    att_mask  = log_df["result"].isin(["Made 2", "Made 3", "Missed 2", "Missed 3"])
    made_counts = log_df[made_mask].groupby(group_col).size()
    shot_attempts = log_df[att_mask].groupby(group_col).size()

    def success_rate(key):
        made = int(made_counts.get(key, 0))
        atts = int(shot_attempts.get(key, 0))
        return (made / atts) if atts else 0.0

    metrics["Success Rate"] = metrics[label].map(success_rate)

    metrics = metrics.sort_values(by=["PPP", "Attempts"], ascending=[False, False]).reset_index(drop=True)
    return metrics

def img_source_for_player(p: dict):
    """
    Return something st.image can display: bytes or URL or None.
    """
    if p.get("img_bytes"):
        return p["img_bytes"]
    if p.get("img_url"):
        return p["img_url"]
    return None

def add_player(name: str, img_bytes: bytes | None = None, img_url: str | None = None):
    name = name.strip()
    if not name:
        return
    # dedupe by case-insensitive name
    existing = {pl["name"].lower() for pl in st.session_state["players"]}
    if name.lower() in existing:
        st.sidebar.warning(f"{name} already in roster.")
        return
    st.session_state["players"].append({"name": name, "img_bytes": img_bytes, "img_url": img_url})

def remove_player(name: str):
    st.session_state["players"] = [p for p in st.session_state["players"] if p["name"] != name]
    if st.session_state["selected_player"] == name:
        st.session_state["selected_player"] = None

init_state()

# ---------------------------
# Sidebar: Game Setup, Playbook, Roster
# ---------------------------
st.sidebar.header("Game Setup")
st.session_state["opponent"] = st.sidebar.text_input("Opponent", value=st.session_state["opponent"])
st.session_state["game_date"] = st.sidebar.date_input("Game Date", value=st.session_state["game_date"])
st.session_state["quarter"] = st.sidebar.selectbox(
    "Quarter",
    ["", "1", "2", "3", "4", "OT"],
    index=["", "1", "2", "3", "4", "OT"].index(st.session_state["quarter"]) if st.session_state["quarter"] in ["", "1", "2", "3", "4", "OT"] else 0
)

ready_to_tag = bool(st.session_state["opponent"] and st.session_state["game_date"] and st.session_state["quarter"])

st.sidebar.markdown("---")
st.sidebar.subheader("Playbook")

st.session_state["new_play"] = st.sidebar.text_input("New Play Name", value=st.session_state["new_play"])

def add_play():
    raw = st.session_state["new_play"].strip()
    if not raw:
        return
    existing_lower = {p.lower() for p in st.session_state["plays"]}
    if raw.lower() in existing_lower:
        st.sidebar.warning("Play already exists.")
        return
    st.session_state["plays"].append(raw)
    st.session_state["new_play"] = ""

if st.sidebar.button("ADD NEW PLAY", use_container_width=True):
    add_play()

if st.session_state["plays"]:
    st.sidebar.caption("Current plays:")
    for p in st.session_state["plays"]:
        st.sidebar.write(f"• {p}")

st.sidebar.markdown("---")
st.sidebar.subheader("Player Roster")

with st.sidebar.expander("Add Player", expanded=True):
    st.session_state["new_player_name"] = st.text_input("Name", value=st.session_state["new_player_name"])
    img_file = st.file_uploader("Photo (PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=False)
    st.session_state["new_player_img_url"] = st.text_input("...or Image URL", value=st.session_state["new_player_img_url"])
    if st.button("ADD PLAYER", use_container_width=True):
        img_bytes = None
        if img_file is not None:
            img_bytes = img_file.read()
        img_url = st.session_state["new_player_img_url"].strip() or None
        add_player(st.session_state["new_player_name"], img_bytes=img_bytes, img_url=img_url)
        st.session_state["new_player_name"] = ""
        st.session_state["new_player_img_url"] = ""

with st.sidebar.expander("Bulk Import (CSV: name,image_url)"):
    roster_csv = st.file_uploader("Upload CSV", type=["csv"], key="roster_csv")
    if roster_csv is not None:
        try:
            df_roster = pd.read_csv(roster_csv)
            for _, row in df_roster.iterrows():
                n = str(row.get("name", "")).strip()
                url = str(row.get("image_url", "")).strip() or None
                if n:
                    add_player(n, img_bytes=None, img_url=url)
            st.success("Roster imported.")
        except Exception as e:
            st.error(f"Import failed: {e}")

if st.sidebar.button("Reset Game (clears log & selections)", type="secondary"):
    st.session_state["log"] = []
    st.session_state["selected_play"] = None
    st.session_state["selected_player"] = None
    st.success("Game state cleared.")

if st.sidebar.button("Clear Roster", type="secondary"):
    st.session_state["players"] = []
    st.session_state["selected_player"] = None
    st.success("Roster cleared.")

st.sidebar.markdown("---")
st.sidebar.subheader("Metrics Filter")
player_names = ["All Players"] + [p["name"] for p in st.session_state["players"]]
metrics_player_filter = st.sidebar.selectbox("Show play metrics for:", player_names)

# ---------------------------
# Main: Player-first Tagging & Metrics
# ---------------------------
st.title("StFx Mens Basketball Tagger")

if not ready_to_tag:
    st.warning("Select Opponent, Game Date, and Quarter in the sidebar to begin.")
    st.stop()
else:
    st.write(f"**Game:** vs **{st.session_state['opponent']}** | **Date:** {st.session_state['game_date']} | **Quarter:** {st.session_state['quarter']}")

# --- Player buttons (always visible) ---
st.subheader("Select a Player")
if not st.session_state["players"]:
    st.info("Add players in the sidebar to begin tagging by player.")
else:
    # grid of player cards
    per_row = 6
    rows = (len(st.session_state["players"]) + per_row - 1) // per_row
    idx = 0
    for r in range(rows):
        row_cols = st.columns(per_row)
        for c in range(per_row):
            if idx >= len(st.session_state["players"]):
                break
            p = st.session_state["players"][idx]
            with row_cols[c]:
                img_src = img_source_for_player(p)
                if img_src is not None:
                    st.image(img_src, use_column_width=True, caption=None)
                else:
                    st.write(":bust_in_silhouette: (no photo)")
                st.markdown(f"<div style='text-align:center; font-weight:600'>{p['name']}</div>", unsafe_allow_html=True)
                if st.button("Select", key=f"select_player_{idx}", use_container_width=True):
                    st.session_state["selected_player"] = p["name"]
                    # keep selected_play as-is; user may switch players quickly
            idx += 1

# --- Play buttons appear after selecting a player ---
if st.session_state["selected_player"] is None:
    st.info("Choose a player to tag a play.")
elif not st.session_state["plays"]:
    st.info("Add at least one play in the sidebar to start tagging.")
else:
    st.markdown(f"**Tagging Player:** `{st.session_state['selected_player']}`")
    st.subheader("Select a Play")
    cols_per_row = 4
    rows = (len(st.session_state["plays"]) + cols_per_row - 1) // cols_per_row
    idx = 0
    for r in range(rows):
        row_cols = st.columns(cols_per_row)
        for c in range(cols_per_row):
            if idx >= len(st.session_state["plays"]):
                break
            play = st.session_state["plays"][idx]
            if row_cols[c].button(play, key=f"play_btn_{idx}", use_container_width=True):
                st.session_state["selected_play"] = play
            idx += 1

# --- Tagging actions for selected play & player ---
if st.session_state.get("selected_play") and st.session_state.get("selected_player"):
    st.markdown(f"**Play:** `{st.session_state['selected_play']}`  |  **Player:** `{st.session_state['selected_player']}`")
    a, b, c, d, e, f, g = st.columns(7)
    if a.button("Made 2", key="act_m2", use_container_width=True):
        add_log(st.session_state["selected_play"], "Made 2", st.session_state["selected_player"])
    if b.button("Made 3", key="act_m3", use_container_width=True):
        add_log(st.session_state["selected_play"], "Made 3", st.session_state["selected_player"])
    if c.button("Missed 2", key="act_x2", use_container_width=True):
        add_log(st.session_state["selected_play"], "Missed 2", st.session_state["selected_player"])
    if d.button("Missed 3", key="act_x3", use_container_width=True):
        add_log(st.session_state["selected_play"], "Missed 3", st.session_state["selected_player"])
    if e.button("Foul", key="act_fl", use_container_width=True):
        add_log(st.session_state["selected_play"], "Foul", st.session_state["selected_player"])
    if f.button("Undo Last (Global)", key="undo_last_global", use_container_width=True):
        if st.session_state["log"]:
            st.session_state["log"].pop()
            st.toast("Last tag removed.")
        else:
            st.toast("No tags to undo.", icon="⚠️")
    if g.button("Undo Last (For Player)", key="undo_last_player", use_container_width=True):
        pl = st.session_state["selected_player"]
        for i in range(len(st.session_state["log"]) - 1, -1, -1):
            if st.session_state["log"][i].get("player") == pl:
                st.session_state["log"].pop(i)
                st.toast(f"Last tag for {pl} removed.")
                break
        else:
            st.toast(f"No tags found for {pl}.", icon="⚠️")

st.markdown("---")

# Build DataFrames
log_df = pd.DataFrame(st.session_state["log"])

# ---------------------------
# Metrics
# ---------------------------
st.subheader("📊 Per Play Metrics")
if log_df.empty:
    st.info("No data yet — tag some plays to see metrics.")
else:
    # Filter by selected player (from sidebar) for the per-play view
    if metrics_player_filter != "All Players":
        filtered_df = log_df[log_df["player"] == metrics_player_filter]
        subtitle = f"(Filtered: {metrics_player_filter})"
    else:
        filtered_df = log_df
        subtitle = "(All Players)"
    st.caption(subtitle)

    metrics_play_df = compute_metrics(filtered_df, group_col="play", label="Play")
    if metrics_play_df.empty:
        st.info("No data for selected filter yet.")
    else:
        st.dataframe(
            metrics_play_df.style.format({
                "PPP": "{:.2f}",
                "Frequency": "{:.1%}",
                "Success Rate": "{:.1%}"
            }),
            use_container_width=True,
            hide_index=True
        )
        left, right = st.columns(2)
        with left:
            st.caption("PPP by Play")
            st.bar_chart(metrics_play_df.set_index("Play")["PPP"], use_container_width=True)
        with right:
            st.caption("Frequency by Play")
            st.bar_chart(metrics_play_df.set_index("Play")["Frequency"], use_container_width=True)

st.subheader("👤 Per Player Metrics (Teamwide)")
if log_df.empty:
    st.info("No player data yet.")
else:
    metrics_player_df = compute_metrics(log_df, group_col="player", label="Player")
    st.dataframe(
        metrics_player_df.style.format({
            "PPP": "{:.2f}",
            "Frequency": "{:.1%}",
            "Success Rate": "{:.1%}"
        }),
        use_container_width=True,
        hide_index=True
    )
    st.caption("PPP by Player")
    if not metrics_player_df.empty:
        st.bar_chart(metrics_player_df.set_index("Player")["PPP"], use_container_width=True)

# ---------------------------
# Play-by-play table
# ---------------------------
st.subheader("🧾 Play-by-Play Log")
if log_df.empty:
    st.info("No events logged yet.")
else:
    st.dataframe(log_df, use_container_width=True, hide_index=True)

# ---------------------------
# Exports
# ---------------------------
st.subheader("📥 Export")
if st.button("Prepare Exports"):
    st.session_state["__exports_ready"] = True

if st.session_state.get("__exports_ready") and not log_df.empty:
    opp = safe_filename(str(st.session_state["opponent"]))
    gdt = safe_filename(str(st.session_state["game_date"]))
    qtr = safe_filename(str(st.session_state["quarter"]))

    # Per-play metrics for current sidebar player filter
    if metrics_player_filter != "All Players":
        export_metrics_df = compute_metrics(log_df[log_df["player"] == metrics_player_filter], group_col="play", label="Play")
        metrics_name_suffix = f"_{safe_filename(metrics_player_filter)}"
    else:
        export_metrics_df = compute_metrics(log_df, group_col="play", label="Play")
        metrics_name_suffix = ""

    metrics_csv = export_metrics_df.to_csv(index=False).encode("utf-8")
    log_csv = log_df.to_csv(index=False).encode("utf-8")
    json_blob = log_df.to_json(orient="records", indent=2).encode("utf-8")
    per_player_metrics_csv = compute_metrics(log_df, group_col="player", label="Player").to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Per-Play Metrics (CSV)",
        data=metrics_csv,
        file_name=f"{opp}_{gdt}_Q{qtr}_metrics{metrics_name_suffix}.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.download_button(
        "Download Per-Player Metrics (CSV)",
        data=per_player_metrics_csv,
        file_name=f"{opp}_{gdt}_Q{qtr}_per_player_metrics.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.download_button(
        "Download Play-by-Play (CSV)",
        data=log_csv,
        file_name=f"{opp}_{gdt}_Q{qtr}_playbyplay.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.download_button(
        "Download Snapshot (JSON)",
        data=json_blob,
        file_name=f"{opp}_{gdt}_Q{qtr}_snapshot.json",
        mime="application/json",
        use_container_width=True
    )
