<#
.SYNOPSIS
    Syncs Approved Revit families from the Notion database to the AUDITED folder.

.DESCRIPTION
    Queries the "Revit Families" Notion database for all entries with Review Status = "Approved",
    then copies each source file to the AUDITED folder under its Category subfolder,
    renaming it to the Proposed Name.

.PARAMETER NotionToken
    Your Notion integration token (starts with "secret_...").
    If omitted, the script reads it from notion_token.txt in the same folder.

.PARAMETER DestRoot
    The root AUDITED folder. Defaults to the folder where this script lives.

.PARAMETER DryRun
    Preview what would be copied without actually copying anything.

.EXAMPLE
    .\Sync-ApprovedFamilies.ps1
    .\Sync-ApprovedFamilies.ps1 -DryRun
    .\Sync-ApprovedFamilies.ps1 -NotionToken "secret_abc123..."

.NOTES
    FIRST-TIME SETUP:
    1. Go to https://www.notion.so/profile/integrations and create a new integration.
    2. Copy the "Internal Integration Token" (starts with secret_...).
    3. Open your Revit Families Notion database, click the 3-dot menu > Connections,
       and connect your integration so it has read access.
    4. Paste the token into a file called "notion_token.txt" in the same folder as this script.
#>

param(
    [string]$NotionToken = "",
    [string]$DestRoot    = $PSScriptRoot,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ── Configuration ────────────────────────────────────────────────────────────

$DATABASE_ID = "e561580b-eff2-4323-95b0-ef2db491dd6f"
$TOKEN_FILE  = Join-Path $PSScriptRoot "notion_token.txt"

# ── Resolve token ─────────────────────────────────────────────────────────────

if (-not $NotionToken) {
    if (Test-Path $TOKEN_FILE) {
        $NotionToken = (Get-Content $TOKEN_FILE -Raw).Trim()
    } else {
        Write-Host ""
        Write-Host "ERROR: No Notion token found." -ForegroundColor Red
        Write-Host ""
        Write-Host "FIRST-TIME SETUP:" -ForegroundColor Yellow
        Write-Host "  1. Go to https://www.notion.so/profile/integrations"
        Write-Host "  2. Create a new integration and copy the token (starts with secret_...)"
        Write-Host "  3. In Notion, open the Revit Families database > 3-dot menu > Connections"
        Write-Host "     and connect your integration."
        Write-Host "  4. Create this file and paste the token into it:"
        Write-Host "     $TOKEN_FILE" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }
}

# ── Helper: safely read a Notion property ────────────────────────────────────

function Get-TextProp($props, $name) {
    try { $props.$name.rich_text[0].plain_text } catch { "" }
}

function Get-TitleProp($props, $name) {
    try { $props.$name.title[0].plain_text } catch { "" }
}

function Get-SelectProp($props, $name) {
    try { $props.$name.select.name } catch { "" }
}

# ── Helper: write Audited File Location back to a Notion page ─────────────────

function Set-AuditedLocation($pageId, $filePath) {
    $body = @{
        properties = @{
            "Audited File Location" = @{
                rich_text = @(
                    @{ type = "text"; text = @{ content = $filePath } }
                )
            }
        }
    }
    $bodyJson = $body | ConvertTo-Json -Depth 8
    $req = [System.Net.WebRequest]::Create("https://api.notion.com/v1/pages/$pageId")
    $req.Method      = "PATCH"
    $req.ContentType = "application/json"
    $req.Headers.Add("Authorization",  "Bearer $NotionToken")
    $req.Headers.Add("Notion-Version", "2022-06-28")
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)
    $req.ContentLength = $bytes.Length
    $stream = $req.GetRequestStream()
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Close()
    $res = $req.GetResponse()
    $res.Close()
}

# ── Query Notion database (paginated) ────────────────────────────────────────

Write-Host ""
Write-Host "Querying Notion for Approved families..." -ForegroundColor Cyan

$allPages = @()
$cursor   = $null
$pageNum  = 0

do {
    $pageNum++
    Write-Host "  Fetching page $pageNum..." -ForegroundColor DarkCyan

    $body = @{
        filter    = @{
            property = "Review Status"
            status   = @{ equals = "Approved" }
        }
        page_size = 100
    }
    if ($cursor) { $body.start_cursor = $cursor }

    try {
        $bodyJson = $body | ConvertTo-Json -Depth 5
        $req = [System.Net.WebRequest]::Create("https://api.notion.com/v1/databases/$DATABASE_ID/query")
        $req.Method      = "POST"
        $req.ContentType = "application/json"
        $req.Headers.Add("Authorization",  "Bearer $NotionToken")
        $req.Headers.Add("Notion-Version", "2022-06-28")
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)
        $req.ContentLength = $bytes.Length
        $stream = $req.GetRequestStream()
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Close()
        $res          = $req.GetResponse()
        $reader       = [System.IO.StreamReader]::new($res.GetResponseStream())
        $responseText = $reader.ReadToEnd()
        $reader.Close(); $res.Close()
        # PS 5.1: ConvertFrom-Json chokes on empty-string property names ("":"...") that
        # Notion includes for unnamed multi_select columns — rename them before parsing.
        $responseText = $responseText -replace '""\s*:', '"__unnamed__":'
        $response = $responseText | ConvertFrom-Json
    } catch {
        Write-Host "ERROR calling Notion API: $_" -ForegroundColor Red
        Write-Host "Check that your token is valid and the integration has access to the database."
        exit 1
    }

    $allPages += $response.results
    $cursor = if ($response.has_more) { $response.next_cursor } else { $null }

} while ($cursor)

Write-Host "  Found $($allPages.Count) Approved entries." -ForegroundColor Green
Write-Host ""

# ── Process each entry ───────────────────────────────────────────────────────

$copied        = 0
$upToDate      = 0
$notFound      = 0
$noData        = 0
$errored       = 0
$notionUpdated = 0
$notionFailed  = 0

foreach ($page in $allPages) {

    $props        = $page.properties
    $familyName   = Get-TitleProp  $props "Family Name"
    $location     = Get-TextProp   $props "Location"
    $proposedName = Get-TextProp   $props "Proposed Name"
    $category     = Get-SelectProp $props "Category"

    # Skip entries missing required fields
    if (-not $location -or -not $proposedName -or -not $category) {
        Write-Host "SKIP (missing data): $familyName" -ForegroundColor Yellow
        $noData++
        continue
    }

    $ext          = [System.IO.Path]::GetExtension($location)
    if (-not $ext) { $ext = ".rfa" }
    $destFileName = $proposedName + $ext
    $destFolder   = Join-Path $DestRoot $category
    $destFile     = Join-Path $destFolder $destFileName

    # Ensure destination folder exists
    if (-not (Test-Path $destFolder)) {
        if (-not $DryRun) {
            New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
        }
        Write-Host "  Created folder: $category" -ForegroundColor DarkCyan
    }

    # Check source exists
    if (-not (Test-Path $location)) {
        Write-Host "NOT FOUND : [$familyName]  $location" -ForegroundColor Red
        $notFound++
        continue
    }

    # Skip if destination is already up-to-date; backfill Notion if location field is blank
    if (Test-Path $destFile) {
        $srcTime = (Get-Item $location).LastWriteTimeUtc
        $dstTime = (Get-Item $destFile).LastWriteTimeUtc
        if ($srcTime -le $dstTime) {
            Write-Host "UP-TO-DATE: $category\$destFileName" -ForegroundColor DarkGray
            $upToDate++

            $currentLocation = Get-TextProp $props "Audited File Location"
            if (-not $DryRun -and -not $currentLocation) {
                try {
                    Set-AuditedLocation $page.id $destFile
                    Write-Host "  NOTION  : 'Audited File Location' backfilled" -ForegroundColor DarkGreen
                    $notionUpdated++
                } catch {
                    Write-Host "  NOTION  : Failed to backfill 'Audited File Location' -- $_" -ForegroundColor Yellow
                    $notionFailed++
                }
            }
            continue
        }
    }

    # Copy (or preview)
    if ($DryRun) {
        Write-Host "[DRY RUN]  $familyName  ->  $category\$destFileName" -ForegroundColor Magenta
        Write-Host "           Notion 'Audited File Location' would be set to: $destFile" -ForegroundColor DarkMagenta
        $copied++
    } else {
        try {
            Copy-Item -Path $location -Destination $destFile -Force
            Write-Host "COPIED    : $familyName  ->  $category\$destFileName" -ForegroundColor Green
            $copied++
        } catch {
            Write-Host "ERROR     : $familyName  --  $_" -ForegroundColor Red
            $errored++
            continue
        }

        # Write destination path back to Notion
        try {
            Set-AuditedLocation $page.id $destFile
            Write-Host "  NOTION  : 'Audited File Location' updated" -ForegroundColor DarkGreen
            $notionUpdated++
        } catch {
            Write-Host "  NOTION  : Failed to update 'Audited File Location' -- $_" -ForegroundColor Yellow
            $notionFailed++
        }
    }
}

# ── Summary ──────────────────────────────────────────────────────────────────

$label = if ($DryRun) { " (DRY RUN)" } else { "" }
Write-Host ""
Write-Host "════════════════ SUMMARY$label ════════════════" -ForegroundColor White
Write-Host "  Copied          : $copied"         -ForegroundColor Green
Write-Host "  Notion updated  : $notionUpdated"  -ForegroundColor $(if ($notionUpdated -gt 0) { "Green" } else { "DarkGray" })
Write-Host "  Up-to-date      : $upToDate"       -ForegroundColor DarkGray
Write-Host "  Source missing  : $notFound"       -ForegroundColor $(if ($notFound -gt 0) { "Red" } else { "DarkGray" })
Write-Host "  Missing data    : $noData"         -ForegroundColor $(if ($noData   -gt 0) { "Yellow" } else { "DarkGray" })
Write-Host "  Copy errors     : $errored"        -ForegroundColor $(if ($errored  -gt 0) { "Red" } else { "DarkGray" })
Write-Host "  Notion failures : $notionFailed"   -ForegroundColor $(if ($notionFailed -gt 0) { "Yellow" } else { "DarkGray" })
Write-Host ""
