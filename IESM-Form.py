# iesm_live_lookup.py
"""
Streamlit app that verifies user email against a live Google Sheet served
by an Apps Script Web App and auto-fills Name / Department / Dept Lead.

Set the Apps Script web app URL and the token in Streamlit secrets for production:
  [deployment]
  APPSCRIPT_URL = "https://script.google.com/macros/s/AKfycb.../exec"
  APPSCRIPT_TOKEN = "DeepakPappusetty"

Or for quick local test, edit APPSCRIPT_URL_FALLBACK and APPSCRIPT_TOKEN_FALLBACK below.
"""
import streamlit as st
import requests
import json
from typing import Optional

# ---- CONFIG - replace with your webapp URL if you want to hardcode for quick test ----
APPSCRIPT_URL_FALLBACK = "https://script.google.com/macros/s/AKfycbziYwpJylR0RqE6rpc1Yehoi3jXNwY4VkkguFznbSF3Of5UkELcN2QL6Yko931mIwz8/exec"
APPSCRIPT_TOKEN_FALLBACK = DeepakPappusetty  # <--- for quick testing you can paste the SECRET_TOKEN here, but DON'T commit to git

# ---- Use secrets when available (recommended) ----
# In Streamlit Cloud: add secrets in Settings -> Secrets
# Example secrets.toml content:
# [deployment]
# APPSCRIPT_URL = "https://script.google.com/macros/s/AKfycb.../exec"
# APPSCRIPT_TOKEN = "long_secret_token_here"
def get_apps_script_config():
    # prefer secrets
    url = None
    token = None
    try:
        url = st.secrets["deployment"]["APPSCRIPT_URL"]
        token = st.secrets["deployment"]["APPSCRIPT_TOKEN"]
    except Exception:
        # fall back to hardcoded test values
        url = APPSCRIPT_URL_FALLBACK
        token = APPSCRIPT_TOKEN_FALLBACK
    return url, token

APPSCRIPT_URL, APPSCRIPT_TOKEN = get_apps_script_config()

# ---- Streamlit UI ----
st.set_page_config(page_title="IESM - Live Lookup", layout="centered")
st.title("IESM — Isha Engineering Service Management")
st.write("Enter your official email; we will verify against the live IESM Users sheet and autofill your details.")

def fetch_users(url: str, token: str, timeout: int = 8) -> Optional[dict]:
    """
    Call Apps Script web app. Returns a dict with keys:
      - 'ok': bool
      - 'data': list of row dicts (if ok)
      - 'error': string (if not ok)
    """
    if not url:
        return {"ok": False, "error": "Apps Script URL not configured."}
    # token may be None -> server returns unauthorized
    params = {}
    if token:
        params["token"] = token
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        j = resp.json()
    except requests.RequestException as e:
        return {"ok": False, "error": f"Network error: {e}"}
    except ValueError:
        return {"ok": False, "error": "Invalid JSON returned by apps script."}

    # handle common server responses
    if isinstance(j, dict) and "error" in j:
        return {"ok": False, "error": f"Server error: {j.get('error')}"}
    if isinstance(j, dict) and "data" in j and isinstance(j["data"], list):
        return {"ok": True, "data": j["data"]}
    # if server returned a list directly
    if isinstance(j, list):
        return {"ok": True, "data": j}
    return {"ok": False, "error": "Unexpected response shape from server."}

def find_email_row(rows, email_norm):
    """
    Search rows (list of dicts) for a matching normalized email.
    Returns matched row dict or None.
    """
    if not rows:
        return None

    # discover possible email columns
    keys = list(rows[0].keys())
    email_cols = [k for k in keys if "email" in k.lower()]
    # fallback: any key that contains '@' in sample values
    if not email_cols:
        sample = rows[0]
        for k in keys:
            try:
                v = str(sample.get(k, "")).strip()
                if "@" in v:
                    email_cols.append(k)
            except Exception:
                pass

    # make normalized matching
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

# ---- Email verification form ----
with st.form("email_form"):
    email_input = st.text_input("Your official email ID", placeholder="you@yourdomain.org")
    verify_btn = st.form_submit_button("Verify email")

if verify_btn:
    email_norm = (email_input or "").strip().lower()
    if not email_norm:
        st.warning("Please enter your email address.")
    else:
        with st.spinner("Checking IESM Users sheet..."):
            result = fetch_users(APPSCRIPT_URL, APPSCRIPT_TOKEN)
        if not result["ok"]:
            st.error(result["error"])
        else:
            rows = result["data"]
            matched = find_email_row(rows, email_norm)
            if not matched:
                st.error("Email not found in IESM Users sheet. Please check spelling or contact admin.")
            else:
                st.success("Email verified — details loaded.")
                # heuristics to pick name / dept / dept lead keys
                keys = list(matched.keys())
                name_key = pick_key(keys, ["name", "full name", "fullname"])
                dept_key = pick_key(keys, ["department", "dept", "team"])
                lead_key = pick_key(keys, ["lead", "department lead", "dept lead", "lead email", "lead_email"])

                name_val = matched.get(name_key, "") if name_key else ""
                dept_val = matched.get(dept_key, "") if dept_key else ""
                lead_val = matched.get(lead_key, "") if lead_key else ""

                # show autofilled fields (disabled by default)
                st.markdown("### Your details (autofilled)")
                c1, c2 = st.columns(2)
                with c1:
                    st.text_input("Name", value=name_val, key="user_name", disabled=True)
                    st.text_input("Department Name", value=dept_val, key="user_dept", disabled=True)
                with c2:
                    st.text_input("Dept Lead Email ID", value=lead_val, key="user_dept_lead", disabled=True)
                    st.write("")  # spacer

                st.write("---")
                # now show request type + dept involved UI
                st.markdown("### Create Request")
                request_type = st.selectbox(
                    "Type of request",
                    options=["-- Select --", "Maintenance", "New", "Project"],
                    index=0,
                    key="ui_request_type"
                )

                if request_type != "-- Select --":
                    if request_type == "Project":
                        st.markdown("**Departments involved:** Multiple (auto-selected for Project)")
                        department_type = "Multiple"
                    else:
                        department_type = st.selectbox(
                            "Departments involved",
                            options=["-- Select --", "Single", "Multiple"],
                            index=0,
                            key="ui_dept_type"
                        )
                        if department_type == "-- Select --":
                            department_type = None

                    # preview
                    st.write("---")
                    preview = {
                        "requester_email": email_norm,
                        "name": name_val,
                        "department": dept_val,
                        "department_lead_email": lead_val,
                        "request_type": request_type,
                        "department_type": department_type,
                    }
                    st.markdown("#### Preview payload")
                    st.code(json.dumps(preview, indent=2))
                    # Optionally you can now add buttons to "Create master ticket" etc.
