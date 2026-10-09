<#
.SYNOPSIS
  Create an isolated ISV Lakehouse and Fabric Data Agent for customer renewal intelligence.
.DESCRIPTION
  This script never defaults to another workspace or item name. The caller must provide the
  target ISV workspace and explicit resource names. It creates or reconciles:
    1. an ISV Lakehouse,
    2. an ISV Data Agent,
    3. the Lakehouse-only staging datasource,
    4. all tables declared by data/isv/fabric/manifest.json,
    5. customer-renewal AI instructions, then publishes the agent.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$WorkspaceId,
  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$LakehouseName,
  [string]$LakehouseId = "",
  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$DataAgentName,
  [string]$DataAgentId = "",
  [string]$ManifestPath = "",
  [switch]$PrepareOnly
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
if (-not $ManifestPath) {
  $ManifestPath = Join-Path $repo "data\isv\fabric\manifest.json"
}
$manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
if ($manifest.schemaVersion -ne "isv.fabric.v1") {
  throw "$ManifestPath is not an isv.fabric.v1 manifest."
}
$requiredTables = @($manifest.tables | ForEach-Object name)
if (-not $requiredTables) {
  throw "$ManifestPath contains no ISV Fabric tables."
}

$fabricToken = az account get-access-token --scope "https://api.fabric.microsoft.com/.default" `
  --query accessToken -o tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or -not $fabricToken) {
  throw "Failed to acquire a Microsoft Fabric access token."
}
function Get-FabricHeaders {
  @{ Authorization = "Bearer $fabricToken"; "Content-Type" = "application/json" }
}
function Wait-FabricOperation {
  param([Parameter(Mandatory)]$Response)
  if ($Response.StatusCode -ne 202) { return }
  $location = @($Response.Headers.Location)[0]
  if (-not $location) { throw "Fabric returned 202 without an operation location." }
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep 4
    $operation = Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri $location
    if ($operation.status -in @("Succeeded", "Completed")) { return }
    if ($operation.status -eq "Failed") {
      throw "Fabric operation failed: $($operation | ConvertTo-Json -Depth 8 -Compress)"
    }
  }
  throw "Fabric operation did not complete within two minutes."
}
$api = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId"

Write-Host "1) ISV Lakehouse" -ForegroundColor Cyan
if ($LakehouseId) {
  $lhId = $LakehouseId
} else {
  $lakehouse = (Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri "$api/lakehouses").value |
    Where-Object displayName -eq $LakehouseName |
    Select-Object -First 1
  if (-not $lakehouse) {
    $body = @{
      displayName = $LakehouseName
      description = "Synthetic customer renewal and expansion data for Microsoft IQ for ISVs."
    } | ConvertTo-Json
    $lakehouse = (
      Invoke-WebRequest -Method Post -Headers (Get-FabricHeaders) -Uri "$api/lakehouses" -Body $body
    ).Content | ConvertFrom-Json
  }
  $lhId = $lakehouse.id
}
Write-Host "   lakehouse=$LakehouseName ($lhId)" -ForegroundColor Green
Write-Host "   Set ISV_FABRIC_WS=$WorkspaceId and ISV_FABRIC_LH=$lhId before loading tables." -ForegroundColor Yellow

Write-Host "2) ISV Data Agent" -ForegroundColor Cyan
if ($DataAgentId) {
  $daId = $DataAgentId
} else {
  $agent = (Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri "$api/items").value |
    Where-Object { $_.type -eq "DataAgent" -and $_.displayName -eq $DataAgentName } |
    Select-Object -First 1
  if (-not $agent) {
    $body = @{
      displayName = $DataAgentName
      type = "DataAgent"
      description = "Customer renewal and expansion intelligence over synthetic ISV data."
    } | ConvertTo-Json
    $agent = (
      Invoke-WebRequest -Method Post -Headers (Get-FabricHeaders) -Uri "$api/items" -Body $body
    ).Content | ConvertFrom-Json
  }
  $daId = $agent.id
}
$base = "$api/dataAgents/$daId"
Write-Host "   data agent=$DataAgentName ($daId)" -ForegroundColor Green

Write-Host "3) Reconcile Lakehouse datasource" -ForegroundColor Cyan
$sources = @((Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri "$base/staging/datasources").value)
$lakehouseSource = $sources | Where-Object {
  $_.id -eq $lhId -or
  $_.itemReference.itemId -eq $lhId -or
  $_.lakehouseReference.itemId -eq $lhId
} | Select-Object -First 1
if (-not $lakehouseSource) {
  $body = @{
    type = "LakehouseTables"
    lakehouseReference = @{
      referenceType = "ById"
      itemId = $lhId
      workspaceId = $WorkspaceId
    }
  } | ConvertTo-Json -Depth 6
  $response = Invoke-WebRequest -Method Post -Headers (Get-FabricHeaders) `
    -Uri "$base/staging/datasources" -Body $body
  Wait-FabricOperation $response
  for ($attempt = 0; $attempt -lt 12; $attempt++) {
    Start-Sleep 5
    $sources = @((Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri "$base/staging/datasources").value)
    $lakehouseSource = $sources | Where-Object {
      $_.id -eq $lhId -or
      $_.itemReference.itemId -eq $lhId -or
      $_.lakehouseReference.itemId -eq $lhId
    } | Select-Object -First 1
    if ($lakehouseSource) { break }
  }
}
if (-not $lakehouseSource) {
  throw "The ISV Lakehouse datasource did not appear on $DataAgentName."
}
foreach ($source in @($sources | Where-Object { $_.id -ne $lakehouseSource.id })) {
  Invoke-WebRequest -Method Delete -Headers (Get-FabricHeaders) `
    -Uri "$base/staging/datasources/$($source.id)" | Out-Null
}
$remaining = $sources
for ($attempt = 0; $attempt -lt 12; $attempt++) {
  $remaining = @((Invoke-RestMethod -Headers (Get-FabricHeaders) -Uri "$base/staging/datasources").value)
  if ($remaining.Count -eq 1 -and $remaining[0].id -eq $lakehouseSource.id) { break }
  Start-Sleep 5
}
if ($remaining.Count -ne 1 -or $remaining[0].id -ne $lakehouseSource.id) {
  throw "Expected exactly one ISV Lakehouse datasource after reconciliation."
}
Write-Host "   Lakehouse-only datasource contract enforced" -ForegroundColor Green

if ($PrepareOnly) {
  Write-Host "   preparation complete; load the generated CSVs before publishing" -ForegroundColor Yellow
  Write-Host "   workspaceId=$WorkspaceId lakehouseId=$lhId dataAgentId=$daId" -ForegroundColor Yellow
  return
}

Write-Host "4) Select ISV tables" -ForegroundColor Cyan
$elements = "$base/staging/datasources/$($lakehouseSource.id)/elements"
$available = @()
$missing = $requiredTables
for ($attempt = 0; $attempt -lt 12; $attempt++) {
  try {
    $schemas = (Invoke-RestMethod -Headers (Get-FabricHeaders) `
      -Uri "${elements}?rootId=U2NoZW1hcw==").value
    $tablesContainer = (Invoke-RestMethod -Headers (Get-FabricHeaders) `
      -Uri "${elements}?rootId=$([uri]::EscapeDataString($schemas[0].id))").value |
      Where-Object displayName -eq "Tables" |
      Select-Object -First 1
    $available = @(
      (Invoke-RestMethod -Headers (Get-FabricHeaders) `
        -Uri "${elements}?rootId=$([uri]::EscapeDataString($tablesContainer.id))").value |
      Where-Object { -not $_.state -or $_.state -eq "Available" }
    )
    $availableNames = @($available | ForEach-Object displayName)
    $missing = @($requiredTables | Where-Object { $_ -notin $availableNames })
  } catch {
    $missing = $requiredTables
  }
  if (-not $missing) { break }
  Start-Sleep 5
}
if ($missing) {
  throw "ISV Lakehouse datasource is missing tables: $($missing -join ', ')."
}
foreach ($table in $available | Where-Object { $_.displayName -in $requiredTables }) {
  if ($table.isSelected -ne $true) {
    Invoke-RestMethod -Method Patch -Headers (Get-FabricHeaders) `
      -Uri "${elements}?id=$([uri]::EscapeDataString($table.id))" `
      -Body (@{ isSelected = $true } | ConvertTo-Json) | Out-Null
  }
}
$missingSelections = $requiredTables
for ($attempt = 0; $attempt -lt 12; $attempt++) {
  $selected = @(
    (Invoke-RestMethod -Headers (Get-FabricHeaders) `
      -Uri "${elements}?rootId=$([uri]::EscapeDataString($tablesContainer.id))").value |
    Where-Object { $_.isSelected -eq $true } |
    ForEach-Object displayName
  )
  $missingSelections = @($requiredTables | Where-Object { $_ -notin $selected })
  if (-not $missingSelections) { break }
  Start-Sleep 5
}
if ($missingSelections) {
  throw "ISV table selections did not propagate: $($missingSelections -join ', ')."
}

Write-Host "5) Instructions and publish" -ForegroundColor Cyan
$instructions = @"
You answer questions about synthetic customer renewal and expansion data using only the selected
ISV Lakehouse tables. Accounts connect to renewals, contracts, subscriptions, product usage,
support cases, invoices, success milestones, commitments, interactions, contacts, account-team
employees, expansion candidates, and external signals. Account IDs look like ACC-1001 and renewal
IDs look like REN-1001. For renewal risk, report exact ARR, renewal date, days to renewal, forecast,
adoption percentage and trend, open P1 count and SLA breaches, overdue invoices, commitments, and
expansion value. Distinguish recorded facts from recommendations. Give precise values and dates.
All data is synthetic and no action may be submitted automatically.
"@
Invoke-RestMethod -Method Patch -Headers (Get-FabricHeaders) -Uri "$base/staging/settings" `
  -Body (@{ aiInstructions = $instructions } | ConvertTo-Json) | Out-Null
$publishResponse = Invoke-WebRequest -Method Post -Headers (Get-FabricHeaders) -Uri "$base/staging/publish" `
  -Body (@{
    publishedDescription = "Microsoft IQ for ISVs customer renewal Data Agent v1"
  } | ConvertTo-Json)
Wait-FabricOperation $publishResponse

Write-Host "   PUBLISHED." -ForegroundColor Green
Write-Host "   workspaceId=$WorkspaceId lakehouseId=$lhId dataAgentId=$daId" -ForegroundColor Yellow
