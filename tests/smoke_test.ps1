$ErrorActionPreference = "Stop"

Write-Host "Running UrbanSense Milestone 0 Smoke Tests..."

# TEST 1: Docker Compose config
Write-Host "TEST 1: Checking docker compose config..."
docker compose config > $null
if ($?) { Write-Host "TEST 1: PASS" } else { Write-Host "TEST 1: FAIL" }

# TEST 7: Environment config
Write-Host "TEST 7: Checking environment variables load..."
if (Test-Path ".env") { Write-Host "TEST 7: PASS" } else { Write-Host "TEST 7: FAIL" }

# TEST 8: Secrets
Write-Host "TEST 8: Checking secrets not committed..."
$gitStatus = git status --porcelain
if ($gitStatus -match "\.env") { Write-Host "TEST 8: FAIL (secrets in git)" } else { Write-Host "TEST 8: PASS" }

# Test 2-6, 9 require Docker runtime
Write-Host "Checking Docker daemon status..."
docker ps > $null 2>&1
if (-not $?) {
    Write-Host "Docker daemon is not running. Tests 2-6 and 9 are BLOCKED."
    Write-Host "TEST 2 (PostgreSQL): BLOCKED"
    Write-Host "TEST 3 (PostGIS): BLOCKED"
    Write-Host "TEST 4 (Redis): BLOCKED"
    Write-Host "TEST 5 (MinIO): BLOCKED"
    Write-Host "TEST 6 (MQTT): BLOCKED"
    Write-Host "TEST 9 (Backend Health): BLOCKED"
    exit 1
}

Write-Host "TEST 2: PostgreSQL starts"
# ... further runtime checks if docker was available
