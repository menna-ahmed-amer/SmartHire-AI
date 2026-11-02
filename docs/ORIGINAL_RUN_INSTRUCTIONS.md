# HireSense AI Full Demo

## 1) Start Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Keep this terminal running.

## 2) Start Frontend
Open the `frontend` folder in VS Code, open `index.html`, then right click -> Open with Live Server.

## 3) Real data
For the strongest demo, copy your real `Jobs.csv` from the notebook output into:

```text
backend/data/jobs.csv
```

The backend supports common columns like Job Title, Job Description, Skills, Responsibilities, Company, Work Type, and Experience.
