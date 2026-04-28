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
   
   # 3. Seed your league for weekly stats (first time — POST with required fields)
   curl -X POST "http://localhost:5001/api/sleeper/league/YOUR_LEAGUE_ID/stats/seed" \
     -H "Content-Type: application/json" \
     -d '{"league_name": "My League", "season": "2024", "league_type": "dynasty"}'

   # 4. Refresh weekly stats for a specific week (PUT; season/league_type read from DB)
   curl -X PUT "http://localhost:5001/api/sleeper/league/YOUR_LEAGUE_ID/stats/week/1"
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

## Route groups

### System health

```
GET /api/ktc/health
GET /api/maintenance/health
```

### Dashboard bundle (read-only, DB + Redis in production)

```
GET /api/dashboard/league/{league_id}
```

League bundle for the dashboard (rosters, merged players, research meta; optional per-player `stats` for weeks **1–17**). Params: `is_redraft`, `league_format`, `tep_level`, `season`. Vercel production: `REDIS_URL` required; responses include `X-Dashboard-League-Cache` and `Cache-Control`. Local: Redis optional.

### Maintenance (server-side secrets only)

```
GET|POST /api/maintenance/nightly-sync
GET /api/maintenance/prewarm
POST /api/maintenance/daily-refresh
```

- **nightly-sync, prewarm:** `Authorization: Bearer <CRON_SECRET>`. On Vercel **production** (`VERCEL_ENV=production`), `CRON_SECRET` must be set (requests without a valid Bearer token are rejected).
- **daily-refresh:** `X-Daily-Refresh-Secret` when `DAILY_REFRESH_SECRET` is set.  
  Pipeline: KTC formats → leagues → research (no full NFL Sleeper player export).

### KTC health (detail)

```
GET /api/ktc/health
```

KTC/database-oriented health check.

### 🏈 KTC Player Rankings

```
POST /api/ktc/refresh
PUT /api/ktc/refresh
GET /api/ktc/refresh/status/{job_id}
GET /api/ktc/rankings
POST /api/ktc/cleanup
```

**POST /api/ktc/refresh** - Enqueue KTC scrape + DB save (default **HTTP 202** with `job_id`); refetch dashboard or poll status until complete
**PUT /api/ktc/refresh** - Same as POST

- Query Parameters:
  - `is_redraft`: "true" or "false" (default: "false")
  - `league_format`: "1qb" or "superflex" (default: "1qb")
  - `tep_level`: "", "tep", "tepp", or "teppp" (default: "")
  - `sync`: "1" / "true" for blocking run (full JSON in response; can exceed one minute)

**GET /api/ktc/refresh/status/{job_id}** - Poll a job returned from 202 (fields: `status`, `error`, `summary`)

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
GET  /api/sleeper/league/{league_id}/stats/week/{week}
PUT  /api/sleeper/league/{league_id}/stats/week/{week}
POST /api/sleeper/league/{league_id}/stats/seed   ← first time only
PUT  /api/sleeper/league/{league_id}/stats/seed   ← subsequent updates
```

**GET /api/sleeper/league/{league_id}/stats/week/{week}** — Read weekly stats

- Optional query params: `season`, `league_type` (looked up from DB if omitted), `average=true` for season averages over **weeks 1–17** (week 18 excluded so end-of-season rests/tanking skew averages less)

**PUT /api/sleeper/league/{league_id}/stats/week/{week}** — Refresh weekly stats from Sleeper API

- `season` and `league_type` are read from the DB automatically; pass as query params to override.

**POST /api/sleeper/league/{league_id}/stats/seed** — Create league stats record (first time)

- Required body fields: `league_name`, `season`
- Optional: `league_type` (default `dynasty`), `scoring_settings`
- After upserting the record, automatically fetches all remaining weeks (from `last_week_updated + 1` through 18) from Sleeper and stores the scoring data. Response includes `last_week_updated` and a `weekly_stats` summary.

**PUT /api/sleeper/league/{league_id}/stats/seed** — Update existing league stats record

- All body fields optional; stored values are used for anything not provided.
- Same auto-fetch behavior as POST: fills in any weeks past `last_week_updated`.

### 🔬 Sleeper Research Data

```
GET /api/sleeper/players/research/{season}
POST /api/sleeper/players/research/{season}
PUT /api/sleeper/players/research/{season}
```

**GET /api/sleeper/players/research/{season}** - Get research data

- Query Parameters:
  - `week`: Week number (default: 1), or `all` for weeks 1-18
  - `league_type`: `dynasty` or `redraft` (default: `dynasty`)

**POST /api/sleeper/players/research/{season}** - Refresh research
**PUT /api/sleeper/players/research/{season}** - Update research

- Same query parameters as GET endpoint. `week=all` refreshes and saves weeks 1-18.

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

- **POST /api/ktc/refresh (default)**: A few seconds (ack + background work)
- **POST /api/ktc/refresh?sync=1**: Often over a minute (full scrape + DB in-request)
- **Cached data retrieval**: < 1 second (from local database)
- **Health checks**: < 100ms (database connection test)

### **Best Practices for Performance**

```bash
# Default: fast ack — poll status or refetch dashboard until ktcLastUpdated moves
curl -X POST "/api/ktc/refresh?league_format=superflex&is_redraft=false&tep_level=tep"
# curl "/api/ktc/refresh/status/<job_id>"

# Blocking (scripts / tests only when needed)
curl -X POST "/api/ktc/refresh?...&sync=1"

# ✅ After refresh completes, reads stay fast
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
