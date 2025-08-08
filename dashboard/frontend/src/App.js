import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Play, Pause, Activity, Database, Settings, Cpu, TrendingUp, Package, Brain, AlertCircle, CheckCircle, XCircle, ChevronRight, Users, Zap, BarChart3 } from 'lucide-react';
import './App.css';

function App() {
  const [events, setEvents] = useState([]);
  const [runs, setRuns] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState('Disconnected');
  const [eventStats, setEventStats] = useState([]);
  const [sidePanelOpen, setSidePanelOpen] = useState(true);
  const [workflowActive, setWorkflowActive] = useState(false);
  const [activeAgents, setActiveAgents] = useState([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState('');

  // Agent definitions based on your wireframe
  const agentDefinitions = {
    orchestrator: {
      name: 'Orchestrator Agent',
      icon: <Brain className="icon" />,
      status: 'idle',
      color: '#667eea',
      description: 'Routes user intents to the right sub-agent'
    },
    eda: {
      name: 'EDA Agent',
      icon: <BarChart3 className="icon" />,
      status: 'idle',
      color: '#48bb78',
      description: 'Exploratory Data Analysis',
      tools: ['load_data', 'list_datasets', 'basic_info', 'statistical_summary', 'create_visualization', 'detect_outliers']
    },
    schema: {
      name: 'Schema & Quality Agent',
      icon: <Database className="icon" />,
      status: 'idle',
      color: '#4299e1',
      description: 'Data quality and schema validation',
      tools: ['infer_schema', 'data_quality_report', 'missing_data_analysis', 'drift_analysis']
    },
    feature: {
      name: 'Feature Engineering Agent',
      icon: <Settings className="icon" />,
      status: 'idle',
      color: '#ed8936',
      description: 'Feature transformation and engineering',
      tools: ['feature_transformation', 'encoding_methods', 'selection_methods']
    },
    model: {
      name: 'Model Creation & Refinement',
      icon: <Cpu className="icon" />,
      status: 'idle',
      color: '#9f7aea',
      description: 'Model training and optimization',
      tools: ['model_training', 'model_tuning', 'model_performance_report', 'explainability']
    }
  };

  const [agents, setAgents] = useState(agentDefinitions);

  // Workflow templates
  const workflowTemplates = [
    {
      id: 'full-pipeline',
      name: 'Full ML Pipeline',
      description: 'Complete end-to-end ML workflow',
      agents: ['orchestrator', 'eda', 'schema', 'feature', 'model']
    },
    {
      id: 'data-analysis',
      name: 'Data Analysis Only',
      description: 'Explore and analyze your data',
      agents: ['orchestrator', 'eda', 'schema']
    },
    {
      id: 'feature-engineering',
      name: 'Feature Engineering',
      description: 'Transform and engineer features',
      agents: ['orchestrator', 'schema', 'feature']
    }
  ];

  useEffect(() => {
    // Fetch initial runs data
    fetch('http://localhost:8003/runs')
      .then(response => response.json())
      .then(data => {
        if (data.runs) {
          setRuns(data.runs);
        }
      })
      .catch(error => console.error('Error fetching runs:', error));

    // Setup WebSocket connection
    const ws = new WebSocket('ws://localhost:8003/ws/events');
    
    ws.onopen = () => {
      setConnectionStatus('Connected');
      console.log('WebSocket Connected');
    };

    ws.onmessage = (event) => {
      try {
        const eventData = JSON.parse(event.data);
        setEvents(prev => [...prev.slice(-49), eventData]); // Keep last 50 events
        
        // Update event stats for chart
        setEventStats(prev => {
          const newStats = [...prev];
          const now = new Date();
          const timeKey = `${now.getHours()}:${now.getMinutes().toString().padStart(2, '0')}`;
          
          const existingIndex = newStats.findIndex(stat => stat.time === timeKey);
          if (existingIndex >= 0) {
            newStats[existingIndex].count += 1;
          } else {
            newStats.push({ time: timeKey, count: 1 });
          }
          
          return newStats.slice(-20); // Keep last 20 time points
        });
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    ws.onclose = () => {
      setConnectionStatus('Disconnected');
      console.log('WebSocket Disconnected');
    };

    ws.onerror = (error) => {
      setConnectionStatus('Error');
      console.error('WebSocket Error:', error);
    };

    return () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    // Simulate agent status updates
    const interval = setInterval(() => {
      if (workflowActive && activeAgents.length > 0) {
        setAgents(prev => {
          const updated = { ...prev };
          activeAgents.forEach(agentId => {
            const statuses = ['running', 'processing', 'idle'];
            updated[agentId] = {
              ...updated[agentId],
              status: statuses[Math.floor(Math.random() * statuses.length)]
            };
          });
          return updated;
        });
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [workflowActive, activeAgents]);

  const startWorkflow = () => {
    if (!selectedWorkflow) return;
    
    const workflow = workflowTemplates.find(w => w.id === selectedWorkflow);
    if (workflow) {
      setWorkflowActive(true);
      setActiveAgents(workflow.agents);
      
      // Update agent statuses
      setAgents(prev => {
        const updated = { ...prev };
        workflow.agents.forEach(agentId => {
          updated[agentId] = { ...updated[agentId], status: 'running' };
        });
        return updated;
      });
    }
  };

  const stopWorkflow = () => {
    setWorkflowActive(false);
    setActiveAgents([]);
    setAgents(agentDefinitions);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
      case 'processing':
        return <Activity className="icon status-icon animate-pulse" />;
      case 'completed':
        return <CheckCircle className="icon status-icon" />;
      case 'error':
        return <XCircle className="icon status-icon" />;
      default:
        return <AlertCircle className="icon status-icon" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running': return '#4CAF50';
      case 'processing': return '#FF9800';
      case 'completed': return '#2196F3';
      case 'error': return '#f44336';
      default: return '#9E9E9E';
    }
  };

  return (
    <div className="app-container">
      {/* Header with Active Agents */}
      <header className="app-header">
        <div className="header-content">
          <div className="header-left">
            <div className="header-title">
              <h1>
                <Zap className="icon header-icon" />
                Deepline Observability Dashboard
              </h1>
              <div className="header-status">
                <span className={`status ${connectionStatus === 'Connected' ? 'connected' : 'disconnected'}`}>
                  {connectionStatus}
                </span>
                {workflowActive && (
                  <span className="active-workflow">
                    Active Workflow: {workflowTemplates.find(w => w.id === selectedWorkflow)?.name}
                  </span>
                )}
              </div>
            </div>
          </div>
          
          {/* Active Agents Display */}
          <div className="active-agents">
            {activeAgents.map(agentId => (
              <div key={agentId} className="active-agent">
                {agents[agentId].icon}
                <span className="agent-name">{agents[agentId].name}</span>
                {getStatusIcon(agents[agentId].status)}
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="main-layout">
        {/* Side Panel - Agent Status */}
        <aside className={`side-panel ${sidePanelOpen ? 'expanded' : 'collapsed'}`}>
          <div className="side-panel-content">
            <div className="side-panel-header">
              <h2 className={`side-panel-title ${!sidePanelOpen ? 'hidden' : ''}`}>Agent Status</h2>
              <button
                onClick={() => setSidePanelOpen(!sidePanelOpen)}
                className="toggle-button"
              >
                <ChevronRight className={`icon ${sidePanelOpen ? 'rotated' : ''}`} />
              </button>
            </div>
            
            {sidePanelOpen && (
              <div className="agents-list">
                {Object.entries(agents).map(([id, agent]) => (
                  <div key={id} className="agent-card">
                    <div className="agent-card-header">
                      <div className="agent-card-info">
                        <div className="agent-icon" style={{ backgroundColor: `${agent.color}20` }}>
                          {React.cloneElement(agent.icon, { color: agent.color })}
                        </div>
                        <div className="agent-details">
                          <h3 className="agent-name">{agent.name}</h3>
                          <p className="agent-description">{agent.description}</p>
                        </div>
                      </div>
                      <div className="agent-status">
                        {getStatusIcon(agent.status)}
                        <span className="status-text" style={{ color: getStatusColor(agent.status) }}>
                          {agent.status}
                        </span>
                      </div>
                    </div>
                    {agent.tools && (
                      <div className="agent-tools">
                        <p className="tools-label">Available Tools:</p>
                        <div className="tools-list">
                          {agent.tools.slice(0, 3).map(tool => (
                            <span key={tool} className="tool-tag">
                              {tool}
                            </span>
                          ))}
                          {agent.tools.length > 3 && (
                            <span className="more-tools">+{agent.tools.length - 3} more</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <main className="main-content">
          {/* Workflow Starter */}
          <div className="workflow-section">
            <h2 className="section-title">
              <Play className="icon" />
              Start New Workflow
            </h2>
            <div className="workflow-templates">
              {workflowTemplates.map(workflow => (
                <div
                  key={workflow.id}
                  onClick={() => setSelectedWorkflow(workflow.id)}
                  className={`workflow-card ${selectedWorkflow === workflow.id ? 'selected' : ''}`}
                >
                  <h3 className="workflow-name">{workflow.name}</h3>
                  <p className="workflow-description">{workflow.description}</p>
                  <div className="workflow-agents">
                    {workflow.agents.map(agentId => (
                      <span key={agentId} className="workflow-agent-tag">
                        {agents[agentId].name}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="workflow-controls">
              <button
                onClick={startWorkflow}
                disabled={!selectedWorkflow || workflowActive}
                className={`workflow-button primary ${(!selectedWorkflow || workflowActive) ? 'disabled' : ''}`}
              >
                <Play className="icon" />
                Start Workflow
              </button>
              {workflowActive && (
                <button
                  onClick={stopWorkflow}
                  className="workflow-button danger"
                >
                  <Pause className="icon" />
                  Stop Workflow
                </button>
              )}
            </div>
          </div>

          {/* Stats Grid */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-content">
                <div className="stat-info">
                  <p className="stat-label">Total Runs</p>
                  <p className="stat-value">{runs.length}</p>
                </div>
                <TrendingUp className="icon stat-icon green" />
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-content">
                <div className="stat-info">
                  <p className="stat-label">Active Agents</p>
                  <p className="stat-value">{activeAgents.length}</p>
                </div>
                <Users className="icon stat-icon blue" />
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-content">
                <div className="stat-info">
                  <p className="stat-label">Events Today</p>
                  <p className="stat-value">{events.length}</p>
                </div>
                <Activity className="icon stat-icon purple" />
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-content">
                <div className="stat-info">
                  <p className="stat-label">Success Rate</p>
                  <p className="stat-value">94%</p>
                </div>
                <Package className="icon stat-icon orange" />
              </div>
            </div>
          </div>

          {/* Charts and Events */}
          <div className="charts-section">
            <div className="chart-card">
              <h2 className="chart-title">Live Event Activity</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={eventStats}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="time" />
                  <YAxis />
                  <Tooltip />
                  <Line 
                    type="monotone" 
                    dataKey="count" 
                    stroke="#667eea" 
                    strokeWidth={3}
                    dot={{ fill: '#667eea', r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="events-card">
              <h2 className="chart-title">Recent Events</h2>
              <div className="events-list">
                {events.length === 0 ? (
                  <p className="no-events">No events received yet</p>
                ) : (
                  events.slice(-5).reverse().map((event, index) => (
                    <div key={index} className="event-item-new">
                      <div className="event-header-new">
                        <span className="event-type-new">
                          {event.type || 'event'}
                        </span>
                        <span className="event-time-new">
                          {new Date().toLocaleTimeString()}
                        </span>
                      </div>
                      <pre className="event-data">
                        {JSON.stringify(event, null, 2)}
                      </pre>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
