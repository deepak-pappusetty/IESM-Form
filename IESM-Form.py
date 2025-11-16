# IESM-Form.py
"""
IESM Streamlit app with dynamic request rows from Config sheet.

Secrets (Streamlit Cloud or local secrets.toml):
[deployment]
APPSCRIPT_URL = "https://script.google.com/macros/s/AKfycbzi.../exec"
APPSCRIPT_TOKEN = "your_token_here"

Notes:
- This app requests the Config sheet by calling the Apps Script endpoint with `sheet=Config`.
- If your Apps Script web app does not support a `sheet` param, update it to return the requested sheet as JSON.
"""
import streamlit as st
import requests
import json
import datetime
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

# caching decorator compatibility
if hasattr(st, "cache_data"):
    cache_decorator = st.cache_data
else:
    cache_decorator = st.cache

@cache_decorator(ttl=60)
def fetch_sheet_data(url: str, token: Optional[str], sheet: Optional[str] = None, timeout: int = 8) -> dict:
    """
    Call the Apps Script web app. Returns dict: {"ok": bool, "data": list|None, "error": str|None}
    If `sheet` is provided, we send it as a query param: ?sheet=Config
    """
    if not url:
        return {"ok": False, "error": "Apps Script URL not configured.", "data": None}
    params = {}
    if token:
        params["token"] = token
    if sheet:
        params["sheet"] = sheet
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

# Parse the config sheet into dict of header -> list of non-empty values
def parse_config_columns(rows):
    """
    rows: list of row dicts or list-of-lists depending on Apps Script output.
    We expect either:
      - list of dicts where keys are headers, or
      - list of lists (first row headers, subsequent rows values)
    Return: dict(header -> [value1, value2...])
    """
    cols = {}
    if not rows:
        return cols

    # If rows are dicts
    if isinstance(rows[0], dict):
        headers = list(rows[0].keys())
        # initialize lists from column values
        for h in headers:
            vals = []
            for r in rows:
                v = r.get(h, "")
                if v is None:
                    v = ""
                v = str(v).strip()
                if v:
                    vals.append(v)
            # drop the header itself if it appeared in rows; we want items below header
            # If first entry equals header text, remove it
            if vals and vals[0].strip().lower() == str(h).strip().lower():
                vals = vals[1:]
            cols[h] = vals
        return cols

    # If rows are lists (first row is headers)
    if isinstance(rows[0], list):
        headers = rows[0]
        for ci, h in enumerate(headers):
            vals = []
            for r in rows[1:]:
                if ci < len(r):
                    v = r[ci]
                    if v is None:
                        v = ""
                    v = str(v).strip()
                    if v:
                        vals.append(v)
            cols[h] = vals
        return cols

    return cols

# ---------- session state defaults ----------
if "email_verified" not in st.session_state:
    st.session_state["email_verified"] = False
if "user_row" not in st.session_state:
    st.session_state["user_row"] = None
if "requester_email" not in st.session_state:
    st.session_state["requester_email"] = None

# widgets will own these keys
if "request_type" not in st.session_state:
    st.session_state["request_type"] = None
if "dept_type" not in st.session_state:
    st.session_state["dept_type"] = None

# small cache for config (so we don't re-request each change)
if "config_columns" not in st.session_state:
    st.session_state["config_columns"] = None
if "config_error" not in st.session_state:
    st.session_state["config_error"] = None

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
            result = fetch_sheet_data(APPSCRIPT_URL, APPSCRIPT_TOKEN, sheet="User")
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

# ---------- Load Config once (lazy) ----------
def load_config_once():
    if st.session_state.get("config_columns") is None and st.session_state.get("config_error") is None:
        # try to fetch Config sheet from the same webapp; requires Apps Script support for `sheet=Config`
        cfg_res = fetch_sheet_data(APPSCRIPT_URL, APPSCRIPT_TOKEN, sheet="Config")
        if not cfg_res["ok"]:
            st.session_state["config_error"] = cfg_res["error"]
            st.session_state["config_columns"] = {}
            return
        cols = parse_config_columns(cfg_res["data"])
        st.session_state["config_columns"] = cols

# run config load lazily when UI is rendered
load_config_once()

# ---------- After verification ----------
if st.session_state["email_verified"] and st.session_state["user_row"]:
    row = st.session_state["user_row"]

    keys = list(row.keys())
    name_key = pick_key(keys, ["name", "full name", "fullname"])
    dept_key = pick_key(keys, ["department", "dept", "team"])
    lead_key = pick_key(keys, ["lead", "department lead", "dept lead", "lead email", "lead_email"])
    # location_key tried but location choices are populated from entire Users sheet (not tied to user)
    location_key = pick_key(keys, ["location", "location name", "campus", "site"]) or "Location"

    name_val = row.get(name_key, "") if name_key else ""
    dept_val = row.get(dept_key, "") if dept_key else ""
    lead_val = row.get(lead_key, "") if lead_key else ""
    user_location = str(row.get(location_key, "")).strip() if row.get(location_key, None) is not None else ""

    st.markdown("## Your details (autofilled)")
    col1, col2 = st.columns([2, 2])
    with col1:
        st.text_input("Name", value=name_val, key="ui_name", disabled=True)
        st.text_input("Department Name", value=dept_val, key="ui_dept", disabled=True)
    with col2:
        st.text_input("Dept Lead Email ID", value=lead_val, key="ui_dept_lead", disabled=True)

    st.write("---")
    st.markdown("## Create Request")

    # Request type selectbox
    request_type = st.selectbox(
        "Type of request",
        options=["-- Select --", "Maintenance", "New", "Project"],
        index=0 if not st.session_state.get("request_type") else (
            ["-- Select --", "Maintenance", "New", "Project"].index(st.session_state["request_type"])
            if st.session_state["request_type"] in ["Maintenance", "New", "Project"] else 0
        ),
        key="request_type",
    )
    current_req = st.session_state.get("request_type")

    # Departments involved selection
    if current_req == "Project":
        st.markdown("**Departments involved:** Multiple (auto-selected for Project)")
        st.text_input("Departments involved", value="Multiple", key="ui_deptinfo", disabled=True)

    elif current_req in ("Maintenance", "New"):
        dept_choice = st.selectbox(
            "Departments involved",
            options=["-- Select --", "Single", "Multiple"],
            index=0 if not st.session_state.get("dept_type") else (
                ["-- Select --", "Single", "Multiple"].index(st.session_state["dept_type"])
                if st.session_state["dept_type"] in ["Single", "Multiple"] else 0
            ),
            key="dept_type"
        )

        # Load config (already loaded lazily earlier; using cached ref)
        config_cols = st.session_state.get("config_columns") or {}
        config_err = st.session_state.get("config_error")

        # ---------- SINGLE department flow ----------
        if st.session_state.get("dept_type") == "Single":
            if config_err:
                st.error(f"Could not load Config sheet: {config_err}")
            else:
                # Location selection (independent of user) - populate from Users sheet unique values
                st.markdown("### Location")
                user_sheet_res = fetch_sheet_data(APPSCRIPT_URL, APPSCRIPT_TOKEN, sheet="User")
                loc_options = []
                if user_sheet_res["ok"] and isinstance(user_sheet_res["data"], list):
                    user_rows_all = user_sheet_res["data"]
                    if user_rows_all:
                        all_keys = list(user_rows_all[0].keys())
                        loc_header = pick_key(all_keys, ["location", "site", "campus", "location name"]) or None
                        if loc_header:
                            seen = set()
                            for ur in user_rows_all:
                                val = str(ur.get(loc_header, "")).strip()
                                if val:
                                    seen.add(val)
                            loc_options = sorted(list(seen))
                if not loc_options:
                    loc_options = ["Main Campus", "Other"]
                if "Other" not in loc_options:
                    loc_options.append("Other")

                selected_location = st.selectbox("Choose location", options=loc_options, key="selected_location")
                manual_location = ""
                if selected_location == "Other":
                    manual_location = st.text_input("Enter location", key="manual_location")

                # Number of requests (Single flow allows multiple request rows)
                num = st.number_input("Number of requests (max 10)", min_value=1, max_value=10, value=1, step=1, key="num_requests")
                st.write("---")
                st.markdown("### Request details")

                # Service department options from Config
                service_dept_options = config_cols.get("Maintenance Service Type")
                if not service_dept_options:
                    for k in config_cols.keys():
                        if "maintenance" in str(k).lower() and "service" in str(k).lower():
                            service_dept_options = config_cols.get(k)
                            break
                if not service_dept_options:
                    service_dept_options = list(config_cols.keys()) or ["General"]

                requests_list = []
                for i in range(int(num)):
                    st.markdown(f"**Request {i+1}**")
                    svc = st.selectbox(f"Service Dept (request {i+1})", options=["-- Select --"] + service_dept_options, key=f"svc_{i}")
                    sub_opts = []
                    if svc and svc != "-- Select --":
                        for h, vals in config_cols.items():
                            if str(h).strip().lower() == svc.strip().lower():
                                sub_opts = vals
                                break
                    sub = st.selectbox(f"Sub Category (request {i+1})", options=["-- Select --"] + (sub_opts or []), key=f"sub_{i}")
                    desc = st.text_area(f"Description (request {i+1})", key=f"desc_{i}", height=80)

                    if current_req == "Maintenance":
                        occ_opts = config_cols.get("Issue Occurrence", [])
                        occ = st.selectbox(f"Issue Occurrence (request {i+1})", options=["-- Select --"] + (occ_opts or []), key=f"occ_{i}")
                        extra = {"occurrence": occ}
                    else:
                        reason = st.text_input(f"Reason (request {i+1})", key=f"reason_{i}")
                        chall = st.text_input(f"Existing Challenges (request {i+1})", key=f"chall_{i}")
                        extra = {"reason": reason, "existing_challenges": chall}

                    photo = st.file_uploader(f"Upload photo (request {i+1}) — placeholder", type=["png", "jpg", "jpeg"], key=f"photo_{i}")

                    requests_list.append({
                        "service_dept": svc,
                        "sub_category": sub,
                        "description": desc,
                        **extra,
                        "photo_provided": bool(photo)
                    })
                    st.write("---")

                # Location Availability for single flow
                st.markdown("### Location Availability")
                loc_avail = st.selectbox("Availability of location/space for the work", options=["Any Day", "Restricted"], key="loc_avail_single")
                loc_avail_details = ""
                if loc_avail == "Restricted":
                    loc_avail_details = st.text_area("Please provide additional information about restrictions (days/times/constraints)", key="loc_avail_details_single", height=80)

                # Priority & expected finish
                st.markdown("### Priority & Expected Completion")
                priority = st.selectbox("Priority", options=["Normal", "Urgent"], index=0, key="priority_select")
                urgent_reason = ""
                if priority == "Urgent":
                    urgent_reason = st.text_area("Please state the reason for urgency", key="urgent_reason", height=80)
                    if not urgent_reason:
                        st.warning("You selected Urgent — please provide the reason above.")

                today = datetime.date.today()
                if priority == "Urgent":
                    default_expected = today + datetime.timedelta(days=3)
                    min_expected = default_expected
                else:
                    default_expected = today + datetime.timedelta(days=10)
                    min_expected = default_expected

                expected_date = st.date_input(
                    "Expected date to finish",
                    value=default_expected,
                    min_value=min_expected,
                    key="expected_finish_date"
                )

                # Budget fields
                st.markdown("### Budget")
                budget_available = st.selectbox("Is Budget Code Available?", options=["No", "Yes"], index=0, key="budget_available")
                budget_info = {}
                if budget_available == "Yes":
                    book_of_accounts = st.text_input("Book of Accounts", key="book_of_accounts")
                    budget_code = st.text_input("Budget Code", key="budget_code")
                    utilization_date = st.date_input("Utilization Date", key="utilization_date")
                    entity_name = st.text_input("Entity Name", key="entity_name")
                    budget_info = {
                        "book_of_accounts": book_of_accounts,
                        "budget_code": budget_code,
                        "utilization_date": str(utilization_date),
                        "entity_name": entity_name
                    }

                # Submit (placeholder)
                if st.button("Create tickets (placeholder - no preview)"):
                    payload = {
                        "requester_email": st.session_state.get("requester_email"),
                        "name": name_val,
                        "department": dept_val,
                        "department_lead_email": lead_val,
                        "request_type": current_req,
                        "department_type": st.session_state.get("dept_type"),
                        "location": (manual_location if selected_location == "Other" else selected_location),
                        "requests": requests_list,
                        "location_availability": {"type": loc_avail, "details": loc_avail_details},
                        "priority": priority,
                        "urgent_reason": urgent_reason if priority == "Urgent" else "",
                        "expected_finish_date": str(expected_date),
                        "budget_available": (budget_available == "Yes"),
                        "budget_info": budget_info
                    }
                    st.success("Requests submitted (placeholder). Next step: integrate with JIRA / backend to create tickets.")

        # ---------- MULTIPLE departments flow ----------
        elif st.session_state.get("dept_type") == "Multiple":
            st.markdown("### Select departments involved (Multiple)")

            user_sheet_res = fetch_sheet_data(APPSCRIPT_URL, APPSCRIPT_TOKEN, sheet="User")
            multi_dept_options = []
            if user_sheet_res["ok"] and isinstance(user_sheet_res["data"], list) and user_sheet_res["data"]:
                all_keys = list(user_sheet_res["data"][0].keys())
                ns_header = pick_key(all_keys, ["new service type", "new_service_type", "new service", "service type"]) or None
                if ns_header:
                    seen = []
                    for ur in user_sheet_res["data"]:
                        v = str(ur.get(ns_header, "")).strip()
                        if v and v not in seen:
                            seen.append(v)
                    multi_dept_options = seen

            if not multi_dept_options:
                fallback = config_cols.get("Maintenance Service Type") or list(config_cols.keys()) or ["Fabrication", "Carpentry", "Plumbing"]
                multi_dept_options = fallback

            selected_depts = []
            for i, dname in enumerate(multi_dept_options):
                chk = st.checkbox(dname, key=f"multi_dept_chk_{i}")
                if chk:
                    selected_depts.append(dname)

            if not selected_depts:
                st.info("Please select at least one department involved to proceed.")

            st.markdown("### Request (one request per ticket)")
            multi_description = st.text_area("Description (single request covering all selected departments)", key="multi_desc", height=140)

            occ_opts = config_cols.get("Issue Occurrence", [])
            multi_occurrence = st.selectbox("Issue Occurrence", options=["-- Select --"] + (occ_opts or []), key="multi_occurrence")

            st.markdown("Upload photos (optional) — attach photos related to this single request")
            multi_photos = st.file_uploader("Upload photos (multiple allowed)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="multi_photos")

            st.markdown("### Location Availability")
            loc_avail_multi = st.selectbox("Availability of location/space for the work", options=["Any Day", "Restricted"], key="loc_avail_multi")
            loc_avail_details_multi = ""
            if loc_avail_multi == "Restricted":
                loc_avail_details_multi = st.text_area("Please provide additional information about restrictions (days/times/constraints)", key="loc_avail_details_multi", height=80)

            st.markdown("### Priority & Expected Completion")
            priority_multi = st.selectbox("Priority", options=["Normal", "Urgent"], index=0, key="priority_multi_select")
            urgent_reason_multi = ""
            if priority_multi == "Urgent":
                urgent_reason_multi = st.text_area("Please state the reason for urgency", key="urgent_reason_multi", height=80)
                if not urgent_reason_multi:
                    st.warning("You selected Urgent — please provide the reason above.")

            today = datetime.date.today()
            if priority_multi == "Urgent":
                default_expected_multi = today + datetime.timedelta(days=3)
                min_expected_multi = default_expected_multi
            else:
                default_expected_multi = today + datetime.timedelta(days=10)
                min_expected_multi = default_expected_multi

            expected_date_multi = st.date_input(
                "Expected date to finish",
                value=default_expected_multi,
                min_value=min_expected_multi,
                key="expected_finish_date_multi"
            )

            st.markdown("### Budget")
            budget_available_multi = st.selectbox("Is Budget Code Available?", options=["No", "Yes"], index=0, key="budget_available_multi")
            budget_info_multi = {}
            if budget_available_multi == "Yes":
                book_of_accounts = st.text_input("Book of Accounts", key="book_of_accounts_multi")
                budget_code = st.text_input("Budget Code", key="budget_code_multi")
                utilization_date = st.date_input("Utilization Date", key="utilization_date_multi")
                entity_name = st.text_input("Entity Name", key="entity_name_multi")
                budget_info_multi = {
                    "book_of_accounts": book_of_accounts,
                    "budget_code": budget_code,
                    "utilization_date": str(utilization_date),
                    "entity_name": entity_name
                }

            can_submit = bool(selected_depts) and bool(str(multi_description).strip())
            if not selected_depts:
                st.warning("Select one or more departments before submitting.")
            if not str(multi_description).strip():
                st.warning("Please provide a description for the request.")

            if st.button("Create ticket (placeholder - multiple)"):
                if not can_submit:
                    st.error("Cannot submit. Make sure you've selected department(s) and provided a description.")
                else:
                    payload = {
                        "requester_email": st.session_state.get("requester_email"),
                        "name": name_val,
                        "department": dept_val,
                        "department_lead_email": lead_val,
                        "request_type": current_req,
                        "department_type": st.session_state.get("dept_type"),
                        "selected_departments": selected_depts,
                        "description": multi_description,
                        "issue_occurrence": multi_occurrence,
                        "location_availability": {"type": loc_avail_multi, "details": loc_avail_details_multi},
                        "priority": priority_multi,
                        "urgent_reason": urgent_reason_multi if priority_multi == "Urgent" else "",
                        "expected_finish_date": str(expected_date_multi),
                        "budget_available": (budget_available_multi == "Yes"),
                        "budget_info": budget_info_multi,
                        "photos_provided": bool(multi_photos),
                    }
                    st.success("Ticket submitted (placeholder). Next step: integrate with JIRA / backend to create a real ticket.")

    # end of Maintenance/New branch

    # For Project or other flows we keep a minimal master ticket option
    elif current_req == "-- Select --" or current_req is None:
        st.info("Please select a request type to continue.")
    else:
        # minimal preview for non-maintenance NEW flows (Project handled above)
        computed_dept_type = "Multiple" if current_req == "Project" else st.session_state.get("dept_type")
        preview = {
            "requester_email": st.session_state.get("requester_email"),
            "name": name_val,
            "department": dept_val,
            "department_lead_email": lead_val,
            "request_type": current_req,
            "department_type": computed_dept_type,
        }
        # keep submit placeholder for master ticket
        if st.button("Create master ticket and children (placeholder)"):
            st.success("Master ticket creation placeholder (no request preview).")

# ---------- If not verified ----------
else:
    st.info("Please verify your email first so we can autofill your details from the IESM Users sheet.")
    if not APPSCRIPT_URL:
        st.warning("Apps Script URL not configured. Please set it in st.secrets or environment variables.")
