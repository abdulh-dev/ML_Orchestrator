# Deepline Observability Dashboard

A real-time observability dashboard for monitoring workflow orchestration, task execution, and system events.

## Architecture

### Backend (FastAPI)
- **Port**: 8000
- **Features**: REST API, WebSocket streaming, MongoDB integration, Kafka consumer
- **Database**: MongoDB (localhost:27017)
- **Message Queue**: Kafka (localhost:9092)

### Frontend (React)
- **Port**: 3000
- **Features**: Real-time charts, live event streaming, responsive design
- **Charts**: Recharts for data visualization

## Setup Instructions

### Prerequisites
- Docker and Docker Compose (for MongoDB and Kafka)
- Python 3.13+
- Node.js 18+

### 1. Start Infrastructure Services
```bash
# Start MongoDB and Kafka
docker-compose up -d
```

### 2. Start Backend Server
```bash
cd dashboard
# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies (if not already installed)
pip install fastapi uvicorn motor confluent-kafka pydantic

# Start FastAPI server
uvicorn backend.main:app --reload --port 8000
```

### 3. Start Frontend Development Server
```bash
cd dashboard-frontend
# Install dependencies (if not already installed)
npm install

# Start React development server
npm start
```

## Usage

### Access the Dashboard
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### Features

#### 📊 Live Event Activity
- Real-time chart showing event frequency over time
- Visual representation of system activity levels

#### 🏃 Recent Runs
- List of recent workflow runs with status indicators
- Color-coded status (Running, Completed, Failed, Pending)
- Creation timestamps

#### ⚡ Live Events
- Real-time streaming of Kafka events
- JSON event details with syntax highlighting
- Automatic scrolling and event history

### API Endpoints

#### GET /runs
Get list of recent workflow runs
```bash
curl http://localhost:8000/runs
```

#### GET /runs/{run_id}
Get specific run with associated tasks
```bash
curl http://localhost:8000/runs/run_123
```

#### GET /tasks/{task_id}
Get specific task details
```bash
curl http://localhost:8000/tasks/task_456
```

#### WebSocket /ws/events
Real-time event streaming
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/events');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received event:', data);
};
```

## Database Schema

### Runs Collection
```json
{
  "run_id": "string",
  "status": "running|completed|failed|pending",
  "created_at": "datetime",
  "metadata": "object"
}
```

### Tasks Collection
```json
{
  "task_id": "string",
  "run_id": "string",
  "status": "running|completed|failed|pending",
  "created_at": "datetime",
  "checkpoints": ["array_of_strings"],
  "metadata": "object"
}
```

## Kafka Topics

### task.events
Real-time task lifecycle events
```json
{
  "type": "task_started|task_completed|task_failed",
  "task_id": "string",
  "run_id": "string",
  "timestamp": "datetime",
  "data": "object"
}
```

## Development

### Project Structure
```
dashboard/
├── backend/
│   └── main.py          # FastAPI application
├── dashboard-frontend/
│   ├── src/
│   │   ├── App.js       # React main component
│   │   └── App.css      # Styling
│   └── package.json     # Frontend dependencies
├── venv/                # Python virtual environment
└── README.md           # This file
```

### Adding New Features

#### Backend
1. Add new endpoints in `backend/main.py`
2. Update database queries as needed
3. Add new Kafka consumers for additional topics

#### Frontend
1. Add new components in `src/`
2. Update `App.js` for new features
3. Add corresponding CSS in `App.css`

## Monitoring

### Health Check
```bash
curl http://localhost:8000/
```

### WebSocket Connection Test
```bash
# Using wscat (install with: npm install -g wscat)
wscat -c ws://localhost:8000/ws/events
```

### Database Connection Test
```bash
# MongoDB shell
docker exec -it $(docker ps -qf "ancestor=mongo:6.0") mongosh
> use deepline
> db.runs.find().limit(5)
```

## Troubleshooting

### Common Issues

1. **WebSocket connection failed**
   - Ensure backend server is running on port 8000
   - Check CORS configuration in FastAPI

2. **No data in dashboard**
   - Verify MongoDB connection
   - Check if Kafka topics exist and have data

3. **Charts not rendering**
   - Ensure recharts is installed
   - Check browser console for errors

4. **Port conflicts**
   - Backend: Change port in uvicorn command
   - Frontend: Set PORT environment variable

## License

This observability dashboard is part of the Deepline project. 