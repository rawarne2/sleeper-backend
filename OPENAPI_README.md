# OpenAPI Documentation for Sleeper Backend API

This project now includes comprehensive OpenAPI 3.1 documentation with interactive Swagger UI interface.

## 📚 Documentation Features

- **Complete API Coverage**: All 13 endpoints documented with detailed schemas
- **Interactive Testing**: Test endpoints directly from the browser interface
- **Comprehensive Examples**: Request/response examples for all endpoints
- **Performance Notes**: Clear guidance on caching behavior and response times
- **Parameter Validation**: Detailed parameter descriptions with examples

## 🚀 Quick Start

### Option 1: Local Server (Recommended)

Start the documentation server with interactive Swagger UI:

```bash
# Start the API locally
./startup.sh
```

Then visit: **<http://localhost:5001/docs/>**

### Option 2: Regular Server

The OpenAPI spec is also available with the regular server:

```bash
./startup.sh
```

Access the OpenAPI spec at: **<http://localhost:5001/openapi.json>**

## 📖 Documentation Access Points

| URL | Description |
|-----|-------------|
| `http://localhost:5001/` | Redirects to documentation |
| `http://localhost:5001/docs/` | Interactive Swagger UI interface |
| `http://localhost:5001/openapi.json` | OpenAPI 3.1 specification (JSON) |
| `http://localhost:5001/apispec.json` | Flasgger-generated spec (Swagger 2.0) |

## 🏗️ Documentation Structure

### API Endpoints Organized by Category

#### 🏥 Health

- `GET /api/ktc/health` - System health check

#### 🏈 KTC Player Rankings  

- `POST /api/ktc/refresh` - Create/populate KTC rankings
- `PUT /api/ktc/refresh` - Update KTC rankings
- `GET /api/ktc/rankings` - Retrieve stored rankings
- `POST /api/ktc/cleanup` - Clean up data
- `POST /api/ktc/refresh/all` - Comprehensive refresh

#### 👤 Sleeper Players

- `POST /api/sleeper/refresh` - Refresh Sleeper data

#### 🏟️ Sleeper Leagues

- `GET /api/sleeper/league/{league_id}` - Get league data
- `GET /api/sleeper/league/{league_id}/rosters` - Get rosters
- `GET /api/sleeper/league/{league_id}/users` - Get users
- `POST /api/sleeper/league/{league_id}` - Refresh league
- `PUT /api/sleeper/league/{league_id}` - Update league

#### 📊 Sleeper Research

- `GET /api/sleeper/players/research/{season}` - Get research data
- `POST /api/sleeper/players/research/{season}` - Refresh research
- `PUT /api/sleeper/players/research/{season}` - Update research

## 🔧 Key Features

### Parameter Documentation

All endpoints include detailed parameter descriptions:

- **Query Parameters**: `is_redraft`, `league_format`, `tep_level`, etc.
- **Path Parameters**: `league_id`, `season`
- **Validation Rules**: Enum values, patterns, ranges
- **Default Values**: Clearly specified for optional parameters

### Response Schemas

Complete response schemas including:

- **Success Responses**: Detailed data structures
- **Error Responses**: Consistent error format
- **Status Codes**: All possible HTTP response codes
- **Examples**: Real-world response examples

### Performance Information

- **Caching Behavior**: Database-first approach explained
- **Response Times**: Expected performance for each endpoint type
- **Best Practices**: Guidance on optimal API usage

## 🧪 Testing the API

### Using Swagger UI

1. Navigate to `http://localhost:5001/docs/`
2. Click on any endpoint to expand it
3. Click "Try it out" to test the endpoint
4. Fill in parameters and click "Execute"
5. View the response directly in the interface

### Using curl Examples

The documentation includes curl examples for common use cases:

```bash
# Health check
curl http://localhost:5001/api/ktc/health

# Update dynasty superflex rankings with TEP
curl -X PUT "http://localhost:5001/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"

# Or use POST endpoint
curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"

# Get league data
curl "http://localhost:5001/api/sleeper/league/1210364682523656192"
```

## 📁 Documentation Files

- `openapi.yaml` - OpenAPI 3.1 specification
- `app.py` - Local Flask app entrypoint
- `swagger_config.py` - Shared Swagger and OpenAPI route configuration
- `startup.sh` - Local startup script
- `OPENAPI_README.md` - This documentation guide

## 🔄 Updating Documentation

When adding new endpoints or modifying existing ones:

1. **Update OpenAPI Spec**: Modify `openapi.yaml`
2. **Add Swagger Docstrings**: Add docstrings to route functions (optional)
3. **Test Changes**: Run `./startup.sh` and verify in browser
4. **Update Examples**: Add new curl examples to documentation

## 💡 Tips for API Users

### Getting Started

1. **Check Health**: Always start with `/api/ktc/health`
2. **Load Data**: Use `/api/ktc/refresh` (PUT or POST) to populate initial data
3. **Query Data**: Use `/api/ktc/rankings` (GET) for fast cached responses

### Parameter Usage

- **League Format**: Use `superflex` for most dynasty leagues
- **TEP Levels**: `tep` is most common (+0.5 per TE reception)
- **Redraft vs Dynasty**: `is_redraft=false` for long-term values

### Performance Optimization

- **First Call**: Update/refresh endpoints take 30-60 seconds
- **Subsequent Calls**: Cached data returns in < 1 second
- **Bulk Operations**: Use `/api/ktc/refresh/all` for scheduled tasks

## 🛠️ Development

### Extending Documentation

To add documentation for new endpoints:

```python
@api_bp.route('/api/new/endpoint', methods=['GET'])
def new_endpoint():
    """
    New endpoint description
    ---
    tags:
      - Category Name
    summary: Brief summary
    description: Detailed description
    parameters:
      - name: param_name
        in: query
        description: Parameter description
        required: false
        schema:
          type: string
          default: "default_value"
    responses:
      200:
        description: Success response
        schema:
          type: object
          properties:
            key:
              type: string
              example: "value"
    """
    # Endpoint implementation
```

### Validation

Always validate your OpenAPI spec:

```bash
# Install validation tools
pip install openapi-spec-validator

# Validate the spec
openapi-spec-validator openapi.yaml
```

## 📝 Notes

- The documentation server runs the full API - all endpoints are functional
- Both OpenAPI 3.1 (modern) and Swagger 2.0 (compatible) specs are available
- The interactive interface allows real API testing without additional tools
- All response examples are based on actual API responses

For questions or issues with the documentation, please check the existing API_DOCUMENTATION.md or create an issue in the repository.
