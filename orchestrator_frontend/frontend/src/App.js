// import React, { useState, useEffect, useRef } from 'react';
// import { Send, Upload, Download, Play, Loader, AlertCircle, CheckCircle, FileText, BarChart3, Brain, Server } from 'lucide-react';

// const OrchestratorFrontend = () => {
//   const [userInput, setUserInput] = useState('');
//   const [messages, setMessages] = useState([]);
//   const [workflows, setWorkflows] = useState([]);
//   const [datasets, setDatasets] = useState([]);
//   const [isProcessing, setIsProcessing] = useState(false);
//   const [apiKey, setApiKey] = useState('');
//   const [showApiKeyInput, setShowApiKeyInput] = useState(true);
//   const [workflowResults, setWorkflowResults] = useState({});
//   const [visualizations, setVisualizations] = useState({});
//   const [isTestingApi, setIsTestingApi] = useState(false);
//   const messagesEndRef = useRef(null);
//   const fileInputRef = useRef(null);

//   const BACKEND_URL = 'http://localhost:3001';

//   const scrollToBottom = () => {
//     messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
//   };

//   const testApiKey = async () => {
//     if (!apiKey.trim()) return;
    
//     setIsTestingApi(true);
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/test-ai`, {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify({ apiKey: apiKey.trim() })
//       });

//       const result = await response.json();
      
//       if (response.ok) {
//         setShowApiKeyInput(false);
//         addMessage('success', '✅ AI connection successful! Welcome to the Data Analysis Orchestrator.');
//       } else {
//         let errorMessage = `❌ API Test Failed: ${result.error}`;
//         if (result.suggestion) {
//           errorMessage += `\n\n💡 Suggestion: ${result.suggestion}`;
//         }
//         alert(errorMessage);
//       }
//     } catch (error) {
//       alert(`❌ Connection failed: ${error.message}\n\nPlease check:\n1. Backend server is running on port 3001\n2. Your internet connection\n3. API key is valid`);
//     } finally {
//       setIsTestingApi(false);
//     }
//   };

//   useEffect(() => {
//     scrollToBottom();
//   }, [messages]);

//   useEffect(() => {
//     fetchDatasets();
//     fetchWorkflows();
//   }, []);

//   const fetchDatasets = async () => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/orchestrator/datasets`);
//       const data = await response.json();
      
//       // Enhance datasets with column information
//       const datasetsWithColumns = await Promise.all(
//         (data.datasets || []).map(async (dataset) => {
//           try {
//             const columnResponse = await fetch(`${BACKEND_URL}/api/dataset-columns/${dataset.filename}`);
//             if (columnResponse.ok) {
//               const columnData = await columnResponse.json();
//               return {
//                 ...dataset,
//                 columns: columnData.columns,
//                 shape: columnData.shape
//               };
//             }
//           } catch (error) {
//             console.log(`Could not get columns for ${dataset.filename}`);
//           }
//           return dataset;
//         })
//       );
      
//       setDatasets(datasetsWithColumns);
//     } catch (error) {
//       console.error('Failed to fetch datasets:', error);
//     }
//   };

//   const fetchWorkflows = async () => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/orchestrator/runs`);
//       const data = await response.json();
//       setWorkflows(data.runs || []);
//     } catch (error) {
//       console.error('Failed to fetch workflows:', error);
//     }
//   };

//   const addMessage = (type, content, metadata = {}) => {
//     const message = {
//       id: Date.now(),
//       type,
//       content,
//       timestamp: new Date().toLocaleTimeString(),
//       metadata
//     };
//     setMessages(prev => [...prev, message]);
//     return message;
//   };

//   const loadVisualizations = async (runId) => {
//     try {
//       console.log(`🔍 Loading visualizations for run: ${runId}`);
      
//       const response = await fetch(`${BACKEND_URL}/api/visualizations-metadata/${runId}`);
//       console.log(`📊 Metadata response status: ${response.status}`);
      
//       if (response.ok) {
//         const vizData = await response.json();
//         console.log(`📈 Found ${vizData.visualizations?.length || 0} visualizations:`, vizData);
        
//         if (!vizData.visualizations || vizData.visualizations.length === 0) {
//           console.log('⚠️ No visualizations found in metadata');
//           return;
//         }
        
//         // Load base64 data for each visualization
//         const vizWithData = await Promise.all(
//           vizData.visualizations.map(async (viz, index) => {
//             try {
//               console.log(`🖼️ Loading visualization ${index + 1}: ${viz.filename}`);
              
//               // Try base64 API first
//               const base64Response = await fetch(`${BACKEND_URL}/api/visualizations-base64/${viz.filename}`);
//               console.log(`📥 Base64 response status for ${viz.filename}: ${base64Response.status}`);
              
//               if (base64Response.ok) {
//                 const base64Data = await base64Response.json();
//                 console.log(`✅ Successfully loaded ${viz.filename}, size: ${base64Data.fileSize} bytes`);
                
//                 return {
//                   ...viz,
//                   dataUrl: base64Data.dataUrl,
//                   loaded: true,
//                   debugInfo: {
//                     fileSize: base64Data.fileSize,
//                     mimeType: base64Data.mimeType,
//                     filePath: base64Data.filePath,
//                     loadMethod: 'base64'
//                   }
//                 };
//               } else {
//                 // If base64 fails, try direct image URL as fallback
//                 console.log(`🔄 Base64 failed, trying direct image URL for ${viz.filename}`);
                
//                 const directImageUrl = `${BACKEND_URL}/api/visualizations/${viz.filename}`;
//                 const directResponse = await fetch(directImageUrl, { method: 'HEAD' });
                
//                 if (directResponse.ok) {
//                   console.log(`✅ Direct image URL works for ${viz.filename}`);
//                   return {
//                     ...viz,
//                     dataUrl: directImageUrl,
//                     loaded: true,
//                     debugInfo: {
//                       loadMethod: 'direct_url',
//                       directUrl: directImageUrl
//                     }
//                   };
//                 } else {
//                   const errorText = await base64Response.text();
//                   console.error(`❌ Both methods failed for ${viz.filename}: base64=${base64Response.status}, direct=${directResponse.status}`);
                  
//                   return {
//                     ...viz,
//                     loaded: false,
//                     error: `Both API and static failed: HTTP ${base64Response.status}`,
//                     debugInfo: {
//                       base64Status: base64Response.status,
//                       directStatus: directResponse.status,
//                       base64Error: errorText
//                     }
//                   };
//                 }
//               }
//             } catch (error) {
//               console.error(`💥 Exception loading visualization ${viz.filename}:`, error);
//               return {
//                 ...viz,
//                 loaded: false,
//                 error: `Exception: ${error.message}`,
//                 debugInfo: {
//                   exception: error.message
//                 }
//               };
//             }
//           })
//         );
        
//         console.log(`🎯 Processed visualizations:`, vizWithData);
        
//         setVisualizations(prev => ({
//           ...prev,
//           [runId]: vizWithData
//         }));
//       } else {
//         const errorText = await response.text();
//         console.error(`❌ Failed to get visualization metadata: ${response.status} - ${errorText}`);
//       }
//     } catch (error) {
//       console.error('💥 Exception in loadVisualizations:', error);
//     }
//   };

//   const parseUserInputWithAI = async (input) => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/parse-input`, {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify({
//           userInput: input,
//           datasets: datasets,
//           apiKey: apiKey
//         })
//       });

//       if (!response.ok) {
//         const errorData = await response.json();
        
//         // If AI fails, try simple pattern matching as fallback
//         if (response.status >= 400) {
//           addMessage('system', '⚠️ AI processing failed, trying simple pattern matching...');
//           return await parseUserInputSimple(input);
//         }
        
//         throw new Error(errorData.error || `API error: ${response.status}`);
//       }

//       const data = await response.json();
//       return data.workflow;
//     } catch (error) {
//       // Fallback to simple parsing
//       addMessage('system', '⚠️ AI unavailable, using basic pattern matching...');
//       return await parseUserInputSimple(input);
//     }
//   };

//   const parseUserInputSimple = async (input) => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/simple-workflow`, {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify({
//           userInput: input,
//           datasets: datasets
//         })
//       });

//       if (!response.ok) {
//         const errorData = await response.json();
//         throw new Error(errorData.error || 'Simple workflow generation failed');
//       }

//       const data = await response.json();
//       return data.workflow;
//     } catch (error) {
//       throw new Error(`Failed to generate workflow: ${error.message}`);
//     }
//   };

//   const executeWorkflow = async (workflowData) => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/orchestrator/workflows/start`, {
//         method: 'POST',
//         headers: {
//           'Content-Type': 'application/json',
//         },
//         body: JSON.stringify(workflowData)
//       });

//       if (!response.ok) {
//         const errorData = await response.json();
//         throw new Error(errorData.error || `Workflow failed: ${response.status}`);
//       }

//       const result = await response.json();
//       return result;
//     } catch (error) {
//       throw new Error(`Failed to execute workflow: ${error.message}`);
//     }
//   };

//   const monitorWorkflow = async (runId) => {
//     const checkStatus = async () => {
//       try {
//         const response = await fetch(`${BACKEND_URL}/api/orchestrator/runs/${runId}/status`);
//         const status = await response.json();
        
//         // Get detailed workflow results
//         const resultsResponse = await fetch(`${BACKEND_URL}/api/workflow-results/${runId}`);
//         const workflowData = await resultsResponse.json();
        
//         // Update workflow results state
//         setWorkflowResults(prev => ({
//           ...prev,
//           [runId]: workflowData
//         }));
        
//         if (status.status === 'COMPLETED') {
//           // Get artifacts
//           const artifactsResponse = await fetch(`${BACKEND_URL}/api/orchestrator/runs/${runId}/artifacts`);
//           const artifacts = await artifactsResponse.json();
          
//           // Load visualizations for display
//           await loadVisualizations(runId);
          
//           addMessage('success', `Workflow completed successfully!`, {
//             runId,
//             artifacts: artifacts.artifacts || [],
//             status,
//             workflowResults: workflowData
//           });
          
//           fetchWorkflows(); // Refresh workflows list
//           return true;
//         } else if (status.status === 'FAILED') {
//           addMessage('error', `Workflow failed: ${status.error_message || 'Unknown error'}`, {
//             runId,
//             workflowResults: workflowData
//           });
//           return true;
//         } else {
//           // Still running, update progress with step details
//           const currentStepInfo = workflowData.steps && workflowData.steps.length > 0 
//             ? ` (${workflowData.steps[workflowData.steps.length - 1].action})`
//             : '';
          
//           addMessage('info', `Workflow ${status.status.toLowerCase()}... ${status.progress?.toFixed(1) || 0}%${currentStepInfo}`, {
//             runId,
//             status,
//             workflowResults: workflowData
//           });
//           return false;
//         }
//       } catch (error) {
//         addMessage('error', `Failed to check workflow status: ${error.message}`);
//         return true;
//       }
//     };

//     // Check immediately and then every 2 seconds
//     const isDone = await checkStatus();
//     if (!isDone) {
//       const interval = setInterval(async () => {
//         const finished = await checkStatus();
//         if (finished) {
//           clearInterval(interval);
//         }
//       }, 2000);
//     }
//   };

//   const handleSubmit = async () => {
//     if (!userInput.trim()) return;

//     setIsProcessing(true);
//     const originalInput = userInput;
//     setUserInput('');

//     // Add user message
//     addMessage('user', originalInput);

//     try {
//       // Step 1: Parse with AI
//       addMessage('system', '🧠 Parsing your request with AI...');
//       const workflowData = await parseUserInputWithAI(originalInput);
      
//       addMessage('system', `📋 Generated workflow: ${workflowData.run_name}`, { workflowData });

//       // Step 2: Execute workflow
//       addMessage('system', '🚀 Starting workflow execution...');
//       const result = await executeWorkflow(workflowData);
      
//       addMessage('info', `✅ Workflow started with ID: ${result.run_id}`);

//       // Step 3: Monitor workflow
//       await monitorWorkflow(result.run_id);

//     } catch (error) {
//       addMessage('error', `❌ ${error.message}`);
//     } finally {
//       setIsProcessing(false);
//     }
//   };

//   const handleFileUpload = async (event) => {
//     const file = event.target.files[0];
//     if (!file) return;

//     const formData = new FormData();
//     formData.append('file', file);
//     formData.append('name', file.name.replace(/\.[^/.]+$/, ''));

//     try {
//       addMessage('system', `📤 Uploading ${file.name}...`);
      
//       const response = await fetch(`${BACKEND_URL}/api/upload`, {
//         method: 'POST',
//         body: formData
//       });

//       if (response.ok) {
//         const result = await response.json();
//         addMessage('success', `✅ Dataset uploaded: ${result.name}`, { dataset: result });
//         fetchDatasets();
//       } else {
//         const errorData = await response.json();
//         throw new Error(errorData.error || `Upload failed: ${response.status}`);
//       }
//     } catch (error) {
//       addMessage('error', `❌ Upload failed: ${error.message}`);
//     }
//   };

//   const downloadArtifact = async (runId, filename) => {
//     try {
//       const response = await fetch(`${BACKEND_URL}/api/orchestrator/artifacts/${runId}/${filename}`);
//       if (response.ok) {
//         const blob = await response.blob();
//         const url = window.URL.createObjectURL(blob);
//         const a = document.createElement('a');
//         a.href = url;
//         a.download = filename;
//         document.body.appendChild(a);
//         a.click();
//         window.URL.revokeObjectURL(url);
//         document.body.removeChild(a);
//         addMessage('success', `📥 Downloaded: ${filename}`);
//       } else {
//         throw new Error(`Download failed: ${response.status}`);
//       }
//     } catch (error) {
//       addMessage('error', `❌ Download failed: ${error.message}`);
//     }
//   };

//   // Helper functions for step styling
//   const getStatusColor = (status) => {
//     const colors = {
//       'RUNNING': '#007acc',
//       'COMPLETED': '#28a745',
//       'FAILED': '#dc3545',
//       'STARTED': '#6f42c1'
//     };
//     return colors[status] || '#6c757d';
//   };

//   const getStepBackgroundColor = (status) => {
//     const colors = {
//       'completed': '#d4edda',
//       'failed': '#f8d7da',
//       'running': '#d1ecf1'
//     };
//     return colors[status] || '#f8f9fa';
//   };

//   const getStepBorderColor = (status) => {
//     const colors = {
//       'completed': '#c3e6cb',
//       'failed': '#f5c6cb',
//       'running': '#bee5eb'
//     };
//     return colors[status] || '#e1e4e8';
//   };

//   // Helper functions for step styling


//   const getStatusTextColor = (status) => {
//     const colors = {
//       'completed': '#155724',
//       'failed': '#721c24',
//       'running': '#0c5460'
//     };
//     return colors[status] || '#495057';
//   };

//   const renderEDAResults = (action, data) => {
//     const containerStyle = {
//       backgroundColor: '#f8f9fa',
//       border: '1px solid #e9ecef',
//       borderRadius: '3px',
//       padding: '6px',
//       fontSize: '8px',
//       color: '#495057',
//       marginTop: '2px'
//     };

//     try {
//       switch (action) {
//         case 'profile_dataset':
//           const basicInfo = data.basic_info || {};
//           const shape = basicInfo.shape || {};
//           const dataTypes = data.data_types || {};
          
//           return (
//             <div style={containerStyle}>
//               <div style={{ fontWeight: '500', marginBottom: '2px' }}>📊 Dataset Overview:</div>
//               <div>📏 Size: {shape.rows || '?'} rows × {shape.columns || '?'} columns</div>
//               <div>📁 Memory: {basicInfo.memory_usage || 'Unknown'}</div>
//               <div>🏷️ Data Types: {Object.keys(dataTypes).length} different types</div>
//               {data.quality_metrics && (
//                 <div>🔍 Missing: {data.quality_metrics.missing_percentage?.toFixed(1) || 0}%</div>
//               )}
//             </div>
//           );

//         case 'statistical_summary':
//           const summary = data.summary || {};
//           const columnCount = Object.keys(summary).length;
          
//           return (
//             <div style={containerStyle}>
//               <div style={{ fontWeight: '500', marginBottom: '2px' }}>📈 Statistical Summary:</div>
//               <div>📊 Analyzed {columnCount} numeric columns</div>
//               {Object.entries(summary).slice(0, 2).map(([col, stats]) => (
//                 <div key={col} style={{ marginTop: '1px' }}>
//                   📋 {col}: mean={stats.mean?.toFixed(2)}, std={stats.std?.toFixed(2)}
//                 </div>
//               ))}
//               {columnCount > 2 && <div style={{ color: '#6c757d' }}>... and {columnCount - 2} more columns</div>}
//             </div>
//           );

//         case 'data_quality':
//           const qualityScore = data.quality_score || 0;
//           const missingValues = data.missing_values || {};
//           const duplicates = data.duplicates || {};
//           const outliers = data.outliers || {};
          
//           const totalMissing = Object.values(missingValues).reduce((sum, info) => 
//             sum + (info.missing_count || 0), 0);
//           const outlierColumns = Object.keys(outliers).length;
          
//           return (
//             <div style={containerStyle}>
//               <div style={{ fontWeight: '500', marginBottom: '2px' }}>🔍 Data Quality Report:</div>
//               <div style={{ color: qualityScore > 80 ? '#28a745' : qualityScore > 60 ? '#ffc107' : '#dc3545' }}>
//                 ⭐ Quality Score: {qualityScore.toFixed(1)}/100
//               </div>
//               <div>❌ Missing Values: {totalMissing} total</div>
//               <div>🔄 Duplicates: {duplicates.total_duplicates || 0} rows ({duplicates.duplicate_percentage?.toFixed(1) || 0}%)</div>
//               <div>📊 Outliers detected in {outlierColumns} columns</div>
//             </div>
//           );

//         case 'correlation_analysis':
//           const correlations = data.correlations || {};
//           const topCorrelations = data.top_correlations || {};
//           const method = data.method || 'pearson';
          
//           return (
//             <div style={containerStyle}>
//               <div style={{ fontWeight: '500', marginBottom: '2px' }}>🔗 Correlation Analysis ({method}):</div>
//               <div>📊 Found {Object.keys(correlations).length} correlation pairs</div>
//               {Object.entries(topCorrelations).slice(0, 3).map(([pair, info]) => {
//                 const corrValue = info.correlation || 0;
//                 const strength = Math.abs(corrValue) > 0.7 ? 'Strong' : Math.abs(corrValue) > 0.4 ? 'Moderate' : 'Weak';
//                 return (
//                   <div key={pair} style={{ marginTop: '1px' }}>
//                     🔗 {pair.replace('_vs_', ' ↔ ')}: {corrValue.toFixed(3)} ({strength})
//                   </div>
//                 );
//               })}
//             </div>
//           );

//         default:
//           return (
//             <div style={containerStyle}>
//               <div style={{ fontWeight: '500' }}>✅ {action} completed</div>
//               <div style={{ color: '#6c757d' }}>Raw data available in details below</div>
//             </div>
//           );
//       }
//     } catch (error) {
//       return (
//         <div style={containerStyle}>
//           <div style={{ color: '#dc3545' }}>⚠️ Error rendering results: {error.message}</div>
//         </div>
//       );
//     }
//   };

//   const renderMessage = (message) => {
//     const iconMap = {
//       user: <Send size={16} />,
//       system: <Server size={16} />,
//       info: <AlertCircle size={16} />,
//       success: <CheckCircle size={16} />,
//       error: <AlertCircle size={16} />
//     };

//     const colorMap = {
//       user: '#007acc',
//       system: '#666',
//       info: '#0066cc',
//       success: '#28a745',
//       error: '#dc3545'
//     };

//     return (
//       <div key={message.id} style={{ 
//         marginBottom: '16px', 
//         padding: '12px', 
//         backgroundColor: message.type === 'user' ? '#f8f9fa' : '#ffffff',
//         border: `1px solid ${colorMap[message.type]}20`,
//         borderLeft: `4px solid ${colorMap[message.type]}`,
//         borderRadius: '4px'
//       }}>
//         <div style={{ 
//           display: 'flex', 
//           alignItems: 'center', 
//           marginBottom: '4px',
//           color: colorMap[message.type]
//         }}>
//           {iconMap[message.type]}
//           <span style={{ marginLeft: '8px', fontSize: '12px', fontWeight: '500' }}>
//             {message.type.toUpperCase()} - {message.timestamp}
//           </span>
//         </div>
        
//         <div style={{ fontSize: '14px', lineHeight: '1.4' }}>
//           {message.content}
//         </div>

//         {/* Render metadata for special message types */}
//         {message.metadata?.workflowData && (
//           <details style={{ marginTop: '8px' }}>
//             <summary style={{ cursor: 'pointer', fontSize: '12px', color: '#666' }}>
//               View Generated Workflow
//             </summary>
//             <pre style={{ 
//               fontSize: '11px', 
//               backgroundColor: '#f8f9fa', 
//               padding: '8px', 
//               borderRadius: '3px',
//               overflow: 'auto',
//               marginTop: '4px'
//             }}>
//               {JSON.stringify(message.metadata.workflowData, null, 2)}
//             </pre>
//           </details>
//         )}

//         {message.metadata?.workflowResults && (
//           <div style={{ marginTop: '8px' }}>
//             <div style={{ fontSize: '12px', fontWeight: '500', marginBottom: '4px' }}>
//               📊 Workflow Progress:
//             </div>
//             <div style={{ 
//               backgroundColor: '#f8f9fa', 
//               border: '1px solid #e1e4e8',
//               borderRadius: '4px', 
//               padding: '8px',
//               fontSize: '11px'
//             }}>
//               <div style={{ marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
//                 <span style={{ fontWeight: '500' }}>Status:</span>
//                 <span style={{ 
//                   padding: '2px 6px', 
//                   borderRadius: '3px',
//                   backgroundColor: getStatusColor(message.metadata.workflowResults.status),
//                   color: 'white',
//                   fontSize: '10px'
//                 }}>
//                   {message.metadata.workflowResults.status}
//                 </span>
//                 {message.metadata.workflowResults.progress !== undefined && (
//                   <span>({message.metadata.workflowResults.progress.toFixed(1)}%)</span>
//                 )}
//               </div>
              
//               {message.metadata.workflowResults.stepSummary && (
//                 <div style={{ marginBottom: '6px', fontSize: '10px', color: '#666' }}>
//                   Steps: {message.metadata.workflowResults.stepSummary.completed} completed, {' '}
//                   {message.metadata.workflowResults.stepSummary.failed} failed, {' '}
//                   {message.metadata.workflowResults.stepSummary.running} running
//                 </div>
//               )}
              
//               {message.metadata.workflowResults.steps && message.metadata.workflowResults.steps.length > 0 && (
//                 <div>
//                   <div style={{ fontWeight: '500', marginBottom: '4px' }}>Step Results:</div>
//                   <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
//                     {message.metadata.workflowResults.steps.map((step, idx) => (
//                       <div key={idx} style={{ 
//                         margin: '3px 0',
//                         padding: '6px 8px',
//                         backgroundColor: getStepBackgroundColor(step.status),
//                         borderRadius: '3px',
//                         border: `1px solid ${getStepBorderColor(step.status)}`
//                       }}>
//                         <div style={{ 
//                           display: 'flex', 
//                           justifyContent: 'space-between', 
//                           alignItems: 'center',
//                           marginBottom: '2px'
//                         }}>
//                           <span style={{ fontWeight: '500', fontSize: '10px' }}>
//                             Step {step.step_number}: {step.agent} → {step.action}
//                           </span>
//                           <span style={{ 
//                             fontSize: '9px', 
//                             color: getStatusTextColor(step.status),
//                             fontWeight: '500'
//                           }}>
//                             {step.status.toUpperCase()}
//                           </span>
//                         </div>
                        
//                         {step.results && step.results.summary && (
//                           <div style={{ color: '#555', fontSize: '9px', marginBottom: '2px' }}>
//                             💡 {step.results.summary}
//                           </div>
//                         )}
                        
//                         {/* Human-readable results for EDA agent */}
//                         {step.agent === 'eda_agent' && step.results && step.results.data && (
//                           <div style={{ marginTop: '4px' }}>
//                             {renderEDAResults(step.action, step.results.data)}
//                           </div>
//                         )}
                        
//                         {step.duration_seconds && (
//                           <div style={{ color: '#666', fontSize: '9px' }}>
//                             ⏱️ Duration: {step.duration_seconds.toFixed(2)}s
//                           </div>
//                         )}
                        
//                         {step.error && (
//                           <div style={{ color: '#dc3545', fontSize: '9px', marginTop: '2px' }}>
//                             ❌ Error: {step.error}
//                           </div>
//                         )}
                        
//                         {step.results && step.results.data && (
//                           <details style={{ marginTop: '3px' }}>
//                             <summary style={{ cursor: 'pointer', fontSize: '9px', color: '#0366d6' }}>
//                               📄 View Raw Data ({step.results.response_size} bytes)
//                             </summary>
//                             <div style={{ 
//                               maxHeight: '120px',
//                               overflow: 'auto',
//                               backgroundColor: '#ffffff', 
//                               padding: '4px', 
//                               borderRadius: '2px',
//                               marginTop: '2px',
//                               border: '1px solid #e1e4e8'
//                             }}>
//                               <pre style={{ 
//                                 fontSize: '8px', 
//                                 margin: 0,
//                                 whiteSpace: 'pre-wrap',
//                                 wordBreak: 'break-word'
//                               }}>
//                                 {JSON.stringify(step.results.data, null, 2)}
//                               </pre>
//                             </div>
//                           </details>
//                         )}
//                       </div>
//                     ))}
//                   </div>
//                 </div>
//               )}
//             </div>
//           </div>
//         )}

//         {message.metadata?.artifacts && message.metadata.artifacts.length > 0 && (
//           <div style={{ marginTop: '8px' }}>
//             <div style={{ fontSize: '12px', fontWeight: '500', marginBottom: '4px' }}>
//               📊 Generated Artifacts:
//             </div>
            
//             {/* Show visualizations inline */}
//             {visualizations[message.metadata.runId] && (
//               <div style={{ marginBottom: '8px' }}>
//                 {visualizations[message.metadata.runId].map((viz, idx) => (
//                   <div key={idx} style={{
//                     marginBottom: '12px',
//                     border: '1px solid #e1e4e8',
//                     borderRadius: '6px',
//                     overflow: 'hidden',
//                     backgroundColor: '#ffffff'
//                   }}>
//                     <div style={{
//                       padding: '8px 12px',
//                       backgroundColor: '#f6f8fa',
//                       borderBottom: '1px solid #e1e4e8',
//                       fontSize: '11px',
//                       fontWeight: '500',
//                       display: 'flex',
//                       justifyContent: 'space-between',
//                       alignItems: 'center'
//                     }}>
//                       <span>📈 {viz.filename}</span>
//                       <div style={{ display: 'flex', gap: '4px' }}>
//                         <button
//                           onClick={() => downloadArtifact(message.metadata.runId, viz.filename)}
//                           style={{
//                             padding: '2px 6px',
//                             backgroundColor: '#007acc',
//                             color: 'white',
//                             border: 'none',
//                             borderRadius: '3px',
//                             fontSize: '9px',
//                             cursor: 'pointer'
//                           }}
//                         >
//                           Download
//                         </button>
//                         {viz.stepNumber && (
//                           <span style={{
//                             padding: '2px 6px',
//                             backgroundColor: '#e1f5fe',
//                             color: '#0277bd',
//                             borderRadius: '3px',
//                             fontSize: '9px'
//                           }}>
//                             Step {viz.stepNumber}
//                           </span>
//                         )}
//                       </div>
//                     </div>
                    
//                     <div style={{ padding: '12px', textAlign: 'center' }}>
//                       {viz.loaded && viz.dataUrl ? (
//                         <div>
//                           <img
//                             src={viz.dataUrl}
//                             alt={viz.filename}
//                             style={{
//                               maxWidth: '100%',
//                               maxHeight: '400px',
//                               border: '1px solid #e1e4e8',
//                               borderRadius: '4px',
//                               boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
//                             }}
//                             onError={(e) => {
//                               console.error(`Image failed to load: ${viz.filename}`);
//                               e.target.style.display = 'none';
//                               e.target.nextSibling.style.display = 'block';
//                             }}
//                             onLoad={() => {
//                               console.log(`✅ Image successfully displayed: ${viz.filename}`);
//                             }}
//                           />
                          
//                           {/* Debug info */}
//                           {viz.debugInfo && (
//                             <details style={{ marginTop: '8px', textAlign: 'left' }}>
//                               <summary style={{ cursor: 'pointer', fontSize: '10px', color: '#666' }}>
//                                 🔧 Debug Info
//                               </summary>
//                               <div style={{ fontSize: '9px', color: '#666', marginTop: '4px' }}>
//                                 <div>File Size: {viz.debugInfo.fileSize} bytes</div>
//                                 <div>MIME Type: {viz.debugInfo.mimeType}</div>
//                                 <div>File Path: {viz.debugInfo.filePath}</div>
//                                 <div>Data URL Length: {viz.dataUrl?.length} chars</div>
//                               </div>
//                             </details>
//                           )}
//                         </div>
//                       ) : viz.error ? (
//                         <div style={{
//                           padding: '20px',
//                           backgroundColor: '#f8d7da',
//                           color: '#721c24',
//                           borderRadius: '4px',
//                           fontSize: '11px'
//                         }}>
//                           <div>❌ Failed to load visualization</div>
//                           <div style={{ marginTop: '4px', fontSize: '10px' }}>
//                             Error: {viz.error}
//                           </div>
//                           <button
//                             onClick={() => {
//                               console.log(`🔄 Retrying load for: ${viz.filename}`);
//                               // Retry loading this specific visualization
//                               loadVisualizations(message.metadata.runId);
//                             }}
//                             style={{
//                               marginTop: '8px',
//                               padding: '4px 8px',
//                               backgroundColor: '#007acc',
//                               color: 'white',
//                               border: 'none',
//                               borderRadius: '3px',
//                               fontSize: '10px',
//                               cursor: 'pointer'
//                             }}
//                           >
//                             🔄 Retry Load
//                           </button>
//                         </div>
//                       ) : (
//                         <div style={{
//                           padding: '20px',
//                           backgroundColor: '#d1ecf1',
//                           color: '#0c5460',
//                           borderRadius: '4px',
//                           fontSize: '11px'
//                         }}>
//                           <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
//                           Loading visualization...
//                         </div>
//                       )}
                      
//                       <div style={{
//                         display: 'none',
//                         padding: '20px',
//                         backgroundColor: '#fff3cd',
//                         color: '#856404',
//                         borderRadius: '4px',
//                         fontSize: '11px',
//                         marginTop: '8px'
//                       }}>
//                         ⚠️ Could not display image. <button
//                           onClick={() => downloadArtifact(message.metadata.runId, viz.filename)}
//                           style={{
//                             background: 'none',
//                             border: 'none',
//                             color: '#007acc',
//                             textDecoration: 'underline',
//                             cursor: 'pointer',
//                             fontSize: '11px'
//                           }}
//                         >
//                           Download instead
//                         </button>
//                       </div>
//                     </div>
//                   </div>
//                 ))}
//               </div>
//             )}
            
//             {/* Download buttons for non-visualization artifacts */}
//             <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
//               {message.metadata.artifacts
//                 .filter(artifact => !visualizations[message.metadata.runId]?.find(v => v.filename === artifact.filename))
//                 .map((artifact, idx) => (
//                   <button
//                     key={idx}
//                     onClick={() => downloadArtifact(message.metadata.runId, artifact.filename)}
//                     style={{
//                       display: 'inline-flex',
//                       alignItems: 'center',
//                       margin: '2px',
//                       padding: '4px 8px',
//                       backgroundColor: '#007acc',
//                       color: 'white',
//                       border: 'none',
//                       borderRadius: '3px',
//                       fontSize: '11px',
//                       cursor: 'pointer'
//                     }}
//                   >
//                     <Download size={12} style={{ marginRight: '4px' }} />
//                     {artifact.filename}
//                   </button>
//                 ))}
//             </div>
//           </div>
//         )}
//       </div>
//     );
//   };

//   if (showApiKeyInput) {
//     return (
//       <div style={{ 
//         display: 'flex', 
//         justifyContent: 'center', 
//         alignItems: 'center', 
//         height: '100vh',
//         backgroundColor: '#f5f5f5'
//       }}>
//         <div style={{ 
//           backgroundColor: 'white', 
//           padding: '32px', 
//           borderRadius: '8px', 
//           boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
//           maxWidth: '400px',
//           width: '100%'
//         }}>
//           <div style={{ textAlign: 'center', marginBottom: '24px' }}>
//             <Brain size={48} style={{ color: '#007acc', marginBottom: '16px' }} />
//             <h2 style={{ margin: '0 0 8px 0', color: '#333' }}>Data Analysis Orchestrator</h2>
//             <p style={{ margin: 0, color: '#666', fontSize: '14px' }}>
//               Enter your Google AI Studio API key to get started
//             </p>
//           </div>
          
//           <input
//             type="password"
//             placeholder="Google AI Studio API Key"
//             value={apiKey}
//             onChange={(e) => setApiKey(e.target.value)}
//             style={{
//               width: '100%',
//               padding: '12px',
//               border: '1px solid #ddd',
//               borderRadius: '4px',
//               fontSize: '14px',
//               marginBottom: '16px',
//               boxSizing: 'border-box'
//             }}
//           />
          
//           <button
//             onClick={testApiKey}
//             disabled={!apiKey.trim() || isTestingApi}
//             style={{
//               width: '100%',
//               padding: '12px',
//               backgroundColor: (!apiKey.trim() || isTestingApi) ? '#ccc' : '#007acc',
//               color: 'white',
//               border: 'none',
//               borderRadius: '4px',
//               fontSize: '14px',
//               cursor: (!apiKey.trim() || isTestingApi) ? 'not-allowed' : 'pointer',
//               display: 'flex',
//               alignItems: 'center',
//               justifyContent: 'center',
//               marginBottom: '8px'
//             }}
//           >
//             {isTestingApi ? (
//               <>
//                 <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
//                 Testing Connection...
//               </>
//             ) : (
//               'Test & Continue'
//             )}
//           </button>
          
//           <button
//             onClick={() => setShowApiKeyInput(false)}
//             style={{
//               width: '100%',
//               padding: '12px',
//               backgroundColor: '#f6f8fa',
//               color: '#666',
//               border: '1px solid #d1d5da',
//               borderRadius: '4px',
//               fontSize: '14px',
//               cursor: 'pointer'
//             }}
//           >
//             Skip AI (Basic Mode)
//           </button>
          
//           <p style={{ 
//             fontSize: '12px', 
//             color: '#666', 
//             textAlign: 'center', 
//             marginTop: '16px',
//             lineHeight: '1.4'
//           }}>
//             Get your free API key from{' '}
//             <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer">
//               Google AI Studio
//             </a>
//             <br />
//             <small style={{ color: '#999' }}>
//               Your key should start with "AIza..." and will be tested before proceeding
//             </small>
//           </p>
//         </div>
//       </div>
//     );
//   }

//   return (
//     <div style={{ 
//       display: 'flex', 
//       height: '100vh', 
//       fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
//       backgroundColor: '#f5f5f5'
//     }}>
//       {/* Main Output Area */}
//       <div style={{ 
//         flex: 1, 
//         display: 'flex', 
//         flexDirection: 'column',
//         backgroundColor: '#ffffff',
//         borderRight: '1px solid #e1e4e8'
//       }}>
//         {/* Header */}
//         <div style={{ 
//           padding: '16px 24px', 
//           borderBottom: '1px solid #e1e4e8',
//           backgroundColor: '#fafbfc',
//           display: 'flex',
//           alignItems: 'center',
//           justifyContent: 'space-between'
//         }}>
//           <div style={{ display: 'flex', alignItems: 'center' }}>
//             <BarChart3 size={24} style={{ color: '#007acc', marginRight: '12px' }} />
//             <h1 style={{ margin: 0, fontSize: '18px', color: '#24292e' }}>
//               Data Analysis Orchestrator
//             </h1>
//           </div>
          
//           <div style={{ display: 'flex', gap: '8px' }}>
//             <span style={{ 
//               fontSize: '12px', 
//               color: '#666',
//               padding: '4px 8px',
//               backgroundColor: '#e1f5fe',
//               borderRadius: '12px'
//             }}>
//               {datasets.length} datasets • {workflows.length} workflows
//             </span>
//           </div>
//         </div>

//         {/* Messages Area */}
//         <div style={{ 
//           flex: 1, 
//           overflow: 'auto', 
//           padding: '24px',
//           backgroundColor: '#ffffff'
//         }}>
//           {messages.length === 0 ? (
//             <div style={{ 
//               textAlign: 'center', 
//               color: '#666', 
//               marginTop: '50px',
//               fontSize: '14px'
//             }}>
//               <FileText size={48} style={{ color: '#ccc', marginBottom: '16px' }} />
//               <p>No analysis yet. Upload data and ask questions to get started!</p>
//               <div style={{ 
//                 marginTop: '24px', 
//                 padding: '16px', 
//                 backgroundColor: '#f8f9fa',
//                 borderRadius: '8px',
//                 textAlign: 'left',
//                 maxWidth: '500px',
//                 margin: '24px auto'
//               }}>
//                 <p style={{ fontWeight: '500', marginBottom: '8px' }}>Smart example queries:</p>
//                 <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px' }}>
//                   <li>"Analyze my dataset and show correlations"</li>
//                   <li>"Create histogram of age" (if age column exists)</li>
//                   <li>"Plot income vs education_years" (uses actual column names)</li>
//                   <li>"Show satisfaction_score by department" (box plots)</li>
//                   <li>"Check data quality and create visualizations"</li>
//                   <li>"Generate comprehensive analysis dashboard"</li>
//                 </ul>
//                 <p style={{ fontSize: '11px', color: '#666', marginTop: '8px' }}>
//                   💡 The AI now knows your exact column names and will use them correctly!
//                   {datasets.length > 0 && datasets[0].columns && (
//                     <span>
//                       <br />Available columns: {datasets[0].columns.all?.slice(0, 3).join(', ')}
//                       {datasets[0].columns.all?.length > 3 && '...'}
//                     </span>
//                   )}
//                 </p>
//               </div>
//             </div>
//           ) : (
//             messages.map(renderMessage)
//           )}
//           <div ref={messagesEndRef} />
//         </div>
//       </div>

//       {/* Right Sidebar - Input Panel */}
//       <div style={{ 
//         width: '400px', 
//         display: 'flex', 
//         flexDirection: 'column',
//         backgroundColor: '#fafbfc',
//         borderLeft: '1px solid #e1e4e8'
//       }}>
//         {/* Sidebar Header */}
//         <div style={{ 
//           padding: '16px', 
//           borderBottom: '1px solid #e1e4e8',
//           backgroundColor: '#ffffff'
//         }}>
//           <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#24292e' }}>
//             Data Analysis Assistant
//           </h3>
          
//           {/* File Upload */}
//           <input
//             ref={fileInputRef}
//             type="file"
//             accept=".csv,.xlsx,.xls,.json"
//             onChange={handleFileUpload}
//             style={{ display: 'none' }}
//           />
//           <button
//             onClick={() => fileInputRef.current?.click()}
//             style={{
//               width: '100%',
//               padding: '8px 12px',
//               backgroundColor: '#f6f8fa',
//               border: '1px solid #d1d5da',
//               borderRadius: '4px',
//               cursor: 'pointer',
//               fontSize: '12px',
//               display: 'flex',
//               alignItems: 'center',
//               justifyContent: 'center'
//             }}
//           >
//             <Upload size={14} style={{ marginRight: '6px' }} />
//             Upload Dataset
//           </button>
//         </div>

//         {/* Datasets List */}
//         <div style={{ 
//           padding: '16px',
//           borderBottom: '1px solid #e1e4e8',
//           maxHeight: '200px',
//           overflow: 'auto'
//         }}>
//           <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
//             Available Datasets ({datasets.length})
//           </h4>
//           {datasets.length === 0 ? (
//             <p style={{ fontSize: '12px', color: '#666', margin: 0 }}>No datasets uploaded</p>
//           ) : (
//             <div style={{ fontSize: '12px' }}>
//               {datasets.map((dataset, idx) => (
//                 <div key={idx} style={{ 
//                   padding: '6px 8px', 
//                   backgroundColor: '#ffffff',
//                   border: '1px solid #e1e4e8',
//                   borderRadius: '3px',
//                   marginBottom: '4px'
//                 }}>
//                   <div style={{ fontWeight: '500', color: '#24292e' }}>
//                     {dataset.name}
//                   </div>
//                   <div style={{ color: '#666' }}>
//                     {dataset.filename} • {(dataset.size / 1024).toFixed(1)}KB
//                   </div>
//                   {dataset.columns && (
//                     <details style={{ marginTop: '4px' }}>
//                       <summary style={{ cursor: 'pointer', fontSize: '11px', color: '#0366d6' }}>
//                         View Columns
//                       </summary>
//                       <div style={{ marginTop: '4px', fontSize: '10px', color: '#666' }}>
//                         <div><strong>Numeric:</strong> {dataset.columns.numeric?.join(', ') || 'None'}</div>
//                         <div><strong>Categorical:</strong> {dataset.columns.categorical?.join(', ') || 'None'}</div>
//                       </div>
//                     </details>
//                   )}
//                 </div>
//               ))}
//             </div>
//           )}
//         </div>

//         {/* Input Area */}
//         <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
//           <div style={{ 
//             padding: '16px',
//             borderBottom: '1px solid #e1e4e8'
//           }}>
//             <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
//               Ask Questions
//             </h4>
//             <textarea
//               value={userInput}
//               onChange={(e) => setUserInput(e.target.value)}
//               placeholder="Describe what analysis or visualization you want..."
//               disabled={isProcessing}
//               style={{
//                 width: '100%',
//                 height: '120px',
//                 padding: '12px',
//                 border: '1px solid #d1d5da',
//                 borderRadius: '4px',
//                 fontSize: '14px',
//                 resize: 'vertical',
//                 fontFamily: 'inherit',
//                 boxSizing: 'border-box'
//               }}
//               onKeyDown={(e) => {
//                 if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
//                   handleSubmit();
//                 }
//               }}
//             />
            
//             <button
//               onClick={handleSubmit}
//               disabled={!userInput.trim() || isProcessing}
//               style={{
//                 width: '100%',
//                 marginTop: '8px',
//                 padding: '10px',
//                 backgroundColor: (!userInput.trim() || isProcessing) ? '#f6f8fa' : '#007acc',
//                 color: (!userInput.trim() || isProcessing) ? '#666' : 'white',
//                 border: '1px solid #d1d5da',
//                 borderRadius: '4px',
//                 cursor: (!userInput.trim() || isProcessing) ? 'not-allowed' : 'pointer',
//                 fontSize: '14px',
//                 fontWeight: '500',
//                 display: 'flex',
//                 alignItems: 'center',
//                 justifyContent: 'center'
//               }}
//             >
//               {isProcessing ? (
//                 <>
//                   <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
//                   Processing...
//                 </>
//               ) : (
//                 <>
//                   <Play size={16} style={{ marginRight: '8px' }} />
//                   Analyze Data
//                 </>
//               )}
//             </button>
            
//             <p style={{ 
//               fontSize: '11px', 
//               color: '#666', 
//               margin: '8px 0 0 0',
//               textAlign: 'center'
//             }}>
//               Press Cmd/Ctrl + Enter to submit
//             </p>
//           </div>

//           {/* Recent Workflows */}
//           <div style={{ 
//             padding: '16px',
//             flex: 1,
//             overflow: 'auto'
//           }}>
//             <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
//               Recent Workflows ({workflows.slice(-5).length})
//             </h4>
            
//             {/* Debug button */}
//             <button
//               onClick={async () => {
//                 try {
//                   const response = await fetch(`${BACKEND_URL}/api/debug/files`);
//                   const debugData = await response.json();
//                   console.log('🔧 Debug Files Info:', debugData);
//                   addMessage('info', '🔧 Debug info logged to console - check browser dev tools');
//                 } catch (error) {
//                   console.error('Debug error:', error);
//                   addMessage('error', `Debug failed: ${error.message}`);
//                 }
//               }}
//               style={{
//                 width: '100%',
//                 padding: '6px',
//                 marginBottom: '4px',
//                 backgroundColor: '#6f42c1',
//                 color: 'white',
//                 border: 'none',
//                 borderRadius: '3px',
//                 fontSize: '10px',
//                 cursor: 'pointer'
//               }}
//             >
//               🔧 Debug File Locations
//             </button>

//             {/* Force copy files button */}
//             <button
//               onClick={async () => {
//                 try {
//                   addMessage('system', '🔄 Attempting to copy visualization files...');
//                   const response = await fetch(`${BACKEND_URL}/api/orchestrator/copy-visualizations`, {
//                     method: 'POST'
//                   });
//                   if (response.ok) {
//                     const result = await response.json();
//                     addMessage('success', `✅ Copied ${result.copied || 0} visualization files`);
//                   } else {
//                     const error = await response.text();
//                     addMessage('error', `❌ Copy failed: ${error}`);
//                   }
//                 } catch (error) {
//                   addMessage('error', `❌ Copy error: ${error.message}`);
//                 }
//               }}
//               style={{
//                 width: '100%',
//                 padding: '6px',
//                 marginBottom: '8px',
//                 backgroundColor: '#28a745',
//                 color: 'white',
//                 border: 'none',
//                 borderRadius: '3px',
//                 fontSize: '10px',
//                 cursor: 'pointer'
//               }}
//             >
//               📋 Copy Viz Files
//             </button>
            
//             <div style={{ fontSize: '11px' }}>
//               {workflows.slice(-5).reverse().map((workflow, idx) => (
//                 <div key={idx} style={{ 
//                   padding: '6px 8px', 
//                   backgroundColor: '#ffffff',
//                   border: '1px solid #e1e4e8',
//                   borderRadius: '3px',
//                   marginBottom: '4px'
//                 }}>
//                   <div style={{ fontWeight: '500', color: '#24292e' }}>
//                     {workflow.run_id?.slice(0, 8)}...
//                   </div>
//                   <div style={{ color: '#666' }}>
//                     {workflow.status} • {workflow.progress?.toFixed(0) || 0}%
//                   </div>
                  
//                   {/* Test visualization loading button for completed workflows */}
//                   {workflow.status === 'COMPLETED' && (
//                     <button
//                       onClick={() => {
//                         console.log(`🧪 Testing visualization loading for run: ${workflow.run_id}`);
//                         loadVisualizations(workflow.run_id);
//                       }}
//                       style={{
//                         padding: '2px 6px',
//                         marginTop: '4px',
//                         backgroundColor: '#007acc',
//                         color: 'white',
//                         border: 'none',
//                         borderRadius: '2px',
//                         fontSize: '9px',
//                         cursor: 'pointer'
//                       }}
//                     >
//                       🧪 Test Load Viz
//                     </button>
//                   )}
//                 </div>
//               ))}
//             </div>
//           </div>
//         </div>
//       </div>
      
//       <style jsx>{`
//         @keyframes spin {
//           from { transform: rotate(0deg); }
//           to { transform: rotate(360deg); }
//         }
//       `}</style>
//     </div>
//   );
// };

// export default OrchestratorFrontend;
import React, { useState, useEffect, useRef } from 'react';
import { Send, Upload, Download, Play, Loader, AlertCircle, CheckCircle, FileText, BarChart3, Brain, Server } from 'lucide-react';

const OrchestratorFrontend = () => {
  const [userInput, setUserInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [showApiKeyInput, setShowApiKeyInput] = useState(true);
  const [workflowResults, setWorkflowResults] = useState({});
  const [visualizations, setVisualizations] = useState({});
  const [isTestingApi, setIsTestingApi] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);
  const [allVisualizations, setAllVisualizations] = useState([]);
  const [debugMode, setDebugMode] = useState(false);
  const [examples, setExamples] = useState([]);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const BACKEND_URL = 'http://localhost:3001';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const testApiKey = async () => {
    if (!apiKey.trim()) return;
    
    setIsTestingApi(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/test-ai`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ apiKey: apiKey.trim() })
      });

      const result = await response.json();
      
      if (response.ok) {
        setShowApiKeyInput(false);
        addMessage('success', '✅ AI connection successful! Welcome to the Data Analysis Orchestrator.');
      } else {
        let errorMessage = `❌ API Test Failed: ${result.error}`;
        if (result.suggestion) {
          errorMessage += `\n\n💡 Suggestion: ${result.suggestion}`;
        }
        alert(errorMessage);
      }
    } catch (error) {
      alert(`❌ Connection failed: ${error.message}\n\nPlease check:\n1. Backend server is running on port 3001\n2. Your internet connection\n3. API key is valid`);
    } finally {
      setIsTestingApi(false);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetchDatasets();
    fetchWorkflows();
    fetchSystemStatus();
    fetchExamples();
  }, []);

  const fetchDatasets = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/orchestrator/datasets`);
      const data = await response.json();
      
      // Enhance datasets with column information
      const datasetsWithColumns = await Promise.all(
        (data.datasets || []).map(async (dataset) => {
          try {
            const columnResponse = await fetch(`${BACKEND_URL}/api/dataset-columns/${dataset.filename}`);
            if (columnResponse.ok) {
              const columnData = await columnResponse.json();
              return {
                ...dataset,
                columns: columnData.columns,
                shape: columnData.shape
              };
            }
          } catch (error) {
            console.log(`Could not get columns for ${dataset.filename}`);
          }
          return dataset;
        })
      );
      
      setDatasets(datasetsWithColumns);
    } catch (error) {
      console.error('Failed to fetch datasets:', error);
    }
  };

  const fetchWorkflows = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/orchestrator/runs`);
      const data = await response.json();
      setWorkflows(data.runs || []);
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    }
  };

  const fetchSystemStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/status`);
      const data = await response.json();
      setSystemStatus(data);
    } catch (error) {
      console.error('Failed to fetch system status:', error);
    }
  };

  const fetchExamples = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/examples`);
      const data = await response.json();
      setExamples(data.examples || []);
    } catch (error) {
      console.error('Failed to fetch examples:', error);
    }
  };

  const fetchAllVisualizations = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/all-visualizations`);
      const data = await response.json();
      setAllVisualizations(data.visualizations || []);
      addMessage('success', `📊 Found ${data.totalVisualizations} visualizations across ${data.totalRuns} workflows`);
    } catch (error) {
      addMessage('error', `❌ Failed to fetch all visualizations: ${error.message}`);
    }
  };

  const testOrchestratorConnection = async () => {
    try {
      addMessage('system', '🔍 Testing orchestrator connection...');
      const response = await fetch(`${BACKEND_URL}/api/test-orchestrator`);
      const data = await response.json();
      
      if (response.ok) {
        addMessage('success', `✅ Orchestrator connected: ${data.orchestratorUrl}`);
        setSystemStatus(prev => ({ ...prev, orchestrator: 'connected' }));
      } else {
        addMessage('error', `❌ Orchestrator test failed: ${data.error}`);
      }
    } catch (error) {
      addMessage('error', `❌ Connection test failed: ${error.message}`);
    }
  };

  const runDebugAnalysis = async () => {
    try {
      addMessage('system', '🔧 Running debug analysis...');
      const response = await fetch(`${BACKEND_URL}/api/debug/orchestrator`);
      const data = await response.json();
      
      addMessage('info', '📊 Debug Results:', { debugData: data });
      console.log('🔧 Debug Analysis:', data);
    } catch (error) {
      addMessage('error', `❌ Debug analysis failed: ${error.message}`);
    }
  };

  const addMessage = (type, content, metadata = {}) => {
    const message = {
      id: Date.now(),
      type,
      content,
      timestamp: new Date().toLocaleTimeString(),
      metadata
    };
    setMessages(prev => [...prev, message]);
    return message;
  };

  const loadVisualizations = async (runId) => {
    try {
      console.log(`🔍 Loading visualizations for run: ${runId}`);
      
      const response = await fetch(`${BACKEND_URL}/api/visualizations-metadata/${runId}`);
      console.log(`📊 Metadata response status: ${response.status}`);
      
      if (response.ok) {
        const vizData = await response.json();
        console.log(`📈 Found ${vizData.visualizations?.length || 0} visualizations:`, vizData);
        
        if (!vizData.visualizations || vizData.visualizations.length === 0) {
          console.log('⚠️ No visualizations found in metadata');
          return;
        }
        
        // Load base64 data for each visualization
        const vizWithData = await Promise.all(
          vizData.visualizations.map(async (viz, index) => {
            try {
              console.log(`🖼️ Loading visualization ${index + 1}: ${viz.filename}`);
              
              // Try base64 API first
              const base64Response = await fetch(`${BACKEND_URL}/api/visualizations-base64/${runId}/${viz.filename}`);
              console.log(`📥 Base64 response status for ${viz.filename}: ${base64Response.status}`);
              
              if (base64Response.ok) {
                const base64Data = await base64Response.json();
                console.log(`✅ Successfully loaded ${viz.filename}, size: ${base64Data.size} bytes`);
                
                return {
                  ...viz,
                  dataUrl: base64Data.dataUrl,
                  loaded: true,
                  debugInfo: {
                    fileSize: base64Data.size,
                    mimeType: base64Data.mimeType,
                    loadMethod: 'base64'
                  }
                };
              } else {
                // If base64 fails, try direct image URL as fallback
                console.log(`🔄 Base64 failed, trying direct image URL for ${viz.filename}`);
                
                const directImageUrl = `${BACKEND_URL}/api/visualizations/${runId}/${viz.filename}`;
                const directResponse = await fetch(directImageUrl, { method: 'HEAD' });
                
                if (directResponse.ok) {
                  console.log(`✅ Direct image URL works for ${viz.filename}`);
                  return {
                    ...viz,
                    dataUrl: directImageUrl,
                    loaded: true,
                    debugInfo: {
                      loadMethod: 'direct_url',
                      directUrl: directImageUrl
                    }
                  };
                } else {
                  const errorText = await base64Response.text();
                  console.error(`❌ Both methods failed for ${viz.filename}: base64=${base64Response.status}, direct=${directResponse.status}`);
                  
                  return {
                    ...viz,
                    loaded: false,
                    error: `Both API and static failed: HTTP ${base64Response.status}`,
                    debugInfo: {
                      base64Status: base64Response.status,
                      directStatus: directResponse.status,
                      base64Error: errorText
                    }
                  };
                }
              }
            } catch (error) {
              console.error(`💥 Exception loading visualization ${viz.filename}:`, error);
              return {
                ...viz,
                loaded: false,
                error: `Exception: ${error.message}`,
                debugInfo: {
                  exception: error.message
                }
              };
            }
          })
        );
        
        console.log(`🎯 Processed visualizations:`, vizWithData);
        
        setVisualizations(prev => ({
          ...prev,
          [runId]: vizWithData
        }));
      } else {
        const errorText = await response.text();
        console.error(`❌ Failed to get visualization metadata: ${response.status} - ${errorText}`);
      }
    } catch (error) {
      console.error('💥 Exception in loadVisualizations:', error);
    }
  };

  const parseUserInputWithAI = async (input) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/parse-input`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userInput: input,
          datasets: datasets,
          apiKey: apiKey
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        
        // If AI fails, try simple pattern matching as fallback
        if (response.status >= 400) {
          addMessage('system', '⚠️ AI processing failed, trying simple pattern matching...');
          return await parseUserInputSimple(input);
        }
        
        throw new Error(errorData.error || `API error: ${response.status}`);
      }

      const data = await response.json();
      return data.workflow;
    } catch (error) {
      // Fallback to simple parsing
      addMessage('system', '⚠️ AI unavailable, using basic pattern matching...');
      return await parseUserInputSimple(input);
    }
  };

  const parseUserInputSimple = async (input) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/simple-workflow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userInput: input,
          datasets: datasets
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Simple workflow generation failed');
      }

      const data = await response.json();
      return data.workflow;
    } catch (error) {
      throw new Error(`Failed to generate workflow: ${error.message}`);
    }
  };

  const executeWorkflow = async (workflowData) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/orchestrator/workflows/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(workflowData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Workflow failed: ${response.status}`);
      }

      const result = await response.json();
      return result;
    } catch (error) {
      throw new Error(`Failed to execute workflow: ${error.message}`);
    }
  };

  const monitorWorkflow = async (runId) => {
    const checkStatus = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/orchestrator/runs/${runId}/status`);
        const status = await response.json();
        
        // Get detailed workflow results
        const resultsResponse = await fetch(`${BACKEND_URL}/api/workflow-results/${runId}`);
        const workflowData = await resultsResponse.json();
        
        // Update workflow results state
        setWorkflowResults(prev => ({
          ...prev,
          [runId]: workflowData
        }));
        
        if (status.status === 'COMPLETED') {
          // Get artifacts
          const artifactsResponse = await fetch(`${BACKEND_URL}/api/orchestrator/runs/${runId}/artifacts`);
          const artifacts = await artifactsResponse.json();
          
          // Load visualizations for display
          await loadVisualizations(runId);
          
          addMessage('success', `Workflow completed successfully!`, {
            runId,
            artifacts: artifacts.artifacts || [],
            status,
            workflowResults: workflowData
          });
          
          fetchWorkflows(); // Refresh workflows list
          return true;
        } else if (status.status === 'FAILED') {
          addMessage('error', `Workflow failed: ${status.error_message || 'Unknown error'}`, {
            runId,
            workflowResults: workflowData
          });
          return true;
        } else {
          // Still running, update progress with step details
          const currentStepInfo = workflowData.steps && workflowData.steps.length > 0 
            ? ` (${workflowData.steps[workflowData.steps.length - 1].action})`
            : '';
          
          addMessage('info', `Workflow ${status.status.toLowerCase()}... ${status.progress?.toFixed(1) || 0}%${currentStepInfo}`, {
            runId,
            status,
            workflowResults: workflowData
          });
          return false;
        }
      } catch (error) {
        addMessage('error', `Failed to check workflow status: ${error.message}`);
        return true;
      }
    };

    // Check immediately and then every 2 seconds
    const isDone = await checkStatus();
    if (!isDone) {
      const interval = setInterval(async () => {
        const finished = await checkStatus();
        if (finished) {
          clearInterval(interval);
        }
      }, 2000);
    }
  };

  const handleSubmit = async () => {
    if (!userInput.trim()) return;

    setIsProcessing(true);
    const originalInput = userInput;
    setUserInput('');

    // Add user message
    addMessage('user', originalInput);

    try {
      // Step 1: Parse with AI
      addMessage('system', '🧠 Parsing your request with AI...');
      const workflowData = await parseUserInputWithAI(originalInput);
      
      addMessage('system', `📋 Generated workflow: ${workflowData.run_name}`, { workflowData });

      // Step 2: Execute workflow
      addMessage('system', '🚀 Starting workflow execution...');
      const result = await executeWorkflow(workflowData);
      
      addMessage('info', `✅ Workflow started with ID: ${result.run_id}`);

      // Step 3: Monitor workflow
      await monitorWorkflow(result.run_id);

    } catch (error) {
      addMessage('error', `❌ ${error.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', file.name.replace(/\.[^/.]+$/, ''));

    try {
      addMessage('system', `📤 Uploading ${file.name}...`);
      
      const response = await fetch(`${BACKEND_URL}/api/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const result = await response.json();
        addMessage('success', `✅ Dataset uploaded: ${result.name}`, { dataset: result });
        fetchDatasets();
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error || `Upload failed: ${response.status}`);
      }
    } catch (error) {
      addMessage('error', `❌ Upload failed: ${error.message}`);
    }
  };

  const downloadArtifact = async (runId, filename) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/orchestrator/artifacts/${runId}/${filename}`);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        addMessage('success', `📥 Downloaded: ${filename}`);
      } else {
        throw new Error(`Download failed: ${response.status}`);
      }
    } catch (error) {
      addMessage('error', `❌ Download failed: ${error.message}`);
    }
  };

  // Helper functions for step styling
  const getStatusColor = (status) => {
    const colors = {
      'RUNNING': '#007acc',
      'COMPLETED': '#28a745',
      'FAILED': '#dc3545',
      'STARTED': '#6f42c1'
    };
    return colors[status] || '#6c757d';
  };

  const getStepBackgroundColor = (status) => {
    const colors = {
      'completed': '#d4edda',
      'failed': '#f8d7da',
      'running': '#d1ecf1'
    };
    return colors[status] || '#f8f9fa';
  };

  const getStepBorderColor = (status) => {
    const colors = {
      'completed': '#c3e6cb',
      'failed': '#f5c6cb',
      'running': '#bee5eb'
    };
    return colors[status] || '#e1e4e8';
  };

  const getStatusTextColor = (status) => {
    const colors = {
      'completed': '#155724',
      'failed': '#721c24',
      'running': '#0c5460'
    };
    return colors[status] || '#495057';
  };

  const renderEDAResults = (action, data) => {
    const containerStyle = {
      backgroundColor: '#f8f9fa',
      border: '1px solid #e9ecef',
      borderRadius: '3px',
      padding: '6px',
      fontSize: '8px',
      color: '#495057',
      marginTop: '2px'
    };

    try {
      switch (action) {
        case 'profile_dataset':
          const basicInfo = data.basic_info || {};
          const shape = basicInfo.shape || {};
          const dataTypes = data.data_types || {};
          
          return (
            <div style={containerStyle}>
              <div style={{ fontWeight: '500', marginBottom: '2px' }}>📊 Dataset Overview:</div>
              <div>📏 Size: {shape.rows || '?'} rows × {shape.columns || '?'} columns</div>
              <div>📁 Memory: {basicInfo.memory_usage || 'Unknown'}</div>
              <div>🏷️ Data Types: {Object.keys(dataTypes).length} different types</div>
              {data.quality_metrics && (
                <div>🔍 Missing: {data.quality_metrics.missing_percentage?.toFixed(1) || 0}%</div>
              )}
            </div>
          );

        case 'statistical_summary':
          const summary = data.summary || {};
          const columnCount = Object.keys(summary).length;
          
          return (
            <div style={containerStyle}>
              <div style={{ fontWeight: '500', marginBottom: '2px' }}>📈 Statistical Summary:</div>
              <div>📊 Analyzed {columnCount} numeric columns</div>
              {Object.entries(summary).slice(0, 2).map(([col, stats]) => (
                <div key={col} style={{ marginTop: '1px' }}>
                  📋 {col}: mean={stats.mean?.toFixed(2)}, std={stats.std?.toFixed(2)}
                </div>
              ))}
              {columnCount > 2 && <div style={{ color: '#6c757d' }}>... and {columnCount - 2} more columns</div>}
            </div>
          );

        case 'data_quality':
          const qualityScore = data.quality_score || 0;
          const missingValues = data.missing_values || {};
          const duplicates = data.duplicates || {};
          const outliers = data.outliers || {};
          
          const totalMissing = Object.values(missingValues).reduce((sum, info) => 
            sum + (info.missing_count || 0), 0);
          const outlierColumns = Object.keys(outliers).length;
          
          return (
            <div style={containerStyle}>
              <div style={{ fontWeight: '500', marginBottom: '2px' }}>🔍 Data Quality Report:</div>
              <div style={{ color: qualityScore > 80 ? '#28a745' : qualityScore > 60 ? '#ffc107' : '#dc3545' }}>
                ⭐ Quality Score: {qualityScore.toFixed(1)}/100
              </div>
              <div>❌ Missing Values: {totalMissing} total</div>
              <div>🔄 Duplicates: {duplicates.total_duplicates || 0} rows ({duplicates.duplicate_percentage?.toFixed(1) || 0}%)</div>
              <div>📊 Outliers detected in {outlierColumns} columns</div>
            </div>
          );

        case 'correlation_analysis':
          const correlations = data.correlations || {};
          const topCorrelations = data.top_correlations || {};
          const method = data.method || 'pearson';
          
          return (
            <div style={containerStyle}>
              <div style={{ fontWeight: '500', marginBottom: '2px' }}>🔗 Correlation Analysis ({method}):</div>
              <div>📊 Found {Object.keys(correlations).length} correlation pairs</div>
              {Object.entries(topCorrelations).slice(0, 3).map(([pair, info]) => {
                const corrValue = info.correlation || 0;
                const strength = Math.abs(corrValue) > 0.7 ? 'Strong' : Math.abs(corrValue) > 0.4 ? 'Moderate' : 'Weak';
                return (
                  <div key={pair} style={{ marginTop: '1px' }}>
                    🔗 {pair.replace('_vs_', ' ↔ ')}: {corrValue.toFixed(3)} ({strength})
                  </div>
                );
              })}
            </div>
          );

        default:
          return (
            <div style={containerStyle}>
              <div style={{ fontWeight: '500' }}>✅ {action} completed</div>
              <div style={{ color: '#6c757d' }}>Raw data available in details below</div>
            </div>
          );
      }
    } catch (error) {
      return (
        <div style={containerStyle}>
          <div style={{ color: '#dc3545' }}>⚠️ Error rendering results: {error.message}</div>
        </div>
      );
    }
  };

  const renderMessage = (message) => {
    const iconMap = {
      user: <Send size={16} />,
      system: <Server size={16} />,
      info: <AlertCircle size={16} />,
      success: <CheckCircle size={16} />,
      error: <AlertCircle size={16} />
    };

    const colorMap = {
      user: '#007acc',
      system: '#666',
      info: '#0066cc',
      success: '#28a745',
      error: '#dc3545'
    };

    return (
      <div key={message.id} style={{ 
        marginBottom: '16px', 
        padding: '12px', 
        backgroundColor: message.type === 'user' ? '#f8f9fa' : '#ffffff',
        border: `1px solid ${colorMap[message.type]}20`,
        borderLeft: `4px solid ${colorMap[message.type]}`,
        borderRadius: '4px'
      }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          marginBottom: '4px',
          color: colorMap[message.type]
        }}>
          {iconMap[message.type]}
          <span style={{ marginLeft: '8px', fontSize: '12px', fontWeight: '500' }}>
            {message.type.toUpperCase()} - {message.timestamp}
          </span>
        </div>
        
        <div style={{ fontSize: '14px', lineHeight: '1.4' }}>
          {message.content}
        </div>

        {/* Render metadata for special message types */}
        {message.metadata?.workflowData && (
          <details style={{ marginTop: '8px' }}>
            <summary style={{ cursor: 'pointer', fontSize: '12px', color: '#666' }}>
              View Generated Workflow
            </summary>
            <pre style={{ 
              fontSize: '11px', 
              backgroundColor: '#f8f9fa', 
              padding: '8px', 
              borderRadius: '3px',
              overflow: 'auto',
              marginTop: '4px'
            }}>
              {JSON.stringify(message.metadata.workflowData, null, 2)}
            </pre>
          </details>
        )}

        {message.metadata?.debugData && (
          <details style={{ marginTop: '8px' }}>
            <summary style={{ cursor: 'pointer', fontSize: '12px', color: '#0366d6' }}>
              🔧 View Debug Information
            </summary>
            <div style={{ 
              fontSize: '11px', 
              backgroundColor: '#f8f9fa', 
              padding: '8px', 
              borderRadius: '3px',
              marginTop: '4px',
              maxHeight: '300px',
              overflow: 'auto'
            }}>
              <div style={{ marginBottom: '8px' }}>
                <strong>Orchestrator URL:</strong> {message.metadata.debugData.orchestratorUrl}
              </div>
              <div style={{ marginBottom: '8px' }}>
                <strong>Connectivity:</strong> 
                <span style={{ 
                  color: message.metadata.debugData.connectivity === 'connected' ? '#28a745' : '#dc3545',
                  marginLeft: '4px'
                }}>
                  {message.metadata.debugData.connectivity}
                </span>
              </div>
              {message.metadata.debugData.runs && (
                <div style={{ marginBottom: '8px' }}>
                  <strong>Runs:</strong> {message.metadata.debugData.runs.total} total
                  <div style={{ fontSize: '10px', color: '#666', marginLeft: '8px' }}>
                    Status breakdown: {JSON.stringify(message.metadata.debugData.runs.statuses)}
                  </div>
                </div>
              )}
              {message.metadata.debugData.artifacts && (
                <div>
                  <strong>Artifact Tests:</strong>
                  {message.metadata.debugData.artifacts.artifactTests.map((test, idx) => (
                    <div key={idx} style={{ 
                      fontSize: '10px', 
                      marginLeft: '8px', 
                      padding: '4px',
                      backgroundColor: test.error ? '#f8d7da' : '#d4edda',
                      borderRadius: '2px',
                      marginTop: '2px'
                    }}>
                      Run {test.runId?.slice(0, 8)}: {test.error || `${test.visualizations} visualizations`}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        )}

        {message.metadata?.workflowResults && (
          <div style={{ marginTop: '8px' }}>
            <div style={{ fontSize: '12px', fontWeight: '500', marginBottom: '4px' }}>
              📊 Workflow Progress:
            </div>
            <div style={{ 
              backgroundColor: '#f8f9fa', 
              border: '1px solid #e1e4e8',
              borderRadius: '4px', 
              padding: '8px',
              fontSize: '11px'
            }}>
              <div style={{ marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: '500' }}>Status:</span>
                <span style={{ 
                  padding: '2px 6px', 
                  borderRadius: '3px',
                  backgroundColor: getStatusColor(message.metadata.workflowResults.status),
                  color: 'white',
                  fontSize: '10px'
                }}>
                  {message.metadata.workflowResults.status}
                </span>
                {message.metadata.workflowResults.progress !== undefined && (
                  <span>({message.metadata.workflowResults.progress.toFixed(1)}%)</span>
                )}
              </div>
              
              {message.metadata.workflowResults.stepSummary && (
                <div style={{ marginBottom: '6px', fontSize: '10px', color: '#666' }}>
                  Steps: {message.metadata.workflowResults.stepSummary.completed} completed, {' '}
                  {message.metadata.workflowResults.stepSummary.failed} failed, {' '}
                  {message.metadata.workflowResults.stepSummary.running} running
                </div>
              )}
              
              {message.metadata.workflowResults.steps && message.metadata.workflowResults.steps.length > 0 && (
                <div>
                  <div style={{ fontWeight: '500', marginBottom: '4px' }}>Step Results:</div>
                  <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                    {message.metadata.workflowResults.steps.map((step, idx) => (
                      <div key={idx} style={{ 
                        margin: '3px 0',
                        padding: '6px 8px',
                        backgroundColor: getStepBackgroundColor(step.status),
                        borderRadius: '3px',
                        border: `1px solid ${getStepBorderColor(step.status)}`
                      }}>
                        <div style={{ 
                          display: 'flex', 
                          justifyContent: 'space-between', 
                          alignItems: 'center',
                          marginBottom: '2px'
                        }}>
                          <span style={{ fontWeight: '500', fontSize: '10px' }}>
                            Step {step.step_number}: {step.agent} → {step.action}
                          </span>
                          <span style={{ 
                            fontSize: '9px', 
                            color: getStatusTextColor(step.status),
                            fontWeight: '500'
                          }}>
                            {step.status.toUpperCase()}
                          </span>
                        </div>
                        
                        {step.results && step.results.summary && (
                          <div style={{ color: '#555', fontSize: '9px', marginBottom: '2px' }}>
                            💡 {step.results.summary}
                          </div>
                        )}
                        
                        {/* Human-readable results for EDA agent */}
                        {step.agent === 'eda_agent' && step.results && step.results.data && (
                          <div style={{ marginTop: '4px' }}>
                            {renderEDAResults(step.action, step.results.data)}
                          </div>
                        )}
                        
                        {step.duration_seconds && (
                          <div style={{ color: '#666', fontSize: '9px' }}>
                            ⏱️ Duration: {step.duration_seconds.toFixed(2)}s
                          </div>
                        )}
                        
                        {step.error && (
                          <div style={{ color: '#dc3545', fontSize: '9px', marginTop: '2px' }}>
                            ❌ Error: {step.error}
                          </div>
                        )}
                        
                        {step.results && step.results.data && (
                          <details style={{ marginTop: '3px' }}>
                            <summary style={{ cursor: 'pointer', fontSize: '9px', color: '#0366d6' }}>
                              📄 View Raw Data ({step.results.response_size} bytes)
                            </summary>
                            <div style={{ 
                              maxHeight: '120px',
                              overflow: 'auto',
                              backgroundColor: '#ffffff', 
                              padding: '4px', 
                              borderRadius: '2px',
                              marginTop: '2px',
                              border: '1px solid #e1e4e8'
                            }}>
                              <pre style={{ 
                                fontSize: '8px', 
                                margin: 0,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}>
                                {JSON.stringify(step.results.data, null, 2)}
                              </pre>
                            </div>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {message.metadata?.artifacts && message.metadata.artifacts.length > 0 && (
          <div style={{ marginTop: '8px' }}>
            <div style={{ fontSize: '12px', fontWeight: '500', marginBottom: '4px' }}>
              📊 Generated Artifacts:
            </div>
            
            {/* Show visualizations inline */}
            {visualizations[message.metadata.runId] && (
              <div style={{ marginBottom: '8px' }}>
                {visualizations[message.metadata.runId].map((viz, idx) => (
                  <div key={idx} style={{
                    marginBottom: '12px',
                    border: '1px solid #e1e4e8',
                    borderRadius: '6px',
                    overflow: 'hidden',
                    backgroundColor: '#ffffff'
                  }}>
                    <div style={{
                      padding: '8px 12px',
                      backgroundColor: '#f6f8fa',
                      borderBottom: '1px solid #e1e4e8',
                      fontSize: '11px',
                      fontWeight: '500',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <span>📈 {viz.filename}</span>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={() => downloadArtifact(message.metadata.runId, viz.filename)}
                          style={{
                            padding: '2px 6px',
                            backgroundColor: '#007acc',
                            color: 'white',
                            border: 'none',
                            borderRadius: '3px',
                            fontSize: '9px',
                            cursor: 'pointer'
                          }}
                        >
                          Download
                        </button>
                        {viz.stepNumber && (
                          <span style={{
                            padding: '2px 6px',
                            backgroundColor: '#e1f5fe',
                            color: '#0277bd',
                            borderRadius: '3px',
                            fontSize: '9px'
                          }}>
                            Step {viz.stepNumber}
                          </span>
                        )}
                      </div>
                    </div>
                    
                    <div style={{ padding: '12px', textAlign: 'center' }}>
                      {viz.loaded && viz.dataUrl ? (
                        <div>
                          <img
                            src={viz.dataUrl}
                            alt={viz.filename}
                            style={{
                              maxWidth: '100%',
                              maxHeight: '400px',
                              border: '1px solid #e1e4e8',
                              borderRadius: '4px',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                            }}
                            onError={(e) => {
                              console.error(`Image failed to load: ${viz.filename}`);
                              e.target.style.display = 'none';
                              e.target.nextSibling.style.display = 'block';
                            }}
                            onLoad={() => {
                              console.log(`✅ Image successfully displayed: ${viz.filename}`);
                            }}
                          />
                          
                          {/* Debug info */}
                          {viz.debugInfo && (
                            <details style={{ marginTop: '8px', textAlign: 'left' }}>
                              <summary style={{ cursor: 'pointer', fontSize: '10px', color: '#666' }}>
                                🔧 Debug Info
                              </summary>
                              <div style={{ fontSize: '9px', color: '#666', marginTop: '4px' }}>
                                <div>File Size: {viz.debugInfo.fileSize} bytes</div>
                                <div>MIME Type: {viz.debugInfo.mimeType}</div>
                                <div>Load Method: {viz.debugInfo.loadMethod}</div>
                                <div>Data URL Length: {viz.dataUrl?.length} chars</div>
                              </div>
                            </details>
                          )}
                        </div>
                      ) : viz.error ? (
                        <div style={{
                          padding: '20px',
                          backgroundColor: '#f8d7da',
                          color: '#721c24',
                          borderRadius: '4px',
                          fontSize: '11px'
                        }}>
                          <div>❌ Failed to load visualization</div>
                          <div style={{ marginTop: '4px', fontSize: '10px' }}>
                            Error: {viz.error}
                          </div>
                          <button
                            onClick={() => {
                              console.log(`🔄 Retrying load for: ${viz.filename}`);
                              // Retry loading this specific visualization
                              loadVisualizations(message.metadata.runId);
                            }}
                            style={{
                              marginTop: '8px',
                              padding: '4px 8px',
                              backgroundColor: '#007acc',
                              color: 'white',
                              border: 'none',
                              borderRadius: '3px',
                              fontSize: '10px',
                              cursor: 'pointer'
                            }}
                          >
                            🔄 Retry Load
                          </button>
                        </div>
                      ) : (
                        <div style={{
                          padding: '20px',
                          backgroundColor: '#d1ecf1',
                          color: '#0c5460',
                          borderRadius: '4px',
                          fontSize: '11px'
                        }}>
                          <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
                          Loading visualization...
                        </div>
                      )}
                      
                      <div style={{
                        display: 'none',
                        padding: '20px',
                        backgroundColor: '#fff3cd',
                        color: '#856404',
                        borderRadius: '4px',
                        fontSize: '11px',
                        marginTop: '8px'
                      }}>
                        ⚠️ Could not display image. <button
                          onClick={() => downloadArtifact(message.metadata.runId, viz.filename)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#007acc',
                            textDecoration: 'underline',
                            cursor: 'pointer',
                            fontSize: '11px'
                          }}
                        >
                          Download instead
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            
            {/* Download buttons for non-visualization artifacts */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              {message.metadata.artifacts
                .filter(artifact => !visualizations[message.metadata.runId]?.find(v => v.filename === artifact.filename))
                .map((artifact, idx) => (
                  <button
                    key={idx}
                    onClick={() => downloadArtifact(message.metadata.runId, artifact.filename)}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      margin: '2px',
                      padding: '4px 8px',
                      backgroundColor: '#007acc',
                      color: 'white',
                      border: 'none',
                      borderRadius: '3px',
                      fontSize: '11px',
                      cursor: 'pointer'
                    }}
                  >
                    <Download size={12} style={{ marginRight: '4px' }} />
                    {artifact.filename}
                  </button>
                ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  if (showApiKeyInput) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        backgroundColor: '#f5f5f5'
      }}>
        <div style={{ 
          backgroundColor: 'white', 
          padding: '32px', 
          borderRadius: '8px', 
          boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
          maxWidth: '400px',
          width: '100%'
        }}>
          <div style={{ textAlign: 'center', marginBottom: '24px' }}>
            <Brain size={48} style={{ color: '#007acc', marginBottom: '16px' }} />
            <h2 style={{ margin: '0 0 8px 0', color: '#333' }}>Data Analysis Orchestrator</h2>
            <p style={{ margin: 0, color: '#666', fontSize: '14px' }}>
              Enter your Google AI Studio API key to get started
            </p>
          </div>
          
          <input
            type="password"
            placeholder="Google AI Studio API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            style={{
              width: '100%',
              padding: '12px',
              border: '1px solid #ddd',
              borderRadius: '4px',
              fontSize: '14px',
              marginBottom: '16px',
              boxSizing: 'border-box'
            }}
          />
          
          <button
            onClick={testApiKey}
            disabled={!apiKey.trim() || isTestingApi}
            style={{
              width: '100%',
              padding: '12px',
              backgroundColor: (!apiKey.trim() || isTestingApi) ? '#ccc' : '#007acc',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: (!apiKey.trim() || isTestingApi) ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '8px'
            }}
          >
            {isTestingApi ? (
              <>
                <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
                Testing Connection...
              </>
            ) : (
              'Test & Continue'
            )}
          </button>
          
          <button
            onClick={() => setShowApiKeyInput(false)}
            style={{
              width: '100%',
              padding: '12px',
              backgroundColor: '#f6f8fa',
              color: '#666',
              border: '1px solid #d1d5da',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: 'pointer'
            }}
          >
            Skip AI (Basic Mode)
          </button>
          
          <p style={{ 
            fontSize: '12px', 
            color: '#666', 
            textAlign: 'center', 
            marginTop: '16px',
            lineHeight: '1.4'
          }}>
            Get your free API key from{' '}
            <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer">
              Google AI Studio
            </a>
            <br />
            <small style={{ color: '#999' }}>
              Your key should start with "AIza..." and will be tested before proceeding
            </small>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ 
      display: 'flex', 
      height: '100vh', 
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      backgroundColor: '#f5f5f5'
    }}>
      {/* Main Output Area */}
      <div style={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column',
        backgroundColor: '#ffffff',
        borderRight: '1px solid #e1e4e8'
      }}>
        {/* Header */}
        <div style={{ 
          padding: '16px 24px', 
          borderBottom: '1px solid #e1e4e8',
          backgroundColor: '#fafbfc',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <BarChart3 size={24} style={{ color: '#007acc', marginRight: '12px' }} />
            <h1 style={{ margin: 0, fontSize: '18px', color: '#24292e' }}>
              Data Analysis Orchestrator
            </h1>
          </div>
          
          <div style={{ display: 'flex', gap: '8px' }}>
            <span style={{ 
              fontSize: '12px', 
              color: '#666',
              padding: '4px 8px',
              backgroundColor: '#e1f5fe',
              borderRadius: '12px'
            }}>
              {datasets.length} datasets • {workflows.length} workflows
            </span>
            
            {systemStatus && (
              <span style={{ 
                fontSize: '12px', 
                color: systemStatus.orchestrator === 'unavailable' ? '#dc3545' : '#28a745',
                padding: '4px 8px',
                backgroundColor: systemStatus.orchestrator === 'unavailable' ? '#f8d7da' : '#d4edda',
                borderRadius: '12px'
              }}>
                {systemStatus.orchestrator === 'unavailable' ? '🔴 Offline' : '🟢 Online'}
              </span>
            )}
            
            {debugMode && (
              <button
                onClick={() => setDebugMode(false)}
                style={{
                  fontSize: '12px',
                  padding: '4px 8px',
                  backgroundColor: '#6f42c1',
                  color: 'white',
                  border: 'none',
                  borderRadius: '12px',
                  cursor: 'pointer'
                }}
              >
                🔧 Debug On
              </button>
            )}
          </div>
        </div>

        {/* Messages Area */}
        <div style={{ 
          flex: 1, 
          overflow: 'auto', 
          padding: '24px',
          backgroundColor: '#ffffff'
        }}>
          {messages.length === 0 ? (
            <div style={{ 
              textAlign: 'center', 
              color: '#666', 
              marginTop: '50px',
              fontSize: '14px'
            }}>
              <FileText size={48} style={{ color: '#ccc', marginBottom: '16px' }} />
              <p>No analysis yet. Upload data and ask questions to get started!</p>
              <div style={{ 
                marginTop: '24px', 
                padding: '16px', 
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                textAlign: 'left',
                maxWidth: '500px',
                margin: '24px auto'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <p style={{ fontWeight: '500', margin: 0 }}>Smart example queries:</p>
                  <button
                    onClick={() => setDebugMode(!debugMode)}
                    style={{
                      padding: '2px 6px',
                      backgroundColor: debugMode ? '#6f42c1' : '#f6f8fa',
                      color: debugMode ? 'white' : '#666',
                      border: '1px solid #d1d5da',
                      borderRadius: '3px',
                      fontSize: '10px',
                      cursor: 'pointer'
                    }}
                  >
                    🔧 Debug
                  </button>
                </div>
                
                {examples.length > 0 ? (
                  <div>
                    {examples.slice(0, 2).map((category, idx) => (
                      <div key={idx} style={{ marginBottom: '8px' }}>
                        <div style={{ fontSize: '12px', fontWeight: '500', color: '#0366d6', marginBottom: '4px' }}>
                          {category.category}:
                        </div>
                        <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '11px' }}>
                          {category.queries.slice(0, 2).map((query, qidx) => (
                            <li key={qidx} style={{ marginBottom: '2px' }}>
                              <button
                                onClick={() => setUserInput(query)}
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  color: '#0366d6',
                                  textDecoration: 'underline',
                                  cursor: 'pointer',
                                  fontSize: '11px',
                                  textAlign: 'left',
                                  padding: 0
                                }}
                              >
                                "{query}"
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    <details style={{ marginTop: '8px' }}>
                      <summary style={{ cursor: 'pointer', fontSize: '11px', color: '#666' }}>
                        Show all examples
                      </summary>
                      <div style={{ marginTop: '8px' }}>
                        {examples.map((category, idx) => (
                          <div key={idx} style={{ marginBottom: '8px' }}>
                            <div style={{ fontSize: '11px', fontWeight: '500', color: '#0366d6', marginBottom: '4px' }}>
                              {category.category}:
                            </div>
                            <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '10px' }}>
                              {category.queries.map((query, qidx) => (
                                <li key={qidx} style={{ marginBottom: '2px' }}>
                                  <button
                                    onClick={() => setUserInput(query)}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      color: '#0366d6',
                                      textDecoration: 'underline',
                                      cursor: 'pointer',
                                      fontSize: '10px',
                                      textAlign: 'left',
                                      padding: 0
                                    }}
                                  >
                                    "{query}"
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </details>
                  </div>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px' }}>
                    <li>"Analyze my dataset and show correlations"</li>
                    <li>"Create histogram of age" (if age column exists)</li>
                    <li>"Plot income vs education_years" (uses actual column names)</li>
                    <li>"Show satisfaction_score by department" (box plots)</li>
                    <li>"Check data quality and create visualizations"</li>
                    <li>"Generate comprehensive analysis dashboard"</li>
                  </ul>
                )}
                
                <p style={{ fontSize: '11px', color: '#666', marginTop: '8px' }}>
                  💡 The AI now knows your exact column names and will use them correctly!
                  {datasets.length > 0 && datasets[0].columns && (
                    <span>
                      <br />Available columns: {datasets[0].columns.all?.slice(0, 3).join(', ')}
                      {datasets[0].columns.all?.length > 3 && '...'}
                    </span>
                  )}
                </p>
              </div>
            </div>
          ) : (
            messages.map(renderMessage)
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Right Sidebar - Input Panel */}
      <div style={{ 
        width: '400px', 
        display: 'flex', 
        flexDirection: 'column',
        backgroundColor: '#fafbfc',
        borderLeft: '1px solid #e1e4e8'
      }}>
        {/* Sidebar Header */}
        <div style={{ 
          padding: '16px', 
          borderBottom: '1px solid #e1e4e8',
          backgroundColor: '#ffffff'
        }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#24292e' }}>
            Data Analysis Assistant
          </h3>
          
          {/* File Upload */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls,.json"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            style={{
              width: '100%',
              padding: '8px 12px',
              backgroundColor: '#f6f8fa',
              border: '1px solid #d1d5da',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <Upload size={14} style={{ marginRight: '6px' }} />
            Upload Dataset
          </button>
        </div>

        {/* Datasets List */}
        <div style={{ 
          padding: '16px',
          borderBottom: '1px solid #e1e4e8',
          maxHeight: '200px',
          overflow: 'auto'
        }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
            Available Datasets ({datasets.length})
          </h4>
          {datasets.length === 0 ? (
            <p style={{ fontSize: '12px', color: '#666', margin: 0 }}>No datasets uploaded</p>
          ) : (
            <div style={{ fontSize: '12px' }}>
              {datasets.map((dataset, idx) => (
                <div key={idx} style={{ 
                  padding: '6px 8px', 
                  backgroundColor: '#ffffff',
                  border: '1px solid #e1e4e8',
                  borderRadius: '3px',
                  marginBottom: '4px'
                }}>
                  <div style={{ fontWeight: '500', color: '#24292e' }}>
                    {dataset.name}
                  </div>
                  <div style={{ color: '#666' }}>
                    {dataset.filename} • {(dataset.size / 1024).toFixed(1)}KB
                  </div>
                  {dataset.columns && (
                    <details style={{ marginTop: '4px' }}>
                      <summary style={{ cursor: 'pointer', fontSize: '11px', color: '#0366d6' }}>
                        View Columns
                      </summary>
                      <div style={{ marginTop: '4px', fontSize: '10px', color: '#666' }}>
                        <div><strong>Numeric:</strong> {dataset.columns.numeric?.join(', ') || 'None'}</div>
                        <div><strong>Categorical:</strong> {dataset.columns.categorical?.join(', ') || 'None'}</div>
                      </div>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ 
            padding: '16px',
            borderBottom: '1px solid #e1e4e8'
          }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
              Ask Questions
            </h4>
            <textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="Describe what analysis or visualization you want..."
              disabled={isProcessing}
              style={{
                width: '100%',
                height: '120px',
                padding: '12px',
                border: '1px solid #d1d5da',
                borderRadius: '4px',
                fontSize: '14px',
                resize: 'vertical',
                fontFamily: 'inherit',
                boxSizing: 'border-box'
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  handleSubmit();
                }
              }}
            />
            
            <button
              onClick={handleSubmit}
              disabled={!userInput.trim() || isProcessing}
              style={{
                width: '100%',
                marginTop: '8px',
                padding: '10px',
                backgroundColor: (!userInput.trim() || isProcessing) ? '#f6f8fa' : '#007acc',
                color: (!userInput.trim() || isProcessing) ? '#666' : 'white',
                border: '1px solid #d1d5da',
                borderRadius: '4px',
                cursor: (!userInput.trim() || isProcessing) ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: '500',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              {isProcessing ? (
                <>
                  <Loader size={16} style={{ marginRight: '8px', animation: 'spin 1s linear infinite' }} />
                  Processing...
                </>
              ) : (
                <>
                  <Play size={16} style={{ marginRight: '8px' }} />
                  Analyze Data
                </>
              )}
            </button>
            
            <p style={{ 
              fontSize: '11px', 
              color: '#666', 
              margin: '8px 0 0 0',
              textAlign: 'center'
            }}>
              Press Cmd/Ctrl + Enter to submit
            </p>
          </div>

          {/* Recent Workflows */}
          <div style={{ 
            padding: '16px',
            flex: 1,
            overflow: 'auto'
          }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>
              Recent Workflows ({workflows.slice(-5).length})
            </h4>
            
            {/* Quick Action Buttons */}
            <div style={{ marginBottom: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <button
                onClick={fetchAllVisualizations}
                style={{
                  width: '100%',
                  padding: '6px',
                  backgroundColor: '#007acc',
                  color: 'white',
                  border: 'none',
                  borderRadius: '3px',
                  fontSize: '10px',
                  cursor: 'pointer'
                }}
              >
                📊 Show All Visualizations
              </button>
              
              <button
                onClick={testOrchestratorConnection}
                style={{
                  width: '100%',
                  padding: '6px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '3px',
                  fontSize: '10px',
                  cursor: 'pointer'
                }}
              >
                🔗 Test Connection
              </button>

              {debugMode && (
                <>
                  <button
                    onClick={runDebugAnalysis}
                    style={{
                      width: '100%',
                      padding: '6px',
                      backgroundColor: '#6f42c1',
                      color: 'white',
                      border: 'none',
                      borderRadius: '3px',
                      fontSize: '10px',
                      cursor: 'pointer'
                    }}
                  >
                    🔧 Debug Analysis
                  </button>
                  
                  <button
                    onClick={async () => {
                      try {
                        addMessage('system', '🔄 Copying visualization files...');
                        const response = await fetch(`${BACKEND_URL}/api/orchestrator/copy-visualizations`, {
                          method: 'POST'
                        });
                        if (response.ok) {
                          const result = await response.json();
                          addMessage('success', `✅ Copied ${result.copied || 0} files`);
                        } else {
                          const error = await response.text();
                          addMessage('error', `❌ Copy failed: ${error}`);
                        }
                      } catch (error) {
                        addMessage('error', `❌ Copy error: ${error.message}`);
                      }
                    }}
                    style={{
                      width: '100%',
                      padding: '6px',
                      backgroundColor: '#28a745',
                      color: 'white',
                      border: 'none',
                      borderRadius: '3px',
                      fontSize: '10px',
                      cursor: 'pointer'
                    }}
                  >
                    📋 Copy Viz Files
                  </button>
                </>
              )}
            </div>

            {/* All Visualizations Display */}
            {allVisualizations.length > 0 && (
              <div style={{ marginBottom: '12px' }}>
                <h5 style={{ margin: '0 0 6px 0', fontSize: '11px', color: '#0366d6' }}>
                  All Visualizations ({allVisualizations.length})
                </h5>
                <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                  {allVisualizations.slice(0, 10).map((viz, idx) => (
                    <div key={idx} style={{
                      padding: '4px 6px',
                      backgroundColor: '#ffffff',
                      border: '1px solid #e1e4e8',
                      borderRadius: '2px',
                      marginBottom: '2px',
                      fontSize: '9px'
                    }}>
                      <div style={{ fontWeight: '500', color: '#24292e' }}>
                        {viz.filename}
                      </div>
                      <div style={{ color: '#666' }}>
                        Run: {viz.runId?.slice(0, 8)} • Status: {viz.runStatus}
                      </div>
                      <button
                        onClick={() => window.open(`${BACKEND_URL}${viz.viewUrl}`, '_blank')}
                        style={{
                          padding: '1px 4px',
                          marginTop: '2px',
                          backgroundColor: '#007acc',
                          color: 'white',
                          border: 'none',
                          borderRadius: '2px',
                          fontSize: '8px',
                          cursor: 'pointer'
                        }}
                      >
                        View
                      </button>
                    </div>
                  ))}
                  {allVisualizations.length > 10 && (
                    <div style={{ fontSize: '9px', color: '#666', textAlign: 'center', padding: '4px' }}>
                      ... and {allVisualizations.length - 10} more
                    </div>
                  )}
                </div>
              </div>
            )}
            
            <div style={{ fontSize: '11px' }}>
              {workflows.slice(-5).reverse().map((workflow, idx) => (
                <div key={idx} style={{ 
                  padding: '6px 8px', 
                  backgroundColor: '#ffffff',
                  border: '1px solid #e1e4e8',
                  borderRadius: '3px',
                  marginBottom: '4px'
                }}>
                  <div style={{ fontWeight: '500', color: '#24292e' }}>
                    {workflow.run_id?.slice(0, 8)}...
                  </div>
                  <div style={{ color: '#666' }}>
                    {workflow.status} • {workflow.progress?.toFixed(0) || 0}%
                  </div>
                  
                  {/* Enhanced action buttons for completed workflows */}
                  {workflow.status === 'COMPLETED' && (
                    <div style={{ marginTop: '4px', display: 'flex', gap: '2px' }}>
                      <button
                        onClick={() => {
                          console.log(`🧪 Testing visualization loading for run: ${workflow.run_id}`);
                          loadVisualizations(workflow.run_id);
                        }}
                        style={{
                          padding: '2px 6px',
                          backgroundColor: '#007acc',
                          color: 'white',
                          border: 'none',
                          borderRadius: '2px',
                          fontSize: '9px',
                          cursor: 'pointer'
                        }}
                      >
                        🧪 Load Viz
                      </button>
                      
                      {debugMode && (
                        <button
                          onClick={async () => {
                            try {
                              const response = await fetch(`${BACKEND_URL}/api/workflow-results/${workflow.run_id}`);
                              const data = await response.json();
                              addMessage('info', `📊 Workflow Details for ${workflow.run_id.slice(0, 8)}`, { workflowResults: data });
                            } catch (error) {
                              addMessage('error', `❌ Failed to get workflow details: ${error.message}`);
                            }
                          }}
                          style={{
                            padding: '2px 6px',
                            backgroundColor: '#6f42c1',
                            color: 'white',
                            border: 'none',
                            borderRadius: '2px',
                            fontSize: '9px',
                            cursor: 'pointer'
                          }}
                        >
                          🔍 Details
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      
      <style jsx>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default OrchestratorFrontend;