import streamlit as st
import subprocess
import os
import json
import time

st.set_page_config(page_title="PhoenixForge 🔥", layout="wide", initial_sidebar_state="expanded")

st.title("🐦🔥 PhoenixForge - Project Risk Analyzer")
st.caption("Scrapes the web for failures and generates a risk heatmap.")

# Sidebar for history
with st.sidebar:
    st.header("📂 Memory Bank")
    if os.path.exists("memory.jsonl"):
        try:
            with open("memory.jsonl", "r") as f:
                lines = f.readlines()
            if lines:
                last = json.loads(lines[-1])
                st.write(f"**Last Scanned:** {last.get('idea', 'Unknown')}")
                st.write(f"**Date:** {last.get('date', 'Unknown')}")
        except:
            st.write("No memory yet.")
    else:
        st.write("No previous projects scanned.")

# Main input
idea = st.text_input("Enter your project idea:", "Build a social media scheduler", placeholder="e.g., AI-powered resume builder")

col1, col2 = st.columns([1, 5])
with col1:
    run_btn = st.button("🔥 Analyze Risks", type="primary", use_container_width=True)

if run_btn:
    if not idea:
        st.error("Please enter a project idea.")
    else:
        with st.status("Researching and analyzing...", expanded=True) as status:
            st.write("📡 Scraping the web for failure patterns...")
            st.write("🧠 Extracting Cost, Tech, and UX risks using local AI...")
            
            # Run the engine
            result = subprocess.run(
                ["python", "engine.py", idea], 
                capture_output=True, 
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                status.update(label="Error!", state="error")
                st.error(f"Engine failed: {result.stderr}")
            else:
                status.update(label="Analysis Complete!", state="complete")
                st.success("Report generated successfully!")
                
                # Load and display the report
                if os.path.exists("phoenixforge_report.md"):
                    time.sleep(0.5)  # Ensure file is fully written
                    with open("phoenixforge_report.md", "r", encoding='utf-8') as f:
                        content = f.read()
                    
                    # Parse the report to extract structured data for beautiful widgets
                    try:
                        # Extract heatmap JSON (between ```json tags or raw)
                        import re
                        heatmap_match = re.search(r'## Risk Heatmap\s*```json\s*([\s\S]*?)```', content)
                        if not heatmap_match:
                            heatmap_match = re.search(r'## Risk Heatmap\s*([\s\S]*?)(?=\n##|$)', content)
                        
                        fixes_match = re.search(r'## Actionable Fixes\s*```json\s*([\s\S]*?)```', content)
                        if not fixes_match:
                            fixes_match = re.search(r'## Actionable Fixes\s*([\s\S]*?)(?=\n##|$)', content)
                        
                        if heatmap_match:
                            heatmap_data = json.loads(heatmap_match.group(1).strip())
                            st.subheader("📊 Risk Heatmap")
                            cols = st.columns(3)
                            colors = {"Cost": "🔴", "Tech": "🟠", "UX": "🟡"}
                            for i, (key, value) in enumerate(heatmap_data.items()):
                                with cols[i % 3]:
                                    st.metric(label=f"{colors.get(key, '📊')} {key} Risk", value=f"{'🔥' * min(value, 5) if value > 0 else '✅ Low'}")
                        else:
                            st.markdown(content)
                            
                        if fixes_match:
                            fixes_data = json.loads(fixes_match.group(1).strip())
                            st.subheader("🩹 Actionable Fixes")
                            for item in fixes_data:
                                with st.container():
                                    st.warning(f"**{item.get('category', 'General')}**: {item.get('issue', 'N/A')}")
                        else:
                            st.markdown(content)
                            
                    except Exception as e:
                        st.warning("Could not parse structured data, showing raw report.")
                        st.markdown(content)
                else:
                    st.error("Report file not found.")

# Show the latest report if it exists and we haven't just run
if not run_btn and os.path.exists("phoenixforge_report.md"):
    with st.expander("📄 View Last Report", expanded=False):
        with open("phoenixforge_report.md", "r", encoding='utf-8') as f:
            st.markdown(f.read())
