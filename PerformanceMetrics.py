import streamlit as st
import pandas as pd
import base64
import datetime

# --- SESSION STATE SETUP ---
if "players" not in st.session_state:
    st.session_state["players"] = []  # list of dicts {name, img_path}
if "playbook" not in st.session_state:
    st.session_state["playbook"] = []  # list of play names
if "events" not in st.session_state:
    st.session_state["events"] = []  # play-by-play tagging
if "selected_player" not in st.session_state:
    st.session_state["selected_player"] = None

# --- SIDEBAR: ADD PLAYERS ---
st.sidebar.header("Team Setup")
player_name = st.sidebar.text_input("Add Player Name")
player_img = st.sidebar.file_uploader("Upload Player Photo", type=["png", "jpg", "jpeg"])
if st.sidebar.button("Add Player") and player_name:
    if player_img:
        st.session_state["players"].append({"name": player_name, "img_bytes": player_img.read()})
    else:
        st.session_state["players"].append({"name": player_name, "img_bytes": None})

# --- SIDEBAR: ADD PLAYS ---
play_name = st.sidebar.text_input("Add Play to Playbook")
if st.sidebar.button("Add Play") and play_name:
    if play_name not in st.session_state["playbook"]:
        st.session_state["playbook"].append(play_name)

# --- GAME CONTEXT ---
st.header("🏀 Team Video & Analytics Tracker")
with st.expander("Game Context"):
    opponent = st.text_input("Opponent")
    date = st.date_input("Game Date", datetime.date.today())
    quarter = st.selectbox("Quarter", [1, 2, 3, 4, "OT"])

# --- PLAYER BUTTONS ---
st.subheader("Select a Player")

cols = st.columns(6)
for i, p in enumerate(st.session_state["players"]):
    with cols[i % 6]:
        if p["img_bytes"]:
            b64 = base64.b64encode(p["img_bytes"]).decode()
            img_html = f"data:image/png;base64,{b64}"
        else:
            img_html = "https://via.placeholder.com/100"

        button_html = f"""
        <div style='text-align:center'>
            <img src='{img_html}' style='width:100px;height:100px;border-radius:50%'>
            <div style='font-size:14px;margin-top:5px'>{p['name']}</div>
        </div>
        """

        if st.button(button_html, key=f"player_{i}"):
            st.session_state["selected_player"] = p["name"]

# --- PLAY TAGGING FOR SELECTED PLAYER ---
if st.session_state["selected_player"]:
    st.markdown(f"### Tagging plays for **{st.session_state['selected_player']}**")
    for play in st.session_state["playbook"]:
        if st.button(play, key=f"{st.session_state['selected_player']}_{play}"):
            st.session_state["events"].append({
                "player": st.session_state["selected_player"],
                "play": play,
                "outcome": None,
                "quarter": quarter,
                "opponent": opponent,
                "date": str(date)
            })

# --- EVENT LOG ---
st.subheader("Play-by-Play Log")
df = pd.DataFrame(st.session_state["events"])
st.dataframe(df)

# --- EXPORT ---
if not df.empty:
    st.download_button("Download CSV", df.to_csv(index=False), file_name="events.csv")
