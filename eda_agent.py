# #!/usr/bin/env python3
# """
# EDA Agent Service

# Performs exploratory data analysis tasks including:
# - Dataset profiling
# - Statistical summaries
# - Data quality assessment
# - Basic visualizations
# """

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# from typing import Dict, Any, List, Optional
# import uvicorn
# import pandas as pd
# import numpy as np
# import json
# import os
# import logging
# from datetime import datetime
# import seaborn as sns
# import matplotlib.pyplot as plt
# from pathlib import Path

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # Initialize FastAPI app
# app = FastAPI(
#     title="EDA Agent Service",
#     description="Exploratory Data Analysis Agent",
#     version="1.0.0",
#     docs_url="/docs"
# )

# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ─── DATA MODELS ──────────────────────────────────────────────────────────────

# class DatasetProfileRequest(BaseModel):
#     file_path: str
#     dataset_name: Optional[str] = "dataset"

# class StatisticalSummaryRequest(BaseModel):
#     file_path: str
#     columns: Optional[List[str]] = None

# class DataQualityRequest(BaseModel):
#     file_path: str

# class CorrelationAnalysisRequest(BaseModel):
#     file_path: str
#     method: Optional[str] = "pearson"

# # ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

# def load_dataset(file_path: str) -> pd.DataFrame:
#     """Load dataset from file path."""
#     try:
#         if not os.path.exists(file_path):
#             raise FileNotFoundError(f"File not found: {file_path}")
        
#         # Determine file type and load accordingly
#         file_ext = Path(file_path).suffix.lower()
        
#         if file_ext == '.csv':
#             df = pd.read_csv(file_path)
#         elif file_ext in ['.xlsx', '.xls']:
#             df = pd.read_excel(file_path)
#         elif file_ext == '.json':
#             df = pd.read_json(file_path)
#         elif file_ext == '.parquet':
#             df = pd.read_parquet(file_path)
#         else:
#             # Try CSV as default
#             df = pd.read_csv(file_path)
        
#         logger.info(f"Loaded dataset: {file_path} - Shape: {df.shape}")
#         return df
        
#     except Exception as e:
#         logger.error(f"Failed to load dataset {file_path}: {str(e)}")
#         raise HTTPException(status_code=400, detail=f"Failed to load dataset: {str(e)}")

# def get_column_info(df: pd.DataFrame) -> Dict[str, Any]:
#     """Get detailed information about each column."""
#     column_info = {}
    
#     for col in df.columns:
#         info = {
#             "dtype": str(df[col].dtype),
#             "non_null_count": int(df[col].count()),
#             "null_count": int(df[col].isnull().sum()),
#             "null_percentage": float(df[col].isnull().sum() / len(df) * 100),
#             "unique_count": int(df[col].nunique()),
#             "unique_percentage": float(df[col].nunique() / len(df) * 100)
#         }
        
#         # Add type-specific statistics
#         if df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
#             info.update({
#                 "min": float(df[col].min()) if pd.notna(df[col].min()) else None,
#                 "max": float(df[col].max()) if pd.notna(df[col].max()) else None,
#                 "mean": float(df[col].mean()) if pd.notna(df[col].mean()) else None,
#                 "median": float(df[col].median()) if pd.notna(df[col].median()) else None,
#                 "std": float(df[col].std()) if pd.notna(df[col].std()) else None,
#                 "is_numeric": True
#             })
#         else:
#             info.update({
#                 "is_numeric": False,
#                 "most_frequent": df[col].mode().iloc[0] if len(df[col].mode()) > 0 else None
#             })
        
#         column_info[col] = info
    
#     return column_info

# def detect_data_types(df: pd.DataFrame) -> Dict[str, List[str]]:
#     """Categorize columns by data type."""
#     numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
#     categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
#     datetime_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
#     boolean_cols = df.select_dtypes(include=['bool']).columns.tolist()
    
#     return {
#         "numeric": numeric_cols,
#         "categorical": categorical_cols,
#         "datetime": datetime_cols,
#         "boolean": boolean_cols
#     }

# def identify_outliers(df: pd.DataFrame, method: str = "iqr") -> Dict[str, Any]:
#     """Identify outliers in numeric columns."""
#     numeric_cols = df.select_dtypes(include=[np.number]).columns
#     outliers = {}
    
#     for col in numeric_cols:
#         if method == "iqr":
#             Q1 = df[col].quantile(0.25)
#             Q3 = df[col].quantile(0.75)
#             IQR = Q3 - Q1
#             lower_bound = Q1 - 1.5 * IQR
#             upper_bound = Q3 + 1.5 * IQR
            
#             outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
#             outlier_count = outlier_mask.sum()
            
#             outliers[col] = {
#                 "count": int(outlier_count),
#                 "percentage": float(outlier_count / len(df) * 100),
#                 "lower_bound": float(lower_bound),
#                 "upper_bound": float(upper_bound),
#                 "outlier_values": df[df[col].isin(df[col][outlier_mask])][col].tolist()[:10]  # First 10
#             }
    
#     return outliers

# # ─── API ENDPOINTS ───────────────────────────────────────────────────────────

# @app.get("/")
# async def root():
#     """Root endpoint with service information."""
#     return {
#         "service": "EDA Agent",
#         "version": "1.0.0",
#         "status": "operational",
#         "capabilities": [
#             "profile_dataset",
#             "statistical_summary", 
#             "data_quality",
#             "correlation_analysis"
#         ]
#     }

# @app.get("/health")
# async def health_check():
#     """Health check endpoint."""
#     return {
#         "status": "healthy",
#         "timestamp": datetime.now().isoformat(),
#         "service": "EDA Agent"
#     }

# @app.post("/profile_dataset")
# async def profile_dataset(request: DatasetProfileRequest):
#     """Generate comprehensive dataset profile."""
#     try:
#         logger.info(f"Profiling dataset: {request.file_path}")
        
#         # Load dataset
#         df = load_dataset(request.file_path)
        
#         # Basic dataset info
#         basic_info = {
#             "dataset_name": request.dataset_name,
#             "shape": {
#                 "rows": int(df.shape[0]),
#                 "columns": int(df.shape[1])
#             },
#             "memory_usage": f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB",
#             "column_names": df.columns.tolist()
#         }
        
#         # Column information
#         column_info = get_column_info(df)
        
#         # Data types categorization
#         data_types = detect_data_types(df)
        
#         # Overall data quality metrics
#         quality_metrics = {
#             "total_missing_values": int(df.isnull().sum().sum()),
#             "missing_percentage": float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100),
#             "duplicate_rows": int(df.duplicated().sum()),
#             "duplicate_percentage": float(df.duplicated().sum() / len(df) * 100)
#         }
        
#         result = {
#             "basic_info": basic_info,
#             "column_info": column_info,
#             "data_types": data_types,
#             "quality_metrics": quality_metrics,
#             "analysis_timestamp": datetime.now().isoformat()
#         }
        
#         logger.info(f"Dataset profiling completed for: {request.dataset_name}")
#         return result
        
#     except Exception as e:
#         logger.error(f"Dataset profiling failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Profiling failed: {str(e)}")

# @app.post("/statistical_summary")
# async def statistical_summary(request: StatisticalSummaryRequest):
#     """Generate statistical summary for numeric columns."""
#     try:
#         logger.info(f"Generating statistical summary: {request.file_path}")
        
#         # Load dataset
#         df = load_dataset(request.file_path)
        
#         # Select columns
#         if request.columns:
#             df = df[request.columns]
        
#         # Generate summary for numeric columns only
#         numeric_df = df.select_dtypes(include=[np.number])
        
#         if numeric_df.empty:
#             return {
#                 "message": "No numeric columns found",
#                 "summary": {},
#                 "analysis_timestamp": datetime.now().isoformat()
#             }
        
#         # Statistical summary
#         summary = {}
#         for col in numeric_df.columns:
#             col_data = numeric_df[col].dropna()
            
#             summary[col] = {
#                 "count": int(len(col_data)),
#                 "mean": float(col_data.mean()),
#                 "std": float(col_data.std()),
#                 "min": float(col_data.min()),
#                 "25%": float(col_data.quantile(0.25)),
#                 "50%": float(col_data.median()),
#                 "75%": float(col_data.quantile(0.75)),
#                 "max": float(col_data.max()),
#                 "skewness": float(col_data.skew()),
#                 "kurtosis": float(col_data.kurtosis())
#             }
        
#         result = {
#             "summary": summary,
#             "total_numeric_columns": len(numeric_df.columns),
#             "analysis_timestamp": datetime.now().isoformat()
#         }
        
#         logger.info("Statistical summary completed")
#         return result
        
#     except Exception as e:
#         logger.error(f"Statistical summary failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Statistical summary failed: {str(e)}")

# @app.post("/data_quality")
# async def data_quality_assessment(request: DataQualityRequest):
#     """Perform comprehensive data quality assessment."""
#     try:
#         logger.info(f"Assessing data quality: {request.file_path}")
        
#         # Load dataset
#         df = load_dataset(request.file_path)
        
#         # Missing values analysis
#         missing_analysis = {}
#         for col in df.columns:
#             missing_count = df[col].isnull().sum()
#             missing_analysis[col] = {
#                 "missing_count": int(missing_count),
#                 "missing_percentage": float(missing_count / len(df) * 100),
#                 "data_type": str(df[col].dtype)
#             }
        
#         # Duplicate analysis
#         duplicate_info = {
#             "total_duplicates": int(df.duplicated().sum()),
#             "duplicate_percentage": float(df.duplicated().sum() / len(df) * 100),
#             "unique_rows": int(len(df.drop_duplicates()))
#         }
        
#         # Outlier detection for numeric columns
#         outliers = identify_outliers(df)
        
#         # Data consistency checks
#         consistency_issues = []
        
#         # Check for mixed data types in object columns
#         for col in df.select_dtypes(include=['object']).columns:
#             unique_types = set(type(x).__name__ for x in df[col].dropna())
#             if len(unique_types) > 1:
#                 consistency_issues.append({
#                     "column": col,
#                     "issue": "Mixed data types",
#                     "types_found": list(unique_types)
#                 })
        
#         # Overall quality score (simple heuristic)
#         quality_score = 100
#         quality_score -= min(50, df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100 * 2)  # Missing values penalty
#         quality_score -= min(20, df.duplicated().sum() / len(df) * 100)  # Duplicates penalty
#         quality_score -= len(consistency_issues) * 5  # Consistency issues penalty
#         quality_score = max(0, quality_score)
        
#         result = {
#             "missing_values": missing_analysis,
#             "duplicates": duplicate_info,
#             "outliers": outliers,
#             "consistency_issues": consistency_issues,
#             "quality_score": float(quality_score),
#             "recommendations": generate_quality_recommendations(df, missing_analysis, duplicate_info, outliers),
#             "analysis_timestamp": datetime.now().isoformat()
#         }
        
#         logger.info("Data quality assessment completed")
#         return result
        
#     except Exception as e:
#         logger.error(f"Data quality assessment failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Data quality assessment failed: {str(e)}")

# @app.post("/correlation_analysis")
# async def correlation_analysis(request: CorrelationAnalysisRequest):
#     """Perform correlation analysis on numeric columns."""
#     try:
#         logger.info(f"Performing correlation analysis: {request.file_path}")
        
#         # Load dataset
#         df = load_dataset(request.file_path)
        
#         # Select numeric columns only
#         numeric_df = df.select_dtypes(include=[np.number])
        
#         if numeric_df.shape[1] < 2:
#             return {
#                 "message": "Need at least 2 numeric columns for correlation analysis",
#                 "correlations": {},
#                 "analysis_timestamp": datetime.now().isoformat()
#             }
        
#         # Calculate correlation matrix
#         corr_matrix = numeric_df.corr(method=request.method)
        
#         # Convert to serializable format
#         correlations = {}
#         for i, col1 in enumerate(corr_matrix.columns):
#             for j, col2 in enumerate(corr_matrix.columns):
#                 if i < j:  # Only upper triangle to avoid duplicates
#                     corr_value = corr_matrix.iloc[i, j]
#                     if not pd.isna(corr_value):
#                         correlations[f"{col1}_vs_{col2}"] = {
#                             "correlation": float(corr_value),
#                             "strength": get_correlation_strength(abs(corr_value)),
#                             "columns": [col1, col2]
#                         }
        
#         # Find strongest correlations
#         sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]["correlation"]), reverse=True)
#         top_correlations = dict(sorted_corrs[:10])  # Top 10
        
#         result = {
#             "method": request.method,
#             "correlations": correlations,
#             "top_correlations": top_correlations,
#             "numeric_columns": numeric_df.columns.tolist(),
#             "analysis_timestamp": datetime.now().isoformat()
#         }
        
#         logger.info("Correlation analysis completed")
#         return result
        
#     except Exception as e:
#         logger.error(f"Correlation analysis failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Correlation analysis failed: {str(e)}")

# # ─── HELPER FUNCTIONS FOR QUALITY ASSESSMENT ────────────────────────────────

# def generate_quality_recommendations(df: pd.DataFrame, missing_analysis: Dict, 
#                                    duplicate_info: Dict, outliers: Dict) -> List[str]:
#     """Generate data quality improvement recommendations."""
#     recommendations = []
    
#     # Missing values recommendations
#     high_missing_cols = [col for col, info in missing_analysis.items() 
#                         if info["missing_percentage"] > 20]
#     if high_missing_cols:
#         recommendations.append(f"Consider dropping or imputing columns with high missing rates: {', '.join(high_missing_cols)}")
    
#     # Duplicates recommendations
#     if duplicate_info["duplicate_percentage"] > 5:
#         recommendations.append("Consider removing duplicate rows to improve data quality")
    
#     # Outliers recommendations
#     outlier_cols = [col for col, info in outliers.items() if info["percentage"] > 5]
#     if outlier_cols:
#         recommendations.append(f"Investigate outliers in columns: {', '.join(outlier_cols)}")
    
#     # Data type recommendations
#     object_cols = df.select_dtypes(include=['object']).columns
#     if len(object_cols) > 0:
#         recommendations.append("Consider converting appropriate object columns to categorical for better performance")
    
#     return recommendations

# def get_correlation_strength(corr_value: float) -> str:
#     """Categorize correlation strength."""
#     abs_corr = abs(corr_value)
#     if abs_corr >= 0.8:
#         return "Very Strong"
#     elif abs_corr >= 0.6:
#         return "Strong"
#     elif abs_corr >= 0.4:
#         return "Moderate"
#     elif abs_corr >= 0.2:
#         return "Weak"
#     else:
#         return "Very Weak"

# # ─── MAIN ────────────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     uvicorn.run(
#         "eda_agent:app",
#         host="0.0.0.0",
#         port=8001,
#         reload=True,
#         log_level="info"
#     )

#!/usr/bin/env python3
"""
Enhanced EDA Agent Service

Performs exploratory data analysis tasks including:
- Dataset profiling
- Statistical summaries
- Data quality assessment
- Basic visualizations

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
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Enhanced EDA Agent Service",
    description="Exploratory Data Analysis Agent with Upload Integration",
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
    "datasets"          # Alternative datasets directory
]

# ─── ENHANCED DATA MODELS ─────────────────────────────────────────────────────

class DatasetProfileRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None  # New: Use dataset ID from orchestrator
    dataset_name: Optional[str] = "dataset"

class StatisticalSummaryRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    columns: Optional[List[str]] = None

class DataQualityRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None

class CorrelationAnalysisRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None
    method: Optional[str] = "pearson"

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

def get_column_info(df: pd.DataFrame) -> Dict[str, Any]:
    """Get detailed information about each column."""
    column_info = {}
    
    for col in df.columns:
        info = {
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].count()),
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": float(df[col].isnull().sum() / len(df) * 100),
            "unique_count": int(df[col].nunique()),
            "unique_percentage": float(df[col].nunique() / len(df) * 100)
        }
        
        # Add type-specific statistics
        if df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
            info.update({
                "min": float(df[col].min()) if pd.notna(df[col].min()) else None,
                "max": float(df[col].max()) if pd.notna(df[col].max()) else None,
                "mean": float(df[col].mean()) if pd.notna(df[col].mean()) else None,
                "median": float(df[col].median()) if pd.notna(df[col].median()) else None,
                "std": float(df[col].std()) if pd.notna(df[col].std()) else None,
                "is_numeric": True
            })
        else:
            info.update({
                "is_numeric": False,
                "most_frequent": df[col].mode().iloc[0] if len(df[col].mode()) > 0 else None
            })
        
        column_info[col] = info
    
    return column_info

def detect_data_types(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Categorize columns by data type."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    datetime_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
    boolean_cols = df.select_dtypes(include=['bool']).columns.tolist()
    
    return {
        "numeric": numeric_cols,
        "categorical": categorical_cols,
        "datetime": datetime_cols,
        "boolean": boolean_cols
    }

def identify_outliers(df: pd.DataFrame, method: str = "iqr") -> Dict[str, Any]:
    """Identify outliers in numeric columns."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    outliers = {}
    
    for col in numeric_cols:
        if method == "iqr":
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
            outlier_count = outlier_mask.sum()
            
            outliers[col] = {
                "count": int(outlier_count),
                "percentage": float(outlier_count / len(df) * 100),
                "lower_bound": float(lower_bound),
                "upper_bound": float(upper_bound),
                "outlier_values": df[df[col].isin(df[col][outlier_mask])][col].tolist()[:10]  # First 10
            }
    
    return outliers

# ─── ENHANCED API ENDPOINTS ───────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Enhanced EDA Agent",
        "version": "1.1.0",
        "status": "operational",
        "capabilities": [
            "profile_dataset",
            "statistical_summary", 
            "data_quality",
            "correlation_analysis"
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
    """Health check endpoint."""
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
        "service": "Enhanced EDA Agent",
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

@app.post("/profile_dataset")
async def profile_dataset(request: DatasetProfileRequest):
    """Generate comprehensive dataset profile - enhanced for orchestrator integration."""
    try:
        logger.info(f"Profiling dataset - file_path: {request.file_path}, dataset_id: {request.dataset_id}")
        
        # Load dataset using enhanced loader
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Get actual file path used
        actual_path = resolve_file_path(request.file_path, request.dataset_id)
        actual_path = find_file_in_directories(actual_path)
        
        # Basic dataset info
        basic_info = {
            "dataset_name": request.dataset_name,
            "file_path": actual_path,
            "shape": {
                "rows": int(df.shape[0]),
                "columns": int(df.shape[1])
            },
            "memory_usage": f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB",
            "column_names": df.columns.tolist()
        }
        
        # Column information
        column_info = get_column_info(df)
        
        # Data types categorization
        data_types = detect_data_types(df)
        
        # Overall data quality metrics
        quality_metrics = {
            "total_missing_values": int(df.isnull().sum().sum()),
            "missing_percentage": float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100),
            "duplicate_rows": int(df.duplicated().sum()),
            "duplicate_percentage": float(df.duplicated().sum() / len(df) * 100)
        }
        
        result = {
            "basic_info": basic_info,
            "column_info": column_info,
            "data_types": data_types,
            "quality_metrics": quality_metrics,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Dataset profiling completed for: {request.dataset_name}")
        return result
        
    except Exception as e:
        logger.error(f"Dataset profiling failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Profiling failed: {str(e)}")

@app.post("/statistical_summary")
async def statistical_summary(request: StatisticalSummaryRequest):
    """Generate statistical summary for numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Generating statistical summary - file_path: {request.file_path}, dataset_id: {request.dataset_id}")
        
        # Load dataset using enhanced loader
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Select columns
        if request.columns:
            df = df[request.columns]
        
        # Generate summary for numeric columns only
        numeric_df = df.select_dtypes(include=[np.number])
        
        if numeric_df.empty:
            return {
                "message": "No numeric columns found",
                "summary": {},
                "analysis_timestamp": datetime.now().isoformat()
            }
        
        # Statistical summary
        summary = {}
        for col in numeric_df.columns:
            col_data = numeric_df[col].dropna()
            
            summary[col] = {
                "count": int(len(col_data)),
                "mean": float(col_data.mean()),
                "std": float(col_data.std()),
                "min": float(col_data.min()),
                "25%": float(col_data.quantile(0.25)),
                "50%": float(col_data.median()),
                "75%": float(col_data.quantile(0.75)),
                "max": float(col_data.max()),
                "skewness": float(col_data.skew()),
                "kurtosis": float(col_data.kurtosis())
            }
        
        result = {
            "summary": summary,
            "total_numeric_columns": len(numeric_df.columns),
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        logger.info("Statistical summary completed")
        return result
        
    except Exception as e:
        logger.error(f"Statistical summary failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Statistical summary failed: {str(e)}")

@app.post("/data_quality")
async def data_quality_assessment(request: DataQualityRequest):
    """Perform comprehensive data quality assessment - enhanced for orchestrator integration."""
    try:
        logger.info(f"Assessing data quality - file_path: {request.file_path}, dataset_id: {request.dataset_id}")
        
        # Load dataset using enhanced loader
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Missing values analysis
        missing_analysis = {}
        for col in df.columns:
            missing_count = df[col].isnull().sum()
            missing_analysis[col] = {
                "missing_count": int(missing_count),
                "missing_percentage": float(missing_count / len(df) * 100),
                "data_type": str(df[col].dtype)
            }
        
        # Duplicate analysis
        duplicate_info = {
            "total_duplicates": int(df.duplicated().sum()),
            "duplicate_percentage": float(df.duplicated().sum() / len(df) * 100),
            "unique_rows": int(len(df.drop_duplicates()))
        }
        
        # Outlier detection for numeric columns
        outliers = identify_outliers(df)
        
        # Data consistency checks
        consistency_issues = []
        
        # Check for mixed data types in object columns
        for col in df.select_dtypes(include=['object']).columns:
            unique_types = set(type(x).__name__ for x in df[col].dropna())
            if len(unique_types) > 1:
                consistency_issues.append({
                    "column": col,
                    "issue": "Mixed data types",
                    "types_found": list(unique_types)
                })
        
        # Overall quality score (simple heuristic)
        quality_score = 100
        quality_score -= min(50, df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100 * 2)  # Missing values penalty
        quality_score -= min(20, df.duplicated().sum() / len(df) * 100)  # Duplicates penalty
        quality_score -= len(consistency_issues) * 5  # Consistency issues penalty
        quality_score = max(0, quality_score)
        
        result = {
            "missing_values": missing_analysis,
            "duplicates": duplicate_info,
            "outliers": outliers,
            "consistency_issues": consistency_issues,
            "quality_score": float(quality_score),
            "recommendations": generate_quality_recommendations(df, missing_analysis, duplicate_info, outliers),
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        logger.info("Data quality assessment completed")
        return result
        
    except Exception as e:
        logger.error(f"Data quality assessment failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Data quality assessment failed: {str(e)}")

@app.post("/correlation_analysis")
async def correlation_analysis(request: CorrelationAnalysisRequest):
    """Perform correlation analysis on numeric columns - enhanced for orchestrator integration."""
    try:
        logger.info(f"Performing correlation analysis - file_path: {request.file_path}, dataset_id: {request.dataset_id}")
        
        # Load dataset using enhanced loader
        df = load_dataset(request.file_path, request.dataset_id)
        
        # Select numeric columns only
        numeric_df = df.select_dtypes(include=[np.number])
        
        if numeric_df.shape[1] < 2:
            return {
                "message": "Need at least 2 numeric columns for correlation analysis",
                "correlations": {},
                "analysis_timestamp": datetime.now().isoformat()
            }
        
        # Calculate correlation matrix
        corr_matrix = numeric_df.corr(method=request.method)
        
        # Convert to serializable format
        correlations = {}
        for i, col1 in enumerate(corr_matrix.columns):
            for j, col2 in enumerate(corr_matrix.columns):
                if i < j:  # Only upper triangle to avoid duplicates
                    corr_value = corr_matrix.iloc[i, j]
                    if not pd.isna(corr_value):
                        correlations[f"{col1}_vs_{col2}"] = {
                            "correlation": float(corr_value),
                            "strength": get_correlation_strength(abs(corr_value)),
                            "columns": [col1, col2]
                        }
        
        # Find strongest correlations
        sorted_corrs = sorted(correlations.items(), key=lambda x: abs(x[1]["correlation"]), reverse=True)
        top_correlations = dict(sorted_corrs[:10])  # Top 10
        
        result = {
            "method": request.method,
            "correlations": correlations,
            "top_correlations": top_correlations,
            "numeric_columns": numeric_df.columns.tolist(),
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        logger.info("Correlation analysis completed")
        return result
        
    except Exception as e:
        logger.error(f"Correlation analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Correlation analysis failed: {str(e)}")

# ─── HELPER FUNCTIONS FOR QUALITY ASSESSMENT ────────────────────────────────

def generate_quality_recommendations(df: pd.DataFrame, missing_analysis: Dict, 
                                   duplicate_info: Dict, outliers: Dict) -> List[str]:
    """Generate data quality improvement recommendations."""
    recommendations = []
    
    # Missing values recommendations
    high_missing_cols = [col for col, info in missing_analysis.items() 
                        if info["missing_percentage"] > 20]
    if high_missing_cols:
        recommendations.append(f"Consider dropping or imputing columns with high missing rates: {', '.join(high_missing_cols)}")
    
    # Duplicates recommendations
    if duplicate_info["duplicate_percentage"] > 5:
        recommendations.append("Consider removing duplicate rows to improve data quality")
    
    # Outliers recommendations
    outlier_cols = [col for col, info in outliers.items() if info["percentage"] > 5]
    if outlier_cols:
        recommendations.append(f"Investigate outliers in columns: {', '.join(outlier_cols)}")
    
    # Data type recommendations
    object_cols = df.select_dtypes(include=['object']).columns
    if len(object_cols) > 0:
        recommendations.append("Consider converting appropriate object columns to categorical for better performance")
    
    return recommendations

def get_correlation_strength(corr_value: float) -> str:
    """Categorize correlation strength."""
    abs_corr = abs(corr_value)
    if abs_corr >= 0.8:
        return "Very Strong"
    elif abs_corr >= 0.6:
        return "Strong"
    elif abs_corr >= 0.4:
        return "Moderate"
    elif abs_corr >= 0.2:
        return "Weak"
    else:
        return "Very Weak"

# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "eda_agent:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )