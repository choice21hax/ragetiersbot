import json
import os
import re
import streamlit as st
import importlib
import sys

# Ensure project root on sys.path for `import main`
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import main as ectiers_main
except Exception as e:
    ectiers_main = None

def get_secret_value(name: str) -> str:
    # Mirror main.py secret resolution for display convenience
    # Prefer OS env and .env so we don't read secrets.toml unnecessarily here
    val = os.environ.get(name, "")
    # Don't silently load .env here; Streamlit reloads often and may duplicate work.
    return val


DATA_DIR = os.path.join(os.getcwd(), "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, 'w') as tf:
        json.dump(data, tf, indent=2)
    os.replace(temp_path, path)


def extract_id(token: str):
    token = token.strip()
    m = re.match(r"^<@&(?P<id>\d+)>$", token)
    if m:
        return int(m.group("id"))
    if token.isdigit():
        return int(token)
    return None


def parse_id_list(csv_text: str):
    if not csv_text:
        return []
    ids = []
    for part in csv_text.split(','):
        part = part.strip()
        maybe = extract_id(part)
        if maybe is not None:
            ids.append(maybe)
    return ids


st.set_page_config(page_title="ECTiers Config", page_icon="⚙️", layout="centered")
st.title("ECTiers Configuration")
st.caption("Edit your Discord bot settings stored in data/settings.json")

with st.expander("Environment info", expanded=False):
    st.write("APP_ID set:", bool(os.environ.get("APP_ID")))
    st.write("PUBLIC_KEY set:", bool(os.environ.get("PUBLIC_KEY")))
    st.write("TOKEN set:", bool(os.environ.get("TOKEN")))


@st.cache_resource(show_spinner=False)
def get_bot_manager():
    class BotManager:
        def __init__(self):
            self.started = False

        def start(self):
            if self.started:
                return
            if ectiers_main is None:
                raise RuntimeError("main.py not importable; run Streamlit from project root or fix PYTHONPATH.")
            try:
                ectiers_main.run_bot(block=False)
                self.started = True
            except Exception as e:
                raise

        def stop(self):
            if not self.started:
                return
            if ectiers_main is None:
                raise RuntimeError("main.py not importable")
            try:
                ectiers_main.stop_bot()
            finally:
                self.started = False

    return BotManager()


# Try to auto-start the bot once per user session if a TOKEN is available
manager = get_bot_manager()
if 'bot_autostarted' not in st.session_state:
    token_present = False
    try:
        src = st.secrets
        token_present = bool(src.get('TOKEN') or (isinstance(src.get('discord'), dict) and src['discord'].get('TOKEN')))
    except Exception:
        token_present = False
    if not token_present:
        token_present = bool(os.environ.get('TOKEN'))
    if token_present:
        try:
            if ectiers_main is not None:
                importlib.reload(ectiers_main)
            manager.start()
            st.session_state['bot_autostarted'] = True
        except Exception as e:
            st.session_state['bot_autostarted'] = False
            st.warning(f"Auto-start failed: {e}")

with st.form("settings_form"):
    current = load_settings()
    results_channel = st.text_input(
        "Results channel ID",
        value=str(current.get("results_channel", "")),
        help="Discord text channel ID to post results in",
    )
    results_roles = st.text_input(
        "Results roles (IDs or mentions, comma-separated)",
        value=",".join(str(v) for v in current.get("results_roles", [])),
        help="Only members with at least one of these roles can run /results",
    )
    queue_role = st.text_input(
        "Queue tester role (ID or mention)",
        value=str(current.get("queue_role", "")),
        help="Members with this role can Join/Leave the tester queue",
    )
    queue_category = st.text_input(
        "Queue category ID",
        value=str(current.get("queue_category", "")),
        help="Category channel where related tickets/threads may be created",
    )
    staff_role = st.text_input(
        "Staff role (optional, ID or mention)",
        value=str(current.get("staff_role", "")),
        help="Optional role used by some queue operations",
    )

    submitted = st.form_submit_button("Save settings")
    if submitted:
        next_settings = dict(current)

        if results_channel:
            rc_id = extract_id(results_channel)
            if rc_id is not None:
                next_settings["results_channel"] = rc_id
        next_settings["results_roles"] = parse_id_list(results_roles)
        if queue_role:
            qr_id = extract_id(queue_role)
            if qr_id is not None:
                next_settings["queue_role"] = qr_id
        if queue_category:
            qc_id = extract_id(queue_category)
            if qc_id is not None:
                next_settings["queue_category"] = qc_id
        if staff_role:
            sr_id = extract_id(staff_role)
            if sr_id is not None:
                next_settings["staff_role"] = sr_id

        atomic_write_json(SETTINGS_PATH, next_settings)
        st.success("Settings saved.")

st.subheader("Current raw settings")
st.code(json.dumps(load_settings(), indent=2), language="json")

st.markdown(
    "If you prefer a lightweight built-in UI instead, the bot also exposes a local panel at `http://127.0.0.1:8765` when run via `main.py`."
)

st.divider()
st.subheader("Bot control")
manager = get_bot_manager()
col1, col2, col3 = st.columns([1,1,2])
with col1:
    if st.button("Start bot", type="primary"):
        try:
            if ectiers_main is None:
                st.error("Could not import main.py. Ensure Streamlit runs from the project root or that the project is on PYTHONPATH.")
            else:
                importlib.reload(ectiers_main)
                manager.start()
                st.success("Bot start requested.")
        except Exception as e:
            st.error(f"Failed to start bot: {e}")
with col2:
    if st.button("Stop bot"):
        try:
            manager.stop()
            st.info("Bot stop requested. It may take a moment to disconnect.")
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
with col3:
    st.caption("The bot runs in a background thread inside Streamlit. Keep this app running to keep the bot online.")


