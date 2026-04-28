cd backend
node src/server.js

cd ai-service
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

cd frontend
npm run dev

Quick health check (after starting):

curl http://localhost:3002/health   # backend
curl http://localhost:8000/health   # AI service