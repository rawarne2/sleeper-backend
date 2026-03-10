# Sleeper Backend API Documentation

A comprehensive fantasy football API that aggregates data from **KeepTradeCut (KTC)** and **Sleeper API**.

## 🚀 Quick Start

1. **Start the server (choose one):**

   ```bash
   # Option A: Local (no Docker)
   ./startup.sh

   # Option B: Docker (PostgreSQL via Docker Compose)
   ./docker-compose.sh up
   ```

2. **Server runs on:**

   ```
   http://localhost:5001
   ```

3. **Seed your data in the correct order:**

   ```bash
   # 1. First, seed Sleeper player data (foundation - takes 30-60 seconds)
   curl -X POST "http://localhost:5001/api/sleeper/refresh"
   
   # 2. Then, merge KTC rankings into existing Sleeper players (fast - takes 5-10 seconds)
   curl -X POST "http://localhost:5001/api/ktc/refresh/all"
   
   # 3. Finally, seed your league for weekly stats (optional)
   curl -X POST "http://localhost:5001/api/sleeper/league/YOUR_LEAGUE_ID/stats/seed" \
     -H "Content-Type: application/json" \
     -d '{"league_name": "My League", "season": "2024", "league_type": "dynasty"}'
   ```

## 📋 API Overview

This API provides comprehensive fantasy football data by combining:

- 🏈 **KeepTradeCut (KTC)**: Player rankings and trade values
  • Dynasty & Redraft rankings
  • 1QB & Superflex league formats  
  • TEP (Tight End Premium) scoring variations

- 🏈 **Sleeper API**: Player data & league management
  • Comprehensive player profiles with physical stats
  • League management (rosters, users, settings)
  • Research data and projections

## 📚 Available Endpoints (13 total)

### 🏥 System Health

```
GET /api/ktc/health
```

Check API and database health status.

### 🏈 KTC Player Rankings

```
POST /api/ktc/refresh
PUT /api/ktc/refresh
GET /api/ktc/rankings
POST /api/ktc/cleanup
```

**POST /api/ktc/refresh** - Create/populate KTC rankings for specific configuration
**PUT /api/ktc/refresh** - Update KTC rankings for specific configuration

- Query Parameters:
  - `is_redraft`: "true" or "false" (default: "false")
  - `league_format`: "1qb" or "superflex" (default: "1qb")
  - `tep_level`: "", "tep", "tepp", or "teppp" (default: "")

**GET /api/ktc/rankings** - Retrieve stored rankings with filtering

- Same query parameters as update endpoint

**POST /api/ktc/cleanup** - Clean up incomplete data

- Same query parameters as update endpoint

### 👤 Sleeper Player Data

```
POST /api/sleeper/refresh
```

Refresh and merge Sleeper player data with KTC data.

### 🏟️ Sleeper League Management

```
GET /api/sleeper/league/{league_id}
GET /api/sleeper/league/{league_id}/rosters
GET /api/sleeper/league/{league_id}/users
POST /api/sleeper/league/{league_id}
PUT /api/sleeper/league/{league_id}
```

**GET /api/sleeper/league/{league_id}** - Get comprehensive league data
**GET /api/sleeper/league/{league_id}/rosters** - Get rosters only
**GET /api/sleeper/league/{league_id}/users** - Get users only
**POST /api/sleeper/league/{league_id}** - Refresh league data
**PUT /api/sleeper/league/{league_id}** - Update league data

### 📊 Sleeper Weekly Stats

```
GET /api/sleeper/league/{league_id}/stats/week/{week}
POST /api/sleeper/league/{league_id}/stats/week/{week}
PUT /api/sleeper/league/{league_id}/stats/week/{week}
POST /api/sleeper/league/{league_id}/stats/seed
```

**GET /api/sleeper/league/{league_id}/stats/week/{week}** - Get weekly stats for a specific week

- Query Parameters:
  - `season`: NFL season year (default: "2024")
  - `league_type`: `dynasty` or `redraft` (default: `dynasty`)
  - `average`: "true" to return season averages (weeks 1-16 only)

**POST /api/sleeper/league/{league_id}/stats/week/{week}** - Refresh weekly stats from Sleeper API
**PUT /api/sleeper/league/{league_id}/stats/week/{week}** - Update weekly stats from Sleeper API

- Same query parameters as GET endpoint

**POST /api/sleeper/league/{league_id}/stats/seed** - Seed league information

- Request Body (JSON):
  - `league_name`: League name (default: "Fantasy League")
  - `season`: NFL season year (required)
  - `scoring_settings`: League scoring settings object

### 🔬 Sleeper Research Data

```
GET /api/sleeper/players/research/{season}
POST /api/sleeper/players/research/{season}
PUT /api/sleeper/players/research/{season}
```

**GET /api/sleeper/players/research/{season}** - Get research data

- Query Parameters:
  - `week`: Week number (default: 1)
  - `league_type`: `dynasty` or `redraft` (default: `dynasty`)

**POST /api/sleeper/players/research/{season}** - Refresh research
**PUT /api/sleeper/players/research/{season}** - Update research

- Same query parameters as GET endpoint

## 🎮 How to Use

### 1. **First-Time Setup**

```bash
# Load KTC data first
curl -X PUT "http://localhost:5001/api/ktc/refresh?league_format=superflex"

# Or use POST endpoint
curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=superflex"

# Then get rankings
curl "http://localhost:5001/api/ktc/rankings?league_format=superflex&tep_level=tep"
```

### 2. **Parameter Examples**

**League Formats:**

- `1qb` - Standard leagues (only 1 QB can start)
- `superflex` - Superflex leagues (can start 2 QBs, making QBs much more valuable)

**Ranking Types:**

- `is_redraft=false` - Dynasty (long-term player value, considers age)
- `is_redraft=true` - Redraft (current season only)

**TEP Levels:**

- `tep_level=""` - Standard scoring
- `tep_level=tep` - +0.5 points per TE reception
- `tep_level=tepp` - +1.0 points per TE reception  
- `tep_level=teppp` - +1.5 points per TE reception

## 📊 Response Data Structure

### Player Data Example

```json
{
  "playerName": "Josh Allen",
  "position": "QB",
  "team": "BUF",
  "sleeper_player_id": "4017",
  "birth_date": "1996-05-21",
  "height": "6'5\"",
  "weight": "237",
  "college": "Wyoming",
  "years_exp": 6,
  "injury_status": "Healthy",
  "ktc": {
    "superflexValues": {
      "value": 8500,
      "rank": 3,
      "positionalRank": 2,
      "overallTier": 1,
      "positionalTier": 1,
      "tep": {
        "value": 8600,
        "rank": 3
      }
    }
  }
}
```

## 🔧 Usage Examples

### KTC Rankings

```bash
# Dynasty Superflex with TEP
curl "http://localhost:5001/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Redraft 1QB Standard
curl "http://localhost:5001/api/ktc/rankings?league_format=1qb&is_redraft=true"

# Dynasty 1QB with maximum TEP
curl "http://localhost:5001/api/ktc/rankings?league_format=1qb&is_redraft=false&tep_level=teppp"
```

### League Management

```bash
# Get league data
curl "http://localhost:5001/api/sleeper/league/1210364682523656192"

# Get only rosters
curl "http://localhost:5001/api/sleeper/league/1210364682523656192/rosters"

# Update league data
curl -X PUT "http://localhost:5001/api/sleeper/league/1210364682523656192"

# Or use POST endpoint
curl -X POST "http://localhost:5001/api/sleeper/league/1210364682523656192"
```

### Research Data

```bash
# Get 2024 dynasty research
curl "http://localhost:5001/api/sleeper/players/research/2024?league_type=dynasty"

# Get 2024 redraft week 10 research  
curl "http://localhost:5001/api/sleeper/players/research/2024?week=10&league_type=redraft"
```

## ⚡ Performance Optimizations

### **Database Caching Strategy**

- **First API call**: Data fetched from external APIs and cached in database
- **Subsequent calls**: Data served instantly from local database cache
- **Smart refresh**: Use refresh endpoints only when data needs updating

### **Response Time Guidelines**

- **First refresh call**: 30-60 seconds (fetching from external APIs)
- **Cached data retrieval**: < 1 second (from local database)
- **Health checks**: < 100ms (database connection test)

### **Best Practices for Performance**

```bash
# ❌ Don't call update/refresh endpoints repeatedly
curl -X PUT /api/ktc/refresh   # Takes 30-60 seconds
curl -X POST /api/ktc/refresh   # Takes 30-60 seconds

# ✅ Call update/refresh once, then use cached data
curl -X PUT /api/ktc/refresh   # One-time setup
curl /api/ktc/rankings          # Fast cached responses

# ✅ Use database-first endpoints for speed
curl /api/sleeper/league/123456789 # Checks cache first, API fallback
```

### **Gunicorn Multi-Worker Setup**

- **9 worker processes** for concurrent request handling
- **Load balancing** across CPU cores
- **Process isolation** prevents blocking between requests

## 🚀 Getting Started

1. **Install dependencies (for local / non-Docker runs):**

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the server (pick one):**

   ```bash
   # Local (no Docker)
   ./startup.sh

   # Or Docker (uses docker-compose)
   ./docker-compose.sh up
   ```

3. **Test the API:**

   ```bash
   curl http://localhost:5001/api/ktc/health
   ```

4. **Load initial data:**

   ```bash
   curl -X PUT "http://localhost:5001/api/ktc/refresh?league_format=superflex"
   
   # Or use POST endpoint
   curl -X POST "http://localhost:5001/api/ktc/refresh?league_format=superflex"
   ```

5. **Get player data:**

   ```bash
   curl "http://localhost:5001/api/ktc/rankings?league_format=superflex"
   ```

## 📈 Production Ready

This API is production-ready with:

- ✅ **Comprehensive error handling**
- ✅ **Database connection pooling**
- ✅ **CORS configuration**
- ✅ **Request validation**
- ✅ **Response standardization**
- ✅ **Logging and monitoring**
- ✅ **Performance optimization** with caching and multi-worker setup

## 📝 Error Response Format

All endpoints return consistent error responses:

```json
{
  "status": "error",
  "error": "Error message",
  "details": "Additional error details",
  "timestamp": "2025-01-05T17:58:12.123456+00:00"
}
```

## 💡 Tips

- Always check `/api/ktc/health` before making other requests
- Use the update/refresh endpoints sparingly to avoid rate limiting
- Cache responses on your end when possible
- The API automatically handles database caching for optimal performance
