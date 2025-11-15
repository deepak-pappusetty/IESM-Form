# iesm_form.py
import streamlit as st
import json

# --- Page config ---
st.set_page_config(page_title="IESM - Service Request", layout="centered")

# --- Initialize session state keys ---
if "request_type" not in st.session_state:
    st.session_state.request_type = None
if "dept_type" not in st.session_state:
    st.session_state.dept_type = None

# --- Header ---
st.title("IESM - Isha Engineering Service Management")
st.write("Step 1: Choose request type. Step 2 will appear based on your answer.")

# --- Question 1: Type of request ---
request_choice = st.selectbox(
    "1) Type of request",
    options=["-- Select --", "Maintenance", "New", "Project"],
    index=0,
    key="q1_type"
)

# Store selection in session_state (ignore the placeholder)
if request_choice and request_choice != "-- Select --":
    st.session_state.request_type = request_choice
else:
    st.session_state.request_type = None
    st.session_state.dept_type = None  # reset

# --- Conditional Question 2 ---
if st.session_state.request_type in ("Maintenance", "New"):
    dept_choice = st.selectbox(
        "2) Departments involved",
        options=["-- Select --", "Single", "Multiple"],
        index=0,
        key="q2_dept"
    )
    if dept_choice and dept_choice != "-- Select --":
        st.session_state.dept_type = dept_choice
    else:
        st.session_state.dept_type = None

elif st.session_state.request_type == "Project":
    # For Project, department type is automatically Multiple
    st.markdown("**2) Departments involved**: Multiple (auto-selected for Project)")
    st.session_state.dept_type = "Multiple"

# --- Small preview (optional) ---
st.write("---")
st.markdown("#### Current selection (preview)")
preview = {
    "request_type": st.session_state.request_type,
    "department_type": st.session_state.dept_type
}
st.code(json.dumps(preview, indent=2))
