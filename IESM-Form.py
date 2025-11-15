import streamlit as st
import json

# --- Page config ---
st.set_page_config(page_title="IASM Master/Child Request Form", layout="centered")

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = 1
if "request_type" not in st.session_state:
    st.session_state.request_type = None
if "dept_type" not in st.session_state:
    st.session_state.dept_type = None
if "children" not in st.session_state:
    st.session_state.children = []
if "master" not in st.session_state:
    st.session_state.master = {}

st.title("IASM — Create Master Ticket and Child Requests")
st.caption("Step-by-step form: choose request type first, then define details and child requests.")

# -----------------
# Step 1: Choose request type
# -----------------
if st.session_state.step == 1:
    with st.form("step1_form"):
        st.markdown("### 1) What kind of request are you raising?")
        request_type = st.radio(
            "Select request type",
            options=["Maintenance", "New", "Project"],
            index=0
        )
        next_clicked = st.form_submit_button("Next →")

    if next_clicked:
        st.session_state.request_type = request_type
        # If project, auto choose Multiple
        if request_type == "Project":
            st.session_state.dept_type = "Multiple"
        else:
            st.session_state.dept_type = None  # will be chosen in step 2
        st.session_state.step = 2
        st.experimental_rerun()

# -----------------
# Step 2: Details and children
# -----------------
elif st.session_state.step == 2:
    st.markdown("### 2) Request details")

    st.info(f"Selected request type: **{st.session_state.request_type}**")

    # Show dept type choice or auto-set for Project
    if st.session_state.request_type in ("Maintenance", "New"):
        dept_choice = st.selectbox(
            "Is this Single-department work or Multi-department work?",
            options=["Single", "Multiple"],
            index=0
        )
        st.session_state.dept_type = dept_choice
    else:  # Project
        # show a disabled input to indicate Multiple is forced
        st.text_input("Department type (auto)", value="Multiple", disabled=True)
        st.session_state.dept_type = "Multiple"

    # Master ticket fields
    st.markdown("#### Master ticket")
    master_title = st.text_input("Master ticket title", key="master_title_input")
    master_description = st.text_area("Master ticket description", key="master_desc_input")

    # Child requests area: simple add-one-at-a-time implementation
    st.markdown("#### Child requests (these will become child tickets)")
    child_short = st.text_input("Child request short title", key="child_title_input")
    child_detail = st.text_area("Child request details", key="child_detail_input", height=120)

    col1, col2, col3 = st.columns([1,1,2])
    with col1:
        add_child = st.button("Add child")
    with col2:
        clear_children = st.button("Clear all children")
    with col3:
        go_back = st.button("← Back to Step 1")

    if add_child:
        # basic validation
        if not child_short:
            st.warning("Please give the child request a short title before adding.")
        else:
            st.session_state.children.append({
                "title": child_short,
                "details": child_detail or "",
                "department_type": st.session_state.dept_type
            })
            # clear input fields (by overwriting keys)
            st.session_state.child_title_input = ""
            st.session_state.child_detail_input = ""
            st.experimental_rerun()

    if clear_children:
        st.session_state.children = []
        st.experimental_rerun()

    if go_back:
        st.session_state.step = 1
        st.experimental_rerun()

    # show current list of children
    if st.session_state.children:
        st.markdown("**Children added so far:**")
        for i, c in enumerate(st.session_state.children, start=1):
            st.write(f"**{i}. {c['title']}** — {c['details'][:200]}")  # short preview

    st.write("---")
    # Submit master + children
    submit = st.button("Create master ticket and child requests (preview payload)")

    if submit:
        # validation
        errors = []
        if not master_title:
            errors.append("Master ticket title is required.")
        if len(st.session_state.children) == 0:
            errors.append("At least one child request should be added.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            # build payload (you will later send this to JIRA integration)
            payload = {
                "master_ticket": {
                    "title": master_title,
                    "description": master_description,
                    "request_type": st.session_state.request_type,
                    "department_type": st.session_state.dept_type,
                },
                "child_requests": st.session_state.children
            }

            # store in session_state (optional)
            st.session_state.master = payload

            st.success("Payload ready — preview below. (Next: wire this payload to your Jira integration.)")
            st.json(payload, expanded=False)

            # Example: show flattened view for developer
            st.markdown("**Developer view (JSON string you can POST to your backend)**")
            st.code(json.dumps(payload, indent=2))

            # Optionally reset everything or keep it
            if st.button("Reset form and start again"):
                for k in ["step", "request_type", "dept_type", "children", "master"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.experimental_rerun()
