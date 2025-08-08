const express = require('express');
const cors = require('cors');
const axios = require('axios');
const multer = require('multer');
const FormData = require('form-data');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Configure multer for file uploads
const upload = multer({ 
  dest: 'uploads/',
  limits: {
    fileSize: 50 * 1024 * 1024 // 50MB limit
  }
});

// Orchestrator URL
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'http://localhost:8000';
const GOOGLE_AI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent';

// Helper function to create AI prompt
const createAnalysisPrompt = (userInput, datasets) => {
  // Extract column information from datasets
  const datasetInfo = datasets.map(dataset => {
    const info = {
      name: dataset.name,
      filename: dataset.filename
    };
    
    if (dataset.columns) {
      info.columns = {
        all: dataset.columns.all || [],
        numeric: dataset.columns.numeric || [],
        categorical: dataset.columns.categorical || [],
        datetime: dataset.columns.datetime || []
      };
      info.shape = dataset.shape;
    }
    
    return info;
  });

  return `
You are an expert data analyst assistant that converts natural language requests into structured API calls for a data analysis orchestrator.

The orchestrator has two main agents:

1. EDA Agent (eda_agent) - for exploratory data analysis
   Available actions:
   - profile_dataset: Get comprehensive dataset overview (requires: file_path, dataset_name)
   - statistical_summary: Generate statistical summaries (requires: file_path, optional: columns)
   - data_quality: Assess data quality issues (requires: file_path)
   - correlation_analysis: Find correlations between variables (requires: file_path, optional: method)

2. Graphing Agent (graphing_agent) - for visualizations
   Available actions:
   - histogram: Distribution of single variable (requires: file_path, column, optional: bins, title)
   - scatter_plot: Relationship between two variables (requires: file_path, x_column, y_column, optional: color_column, size_column, title)
   - correlation_heatmap: Visual correlation matrix (requires: file_path, optional: columns, method, title)
   - box_plot: Distribution summary with quartiles (requires: file_path, columns, optional: groupby_column, title)
   - time_series: Time-based visualization (requires: file_path, date_column, value_columns, optional: title)
   - distribution_plot: Advanced distribution analysis (requires: file_path, columns, optional: title)
   - multi_plot: Dashboard with multiple plots (requires: file_path, plots array, optional: layout, title)

Available datasets with EXACT column information:
${datasetInfo.map(d => `
Dataset: ${d.name} (${d.filename})
${d.columns ? `
- All columns: ${d.columns.all.join(', ')}
- Numeric columns: ${d.columns.numeric.join(', ')}
- Categorical columns: ${d.columns.categorical.join(', ')}
- Shape: ${d.shape?.rows || '?'} rows × ${d.shape?.columns || '?'} columns` : 
'- Columns: Not available (use safe actions only)'}
`).join('\n')}

CRITICAL RULES:
1. Use ONLY the EXACT column names listed above - never invent or guess column names
2. For histogram: choose ONE column from the numeric columns list
3. For scatter_plot: choose x_column and y_column from numeric columns, color_column from categorical
4. For box_plot: choose columns from numeric columns, groupby_column from categorical
5. If no column information is available, use ONLY these safe actions: profile_dataset, statistical_summary, data_quality, correlation_analysis, correlation_heatmap

Convert this user request into a workflow JSON structure:
"${userInput}"

Return ONLY a valid JSON object with this structure:
{
  "run_name": "Descriptive name for the analysis",
  "tasks": [
    {
      "agent": "eda_agent" or "graphing_agent",
      "action": "specific_action_name",
      "args": {
        "file_path": "exact_filename.csv",
        "column": "EXACT_COLUMN_NAME_FROM_LIST_ABOVE",
        "x_column": "EXACT_NUMERIC_COLUMN_NAME",
        "y_column": "EXACT_NUMERIC_COLUMN_NAME",
        "color_column": "EXACT_CATEGORICAL_COLUMN_NAME",
        "title": "Descriptive title"
      }
    }
  ]
}

Examples based on available columns:
- "create histogram of age" → histogram with column: "age" (if age exists in numeric columns)
- "plot income vs education" → scatter_plot with x_column: "education_years", y_column: "income" (if these exist)
- "show satisfaction by department" → box_plot with columns: ["satisfaction_score"], groupby_column: "department"
- "analyze correlations" → correlation_analysis + correlation_heatmap (always safe)

NEVER use column names that are not in the exact lists provided above!
`;
};

// Helper function for API error suggestions
function getApiErrorSuggestion(status) {
  switch (status) {
    case 400:
      return 'Check if your API key format is correct (should start with AIza...)';
    case 403:
      return 'API key may not have permission to access Gemini API. Check your Google AI Studio settings.';
    case 404:
      return 'The API endpoint was not found. The model name might be incorrect.';
    case 429:
      return 'Rate limit exceeded. Wait a moment and try again.';
    default:
      return 'Check your internet connection and API key validity.';
  }
}

// Helper function to get step description
async function getStepDescription(stepNumber, runId) {
    try {
        const stepResponse = await axios.get(
            `${ORCHESTRATOR_URL}/runs/${runId}/steps/${stepNumber}`,
            { timeout: 3000 }
        );
        return stepResponse.data.results?.summary || `Step ${stepNumber}`;
    } catch (error) {
        return `Step ${stepNumber}`;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// AI PROCESSING ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Test Google AI API connection
app.post('/api/test-ai', async (req, res) => {
  try {
    const { apiKey } = req.body;

    if (!apiKey) {
      return res.status(400).json({ error: 'API key is required' });
    }

    console.log('Testing API key...');
    
    const testResponse = await axios.post(`${GOOGLE_AI_API_URL}?key=${apiKey}`, {
      contents: [{
        parts: [{
          text: "Hello, please respond with 'AI connection successful'"
        }]
      }]
    }, {
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json'
      }
    });

    console.log('Test response:', testResponse.data);

    res.json({
      success: true,
      message: 'AI connection successful',
      response: testResponse.data
    });

  } catch (error) {
    console.error('AI test error:', error.response?.data || error.message);
    
    if (error.response) {
      return res.status(error.response.status).json({
        error: 'AI API test failed',
        status: error.response.status,
        details: error.response.data,
        suggestion: getApiErrorSuggestion(error.response.status)
      });
    }

    res.status(500).json({
      error: 'AI connection test failed',
      message: error.message
    });
  }
});

// Route: Parse user input with Google AI
app.post('/api/parse-input', async (req, res) => {
  try {
    const { userInput, datasets, apiKey } = req.body;

    if (!apiKey) {
      return res.status(400).json({ error: 'API key is required' });
    }

    if (!userInput || !datasets) {
      return res.status(400).json({ error: 'User input and datasets are required' });
    }

    // Get actual column information for each dataset
    const datasetsWithColumns = await Promise.all(
      datasets.map(async (dataset) => {
        try {
          // Try to get column info from graphing agent
          const columnResponse = await axios.get(`http://localhost:8002/dataset_info/${dataset.filename}`, {
            timeout: 5000
          });
          
          if (columnResponse.status === 200) {
            return {
              ...dataset,
              columns: columnResponse.data.columns,
              shape: columnResponse.data.shape
            };
          }
        } catch (error) {
          console.log(`Could not get columns for ${dataset.filename}, using defaults`);
        }
        
        // Fallback to basic dataset info
        return dataset;
      })
    );

    const prompt = createAnalysisPrompt(userInput, datasetsWithColumns);

    console.log('Making request to Google AI Studio...');
    console.log('API URL:', `${GOOGLE_AI_API_URL}?key=${apiKey.substring(0, 10)}...`);

    const response = await axios.post(`${GOOGLE_AI_API_URL}?key=${apiKey}`, {
      contents: [{
        parts: [{
          text: prompt
        }]
      }],
      generationConfig: {
        temperature: 0.1,
        topK: 1,
        topP: 1,
        maxOutputTokens: 2048,
      },
      safetySettings: [
        {
          category: "HARM_CATEGORY_HARASSMENT",
          threshold: "BLOCK_NONE"
        },
        {
          category: "HARM_CATEGORY_HATE_SPEECH", 
          threshold: "BLOCK_NONE"
        },
        {
          category: "HARM_CATEGORY_SEXUALLY_EXPLICIT",
          threshold: "BLOCK_NONE"
        },
        {
          category: "HARM_CATEGORY_DANGEROUS_CONTENT",
          threshold: "BLOCK_NONE"
        }
      ]
    }, {
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    });

    console.log('AI Response status:', response.status);

    if (!response.data?.candidates?.[0]?.content?.parts?.[0]?.text) {
      console.error('Invalid AI response structure:', response.data);
      throw new Error('Invalid response from Google AI - no content generated');
    }

    const aiResponse = response.data.candidates[0].content.parts[0].text;
    console.log('AI Generated Text:', aiResponse);
    
    // Extract JSON from AI response
    const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.error('No JSON found in AI response:', aiResponse);
      throw new Error('Could not extract valid JSON from AI response');
    }
    
    let workflowData;
    try {
      workflowData = JSON.parse(jsonMatch[0]);
    } catch (parseError) {
      console.error('JSON Parse error:', parseError);
      console.error('Attempted to parse:', jsonMatch[0]);
      throw new Error('AI generated invalid JSON format');
    }

    // Validate the workflow structure
    if (!workflowData.run_name || !workflowData.tasks || !Array.isArray(workflowData.tasks)) {
      console.error('Invalid workflow structure:', workflowData);
      throw new Error('Invalid workflow structure generated by AI');
    }

    console.log('Successfully parsed workflow:', workflowData);

    res.json({
      success: true,
      workflow: workflowData,
      originalInput: userInput,
      aiResponse: aiResponse,
      datasetsWithColumns: datasetsWithColumns
    });

  } catch (error) {
    console.error('Parse input error:', error);
    
    // Enhanced error details
    if (error.response) {
      console.error('API Response Status:', error.response.status);
      console.error('API Response Data:', error.response.data);
      
      if (error.response.status === 400) {
        return res.status(400).json({ 
          error: 'Invalid API request - check your API key and request format',
          details: error.response.data,
          suggestion: 'Verify your Google AI Studio API key is correct and has the necessary permissions'
        });
      } else if (error.response.status === 403) {
        return res.status(403).json({ 
          error: 'API key forbidden - check permissions',
          details: error.response.data,
          suggestion: 'Ensure your API key has access to the Gemini API'
        });
      } else if (error.response.status === 404) {
        return res.status(404).json({ 
          error: 'API endpoint not found - check the model name',
          details: error.response.data,
          suggestion: 'Try using a different model name like gemini-1.5-flash or gemini-pro'
        });
      }
    }
    
    res.status(500).json({ 
      error: error.message || 'Failed to parse input with AI',
      details: error.response?.data || null,
      type: error.code || 'unknown'
    });
  }
});

// Route: Simple workflow generation (fallback without AI)
app.post('/api/simple-workflow', async (req, res) => {
  try {
    const { userInput, datasets } = req.body;
    
    if (!userInput || !datasets || datasets.length === 0) {
      return res.status(400).json({ error: 'User input and datasets are required' });
    }

    const input = userInput.toLowerCase();
    const firstDataset = datasets[0];
    
    // Try to get column information
    let columns = null;
    try {
      const columnResponse = await axios.get(`http://localhost:8002/dataset_info/${firstDataset.filename}`, {
        timeout: 5000
      });
      if (columnResponse.status === 200) {
        columns = columnResponse.data.columns;
      }
    } catch (error) {
      console.log('Could not get column info for simple workflow');
    }
    
    let workflow = {
      run_name: "Simple Analysis",
      tasks: []
    };

    // Simple pattern matching for common requests
    if (input.includes('analyze') || input.includes('profile')) {
      workflow.run_name = "Dataset Analysis";
      workflow.tasks = [
        {
          agent: "eda_agent",
          action: "profile_dataset",
          args: {
            file_path: firstDataset.filename,
            dataset_name: firstDataset.name
          }
        },
        {
          agent: "eda_agent",
          action: "statistical_summary",
          args: {
            file_path: firstDataset.filename
          }
        }
      ];
    } else if (input.includes('correlation') || input.includes('heatmap')) {
      workflow.run_name = "Correlation Analysis";
      workflow.tasks = [
        {
          agent: "eda_agent",
          action: "correlation_analysis",
          args: {
            file_path: firstDataset.filename
          }
        },
        {
          agent: "graphing_agent",
          action: "correlation_heatmap",
          args: {
            file_path: firstDataset.filename,
            title: "Correlation Heatmap"
          }
        }
      ];
    } else if (input.includes('histogram') && columns?.numeric?.length > 0) {
      workflow.run_name = "Distribution Analysis";
      const columnToUse = columns.numeric[0];
      
      workflow.tasks = [
        {
          agent: "graphing_agent",
          action: "histogram",
          args: {
            file_path: firstDataset.filename,
            column: columnToUse,
            bins: 30,
            title: `${columnToUse.charAt(0).toUpperCase() + columnToUse.slice(1)} Distribution`
          }
        }
      ];
    } else if (input.includes('quality')) {
      workflow.run_name = "Data Quality Assessment";
      workflow.tasks = [
        {
          agent: "eda_agent",
          action: "data_quality",
          args: {
            file_path: firstDataset.filename
          }
        }
      ];
    } else {
      // Default comprehensive analysis
      workflow.run_name = "Comprehensive Analysis";
      workflow.tasks = [
        {
          agent: "eda_agent",
          action: "profile_dataset",
          args: {
            file_path: firstDataset.filename,
            dataset_name: firstDataset.name
          }
        },
        {
          agent: "eda_agent",
          action: "data_quality",
          args: {
            file_path: firstDataset.filename
          }
        },
        {
          agent: "graphing_agent",
          action: "correlation_heatmap",
          args: {
            file_path: firstDataset.filename,
            title: "Data Correlations"
          }
        }
      ];
    }

    res.json({
      success: true,
      workflow: workflow,
      originalInput: userInput,
      method: 'simple_pattern_matching',
      columnsFound: columns ? true : false,
      availableColumns: columns
    });

  } catch (error) {
    console.error('Simple workflow error:', error);
    res.status(500).json({
      error: 'Failed to generate simple workflow',
      details: error.message
    });
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// DATASET MANAGEMENT ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Get dataset column information
app.get('/api/dataset-columns/:filename', async (req, res) => {
  try {
    const { filename } = req.params;
    
    // Try to get column info from graphing agent
    const response = await axios.get(`http://localhost:8002/dataset_info/${filename}`);
    
    if (response.status === 200) {
      const info = response.data;
      res.json({
        success: true,
        columns: info.columns,
        shape: info.shape,
        filename: filename
      });
    } else {
      throw new Error('Could not get dataset info');
    }
  } catch (error) {
    console.error('Dataset columns error:', error);
    
    // Fallback: return common column names
    res.json({
      success: false,
      columns: {
        all: ['age', 'income', 'education_years', 'satisfaction_score', 'department'],
        numeric: ['age', 'income', 'education_years', 'satisfaction_score'],
        categorical: ['department']
      },
      filename: req.params.filename,
      fallback: true
    });
  }
});

// Route: Handle file uploads and forward to orchestrator
app.post('/api/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' });
    }

    const formData = new FormData();
    formData.append('file', require('fs').createReadStream(req.file.path), {
      filename: req.file.originalname,
      contentType: req.file.mimetype
    });
    formData.append('name', req.body.name || path.parse(req.file.originalname).name);

    const response = await axios.post(`${ORCHESTRATOR_URL}/datasets/upload`, formData, {
      headers: {
        ...formData.getHeaders(),
      },
      maxContentLength: Infinity,
      maxBodyLength: Infinity
    });

    // Clean up uploaded file
    require('fs').unlinkSync(req.file.path);

    res.json(response.data);
  } catch (error) {
    console.error('Upload error:', error);
    
    // Clean up uploaded file on error
    if (req.file) {
      try {
        require('fs').unlinkSync(req.file.path);
      } catch (cleanupError) {
        console.error('Failed to cleanup file:', cleanupError);
      }
    }

    res.status(error.response?.status || 500).json({
      error: error.message,
      details: error.response?.data || null
    });
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// VISUALIZATION ROUTES (ORCHESTRATOR PROXY)
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Serve visualizations via orchestrator proxy
app.get('/api/visualizations/:runId/:filename', async (req, res) => {
    try {
        const { runId, filename } = req.params;
        const { download } = req.query;
        
        console.log(`🔄 Proxying visualization: ${runId}/${filename}${download ? ' (download)' : ''}`);
        
        // Proxy the request to orchestrator
        const response = await axios.get(
            `${ORCHESTRATOR_URL}/artifacts/${runId}/${filename}`,
            { 
                responseType: 'stream',
                timeout: 15000,
                headers: {
                    'Accept': 'application/octet-stream, image/*, */*'
                }
            }
        );
        
        // Set appropriate headers based on request type
        if (download === 'true') {
            res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
            res.setHeader('Content-Type', 'application/octet-stream');
        } else {
            // For viewing, set proper image content type
            const ext = path.extname(filename).toLowerCase();
            const contentTypes = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.pdf': 'application/pdf'
            };
            res.setHeader('Content-Type', contentTypes[ext] || 'application/octet-stream');
        }
        
        // Forward response headers
        if (response.headers['content-length']) {
            res.setHeader('Content-Length', response.headers['content-length']);
        }
        
        // Add caching headers
        res.setHeader('Cache-Control', 'public, max-age=3600');
        res.setHeader('X-Served-By', 'orchestrator-proxy');
        res.setHeader('X-Run-ID', runId);
        
        console.log(`✅ Streaming visualization: ${filename} (${response.headers['content-length'] || 'unknown'} bytes)`);
        
        // Stream the response
        response.data.pipe(res);
        
    } catch (error) {
        console.error(`❌ Failed to proxy visualization ${req.params.filename}:`, error.message);
        
        if (error.response?.status === 404) {
            res.status(404).json({
                error: 'Visualization not found',
                runId: req.params.runId,
                filename: req.params.filename,
                suggestion: 'File may still be generating or workflow may have failed'
            });
        } else if (error.code === 'ECONNREFUSED') {
            res.status(503).json({
                error: 'Orchestrator service unavailable',
                suggestion: 'Check if the orchestrator is running on ' + ORCHESTRATOR_URL
            });
        } else {
            res.status(500).json({
                error: 'Failed to retrieve visualization',
                details: error.message
            });
        }
    }
});

// Route: Get visualization metadata with proper URLs
app.get('/api/visualizations-metadata/:runId', async (req, res) => {
    try {
        const { runId } = req.params;
        
        console.log(`📊 Getting visualization metadata for run: ${runId}`);
        
        // Get artifacts from orchestrator
        const artifactsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${runId}/artifacts`);
        const artifacts = artifactsResponse.data.artifacts || [];
        
        // Transform artifacts to include proper proxy URLs
          const visualizations = await Promise.all(
            artifacts
              .filter(artifact => artifact.type === 'visualization')
              .map(async (artifact) => {
                const safeFilename = path.basename(artifact.filename);
                const fileExtension = path.extname(safeFilename).toLowerCase();
                const isImage = ['.png', '.jpg', '.jpeg', '.svg'].includes(fileExtension);

                return {
                  ...artifact,
                  viewUrl: `/api/visualizations/${runId}/${safeFilename}`,
                  downloadUrl: `/api/visualizations/${runId}/${safeFilename}?download=true`,
                  thumbnailUrl: `/api/visualizations/${runId}/${safeFilename}?thumbnail=true`,
                  isImage,
                  fileExtension,
                  stepDescription: await getStepDescription(artifact.step_number, runId)
                };
              })
          );

        
        console.log(`✅ Found ${visualizations.length} visualizations for run ${runId}`);
        
        res.json({
            runId,
            visualizations,
            count: visualizations.length,
            orchestratorUrl: ORCHESTRATOR_URL
        });
        
    } catch (error) {
        console.error('❌ Error getting visualization metadata:', error);
        res.status(500).json({
            error: 'Failed to get visualization metadata',
            details: error.message,
            runId: req.params.runId
        });
    }
});

// Route: Get base64 visualization via orchestrator
app.get('/api/visualizations-base64/:runId/:filename', async (req, res) => {
    try {
        const { runId, filename } = req.params;
        
        console.log(`📊 Getting base64 for: ${runId}/${filename}`);
        
        // Get file as buffer from orchestrator
        const response = await axios.get(
            `${ORCHESTRATOR_URL}/artifacts/${runId}/${filename}`,
            { responseType: 'arraybuffer', timeout: 10000 }
        );
        
        const base64Data = Buffer.from(response.data).toString('base64');
        const ext = path.extname(filename).toLowerCase();
        
        const mimeTypes = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg', 
            '.jpeg': 'image/jpeg',
            '.svg': 'image/svg+xml'
        };
        
        const mimeType = mimeTypes[ext] || 'image/png';
        
        res.json({
            runId,
            filename,
            mimeType,
            base64Data,
            dataUrl: `data:${mimeType};base64,${base64Data}`,
            size: response.data.length
        });
        
    } catch (error) {
        console.error('❌ Error encoding visualization via proxy:', error);
        res.status(error.response?.status || 500).json({ 
            error: 'Failed to encode visualization',
            details: error.message 
        });
    }
});

// Route: List all visualizations across all runs
app.get('/api/all-visualizations', async (req, res) => {
    try {
        console.log('🔍 Getting all visualizations across runs...');
        
        // Get all runs
        const runsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs`);
        const runs = runsResponse.data.runs || [];
        
        const allVisualizations = [];
        
        // Get artifacts for each run
        for (const run of runs) {
            try {
                const artifactsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${run.run_id}/artifacts`);
                const artifacts = artifactsResponse.data.artifacts || [];
                
                const runVizs = artifacts
                    .filter(artifact => artifact.type === 'visualization')
                    .map(artifact => ({
                        ...artifact,
                        runId: run.run_id,
                        runStatus: run.status,
                        viewUrl: `/api/visualizations/${run.run_id}/${artifact.filename}`,
                        downloadUrl: `/api/visualizations/${run.run_id}/${artifact.filename}?download=true`
                    }));
                
                allVisualizations.push(...runVizs);
            } catch (error) {
                console.log(`⚠️ Could not get artifacts for run ${run.run_id}`);
            }
        }
        
        res.json({
            totalRuns: runs.length,
            totalVisualizations: allVisualizations.length,
            visualizations: allVisualizations,
            orchestratorUrl: ORCHESTRATOR_URL
        });
        
    } catch (error) {
        console.error('❌ Error getting all visualizations:', error);
        res.status(500).json({
            error: 'Failed to get all visualizations',
            details: error.message
        });
    }
});

// ═══════════════════════════════════════════════════════════════════════════════
// WORKFLOW MANAGEMENT ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Get detailed workflow results with step-by-step data
app.get('/api/workflow-results/:runId', async (req, res) => {
  try {
    const { runId } = req.params;
    
    // Get enhanced workflow status with step details
    const statusResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${runId}/status`);
    const status = statusResponse.data;
    
    // Get artifacts
    const artifactsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${runId}/artifacts`);
    const artifacts = artifactsResponse.data;
    
    // Structure the enhanced workflow results
    const workflowResults = {
      runId,
      status: status.status,
      progress: status.progress,
      startTime: status.start_time,
      endTime: status.end_time,
      steps: status.steps || [],
      artifacts: artifacts.artifacts || [],
      error: status.error_message,
      totalSteps: status.total_steps || 0,
      stepSummary: {
        completed: (status.steps || []).filter(s => s.status === 'completed').length,
        failed: (status.steps || []).filter(s => s.status === 'failed').length,
        running: (status.steps || []).filter(s => s.status === 'running').length
      }
    };
    
    res.json(workflowResults);
    
  } catch (error) {
    console.error('Failed to get workflow results:', error);
    res.status(500).json({
      error: 'Failed to get workflow results',
      details: error.message
    });
  }
});

// Route: Get detailed step results
app.get('/api/step-results/:runId/:stepNumber', async (req, res) => {
  try {
    const { runId, stepNumber } = req.params;
    
    // Get specific step details from enhanced orchestrator
    const stepResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${runId}/steps/${stepNumber}`);
    const stepData = stepResponse.data;
    
    res.json({
      runId,
      stepNumber: parseInt(stepNumber),
      stepData
    });
    
  } catch (error) {
    console.error('Failed to get step results:', error);
    res.status(error.response?.status || 500).json({
      error: 'Failed to get step results',
      details: error.message
    });
  }
});

// Route: Get all steps for a workflow
app.get('/api/workflow-steps/:runId', async (req, res) => {
  try {
    const { runId } = req.params;
    
    const stepsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${runId}/steps`);
    const stepsData = stepsResponse.data;
    
    res.json(stepsData);
    
  } catch (error) {
    console.error('Failed to get workflow steps:', error);
    res.status(error.response?.status || 500).json({
      error: 'Failed to get workflow steps',
      details: error.message
    });
  }
});

// Route: Get workflow analytics
app.get('/api/analytics', async (req, res) => {
  try {
    const analyticsResponse = await axios.get(`${ORCHESTRATOR_URL}/analytics`);
    res.json(analyticsResponse.data);
  } catch (error) {
    console.error('Failed to get analytics:', error);
    res.status(500).json({
      error: 'Failed to get analytics',
      details: error.message
    });
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// ORCHESTRATOR PROXY ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Proxy orchestrator requests to avoid CORS
app.use('/api/orchestrator', async (req, res) => {
  try {
    const targetUrl = `${ORCHESTRATOR_URL}${req.path}`;
    const config = {
      method: req.method,
      url: targetUrl,
      headers: {
        'Content-Type': req.headers['content-type'] || 'application/json',
      },
      data: req.body,
      params: req.query
    };

    const response = await axios(config);
    res.status(response.status).json(response.data);
  } catch (error) {
    console.error('Orchestrator proxy error:', error);
    res.status(error.response?.status || 500).json({
      error: error.message,
      details: error.response?.data || null
    });
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// SYSTEM & HEALTH ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Test orchestrator connectivity
app.get('/api/test-orchestrator', async (req, res) => {
    try {
        const healthResponse = await axios.get(`${ORCHESTRATOR_URL}/health`, { timeout: 5000 });
        
        res.json({
            status: 'connected',
            orchestratorUrl: ORCHESTRATOR_URL,
            orchestratorHealth: healthResponse.data,
            proxyMode: 'enabled'
        });
        
    } catch (error) {
        res.status(503).json({
            status: 'disconnected',
            orchestratorUrl: ORCHESTRATOR_URL,
            error: error.message,
            suggestion: 'Check if orchestrator is running and accessible'
        });
    }
});

// Route: Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'Frontend Backend API',
    visualizationMode: 'orchestrator-proxy'
  });
});

// Route: Get system status
app.get('/api/status', async (req, res) => {
  try {
    const orchestratorHealth = await axios.get(`${ORCHESTRATOR_URL}/health`, { timeout: 5000 });
    
    res.json({
      backend: 'healthy',
      orchestrator: orchestratorHealth.data,
      timestamp: new Date().toISOString(),
      visualizationMode: 'orchestrator-proxy'
    });
  } catch (error) {
    res.status(200).json({
      backend: 'healthy',
      orchestrator: 'unavailable',
      error: error.message,
      timestamp: new Date().toISOString(),
      visualizationMode: 'orchestrator-proxy'
    });
  }
});

// Route: Serve example queries
app.get('/api/examples', (req, res) => {
  res.json({
    examples: [
      {
        category: "Data Exploration",
        queries: [
          "Analyze the employee dataset and show me key statistics",
          "What's the data quality like in my sales data?",
          "Profile the customer dataset and check for missing values",
          "Show me correlations between all numeric variables"
        ]
      },
      {
        category: "Visualizations",
        queries: [
          "Create a histogram of age distribution",
          "Plot income vs education level colored by department",
          "Show me a correlation heatmap of all variables",
          "Create box plots of salary by department",
          "Generate a dashboard with age, income, and satisfaction distributions"
        ]
      },
      {
        category: "Advanced Analysis",
        queries: [
          "Perform complete data analysis with quality assessment and visualizations",
          "Create time series plots of sales data over months",
          "Show distribution plots for all numeric columns",
          "Generate multi-plot dashboard comparing departments",
          "Analyze customer satisfaction scores and create relevant visualizations"
        ]
      }
    ]
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DEBUG & DEVELOPMENT ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

// Route: Debug orchestrator connectivity and artifact availability
app.get('/api/debug/orchestrator', async (req, res) => {
  try {
    const result = {
      orchestratorUrl: ORCHESTRATOR_URL,
      connectivity: 'checking...',
      health: null,
      runs: null,
      artifacts: null
    };
    
    // Test basic connectivity
    try {
      const healthResponse = await axios.get(`${ORCHESTRATOR_URL}/health`, { timeout: 5000 });
      result.connectivity = 'connected';
      result.health = healthResponse.data;
    } catch (error) {
      result.connectivity = 'failed';
      result.healthError = error.message;
    }
    
    // Get runs information
    try {
      const runsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs`, { timeout: 5000 });
      result.runs = {
        total: runsResponse.data.runs?.length || 0,
        statuses: runsResponse.data.runs?.reduce((acc, run) => {
          acc[run.status] = (acc[run.status] || 0) + 1;
          return acc;
        }, {}) || {}
      };
    } catch (error) {
      result.runsError = error.message;
    }
    
    // Test artifact access for latest runs
    try {
      const runsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs`, { timeout: 5000 });
      const runs = runsResponse.data.runs || [];
      const completedRuns = runs.filter(run => run.status === 'COMPLETED').slice(0, 3);
      
      result.artifacts = {
        testedRuns: completedRuns.length,
        artifactTests: []
      };
      
      for (const run of completedRuns) {
        try {
          const artifactsResponse = await axios.get(`${ORCHESTRATOR_URL}/runs/${run.run_id}/artifacts`);
          const artifacts = artifactsResponse.data.artifacts || [];
          const visualizations = artifacts.filter(a => a.type === 'visualization');
          
          result.artifacts.artifactTests.push({
            runId: run.run_id,
            totalArtifacts: artifacts.length,
            visualizations: visualizations.length,
            artifactFiles: visualizations.map(v => v.filename)
          });
        } catch (error) {
          result.artifacts.artifactTests.push({
            runId: run.run_id,
            error: error.message
          });
        }
      }
    } catch (error) {
      result.artifactsError = error.message;
    }
    
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Route: Debug specific visualization access
app.get('/api/debug/visualization/:runId/:filename', async (req, res) => {
  try {
    const { runId, filename } = req.params;
    
    const result = {
      runId,
      filename,
      orchestratorUrl: `${ORCHESTRATOR_URL}/artifacts/${runId}/${filename}`,
      tests: []
    };
    
    // Test direct orchestrator access
    try {
      const response = await axios.head(`${ORCHESTRATOR_URL}/artifacts/${runId}/${filename}`, { timeout: 5000 });
      result.tests.push({
        test: 'orchestrator_head_request',
        status: 'success',
        headers: response.headers
      });
    } catch (error) {
      result.tests.push({
        test: 'orchestrator_head_request',
        status: 'failed',
        error: error.message,
        statusCode: error.response?.status
      });
    }
    
    // Test our proxy
    try {
      const response = await axios.head(`http://localhost:${PORT}/api/visualizations/${runId}/${filename}`, { timeout: 5000 });
      result.tests.push({
        test: 'proxy_head_request',
        status: 'success',
        headers: response.headers
      });
    } catch (error) {
      result.tests.push({
        test: 'proxy_head_request',
        status: 'failed',
        error: error.message,
        statusCode: error.response?.status
      });
    }
    
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Route: Debug endpoint for legacy file checking (for comparison)
app.get('/api/debug/files', (req, res) => {
  try {
    const searchPaths = [
      path.join(process.cwd(), 'shared_artifacts'),
      process.cwd(),
      path.join(process.cwd(), 'artifacts'),
      __dirname,
      path.join(__dirname, '..', '..', 'agents'),
      path.join(__dirname, '..'),
    ];
    
    const result = {
      currentWorkingDirectory: process.cwd(),
      backendDirectory: __dirname,
      note: 'This endpoint shows local file locations for debugging. With orchestrator proxy, these files are not needed.',
      searchPaths,
      foundFiles: {}
    };
    
    // Check each path for visualization files
    searchPaths.forEach((searchPath, index) => {
      try {
        if (require('fs').existsSync(searchPath)) {
          const files = require('fs').readdirSync(searchPath)
            .filter(file => /\.(png|jpg|jpeg|svg|pdf)$/i.test(file))
            .map(file => {
              const filePath = path.join(searchPath, file);
              const stats = require('fs').statSync(filePath);
              return {
                name: file,
                size: stats.size,
                isEmpty: stats.size === 0,
                modified: stats.mtime
              };
            });
          
          result.foundFiles[`path_${index}_${path.basename(searchPath) || 'root'}`] = {
            path: searchPath,
            exists: true,
            files: files,
            totalFiles: files.length,
            emptyFiles: files.filter(f => f.isEmpty).length
          };
        } else {
          result.foundFiles[`path_${index}_${path.basename(searchPath) || 'root'}`] = {
            path: searchPath,
            exists: false,
            files: []
          };
        }
      } catch (error) {
        result.foundFiles[`path_${index}_error`] = {
          path: searchPath,
          error: error.message
        };
      }
    });
    
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// ERROR HANDLING MIDDLEWARE
// ═══════════════════════════════════════════════════════════════════════════════

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Unhandled error:', error);
  res.status(500).json({
    error: 'Internal server error',
    message: error.message,
    timestamp: new Date().toISOString()
  });
});

// Handle 404 routes
app.use((req, res) => {
  res.status(404).json({
    error: 'Route not found',
    path: req.path,
    method: req.method,
    suggestion: 'Check the API documentation at /api/health',
    availableEndpoints: [
      'GET /api/health',
      'GET /api/status', 
      'GET /api/test-orchestrator',
      'POST /api/upload',
      'POST /api/parse-input',
      'GET /api/visualizations/:runId/:filename',
      'GET /api/workflow-results/:runId'
    ]
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// SERVER STARTUP
// ═══════════════════════════════════════════════════════════════════════════════

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Frontend Backend API running on port ${PORT}`);
  console.log(`📊 Proxying to orchestrator at: ${ORCHESTRATOR_URL}`);
  console.log(`🔗 Frontend should connect to: http://localhost:${PORT}`);
  console.log(`🖼️  Visualization mode: orchestrator-proxy`);
  console.log(`🔍 Debug endpoints available:`);
  console.log(`   - Health: http://localhost:${PORT}/api/health`);
  console.log(`   - Status: http://localhost:${PORT}/api/status`);
  console.log(`   - Test Orchestrator: http://localhost:${PORT}/api/test-orchestrator`);
  console.log(`   - Debug Orchestrator: http://localhost:${PORT}/api/debug/orchestrator`);
  console.log(`   - Examples: http://localhost:${PORT}/api/examples`);
  console.log(`   - All Visualizations: http://localhost:${PORT}/api/all-visualizations`);
  console.log(`✨ Ready to handle AI-powered data analysis workflows!`);
});

module.exports = app;