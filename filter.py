import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
import re
from collections import Counter

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "ncube-keywords-db"
TAB_NAME = "keywords"
REMOVE_TAB = "remove"

# --- Loaders ---
def load_keywords():
    sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
    return list(set([kw.strip().lower() for kw in sheet.col_values(1) if kw.strip()]))

def load_exclusion_keywords():
    try:
        sheet = client.open(SHEET_NAME).worksheet(REMOVE_TAB)
        return list(set([kw.strip().lower() for kw in sheet.col_values(1) if kw.strip()]))
    except Exception as e:
        st.warning("Couldn't load exclusion keywords. Continuing without them.")
        return []

def save_keywords_to_sheet(new_keywords):
    sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
    current = load_keywords()
    all_keywords = sorted(set(current + new_keywords))
    sheet.clear()
    sheet.update([["Keyword"]] + [[kw] for kw in all_keywords])

# --- Keyword Filter Logic ---
def is_relevant_entry(headline, position, keywords, exclusion_keywords):
    def contains_exact_exclusion(text):
        text = f" {text.lower()} "
        for ex_kw in exclusion_keywords:
            ex_kw_spaced = f" {ex_kw} "
            if ex_kw_spaced in text or text.strip() == ex_kw:
                return True
        return False

    def contains_inclusion(text):
        text = text.lower()
        return any(kw in text for kw in keywords)

    # Check headline and position against exclusions (strict match)
    if contains_exact_exclusion(str(headline)) or contains_exact_exclusion(str(position)):
        return False

    # Check for any inclusion in either
    return contains_inclusion(str(headline)) or contains_inclusion(str(position))

# --- Keyword Suggestion ---
def extract_potential_keywords(text_series, existing_keywords):
    stopwords = {
        "and", "the", "for", "with", "from", "this", "that", "you", "are", "have", "has", "not",
        "all", "any", "can", "but", "out", "via", "its", "his", "her", "our", "your", "they", "them",
        "on", "at", "in", "to", "by", "of", "is", "as", "an", "or", "be", "a", "we", "i", "it"
    }

    all_tokens = []
    for text in text_series.dropna():
        tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        all_tokens.extend(tokens)

    counts = Counter(all_tokens)
    suggestions = {
        word: count for word, count in counts.items()
        if word not in existing_keywords and word not in stopwords and count > 1
    }

    return dict(sorted(suggestions.items(), key=lambda x: x[1], reverse=True)[:25])

# --- Streamlit App ---
st.title("nCube Lead Filter with Google Sheets Integration")
st.write("Upload a CSV, filter tech leads based on smart keyword logic, and manage keywords via Google Sheets.")

# Load keywords from both tabs
try:
    keywords = load_keywords()
    exclusion_keywords = load_exclusion_keywords()
    st.success("✅ Connected to Google Sheets.")
except Exception as e:
    st.error(f"❌ Could not load keywords: {e}")
    st.stop()

# File uploader
uploaded_file = st.file_uploader("📁 Upload your CSV file", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    if 'headline' not in df.columns or 'current_company_position' not in df.columns:
        st.error("CSV must include 'headline' and 'current_company_position' columns.")
    else:
        mask = df.apply(lambda row: is_relevant_entry(row['headline'], row['current_company_position'], keywords, exclusion_keywords), axis=1)
        filtered_df = df[mask]
        excluded_df = df[~mask]

        st.subheader("✅ Filtered Leads")
        st.write(f"{len(filtered_df)} out of {len(df)} leads passed the keyword filters.")
        st.dataframe(filtered_df)

        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Filtered Leads", csv, "filtered_ncube_leads.csv", "text/csv")

        st.subheader("🧠 Smart Keyword Suggestions (from excluded leads)")
        suggestions = extract_potential_keywords(excluded_df['headline'], keywords)
        selected = st.multiselect("Select keywords to add to your list:", list(suggestions.keys()))

        if st.button("➕ Add Selected Keywords"):
            save_keywords_to_sheet(selected)
            st.success(f"✅ Added {len(selected)} new keywords to Google Sheets!")
            st.rerun()

# Show current keyword lists
with st.expander("📂 View Keywords in Google Sheets"):
    st.write("**Inclusion Keywords (Tab: `keywords`)**")
    st.write(sorted(set(keywords)))
    st.write("**Exclusion Keywords (Tab: `remove`)**")
    st.write(sorted(set(exclusion_keywords)))
