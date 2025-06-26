# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Start Applications

```bash
# Start Chainlit conversational interface (primary UI)
chainlit run chainlit_app.py

# Start Flask web interface (simple API)
python flask_app.py

# Start advanced Flask application with full agent APIs
python citu_app.py
```

### Training and Data Management

```bash
# Run training pipeline with data from data_pipeline/training_data directory
python -m data_pipeline.trainer.run_training --data_path ./data_pipeline/training_data/

# Complete automated schema workflow (DDL generation → Q&A generation → SQL validation → Training data loading)
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@host:port/database_name" \
  --table-list tables.txt \
  --business-context "业务系统描述" \
  --output-dir ./data_pipeline/training_data/

# Generate only schema documentation without validation
python -m data_pipeline.schema_workflow \
  --db-connection "postgresql://user:pass@host:port/db_name" \
  --table-list tables.txt \
  --business-context "系统描述" \
  --skip-validation
```

### Testing

```bash
# Test QA feedback and conversation management APIs
python test_qa_apis.py

# Test training data management APIs  
python test_training_data_apis.py
```

## Core Architecture

### Application Entry Points

- **`chainlit_app.py`** - Modern conversational UI with streaming responses, fallback mechanisms, and comprehensive error handling
- **`citu_app.py`** - Production Flask application with full REST APIs for agent queries, conversation management, QA feedback, and health monitoring
- **`flask_app.py`** - Simple REST API for basic database queries

### Central Configuration

**`app_config.py`** is the main configuration hub controlling:

```python
# Multi-provider LLM selection
LLM_MODEL_TYPE = "api"  # api or ollama
API_LLM_MODEL = "qianwen"  # qianwen or deepseek

# Vector database selection  
VECTOR_DB_TYPE = "pgvector"  # chromadb or pgvector

# Agent routing behavior
QUESTION_ROUTING_MODE = "hybrid"  # hybrid, database_direct, chat_direct, llm_only

# Feature toggles
ENABLE_RESULT_SUMMARY = True
ENABLE_CONVERSATION_CONTEXT = True
DISPLAY_RESULT_THINKING = False
```

### LLM and Vector Database Combinations

The system supports 6 LLM + vector database combinations via **`common/vanna_combinations.py`**:
- QianWen + ChromaDB/PgVector
- DeepSeek + ChromaDB/PgVector  
- Ollama + ChromaDB/PgVector

All combinations are created through **`core/vanna_llm_factory.py`** using factory pattern.

### Agent System Architecture

**`agent/citu_agent.py`** implements a sophisticated LangGraph-based workflow:

```
Question → Classify → [DATABASE Path] → SQL Generation → SQL Validation → SQL Execution → Summary
                   → [CHAT Path] → General Chat
```

**Routing Modes:**
- `hybrid` (default) - Intelligent classification between database and chat
- `database_direct` - Skip classification, direct SQL generation
- `chat_direct` - Skip classification, direct chat response
- `llm_only` - LLM-based classification only

### Database Integration

**Three-Database Architecture:**
1. **Business Database** (`APP_DB_CONFIG`) - Source data for queries
2. **Vector Database** (`PGVECTOR_CONFIG`) - Training data and embeddings
3. **Redis Cache** (`REDIS_*`) - Conversations, QA results, embedding cache

### Training Data Pipeline

**Training data is managed in `data_pipeline/training_data/` directory.**

**File Format Mapping:**
- `.ddl` files → `train_ddl_statements()`
- `.md/.markdown` → `train_documentation_blocks()`
- `_pair.json/_pairs.json` → `train_json_question_sql_pairs()`
- `_pair.sql/_pairs.sql` → `train_formatted_question_sql_pairs()`
- `.sql` (other) → `train_sql_examples()`

### Data Pipeline System

**`data_pipeline/`** provides automated database reverse engineering:

1. **Database Inspector** - Automatic schema discovery
2. **DDL Generator** - PostgreSQL DDL with intelligent comments
3. **Documentation Generator** - Detailed markdown documentation  
4. **Q&A Generator** (`qa_generation/`) - LLM-generated question-SQL pairs
5. **SQL Validator** (`validators/`) - EXPLAIN-based validation with auto-repair
6. **Training Pipeline** (`trainer/`) - Vanna.ai training data ingestion

## Key Patterns

### Singleton Pattern
**`common/vanna_instance.py`** implements thread-safe singleton for global Vanna instance management.

### Caching Strategy
Multi-layer caching via **`common/`**:
- **`session_aware_cache.py`** - Web session-aware caching
- **`embedding_cache_manager.py`** - High-performance embedding caching
- **`redis_conversation_manager.py`** - Conversation lifecycle management

### Error Handling
Comprehensive fallback mechanisms throughout the stack:
- SQL generation failures → General chat responses
- LLM timeouts → Cached responses
- Database connection issues → Health check endpoints

### Configuration Precedence
1. Environment variables (`.env` file)
2. **`app_config.py`** defaults
3. Module-specific configs (e.g., **`data_pipeline/config.py`**)

## Important Notes

- The system requires PostgreSQL for business data and optionally PgVector for vector storage
- Redis is essential for conversation management and caching
- Training data generation is resource-intensive and should be run with appropriate database permissions
- The agent system supports both streaming and non-streaming responses based on LLM provider capabilities
- Always test configuration changes with health check endpoints before production deployment