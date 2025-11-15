# iesm_live_lookup.py
"""
Streamlit app that verifies user email against a live Google Sheet served
by an Apps Script Web App and auto-fills Name / Department / Dept Lead.

Set the Apps Script web app URL and the token in Streamlit secrets for production:
  [deployment]
  APPSCRIPT_URL = "https://script.google.com/macros/s/AKfycbziYwpJylR0RqE6rpc1Yehoi3jXNwY4VkkguFznbSF3Of5UkELcN2QL6Yko931mIwz8/exec"
  APPSCRIPT_TOKEN = "DeepakPappusetty"

Or for quick local test, edit APPSCRIPT_URL_FALLBACK and APPSCRIPT_TOKEN_FALLBACK below.
"""
import streamlit as st
import requests
import json
from typing import Optional

# ---------- FALLBACK (safe) ----------
APPSCRIPT_URL_FALLBACK = "https://script.google.com/macros/s/AKfycbziYwpJylR0RqE6rpc1Yehoi3jXNwY4VkkguFznbSF3Of5UkELcN2QL6Yko931mIwz8/exec"
APPSCRIPT_TOKEN_FALLBACK = None  # never store token here

# ---------- Helpers ----------
def get_apps_script_config():
    import os
    # 1) nested [deployment]
    try:
        d = st.secrets.get("deployment")
        if d and "APPSCRIPT_URL" in d:
            return d.get("APPSCRIPT_URL"), d.get("APPSCRIPT_TOKEN")
    except Exception:
        pass
    # 2) top-level secrets
    try:
        url = st.secrets.get("APPSCRIPT_URL")
        token = st.secrets.get("APPSCRIPT_TOKEN")
        if url:
            return url, token
    except Exception:
        pass
    # 3) environment
    env_url = os.getenv("APPSCRIPT_URL")
    env_token = os.getenv("APPSCRIPT_TOKEN")
    if env_url:
        return env_url, env_token
    # 4) fallback
    return APPSCRIPT_URL_FALLBACK, APPSCRIPT_TOKEN_FALLBACK

APPSCRIPT_URL, APPSCRIPT_TOKEN = get_apps_script_config()

if hasattr(st, "cache_data"):
    cache_decorator = st.cache_data
else:
    cache_decorator = st.cache

@cache_decorator(ttl=60)
def fetch_sheet_data(url: str, token: Optional[str], timeout: int = 8) -> dict:
    if not url:
        return {"ok": False, "error": "Apps Script URL not configured.", "data": None}
    params = {}
    if token:
        params["token"] = token
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        j = resp.json()
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Network error: {e}", "data": None}
    except ValueError:
        return {"ok": False, "error": "Invalid JSON returned from apps script.", "data": None}

    if isinstance(j, dict) and "error" in j:
        return {"ok": False, "error": f"Server error: {j.get('error')}", "data": None}
    if isinstance(j, dict) and "data" in j and isinstance(j["data"], list):
        return {"ok": True, "error": None, "data": j["data"]}
    if isinstance(j, list):
        return {"ok": True, "error": None, "data": j}
    return {"ok": False, "error": "Unexpected response from apps script.", "data": None}

def find_email_row(rows, email_norm):
    if not rows:
        return None
    keys = list(rows[0].keys())
    email_cols = [k for k in keys if "email" in k.lower()]
    if not email_cols:
        sample = rows[0]
        for k in keys:
            v = str(sample.get(k, "")).strip()
            if "@" in v:
                email_cols.append(k)
    for r in rows:
        for ec in email_cols:
            val = str(r.get(ec, "")).strip().lower()
            if val == email_norm:
                return r
    return None

def pick_key(keys, candidates):
    for cand in candidates:
        for k in keys:
            if cand in k.lower():
                return k
    return None

# ---------- session_state defaults ----------
if "email_verified" not in st.session_state:
    st.session_state["email_verified"] = False
if "user_row" not in st.session_state:
    st.session_state["user_row"] = None
if "requester_email" not in st.session_state:
    st.session_state["requester_email"] = None
# widgets will own these keys; initialize if absent
if "request_type" not in st.session_state:
    st.session_state["request_type"] = None
if "dept_type" not in st.session_state:
    st.session_state["dept_type"] = None

# ---------- UI ----------
st.set_page_config(page_title="IESM - Isha Engineering Service Management", layout="centered")
st.title("IESM — Isha Engineering Service Management")
st.write("Enter your official email; we will verify against the live IESM Users sheet and autofill your details.")

with st.form("email_form", clear_on_submit=False):
    email_input = st.text_input("Your official email ID", placeholder="you@yourdomain.org")
    verify_btn = st.form_submit_button("Verify email")

if verify_btn:
    email_norm = (email_input or "").strip().lower()
    if not email_norm:
        st.warning("Please enter an email to verify.")
    else:
        with st.spinner("Checking IESM Users sheet..."):
            result = fetch_sheet_data(APPSCRIPT_URL, APPSCRIPT_TOKEN)
        if not result["ok"]:
            st.error(result["error"])
        else:
            rows = result["data"]
            matched = find_email_row(rows, email_norm)
            if not matched:
                st.session_state["email_verified"] = False
                st.session_state["user_row"] = None
                st.session_state["requester_email"] = None
                st.error("Email not found in IESM Users sheet. Please check spelling or contact admin.")
            else:
                st.session_state["email_verified"] = True
                st.session_state["user_row"] = matched
                st.session_state["requester_email"] = email_norm
                st.success("Email verified — details loaded.")

# ---------- After verification ----------
if st.session_state["email_verified"] and st.session_state["user_row"]:
    row = st.session_state["user_row"]

    keys = list(row.keys())
    name_key = pick_key(keys, ["name", "full name", "fullname"])
    dept_key = pick_key(keys, ["department", "dept", "team"])
    lead_key = pick_key(keys, ["lead", "department lead", "dept lead", "lead email", "lead_email"])

    name_val = row.get(name_key, "") if name_key else ""
    dept_val = row.get(dept_key, "") if dept_key else ""
    lead_val = row.get(lead_key, "") if lead_key else ""

    st.markdown("## Your details (autofilled)")
    col1, col2 = st.columns([2, 2])
    with col1:
        st.text_input("Name", value=name_val, key="ui_name", disabled=True)
        st.text_input("Department Name", value=dept_val, key="ui_dept", disabled=True)
    with col2:
        st.text_input("Dept Lead Email ID", value=lead_val, key="ui_dept_lead", disabled=True)
        st.write("")

    st.write("---")
    st.markdown("## Create Request")

    # Let the widget manage request_type
    request_type = st.selectbox(
        "Type of request",
        options=["-- Select --", "Maintenance", "New", "Project"],
        index=0 if not st.session_state.get("request_type") else (
            ["-- Select --", "Maintenance", "New", "Project"].index(st.session_state["request_type"])
            if st.session_state["request_type"] in ["Maintenance", "New", "Project"] else 0
        ),
        key="request_type",
    )

    # read current selected request type from session_state (widget wrote it)
    current_req = st.session_state.get("request_type")

    # Departments involved UI — do NOT assign into the same widget keys
    if current_req == "Project":
        st.markdown("**Departments involved:** Multiple (auto-selected for Project)")
        st.text_input("Departments involved", value="Multiple", key="ui_deptinfo", disabled=True)

    elif current_req in ("Maintenance", "New"):
        # widget will set st.session_state["dept_type"]
        dept_choice = st.selectbox(
            "Departments involved",
            options=["-- Select --", "Single", "Multiple"],
            index=0 if not st.session_state.get("dept_type") else (
                ["-- Select --", "Single", "Multiple"].index(st.session_state["dept_type"])
                if st.session_state["dept_type"] in ["Single", "Multiple"] else 0
            ),
            key="dept_type"
        )
        # do NOT set st.session_state["dept_type"] manually here

   # master ticket UI removed for now
# compute department_type for preview without writing to widget keys
if st.session_state.get("request_type") == "Project":
    computed_dept_type = "Multiple"
else:
    computed_dept_type = st.session_state.get("dept_type")

    preview = {
        "requester_email": st.session_state.get("requester_email"),
        "name": name_val,
        "department": dept_val,
        "department_lead_email": lead_val,
        "request_type": st.session_state.get("request_type"),
        "department_type": computed_dept_type,
    }
    st.markdown("#### Preview payload")
    st.code(json.dumps(preview, indent=2))

    if st.button("Create master ticket and children (preview only)"):
        st.success("Payload ready — see preview above. (Integrate with JIRA API next.)")

else:
    st.info("Please verify your email first so we can autofill your details from the IESM Users sheet.")
    if not APPSCRIPT_URL:
        st.warning("Apps Script URL not configured. Please set it in st.secrets or environment variables.")
    # The widget already sets st.session_state["dept_type"] for us.

    
