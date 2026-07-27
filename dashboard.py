"""
Streamlit monitor for the algo (Step 4 of deployment). Read-only: it never
places orders, it only visualizes what main_algo.py has already logged to
trade_history.db.

Run with: streamlit run dashboard.py
"""
import pandas as pd
import streamlit as st

import config
import db
import risk_manager

st.set_page_config(page_title="Break-and-Retest Monitor", layout="wide")
st.title("Break-and-Retest Day Trading Monitor")

if st.button("Refresh"):
    st.rerun()

trades = db.get_all_trades()
df = pd.DataFrame(trades)

cumulative_pnl = db.get_cumulative_pnl()
current_risk = risk_manager.get_current_risk_limit(
    cumulative_pnl, config.BASE_RISK, config.PROFIT_BUFFER_TARGET, config.SCALED_RISK
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Ticker", config.TICKER)
col2.metric("Cumulative Realized P&L", f"${cumulative_pnl:.2f}")
col3.metric("Current Risk / Trade", f"${current_risk:.2f}")
col4.metric("Mode", "LIVE" if config.IS_LIVE else "PAPER")

if config.IS_LIVE:
    st.warning("LIVE TRADING IS ACTIVE. Real money is at risk.")

st.subheader("Trade History")
if df.empty:
    st.info("No trades logged yet.")
else:
    closed = df[df["status"] == "closed"].sort_values("closed_at")
    if not closed.empty:
        closed = closed.assign(running_pnl=closed["pnl"].cumsum())
        st.line_chart(closed.set_index("closed_at")["running_pnl"])
    st.dataframe(df.sort_values("opened_at", ascending=False), use_container_width=True)
