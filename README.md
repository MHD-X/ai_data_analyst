# Between Data

Arabic-first AI data analyst with deterministic calculations and PII protection.

## Product principles
- Calculation is deterministic code; the LLM only explains pre-computed facts.
- No row is deleted or imputed: valid rows plus quarantined rows equal the total.
- PII is masked before reaching the LLM; formulas are neutralized in exported reports.
- Users are isolated by `user_id`.

## Theme
Streamlit follows the user's Light, Dark, or System setting. `primaryColor` is blue and the font is sans serif; application CSS does not force a background or text mode.

## Security
- The sandbox uses a restricted builtins set and import allowlist.
- Child processes receive only a minimal environment and run with POSIX resource limits.
- Deployed environments require `DATA_ENCRYPTION_KEY`.

## Configuration
Set variables in `.env` or Streamlit Secrets. The timeout defaults to 60 seconds via `LLM_TIMEOUT`; sandbox execution defaults to 30 seconds.

Required/optional variables: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, `DATABASE_URL`, `TEST_DATABASE_URL`, `DB_PATH`, `AUTH_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SIGNUP_OPEN`, `AUTH_DEV_SHOW_CODE`, `DATA_ENCRYPTION_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY`.

## Run
```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```
