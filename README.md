# IdeaValidator AI ⚖️

> **Get judged before the judges judge you.**

IdeaValidator AI is an agentic AI-powered hackathon project evaluation platform. Upload a pitch deck and/or README to receive structured feedback across four dimensions—technical implementation, business viability, innovation, and presentation—from a simulated panel of five specialized AI judges.

## Features

- **5 AI judge agents** evaluate submissions in parallel, followed by a chief judge verdict.
- **Judge Attack Mode** provides adversarial, high-pressure questions.
- **Radar chart** visualizes scores across evaluation dimensions.
- **Improvement roadmap** gives concrete next steps.
- **Zero persistence:** uploaded files are deleted after evaluation.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite, Tailwind CSS |
| Backend | FastAPI, Python |
| AI | Google Gemini |
| Parsing | PyMuPDF (PDF), python-pptx (PPTX) |

## Setup

### Prerequisites

- Node.js 18+
- Python 3.10+
- A [Google AI Studio](https://aistudio.google.com) API key

### Backend

```bash
cd backend
cp .env.example .env
# Set GEMINI_API_KEY in .env
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

## API

### `POST /evaluate`

Multipart form fields:

| Field | Type | Required |
| --- | --- | --- |
| `pitch_deck` | PDF or PPTX file | Optional* |
| `readme` | Markdown file | Optional* |
| `attack_mode` | Boolean | Optional (defaults to `false`) |

*At least one file is required. The response contains individual judge scores and feedback, an overall verdict, improvement suggestions, a roadmap, and questions for the team.

## Environment variables

Create `backend/.env` from `backend/.env.example` and set `GEMINI_API_KEY`. Do not commit `.env` or real API keys.

## Notes

- Uploaded files are kept in the OS temporary directory and removed after processing.
- Evaluation time depends on API response latency; the four specialist judges run in parallel, then the chief judge synthesizes their reports.
- Large files are truncated to fit API limits. Image-only PDFs may not yield extractable text.
