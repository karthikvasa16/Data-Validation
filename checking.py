
import streamlit as st
import pandas as pd
import re
from io import BytesIO
import numpy as np

st.set_page_config(page_title="University Data Validator", layout="wide")
st.title("📊 University Data Validator & Auto-Fix Tool")

# ==============================================
# CONSTANTS & CONFIG
# ==============================================

VALID_REGIONS = [
    "england",
    "scotland",
    "wales",
    "northern ireland",
]

MONTH_MAP = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "may": "may", "jun": "june", "jul": "july", "aug": "august",
    "sep": "september", "sept": "september", "oct": "october", "nov": "november", "dec": "december"
}

QUAL_PATTERN = r"^(msc|ma|mba|mphil|mres|meng|med|llm|pgcert|pgdip|pgce|ba|ba\(hons\)|bsc|bsc\(hons\)|beng|bed|foundation|certificate|diploma|llb)\b"

# ==============================================
# HELPER FUNCTIONS
# ==============================================

def trim_dataframe(df):
    """Trims whitespace from all string columns."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df

def normalize(text: str) -> str:
    """Normalizes string for column matching (lowercase, no special chars)."""
    return re.sub(r"[\W_]+", "", str(text).strip().lower())

def find_column(df, candidates):
    """Finds a column in df that matches one of the candidates."""
    for col in df.columns:
        if normalize(col) in candidates or any(c in normalize(col) for c in candidates):
            return col
    return None

def is_valid_intake(v):
    if pd.isna(v): return True
    v_str = str(v).lower().strip()
    return v_str in MONTH_MAP.values() or v_str in MONTH_MAP.keys()

def is_valid_region(v):
    if pd.isna(v): return True
    return str(v).lower().strip() in VALID_REGIONS

def get_outliers(series):
    """Returns indices of outliers using Z-score > 3 method."""
    try:
        data = pd.to_numeric(series, errors='coerce').dropna()
        if len(data) < 5: return []
        mean = np.mean(data)
        std = np.std(data)
        if std == 0: return []
        z_scores = (data - mean) / std
        return z_scores[abs(z_scores) > 3].index.tolist()
    except:
        return []

# ==============================================
# SIDEBAR - INPUTS
# ==============================================

st.sidebar.header("1. Upload & Settings")
uploaded_file = st.sidebar.file_uploader("Upload Excel File", type=["xlsx", "xlsm", "xls"])

st.sidebar.markdown("---")
st.sidebar.header("2. University Details")
user_uni_name = st.sidebar.text_input("University Name", placeholder="e.g. Northumbria University")
user_uni_link = st.sidebar.text_input("University Link", placeholder="e.g. https://...")

st.sidebar.markdown("---")
st.sidebar.header("3. Allowed Levels")
all_levels = [
    "UG Top-Up", "UG with Foundation", "UG Year One", "Foundation", 
    "Undergraduate", "Postgraduate", "Pre-Masters", "DBA", "PhD", "Masters in Research"
]
selected_levels = st.sidebar.multiselect(
    "Select valid levels for this file", 
    options=all_levels,
    default=all_levels # Default select all, user can uncheck
)
valid_levels_set = set(selected_levels)

# ==============================================
# DATA LOADING
# ==============================================

if not uploaded_file:
    st.info("👈 Please upload an Excel file to start.")
    st.stop()

@st.cache_data
def load_data(file):
    raw_sheets = pd.read_excel(file, sheet_name=None)
    return {sh: trim_dataframe(df) for sh, df in raw_sheets.items()}

sheets = load_data(uploaded_file)
st.success(f"Loaded {len(sheets)} sheets: {', '.join(sheets.keys())}")

# ==============================================
# MAIN TABS
# ==============================================

tab1, tab2, tab3 = st.tabs(["🔍 Validation Report", "📊 Data Summary", "🛠️ Auto-Fix & Editor"])

# -------------------------------------------------------------------------
# TAB 1: VALIDATION REPORT
# -------------------------------------------------------------------------
with tab1:
    st.header("Detailed Validation Report")
    
    for sh, df in sheets.items():
        with st.expander(f"Sheet: {sh}", expanded=True):
            errors_found = False
            
            # --- Check Sheet Name vs Intake Column ---
            # Try to infer month from sheet name
            sheet_month_target = None
            sh_lower = sh.lower()
            for short_m, full_m in MONTH_MAP.items():
                if short_m in sh_lower or full_m in sh_lower:
                    sheet_month_target = (short_m, full_m)
                    break
            
            # --- Column Loop ---
            for col in df.columns:
                errors = []
                col_n = normalize(col)
                
                # 1. SL NO
                if col_n in ["slno", "serialnumber", "sno"]:
                    try:
                        col_vals = df[col].astype("Int64")
                        expected = list(range(1, len(col_vals) + 1))
                        actual = list(col_vals)
                        for i, (a, e) in enumerate(zip(actual, expected)):
                            if a != e: errors.append((i+2, a, f"Expected {e}"))
                    except:
                        errors.append(("-", "-", "Column contains non-numeric values"))

                # 2. COUNTRY
                if col_n == "country":
                    for i, v in enumerate(df[col]):
                        if str(v).lower().strip() != "united kingdom":
                            errors.append((i+2, v, "Must be 'United Kingdom'"))

                # 3. REGION
                if col_n == "region":
                    for i, v in enumerate(df[col]):
                        if not is_valid_region(v):
                            errors.append((i+2, v, f"Invalid Region. Must be one of: {', '.join(VALID_REGIONS)}"))

                # 4. MODE OF EDUCATION
                if col_n in ["modeofeducation", "mode"]:
                    for i, v in enumerate(df[col]):
                        if str(v).lower().strip() != "on campus":
                            errors.append((i+2, v, "Must be 'On campus'"))

                # 5. CREDIBILITY INTERVIEW
                if col_n in ["credibiltyinterview", "credibilityinterview"]:
                    for i, v in enumerate(df[col]):
                        if str(v).lower().strip() != "yes":
                            errors.append((i+2, v, "Must be 'Yes'"))

                # 6. APPLICATION FEE
                if col_n == "applicationfee":
                    for i, v in enumerate(df[col]):
                        if str(v).strip() != "0":
                            errors.append((i+2, v, "Must be '0'"))

                # 7. INTAKE
                if col_n == "intake":
                    for i, v in enumerate(df[col]):
                        v_str = str(v).lower().strip()
                        # Base validity
                        if not is_valid_intake(v):
                            errors.append((i+2, v, "Invalid Month Name"))
                        # Sheet Name Match
                        elif sheet_month_target:
                            # if valid month, check conformity
                            if v_str not in sheet_month_target:
                                errors.append((i+2, v, f"Mismatch with Sheet Name '{sh}'"))
                
                # 8. LEVEL (User Defined)
                if col_n == "level":
                    for i, v in enumerate(df[col]):
                        if str(v).strip() not in valid_levels_set:
                            errors.append((i+2, v, "Not in 'Allowed Levels'"))

                # 9. COURSE (Strict Format)
                if col_n == "course":
                    for i, v in enumerate(df[col]):
                        val_str = str(v).lower().strip()
                        starts = re.match(QUAL_PATTERN, val_str)
                        ends = re.search(QUAL_PATTERN + r"$", val_str)
                        if not starts and not ends:
                            errors.append((i+2, v, "Qualification invalid/misplaced"))

                # 10. DURATION (Outliers)
                if col_n == "duration":
                    outlier_indices = get_outliers(df[col])
                    for idx in outlier_indices:
                        val = df[col].iloc[idx]
                        errors.append((idx+2, val, "Possible Outlier (Statistical)"))

                # 11. UNIVERSITY NAME (User Defined)
                if "university" in col_n and "link" not in col_n:
                    if user_uni_name:
                        for i, v in enumerate(df[col]):
                            if str(v).strip() != user_uni_name.strip():
                                errors.append((i+2, v, f"Expected '{user_uni_name}'"))

                # 12. UNIVERSITY LINK (User Defined)
                if ("universitylink" in col_n) or ("link" in col_n and "course" not in col_n):
                    if user_uni_link:
                        for i, v in enumerate(df[col]):
                            if str(v).strip() != user_uni_link.strip():
                                errors.append((i+2, v, f"Expected '{user_uni_link}'"))

                # OUTPUT ERRORS
                if errors:
                    errors_found = True
                    st.error(f"❌ Column `{col}` ({len(errors)} issues)")
                    # Show ALL errors
                    err_df = pd.DataFrame(errors, columns=["Row", "Value", "Issue"])
                    st.dataframe(err_df, use_container_width=True, hide_index=True)
                    # if len(errors) > 10:
                    #     st.caption(f"...and {len(errors)-10} more.")

            if not errors_found:
                st.success("✅ No validation errors found in this sheet.")

# -------------------------------------------------------------------------
# TAB 2: DATA SUMMARY
# -------------------------------------------------------------------------
with tab2:
    st.header("📊 Data Summary Inspection")
    
    sel_sheet = st.selectbox("Select Sheet for Summary", list(sheets.keys()))
    df_sum = sheets[sel_sheet]
    
    st.markdown(f"**Showing unique values for all {len(df_sum.columns)} columns:**")
    
    cols = st.columns(2)
    for idx, col in enumerate(df_sum.columns):
        with cols[idx % 2]:
            try:
                # Convert to string to ensure unique() works and for display
                unique_vals = df_sum[col].dropna().astype(str).unique()
                st.selectbox(
                    f"Unique values in `{col}` ({len(unique_vals)})", 
                    options=unique_vals,
                    key=f"sum_{sel_sheet}_{col}"
                )
            except Exception as e:
                st.warning(f"Could not process `{col}`: {e}")

# -------------------------------------------------------------------------
# TAB 3: AUTO-FIX & EDITOR
# -------------------------------------------------------------------------
with tab3:
    st.header("🛠️ Auto-Fix & Live Editor")
    
    # Session state for fixed data
    if "fixed_data" not in st.session_state:
        st.session_state["fixed_data"] = {k: v.copy() for k, v in sheets.items()}

    # --- ACTION BUTTON ---
    if st.button("🚀 Run Auto-Fix (Apply Rules + User Inputs)", type="primary"):
        fixed_dict = {}
        for sh, df_orig in sheets.items():
            df_fix = df_orig.copy()
            
            # 1. Serial No
            sno_col = find_column(df_fix, ["slno", "serialnumber", "sno"])
            if sno_col: df_fix[sno_col] = range(1, len(df_fix) + 1)
            
            # 2. Country
            country_col = find_column(df_fix, ["country"])
            if country_col: df_fix[country_col] = "United Kingdom"
            
            # 3. Mode
            mode_col = find_column(df_fix, ["mode", "modeofeducation"])
            if mode_col: df_fix[mode_col] = "On Campus"
            
            # 4. Credibility
            cred_col = find_column(df_fix, ["credibiltyinterview", "credibilityinterview"])
            if cred_col: df_fix[cred_col] = "Yes"
            
            # 5. App Fee
            fee_col = find_column(df_fix, ["applicationfee"])
            if fee_col: df_fix[fee_col] = 0  # Int/String handling? better to set as 0
            
            # 6. Apply User Inputs (University & Link)
            # Find column containing "university" but NOT "link"
            uni_col = None
            for col in df_fix.columns:
                if "university" in normalize(col) and "link" not in normalize(col):
                    uni_col = col
                    break
            
            if uni_col and user_uni_name:
                df_fix[uni_col] = user_uni_name
                
            link_col = None
            for col in df_fix.columns:
                c_norm = normalize(col)
                if ("universitylink" in c_norm) or ("link" in c_norm and "course" not in c_norm):
                    link_col = col
                    break
            
            if link_col and user_uni_link:
                df_fix[link_col] = user_uni_link

            fixed_dict[sh] = df_fix
            
        st.session_state["fixed_data"] = fixed_dict
        st.success("Auto-Fix Applied! You can now verify or edit below.")

    # --- LIVE EDITOR ---
    st.markdown("### ✏️ Live Editor")
    edit_sheet = st.selectbox("Select Sheet to Edit", list(st.session_state["fixed_data"].keys()), key="editor_select")
    
    # Data Editor
    edited_df = st.data_editor(
        st.session_state["fixed_data"][edit_sheet],
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor_widget"
    )
    
    # Update session state with manual edits
    st.session_state["fixed_data"][edit_sheet] = edited_df

    # --- DOWNLOAD ---
    st.markdown("### 📥 Download Result")
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for name, data in st.session_state["fixed_data"].items():
            data.to_excel(writer, sheet_name=name, index=False)
    buffer.seek(0)
    
    st.download_button(
        label="Download Cleaned Excel File",
        data=buffer,
        file_name="cleaned_university_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
