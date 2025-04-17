import streamlit as st
import pandas as pd
import gspread  # FIXED: changed from `spread` to `gspread`
import json
from oauth2client.service_account import ServiceAccountCredentials
import re
from collections import Counter

# --- Google Sheets Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_NAME = "ncube-keywords-db"  # ✅ REPLACE with your actual sheet name
TAB_NAME = "keywords"

def load_keywords():
    sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
    return list(set([kw.strip().lower() for kw in sheet.col_values(1) if kw.strip()]))

def save_keywords_to_sheet(new_keywords):
    sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
    current = load_keywords()
    all_keywords = sorted(set(current + new_keywords))
    sheet.clear()
    sheet.update([["Keyword"]] + [[kw] for kw in all_keywords])

# --- Filter Helpers ---
def is_relevant_headline(headline, keywords):
    if pd.isna(headline):
        return False
    headline_lower = headline.lower()
    return any(keyword in headline_lower for keyword in keywords)

def extract_potential_keywords(text_series, existing_keywords):
    # Common stopwords to ignore
    stopwords = {
        "and", "the", "for", "with", "from", "this", "that", "you", "are", "have", "has", "not",
        "all", "any", "can", "but", "out", "via", "its", "his", "her", "our", "your", "they", "them",
        "on", "at", "in", "to", "by", "of", "is", "as", "an", "or", "be", "a", "we", "i", "it"
    }

    all_tokens = []
    for text in text_series.dropna():
        tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())  # Only words with 3+ letters
        all_tokens.extend(tokens)

    counts = Counter(all_tokens)

    suggestions = {
        word: count
        for word, count in counts.items()
        if word not in existing_keywords
        and word not in stopwords
        and count > 1
    }

    return dict(sorted(suggestions.items(), key=lambda x: x[1], reverse=True)[:25])

# --- Streamlit UI ---
st.title("nCube Lead Filter with Google Sheets Integration")
st.write("Upload a CSV, filter relevant tech leads, and maintain a cloud-based keyword list in Google Sheets.")

# Test connection
try:
    keywords = load_keywords()
    st.success("✅ Connected to Google Sheets.")
except Exception as e:
    st.error(f"❌ Could not load keywords from Google Sheets: {e}")
    st.stop()

# File upload
uploaded_file = st.file_uploader("📁 Upload your CSV file", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    if 'headline' not in df.columns:
        st.error("This file doesn't contain a 'headline' column.")
    else:
        filtered_df = df[df['headline'].apply(lambda h: is_relevant_headline(h, keywords))]
        excluded_df = df[~df['headline'].apply(lambda h: is_relevant_headline(h, keywords))]

        st.subheader("✅ Filtered Leads")
        st.write(f"Found {len(filtered_df)} out of {len(df)} leads that match your current keyword list.")
        st.dataframe(filtered_df)

        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Filtered Leads", csv, "filtered_ncube_leads.csv", "text/csv")

        st.subheader("🧠 Smart Keyword Suggestions")
        suggestions = extract_potential_keywords(excluded_df['headline'], keywords)
        selected = st.multiselect("Select keywords to add:", list(suggestions.keys()))

        if st.button("➕ Add Selected Keywords"):
            save_keywords_to_sheet(selected)
            st.success(f"Added {len(selected)} new keywords to Google Sheets!")
            st.rerun()

# Show current keywords
with st.expander("📂 View/Edit Keywords from Google Sheets"):
    st.write(sorted(set(keywords)))
