#!/usr/bin/env python3
"""
Enhanced Graphing Agent Service

Specialized agent for creating various types of visualizations:
- Statistical plots (histograms, box plots, scatter plots)
- Correlation heatmaps
- Distribution plots
- Time series plots
- Custom visualizations

Enhanced to work with master orchestrator file uploads
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Union
import uvicorn
import pandas as pd
import numpy as np
import json
import os
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
from plotly.subplots import make_subplots
from pathlib import Path
import base64
from io import BytesIO
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set style preferences
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

# Initialize FastAPI app
app = FastAPI(
    title="Enhanced Graphing Agent Service",
    description="Specialized visualization agent with upload integration",
    version="1.1.0",
    docs_url="/docs"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MASTER_ORCHESTRATOR_URL = "http://localhost:8000"
UPLOAD_DIRECTORIES = [
    "uploads",           # Master orchestrator uploads
    ".",                # Current directory
    "data",             # Common data directory
    "datasets",         # Alternative datasets directory
    "shared_artifacts"  # Shared artifacts from orchestrator
]

# ─── ENHANCED DATA MODELS ─────────────────────────────────────────────────────

class PlotRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None  # New: Use dataset ID from orchestrator
    plot_type: str
    columns: List[str]
    title: Optional[str] = None
    save_path: Optional[str] = None
    width: Optional[int] = 800
    height: Optional[int] = 600
    color_palette: Optional[str] = "viridis"

class HistogramRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    column: str
    bins: Optional[int] = 30
    title: Optional[str] = None
    save_path: Optional[str] = None

class ScatterPlotRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    x_column: str
    y_column: str
    color_column: Optional[str] = None
    size_column: Optional[str] = None
    title: Optional[str] = None
    save_path: Optional[str] = None

class CorrelationHeatmapRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    columns: Optional[List[str]] = None
    method: Optional[str] = "pearson"
    title: Optional[str] = None
    save_path: Optional[str] = None

class BoxPlotRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    columns: List[str]
    groupby_column: Optional[str] = None
    title: Optional[str] = None
    save_path: Optional[str] = None

class TimeSeriesRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    date_column: str
    value_columns: List[str]
    title: Optional[str] = None
    save_path: Optional[str] = None

class MultiPlotRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    plots: List[Dict[str, Any]]
    layout: Optional[str] = "grid"  # grid, horizontal, vertical
    title: Optional[str] = None
    save_path: Optional[str] = None

# ─── ENHANCED HELPER FUNCTIONS ────────────────────────────────────────────────

def resolve_file_path(file_path: str = None, dataset_id: str = None) -> str:
    """
    Resolve file path from either direct path or dataset ID.
    Enhanced to work with master orchestrator uploads.
    """
    resolved_path = None
    
    # Option 1: Try to get file path from dataset_id via orchestrator
    if dataset_id:
        try:
            response = requests.get(f"{MASTER_ORCHESTRATOR_URL}/datasets", timeout=10)
            if response.status_code == 200:
                datasets = response.json().get("datasets", [])
                for dataset in datasets:
                    if dataset.get("id") == dataset_id:
                        resolved_path = dataset.get("file_path")
                        logger.info(f"Resolved dataset_id {dataset_id} to path: {resolved_path}")
                        break
                        
                if not resolved_path:
                    logger.warning(f"Dataset ID {dataset_id} not found in orchestrator")
        except Exception as e:
            logger.warning(f"Could not fetch datasets from orchestrator: {e}")
    
    # Option 2: Use provided file_path
    if not resolved_path and file_path:
        resolved_path = file_path
    
    # Option 3: If no path resolved, raise error
    if not resolved_path:
        raise HTTPException(
            status_code=400, 
            detail="Must provide either 'file_path' or 'dataset_id'"
        )
    
    return resolved_path

def find_file_in_directories(filename: str) -> str:
    """
    Search for a file in multiple possible directories.
    """
    # If filename is already a full/relative path that exists, use it
    if os.path.exists(filename):
        return filename
    
    # Extract just the filename if a path was provided
    base_filename = os.path.basename(filename)
    
    # Search in predefined directories
    for directory in UPLOAD_DIRECTORIES:
        possible_path = os.path.join(directory, base_filename)
        if os.path.exists(possible_path):
            logger.info(f"Found file: {possible_path}")
            return possible_path
        
        # Also try the original filename in each directory
        possible_path = os.path.join(directory, filename)
        if os.path.exists(possible_path):
            logger.info(f"Found file: {possible_path}")
            return possible_path
    
    # If not found, list available files for debugging
    logger.error(f"File not found: {filename}")
    logger.info("Available files in search directories:")
    for directory in UPLOAD_DIRECTORIES:
        if os.path.exists(directory):
            files = [f for f in os.listdir(directory) if f.endswith(('.csv', '.xlsx', '.json', '.parquet'))]
            logger.info(f"  {directory}/: {files}")
    
    raise FileNotFoundError(f"File not found: {filename}")

def load_dataset(file_path: str = None, dataset_id: str = None) -> pd.DataFrame:
    """Enhanced dataset loader that works with orchestrator uploads."""
    try:
        # Resolve the actual file path
        resolved_path = resolve_file_path(file_path, dataset_id)
        
        # Find the file in possible directories
        actual_path = find_file_in_directories(resolved_path)
        
        # Determine file type and load accordingly
        file_ext = Path(actual_path).suffix.lower()
        
        logger.info(f"Loading dataset from: {actual_path}")
        
        if file_ext == '.csv':
            # Try different encodings and separators for robustness
            try:
                df = pd.read_csv(actual_path)
            except UnicodeDecodeError:
                df = pd.read_csv(actual_path, encoding='latin1')
            except pd.errors.ParserError:
                df = pd.read_csv(actual_path, sep=';')  # Try semicolon separator
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(actual_path)
        elif file_ext == '.json':
            df = pd.read_json(actual_path)
        elif file_ext == '.parquet':
            df = pd.read_parquet(actual_path)
        else:
            # Try CSV as default with robust loading
            try:
                df = pd.read_csv(actual_path)
            except:
                df = pd.read_csv(actual_path, encoding='latin1')
        
        logger.info(f"Successfully loaded dataset: {actual_path} - Shape: {df.shape}")
        return df
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to load dataset: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to load dataset: {str(e)}")

def save_figure(fig, save_path: str, plot_type: str) -> str:
    """Save figure and return the file path."""
    if save_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = f"{plot_type}_{timestamp}.png"
    
    try:
        if hasattr(fig, 'write_image'):  # Plotly figure
            fig.write_image(save_path, width=800, height=600)
        else:  # Matplotlib/Seaborn figure
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
        
        logger.info(f"Plot saved: {save_path}")
        return save_path
        
    except Exception as e:
        logger.error(f"Failed to save plot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save plot: {str(e)}")

def validate_columns(df: pd.DataFrame, columns: List[str]) -> None:
    """Validate that columns exist in the dataframe."""
    missing_cols = [col for col in columns if col not in df.columns]
    if missing_cols:
        raise HTTPException(
            status_code=400, 
            detail=f"Columns not found in dataset: {missing_cols}"
        )

def get_color_palette(palette_name: str, n_colors: int = 10) -> List[str]:
    """Get color palette for plots."""
    try:
        if palette_name in ['viridis', 'plasma', 'inferno', 'magma']:
            return px.colors.sequential.__dict__[palette_name.capitalize()]
        elif palette_name in ['Set1', 'Set2', 'Set3', 'Pastel1', 'Pastel2']:
            return px.colors.qualitative.__dict__[palette_name]
        else:
            return px.colors.qualitative.Plotly
    except:
        return px.colors.qualitative.Plotly

# ─── ENHANCED API ENDPOINTS ───────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Enhanced Graphing Agent",
        "version": "1.1.0",
        "status": "operational",
        "capabilities": [
            "histogram",
            "scatter_plot",
            "correlation_heatmap",
            "box_plot",
            "time_series",
            "distribution_plot",
            "multi_plot",
            "custom_plot"
        ],
        "enhancements": [
            "orchestrator_integration",
            "dataset_id_support",
            "multi_directory_search",
            "robust_file_loading"
        ],
        "upload_directories": UPLOAD_DIRECTORIES
    }

@app.get("/health")
async def health_check():
    """Enhanced health check endpoint."""
    # Check orchestrator connectivity
    orchestrator_status = "unknown"
    try:
        response = requests.get(f"{MASTER_ORCHESTRATOR_URL}/health", timeout=5)
        orchestrator_status = "connected" if response.status_code == 200 else "disconnected"
    except:
        orchestrator_status = "unreachable"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Enhanced Graphing Agent",
        "orchestrator_connection": orchestrator_status,
        "upload_directories": {
            dir_name: os.path.exists(dir_name) for dir_name in UPLOAD_DIRECTORIES
        }
    }

@app.get("/files")
async def list_available_files():
    """List all available data files in search directories."""
    available_files = {}
    
    for directory in UPLOAD_DIRECTORIES:
        if os.path.exists(directory):
            files = []
            for file in os.listdir(directory):
                if file.endswith(('.csv', '.xlsx', '.xls', '.json', '.parquet')):
                    file_path = os.path.join(directory, file)
                    file_info = {
                        "filename": file,
                        "path": file_path,
                        "size_mb": round(os.path.getsize(file_path) / 1024 / 1024, 2),
                        "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                    }
                    files.append(file_info)
            available_files[directory] = files
        else:
            available_files[directory] = "Directory not found"
    
    return {
        "available_files": available_files,
        "total_files": sum(len(files) if isinstance(files, list) else 0 for files in available_files.values())
    }

@app.post("/histogram")
async def create_histogram(request: HistogramRequest):
    """Create histogram for a numeric column - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating histogram for column: {request.column}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        validate_columns(df, [request.column])
        
        # Check if column is numeric
        if not pd.api.types.is_numeric_dtype(df[request.column]):
            raise HTTPException(status_code=400, detail=f"Column {request.column} is not numeric")
        
        # Create plotly histogram
        fig = px.histogram(
            df, 
            x=request.column,
            nbins=request.bins,
            title=request.title or f"Distribution of {request.column}",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        
        fig.update_layout(
            xaxis_title=request.column,
            yaxis_title="Frequency",
            showlegend=False
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "histogram")
        
        # Calculate statistics
        stats = {
            "mean": float(df[request.column].mean()),
            "median": float(df[request.column].median()),
            "std": float(df[request.column].std()),
            "min": float(df[request.column].min()),
            "max": float(df[request.column].max())
        }
        
        result = {
            "plot_type": "histogram",
            "column": request.column,
            "file_path": save_path,
            "statistics": stats,
            "bins": request.bins,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Histogram created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Histogram creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Histogram creation failed: {str(e)}")

@app.post("/scatter_plot")
async def create_scatter_plot(request: ScatterPlotRequest):
    """Create scatter plot between two numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating scatter plot: {request.x_column} vs {request.y_column}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        columns_to_validate = [request.x_column, request.y_column]
        
        if request.color_column:
            columns_to_validate.append(request.color_column)
        if request.size_column:
            columns_to_validate.append(request.size_column)
            
        validate_columns(df, columns_to_validate)
        
        # Create plotly scatter plot
        fig = px.scatter(
            df,
            x=request.x_column,
            y=request.y_column,
            color=request.color_column,
            size=request.size_column,
            title=request.title or f"{request.x_column} vs {request.y_column}",
            color_continuous_scale="viridis"
        )
        
        fig.update_layout(
            xaxis_title=request.x_column,
            yaxis_title=request.y_column
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "scatter_plot")
        
        # Calculate correlation if both columns are numeric
        correlation = None
        if (pd.api.types.is_numeric_dtype(df[request.x_column]) and 
            pd.api.types.is_numeric_dtype(df[request.y_column])):
            correlation = float(df[request.x_column].corr(df[request.y_column]))
        
        result = {
            "plot_type": "scatter_plot",
            "x_column": request.x_column,
            "y_column": request.y_column,
            "color_column": request.color_column,
            "size_column": request.size_column,
            "file_path": save_path,
            "correlation": correlation,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Scatter plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Scatter plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scatter plot creation failed: {str(e)}")

@app.post("/correlation_heatmap")
async def create_correlation_heatmap(request: CorrelationHeatmapRequest):
    """Create correlation heatmap for numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating correlation heatmap")
        
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Select columns
        if request.columns:
            validate_columns(df, request.columns)
            df = df[request.columns]
        
        # Select only numeric columns
        numeric_df = df.select_dtypes(include=[np.number])
        
        if numeric_df.shape[1] < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 numeric columns for correlation heatmap")
        
        # Calculate correlation matrix
        corr_matrix = numeric_df.corr(method=request.method)
        
        # Create plotly heatmap
        fig = px.imshow(
            corr_matrix,
            color_continuous_scale="RdBu_r",
            aspect="auto",
            title=request.title or f"Correlation Heatmap ({request.method.capitalize()})"
        )
        
        fig.update_layout(
            xaxis_title="Variables",
            yaxis_title="Variables"
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "correlation_heatmap")
        
        # Find strongest correlations
        corr_pairs = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                corr_value = corr_matrix.iloc[i, j]
                if not np.isnan(corr_value):
                    corr_pairs.append({
                        "variable1": corr_matrix.columns[i],
                        "variable2": corr_matrix.columns[j],
                        "correlation": float(corr_value)
                    })
        
        # Sort by absolute correlation
        corr_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        
        result = {
            "plot_type": "correlation_heatmap",
            "method": request.method,
            "file_path": save_path,
            "variables": numeric_df.columns.tolist(),
            "strongest_correlations": corr_pairs[:10],  # Top 10
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Correlation heatmap created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Correlation heatmap creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Correlation heatmap creation failed: {str(e)}")

@app.post("/box_plot")
async def create_box_plot(request: BoxPlotRequest):
    """Create box plot for numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating box plot for columns: {request.columns}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        columns_to_validate = request.columns.copy()
        
        if request.groupby_column:
            columns_to_validate.append(request.groupby_column)
            
        validate_columns(df, columns_to_validate)
        
        # Check if columns are numeric
        numeric_cols = [col for col in request.columns if pd.api.types.is_numeric_dtype(df[col])]
        if not numeric_cols:
            raise HTTPException(status_code=400, detail="No numeric columns found for box plot")
        
        if request.groupby_column:
            # Create grouped box plot
            fig = go.Figure()
            
            for group in df[request.groupby_column].unique():
                group_data = df[df[request.groupby_column] == group]
                for col in numeric_cols:
                    fig.add_trace(go.Box(
                        y=group_data[col],
                        name=f"{col} - {group}",
                        boxpoints='outliers'
                    ))
        else:
            # Create simple box plot
            fig = go.Figure()
            for col in numeric_cols:
                fig.add_trace(go.Box(
                    y=df[col],
                    name=col,
                    boxpoints='outliers'
                ))
        
        fig.update_layout(
            title=request.title or f"Box Plot: {', '.join(numeric_cols)}",
            yaxis_title="Values"
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "box_plot")
        
        # Calculate summary statistics
        summary_stats = {}
        for col in numeric_cols:
            summary_stats[col] = {
                "median": float(df[col].median()),
                "q1": float(df[col].quantile(0.25)),
                "q3": float(df[col].quantile(0.75)),
                "iqr": float(df[col].quantile(0.75) - df[col].quantile(0.25)),
                "outliers_count": int(len(df[col][(df[col] < df[col].quantile(0.25) - 1.5 * (df[col].quantile(0.75) - df[col].quantile(0.25))) | 
                                                   (df[col] > df[col].quantile(0.75) + 1.5 * (df[col].quantile(0.75) - df[col].quantile(0.25)))]))
            }
        
        result = {
            "plot_type": "box_plot",
            "columns": numeric_cols,
            "groupby_column": request.groupby_column,
            "file_path": save_path,
            "summary_statistics": summary_stats,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Box plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Box plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Box plot creation failed: {str(e)}")

@app.post("/time_series")
async def create_time_series_plot(request: TimeSeriesRequest):
    """Create time series plot - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating time series plot for: {request.value_columns}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        columns_to_validate = [request.date_column] + request.value_columns
        validate_columns(df, columns_to_validate)
        
        # Convert date column to datetime
        try:
            df[request.date_column] = pd.to_datetime(df[request.date_column])
        except:
            raise HTTPException(status_code=400, detail=f"Cannot convert {request.date_column} to datetime")
        
        # Sort by date
        df = df.sort_values(request.date_column)
        
        # Create time series plot
        fig = go.Figure()
        
        for col in request.value_columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                fig.add_trace(go.Scatter(
                    x=df[request.date_column],
                    y=df[col],
                    mode='lines+markers',
                    name=col,
                    line=dict(width=2)
                ))
        
        fig.update_layout(
            title=request.title or f"Time Series: {', '.join(request.value_columns)}",
            xaxis_title=request.date_column,
            yaxis_title="Values",
            hovermode='x unified'
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "time_series")
        
        # Calculate time series statistics
        time_stats = {
            "time_range": {
                "start": df[request.date_column].min().isoformat(),
                "end": df[request.date_column].max().isoformat(),
                "duration_days": int((df[request.date_column].max() - df[request.date_column].min()).days)
            },
            "data_points": len(df),
            "variables": request.value_columns
        }
        
        result = {
            "plot_type": "time_series",
            "date_column": request.date_column,
            "value_columns": request.value_columns,
            "file_path": save_path,
            "time_statistics": time_stats,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Time series plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Time series plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Time series plot creation failed: {str(e)}")

@app.post("/distribution_plot")
async def create_distribution_plot(request: PlotRequest):
    """Create distribution plots (histogram + KDE) for numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating distribution plot for columns: {request.columns}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        validate_columns(df, request.columns)
        
        # Filter numeric columns
        numeric_cols = [col for col in request.columns if pd.api.types.is_numeric_dtype(df[col])]
        if not numeric_cols:
            raise HTTPException(status_code=400, detail="No numeric columns found for distribution plot")
        
        # Create subplots
        n_cols = min(3, len(numeric_cols))
        n_rows = (len(numeric_cols) + n_cols - 1) // n_cols
        
        fig = make_subplots(
            rows=n_rows, 
            cols=n_cols,
            subplot_titles=numeric_cols,
            vertical_spacing=0.08
        )
        
        colors = get_color_palette(request.color_palette, len(numeric_cols))
        
        for i, col in enumerate(numeric_cols):
            row = i // n_cols + 1
            col_pos = i % n_cols + 1
            
            # Add histogram
            fig.add_trace(
                go.Histogram(
                    x=df[col],
                    name=f"{col} (hist)",
                    nbinsx=30,
                    opacity=0.7,
                    marker_color=colors[i % len(colors)]
                ),
                row=row, col=col_pos
            )
        
        fig.update_layout(
            title=request.title or "Distribution Plots",
            showlegend=False,
            height=request.height or (400 * n_rows),
            width=request.width or 1200
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "distribution_plot")
        
        # Calculate distribution statistics
        dist_stats = {}
        for col in numeric_cols:
            col_data = df[col].dropna()
            dist_stats[col] = {
                "mean": float(col_data.mean()),
                "median": float(col_data.median()),
                "std": float(col_data.std()),
                "skewness": float(col_data.skew()),
                "kurtosis": float(col_data.kurtosis()),
                "range": float(col_data.max() - col_data.min())
            }
        
        result = {
            "plot_type": "distribution_plot",
            "columns": numeric_cols,
            "file_path": save_path,
            "distribution_statistics": dist_stats,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Distribution plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Distribution plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Distribution plot creation failed: {str(e)}")

@app.post("/multi_plot")
async def create_multi_plot(request: MultiPlotRequest):
    """Create multiple plots in a single figure - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating multi-plot with {len(request.plots)} plots")
        
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Determine layout
        n_plots = len(request.plots)
        if request.layout == "horizontal":
            rows, cols = 1, n_plots
        elif request.layout == "vertical":
            rows, cols = n_plots, 1
        else:  # grid
            cols = min(3, n_plots)
            rows = (n_plots + cols - 1) // cols
        
        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[plot.get("title", f"Plot {i+1}") for i, plot in enumerate(request.plots)],
            vertical_spacing=0.08,
            horizontal_spacing=0.05
        )
        
        # List to store visualization files if multiple files are created
        visualization_files = []
        
        for i, plot_config in enumerate(request.plots):
            row = i // cols + 1
            col = i % cols + 1
            
            plot_type = plot_config.get("type", "scatter")
            
            if plot_type == "scatter":
                x_col = plot_config["x_column"]
                y_col = plot_config["y_column"]
                validate_columns(df, [x_col, y_col])
                
                fig.add_trace(
                    go.Scatter(
                        x=df[x_col],
                        y=df[y_col],
                        mode='markers',
                        name=f"{x_col} vs {y_col}",
                        showlegend=False
                    ),
                    row=row, col=col
                )
                
            elif plot_type == "histogram":
                column = plot_config["column"]
                validate_columns(df, [column])
                
                fig.add_trace(
                    go.Histogram(
                        x=df[column],
                        name=column,
                        showlegend=False
                    ),
                    row=row, col=col
                )
                
            elif plot_type == "box":
                column = plot_config["column"]
                validate_columns(df, [column])
                
                fig.add_trace(
                    go.Box(
                        y=df[column],
                        name=column,
                        showlegend=False
                    ),
                    row=row, col=col
                )
        
        fig.update_layout(
            title=request.title or "Multi-Plot Dashboard",
            height=400 * rows,
            width=400 * cols
        )
        
        # Save figure
        save_path = save_figure(fig, request.save_path, "multi_plot")
        visualization_files.append(save_path)
        
        result = {
            "plot_type": "multi_plot",
            "layout": request.layout,
            "number_of_plots": n_plots,
            "file_path": save_path,
            "visualization_files": visualization_files,  # For orchestrator compatibility
            "plots_config": request.plots,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Multi-plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Multi-plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Multi-plot creation failed: {str(e)}")

@app.post("/custom_plot")
async def create_custom_plot(request: PlotRequest):
    """Create custom visualization based on plot_type parameter - enhanced for orchestrator integration."""
    try:
        logger.info(f"Creating custom plot: {request.plot_type}")
        
        df = load_dataset(request.file_path, request.dataset_id)
        validate_columns(df, request.columns)
        
        if request.plot_type == "pair_plot":
            # Create pair plot for multiple numeric columns
            numeric_cols = [col for col in request.columns if pd.api.types.is_numeric_dtype(df[col])]
            if len(numeric_cols) < 2:
                raise HTTPException(status_code=400, detail="Need at least 2 numeric columns for pair plot")
            
            # Create scatter matrix
            fig = px.scatter_matrix(
                df[numeric_cols],
                title=request.title or "Pair Plot",
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            
        elif request.plot_type == "violin_plot":
            # Create violin plot
            fig = go.Figure()
            for col in request.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    fig.add_trace(go.Violin(
                        y=df[col],
                        name=col,
                        box_visible=True,
                        meanline_visible=True
                    ))
            
            fig.update_layout(title=request.title or "Violin Plot")
            
        elif request.plot_type == "density_plot":
            # Create density plot
            fig = go.Figure()
            for col in request.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    hist, bin_edges = np.histogram(df[col].dropna(), bins=50, density=True)
                    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                    
                    fig.add_trace(go.Scatter(
                        x=bin_centers,
                        y=hist,
                        mode='lines',
                        name=col,
                        fill='tonexty' if col != request.columns[0] else 'tozeroy'
                    ))
            
            fig.update_layout(
                title=request.title or "Density Plot",
                xaxis_title="Value",
                yaxis_title="Density"
            )
            
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported custom plot type: {request.plot_type}")
        
        # Save figure
        save_path = save_figure(fig, request.save_path, f"custom_{request.plot_type}")
        
        result = {
            "plot_type": f"custom_{request.plot_type}",
            "columns": request.columns,
            "file_path": save_path,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info(f"Custom plot created successfully: {save_path}")
        return result
        
    except Exception as e:
        logger.error(f"Custom plot creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Custom plot creation failed: {str(e)}")

# ─── UTILITY ENDPOINTS ────────────────────────────────────────────────────────

@app.get("/plot_types")
async def get_available_plot_types():
    """Get list of available plot types and their requirements."""
    return {
        "plot_types": {
            "histogram": {
                "description": "Distribution of a single numeric variable",
                "required_columns": 1,
                "column_types": ["numeric"]
            },
            "scatter_plot": {
                "description": "Relationship between two numeric variables",
                "required_columns": 2,
                "column_types": ["numeric", "numeric"],
                "optional": ["color", "size"]
            },
            "correlation_heatmap": {
                "description": "Correlation matrix of numeric variables",
                "required_columns": "2+",
                "column_types": ["numeric"]
            },
            "box_plot": {
                "description": "Distribution summary with quartiles",
                "required_columns": "1+",
                "column_types": ["numeric"],
                "optional": ["groupby"]
            },
            "time_series": {
                "description": "Time-based data visualization",
                "required_columns": "2+",
                "column_types": ["datetime", "numeric"]
            },
            "distribution_plot": {
                "description": "Histogram with kernel density estimation",
                "required_columns": "1+",
                "column_types": ["numeric"]
            },
            "custom_plot": {
                "description": "Custom visualizations (pair_plot, violin_plot, density_plot)",
                "required_columns": "varies",
                "column_types": ["varies"]
            }
        }
    }

@app.post("/dataset_info")
async def get_dataset_info(request: dict):
    """Get basic information about a dataset for plotting - enhanced for orchestrator integration."""
    try:
        file_path = request.get("file_path")
        dataset_id = request.get("dataset_id")
        
        df = load_dataset(file_path, dataset_id)
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        datetime_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
        
        return {
            "shape": {"rows": df.shape[0], "columns": df.shape[1]},
            "columns": {
                "all": df.columns.tolist(),
                "numeric": numeric_cols,
                "categorical": categorical_cols,
                "datetime": datetime_cols
            },
            "missing_values": df.isnull().sum().to_dict(),
            "data_types": df.dtypes.astype(str).to_dict(),
            "sample_data": df.head().to_dict(),
            "plot_suggestions": {
                "scatter_plot": {
                    "x_options": numeric_cols,
                    "y_options": numeric_cols,
                    "color_options": categorical_cols + numeric_cols
                } if len(numeric_cols) >= 2 else "Need at least 2 numeric columns",
                "histogram": numeric_cols if numeric_cols else "No numeric columns available",
                "box_plot": numeric_cols if numeric_cols else "No numeric columns available"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze dataset: {str(e)}")

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "graphing_agent:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )