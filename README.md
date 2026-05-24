# NM Portfolio Intelligence

Institutional portfolio analytics dashboard built on Northwestern Mutual's
public SEC NPORT-P filings (Feb 2026).

**Stack:** SEC EDGAR → Python → Snowflake → dbt → Streamlit

**Live data:**
- 29 portfolios from NM Series Fund Inc (CIK: 0000742212)
- 7,324 holdings across 5 fully-analyzed portfolios
- dbt pipeline: staging → intermediate → mart (46 tests passing)

## Deploy on Streamlit Community Cloud

1. Fork this repo
2. Go to share.streamlit.io
3. Connect your GitHub account
4. Select this repo and `app.py`
5. Add secrets in the Streamlit Cloud dashboard:
```toml
[snowflake]
account   = "your-account"
user      = "your-user"
password  = "your-password"
warehouse = "NM_WH"
database  = "NM_ANALYTICS"
schema    = "RAW_MARTS"
role      = "SYSADMIN"
```
