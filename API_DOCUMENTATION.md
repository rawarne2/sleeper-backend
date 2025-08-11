# Sleeper Backend API Documentation

A comprehensive fantasy football API that aggregates data from **KeepTradeCut (KTC)** and **Sleeper API**.

## 🚀 Quick Start

1. **Start the server:**
   ```bash
   ./startup.sh
   ```

2. **Server runs on:**
   ```
   http://localhost:5000
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
GET /api/ktc/rankings
POST /api/ktc/cleanup
```

**POST /api/ktc/refresh** - Refresh KTC rankings for specific configuration
- Query Parameters:
  - `is_redraft`: "true" or "false" (default: "false")
  - `league_format`: "1qb" or "superflex" (default: "1qb")
  - `tep_level`: "", "tep", "tepp", or "teppp" (default: "")

**GET /api/ktc/rankings** - Get stored rankings with filtering
- Same query parameters as refresh endpoint

**POST /api/ktc/cleanup** - Clean up incomplete data
- Same query parameters as refresh endpoint

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
POST /api/sleeper/league/{league_id}/refresh
```

**GET /api/sleeper/league/{league_id}** - Get comprehensive league data
**GET /api/sleeper/league/{league_id}/rosters** - Get rosters only
**GET /api/sleeper/league/{league_id}/users** - Get users only
**POST /api/sleeper/league/{league_id}/refresh** - Refresh league data

### 📊 Sleeper Research Data
```
GET /api/sleeper/players/research/{season}
POST /api/sleeper/players/research/{season}/refresh
```

**GET /api/sleeper/players/research/{season}** - Get research data
- Query Parameters:
  - `week`: Week number (default: 1)
  - `league_type`: 1=redraft, 2=dynasty (default: 2)

**POST /api/sleeper/players/research/{season}/refresh** - Refresh research
- Same query parameters as GET endpoint


## 🎮 How to Use

### 1. **First-Time Setup**
```bash
# Load KTC data first
curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex"

# Then get rankings
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&tep_level=tep"
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
curl "http://localhost:5000/api/ktc/rankings?league_format=superflex&is_redraft=false&tep_level=tep"

# Redraft 1QB Standard
curl "http://localhost:5000/api/ktc/rankings?league_format=1qb&is_redraft=true"

# Dynasty 1QB with maximum TEP
curl "http://localhost:5000/api/ktc/rankings?league_format=1qb&is_redraft=false&tep_level=teppp"
```

### League Management
```bash
# Get league data
curl "http://localhost:5000/api/sleeper/league/1210364682523656192"

# Get only rosters
curl "http://localhost:5000/api/sleeper/league/1210364682523656192/rosters"

# Refresh league data
curl -X POST "http://localhost:5000/api/sleeper/league/1210364682523656192/refresh"
```

### Research Data
```bash
# Get 2024 dynasty research
curl "http://localhost:5000/api/sleeper/players/research/2024?league_type=2"

# Get 2024 redraft week 10 research  
curl "http://localhost:5000/api/sleeper/players/research/2024?week=10&league_type=1"
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
# ❌ Don't call refresh endpoints repeatedly
curl -X POST /api/ktc/refresh  # Takes 30-60 seconds

# ✅ Call refresh once, then use cached data
curl -X POST /api/ktc/refresh  # One-time setup
curl /api/ktc/rankings         # Fast cached responses

# ✅ Use database-first endpoints for speed
curl /api/sleeper/league/123456789 # Checks cache first, API fallback
```

### **Gunicorn Multi-Worker Setup**
- **9 worker processes** for concurrent request handling
- **Load balancing** across CPU cores
- **Process isolation** prevents blocking between requests

## 🚀 Getting Started

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the server:**
   ```bash
   ./startup.sh
   ```

3. **Test the API:**
   ```bash
   curl http://localhost:5000/api/ktc/health
   ```

4. **Load initial data:**
   ```bash
   curl -X POST "http://localhost:5000/api/ktc/refresh?league_format=superflex"
   ```

5. **Get player data:**
   ```bash
   curl "http://localhost:5000/api/ktc/rankings?league_format=superflex"
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
- Use the refresh endpoints sparingly to avoid rate limiting
- Cache responses on your end when possible
- The API automatically handles database caching for optimal performance
