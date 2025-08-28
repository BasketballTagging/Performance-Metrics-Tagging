import streamlit as st
import pandas as pd
from datetime import datetime, date
import base64
import re

st.set_page_config(page_title="StFx Mens Basketball Tagger", layout="wide")

# ---------------------------
# Session State & Utilities
# ---------------------------
def init_state():
    st.session_state.setdefault("plays", [])                 
    st.session_state.setdefault("log", [])                   
    st.session_state.setdefault("selected_play", None)       
    st.session_state.setdefault("selected_player", None)     
    st.session_state.setdefault("opponent", "")
    st.session_state.setdefault("game_date", date.today())
    st.session_state.setdefault("quarter", "")
    st.session_state.setdefault("new_play", "")
    st.session_state.setdefault("players", [])  # list of dicts
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
    return metrics.sort_values(by=["PPP", "Attempts"], ascending=[False, False]).reset_index(drop=True)

def img_source_for_player(p: dict):
    if p.get("img_bytes"):
        return f"data:image/png;base64,{base64.b64encode(p['img_bytes']).decode()}"
    if p.get("img_url"):
        return p["img_url"]
    return None

def add_player(name: str, img_bytes: bytes | None = None, img_url: str | None = None):
    name = name.strip()
    if not name:
        return
    existing = {pl["name"].lower() for pl in st.session_state["players"]}
    if name.lower() in existing:
        st.sidebar.warning(f"{name} already in roster.")
        return
    st.session_state["players"].append({"name": name, "img_bytes": img_bytes, "img_url": img_url})

init_state()

# ---------------------------
# Sidebar: Game Setup, Playbook, Roster
# ---------------------------
st.sidebar.header("Game Setup")
st.session_state["opponent"] = st.sidebar.text_input("Opponent", value=st.session_state["opponent"])
st.session_state["game_date"] = st.sidebar.date_input("Game Date", value=st.session_state["game_date"])
st.session_state["quarter"] = st.sidebar.selectbox(
    "Quarter", ["", "1", "2", "3", "4", "OT"],
    index=["", "1", "2", "3", "4", "OT"].index(st.session_state["quarter"]) if st.session_state["quarter"] in ["", "1", "2", "3", "4", "OT"] else 0
)

ready_to_tag = bool(st.session_state["opponent"] and st.session_state["game_date"] and st.session_state["quarter"])

st.sidebar.markdown("---")
st.sidebar.subheader("Playbook")

st.session_state["new_play"] = st.sidebar.text_input("New Play Name", value=st.session_state["new_play"])
if st.sidebar.button("ADD NEW PLAY", use_container_width=True):
    raw = st.session_state["new_play"].strip()
    if raw and raw.lower() not in {p.lower() for p in st.session_state["plays"]}:
        st.session_state["plays"].append(raw)
        st.session_state["new_play"] = ""
if st.session_state["plays"]:
    st.sidebar.caption("Current plays:")
    for p in st.session_state["plays"]:
        st.sidebar.write(f"• {p}")

st.sidebar.markdown("---")
st.sidebar.subheader("Player Roster")
with st.sidebar.expander("Add Player", expanded=True):
    st.session_state["new_player_name"] = st.text_input("Name", value=st.session_state["new_player_name"])
    img_file = st.file_uploader("Photo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    st.session_state["new_player_img_url"] = st.text_input("...or Image URL", value=st.session_state["new_player_img_url"])
    if st.button("ADD PLAYER", use_container_width=True):
        img_bytes = img_file.read() if img_file else None
        img_url = st.session_state["new_player_img_url"].strip() or None
        add_player(st.session_state["new_player_name"], img_bytes=img_bytes, img_url=img_url)
        st.session_state["new_player_name"] = ""
        st.session_state["new_player_img_url"] = ""

if st.sidebar.button("Reset Game (clears log & selections)", type="secondary"):
    st.session_state["log"].clear()
    st.session_state["selected_play"] = None
    st.session_state["selected_player"] = None
    st.success("Game state cleared.")

if st.sidebar.button("Clear Roster", type="secondary"):
    st.session_state["players"].clear()
    st.session_state["selected_player"] = None
    st.success("Roster cleared.")

st.sidebar.markdown("---")
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

# --- Player photo buttons ---
st.subheader("Select a Player")
if not st.session_state["players"]:
    st.info("Add players in the sidebar to begin tagging.")
else:
    per_row = 6
    rows = (len(st.session_state["players"]) + per_row - 1) // per_row
    idx = 0
    for r in range(rows):
        row_cols = st.columns(per_row)
        for c in range(per_row):
            if idx >= len(st.session_state["players"]):
                break
            p = st.session_state["players"][idx]
            img_src = img_source_for_player(p)
            with row_cols[c]:
                button_id = f"player_{idx}"
                selected = (st.session_state.get("selected_player") == p["name"])
                border_color = "#007BFF" if selected else "#ccc"
                if img_src:
                    button_html = f"""
                        <style>
                        .player-btn-{button_id} {{
                            border: 3px solid {border_color};
                            border-radius: 12px;
                            padding: 5px;
                            text-align: center;
                            transition: 0.2s;
                        }}
                        .player-btn-{button_id}:hover {{
                            border-color: #007BFF;
                            cursor: pointer;
                        }}
                        </style>
                        <a href="?player={p['name']}" style="text-decoration: none;">
                            <div class="player-btn-{button_id}">
                                <img src="{img_src}" style="width:100%; border-radius:12px;"/>
                                <div style="font-weight:600; color:black; margin-top:4px;">{p['name']}</div>
                            </div>
                        </a>
                    """
                else:
                    button_html = f"<div style='text-align:center;'>{p['name']}<br><em>No photo</em></div>"
                st.markdown(button_html, unsafe_allow_html=True)
            idx += 1

# --- Capture player selection from URL ---
query_params = st.experimental_get_query_params()
if "player" in query_params:
    st.session_state["selected_player"] = query_params["player"][0]

# --- Play buttons ---
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

# --- Tagging actions ---
if st.session_state.get("selected_play") and st.session_state.get("selected_player"):
    st.markdown(f"**Play:** `{st.session_state['selected_play']}` | **Player:** `{st.session_state['selected_player']}`")
    a, b, c, d, e, f = st.columns(6)
    if a.button("Made 2"): add_log(st.session_state["selected_play"], "Made 2", st.session_state["selected_player"])
    if b.button("Made 3"): add_log(st.session_state["selected_play"], "Made 3", st.session_state["selected_player"])
    if c.button("Missed 2"): add_log(st.session_state["selected_play"], "Missed 2", st.session_state["selected_player"])
    if d.button("Missed 3"): add_log(st.session_state["selected_play"], "Missed 3", st.session_state["selected_player"])
    if e.button("Foul"): add_log(st.session_state["selected_play"], "Foul", st.session_state["selected_player"])
    if f.button("Undo Last"):
        if st.session_state["log"]:
            st.session_state["log"].pop()
            st.toast("Last tag removed.")

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
    if metrics_player_filter != "All Players":
        filtered_df = log_df[log_df["player"] == metrics_player_filter]
    else:
        filtered_df = log_df
    metrics_play_df = compute_metrics(filtered_df, group_col="play", label="Play")
    st.dataframe(metrics_play_df, use_container_width=True, hide_index=True)

st.subheader("👤 Per Player Metrics")
if not log_df.empty:
    metrics_player_df = compute_metrics(log_df, group_col="player", label="Player")
    st.dataframe(metrics_player_df, use_container_width=True, hide_index=True)

# ---------------------------
# Play-by-play log
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
    metrics_csv = compute_metrics(log_df, group_col="play", label="Play").to_csv(index=False).encode("utf-8")
    log_csv = log_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Metrics CSV", metrics_csv, file_name=f"{opp}_{gdt}_Q{qtr}_metrics.csv", mime="text/csv")
    st.download_button("Download Play-by-Play CSV", log_csv, file_name=f"{opp}_{gdt}_Q{qtr}_playbyplay.csv", mime="text/csv")
