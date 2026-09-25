# IdeaValidator AI ⚖️

> **Get judged before the judges judge you.**

An agentic AI-powered hackathon project evaluation platform that simulates a real judging panel. Upload your pitch deck and README — five specialized AI judges independently evaluate your project and deliver a comprehensive panel verdict.

---

## Features

- **5 AI Judge Agents** running in parallel (Innovation, Technical, Business, Presentation, Chief)
- **Judge Attack Mode** — adversarial, high-pressure questioning
- **Radar Chart** visualization of scores across all dimensions  
- **Improvement Roadmap** — concrete next steps
- **Zero persistence** — files deleted immediately after evaluation

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite + Tailwind CSS |
| Backend | FastAPI + Python |
| AI | Google Gemini 1.5 Flash |
| Parsing | PyMuPDF (PDF), python-pptx (PPTX) |

---

## Setup

### Prerequisites

- Node.js 18+
- Python 3.10+
- A [Google AI Studio](https://aistudio.google.com) API key (free)

---

### 1. Get a Gemini API Key

1. Visit https://aistudio.google.com/app/apikey
2. Create a new API key
3. Copy it for the next step

---

### 2. Backend Setup

```bash
cd backend

# Copy env file and add your key
cp .env.example .env
# Edit .env and set: GEMINI_API_KEY=your_actual_key_here

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload
```

Backend runs at: http://localhost:8000

---

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend runs at: http://localhost:5173

---

## Project Structure

```
ideavalidator-ai/
├── backend/
│   ├── main.py           # FastAPI app & /evaluate endpoint
│   ├── judges.py         # Judge agent runners (parallel execution)
│   ├── prompts.py        # All AI judge prompts
│   ├── file_parser.py    # PDF / PPTX / Markdown extraction
│   ├── gemini_service.py # Gemini API client
│   ├── utils.py          # File cleanup helpers
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/
    ├── src/
    │   ├── App.jsx              # Main application
    │   ├── components/
    │   │   ├── UploadZone.jsx   # Drag-and-drop file upload
    │   │   ├── LoadingScreen.jsx # Animated judging progress
    │   │   ├── ScoreCard.jsx    # Individual judge report card
    │   │   ├── OverallScore.jsx # Chief judge hero card
    │   │   ├── JudgeQuestions.jsx # Q&A panel
    │   │   └── RadarChart.jsx   # SVG score radar
    │   └── index.css
    ├── package.json
    ├── vite.config.js
    └── tailwind.config.js
```

---

## API

### `POST /evaluate`

Multipart form request:

| Field | Type | Required |
|-------|------|----------|
| `pitch_deck` | File (PDF/PPTX) | Optional* |
| `readme` | File (.md) | Optional* |
| `attack_mode` | Boolean | Optional (default: false) |

*At least one file required.

**Response:**
```json
{
  "innovation": {
    "score": 8,
    "strengths": ["..."],
    "weaknesses": ["..."],
    "comments": "..."
  },
  "technical": { ... },
  "business": { ... },
  "presentation": { ... },
  "chief_judge": {
    "overall_score": 7.8,
    "final_verdict": "...",
    "top_strengths": ["..."],
    "top_improvements": ["..."],
    "improvement_roadmap": ["..."],
    "judge_questions": ["..."]
  }
}
```

---

## Environment Variables

Create `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## Notes

- Files are stored in the OS temp directory and deleted immediately after processing
- Evaluation takes 15–30 seconds (4 parallel judges + 1 chief judge synthesis)
- Large files are truncated at ~30,000 characters to fit API limits
- Image-only PDFs will not extract text (text-based slides work best)
