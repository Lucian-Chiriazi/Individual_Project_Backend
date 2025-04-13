
# PC Builder Backend (FastAPI)

This is the backend service for the **PC Builder Recommendation System**. It uses **FastAPI**, **MongoDB**, and **OpenAI GPT-4** to provide optimized PC builds based on user budget, purpose, and preferences.

---

**Live Demo**: [https://lucian-chiriazi.github.io/Individual_Project_Frontend/](https://lucian-chiriazi.github.io/Individual_Project_Frontend/)

## Instalation option

```bash
git clone https://github.com/Lucian-Chiriazi/Individual_Project_Backend.git
cd Individual_Project_Backend
```

## Requirements

Create and activate a virtual environment first (optional but recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
or
``` bash
source venv/Scripts/activate # For mac, bash console
```
Then install the required packages:

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not present, manually install:

```bash
pip install fastapi uvicorn pymongo openai python-dotenv pytest mongomock matplotlib
```

---

## Environment Variables

Create a `.env` file in the project root:

```ini
MONGO_URI=your_mongo_connection_string
MONGO_DB_NAME=your_database_name
OPENAI_API_KEY=your_openai_api_key
```

---

## Running the Server Locally

```bash
uvicorn main:app --reload
```

This starts the FastAPI app on `http://localhost:8000`.

---

## Running the Test Suite

Tests are written using `pytest` and `mongomock` for mocking MongoDB.

Run all tests:

```bash
pytest test_main_mongomock.py
```

The tests include:
- Endpoint availability (`/`)
- Successful build generation
- Category completeness validation
- Budget limit enforcement
- Component prioritization by purpose
- Compatibility checks (socket & PSU wattage)
- Budget utilization (85%+)

Some tests also visualize results with `matplotlib` charts.

---

## File Structure

- `main.py`: Main FastAPI application.
- `test_main_mongomock.py`: Pytest test suite with mock data.
- `.env`: Configuration file for secrets and credentials (not included here).
- `requirements.txt`: Python dependencies (optional but recommended).

---

##  Endpoints

### `GET /`
Returns basic status message for connectivity check.

### `POST /recommend`
Request a recommended PC build.

#### JSON Body Format:

```json
{
  "budget": 1500,
  "purpose": "gaming",
  "include_os": true,
  "peripherals": ["keyboard", "mouse"]
}
```

Returns a build recommendation and a user-friendly GPT-generated description.

---

## OpenAI Integration

The system uses GPT-4 to:
- Describe the build in plain English
- Suggest peripherals (if selected)
- Recommend an OS if requested

You will need a OpenAI API key for this to run which is not provided with this file.
---


