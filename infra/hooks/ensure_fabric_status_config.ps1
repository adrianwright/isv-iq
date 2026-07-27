[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$required = @(
  "AZURE_SUBSCRIPTION_ID",
  "AZURE_RESOURCE_GROUP",
  "API_CONTAINER_APP_NAME",
  "FABRIC_CAPACITY_RESOURCE_GROUP",
  "FABRIC_CAPACITY_NAME"
)
$missing = @($required | Where-Object { -not (Get-Item "env:$_" -ErrorAction SilentlyContinue).Value })
if ($missing.Count -gt 0) {
  throw "Missing required AZD environment values: $($missing -join ', ')."
}

az account set --subscription $env:AZURE_SUBSCRIPTION_ID | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Failed to select Azure subscription $env:AZURE_SUBSCRIPTION_ID."
}

$desired = [ordered]@{
  AZURE_SUBSCRIPTION_ID = $env:AZURE_SUBSCRIPTION_ID
  FABRIC_CAPACITY_RG     = $env:FABRIC_CAPACITY_RESOURCE_GROUP
  FABRIC_CAPACITY_NAME   = $env:FABRIC_CAPACITY_NAME
}
$currentJson = az containerapp show `
  --name $env:API_CONTAINER_APP_NAME `
  --resource-group $env:AZURE_RESOURCE_GROUP `
  --query "properties.template.containers[0].env" `
  --output json
if ($LASTEXITCODE -ne 0) {
  throw "Failed to read Container App $env:API_CONTAINER_APP_NAME."
}

$current = @{}
@($currentJson | ConvertFrom-Json) | ForEach-Object {
  if ($_.name -and $null -ne $_.value) {
    $current[$_.name] = [string]$_.value
  }
}
$requiresUpdate = $false
foreach ($entry in $desired.GetEnumerator()) {
  if ($current[$entry.Key] -ne $entry.Value) {
    $requiresUpdate = $true
    break
  }
}
if (-not $requiresUpdate) {
  Write-Host "Fabric capacity status settings are already current." -ForegroundColor Green
  exit 0
}

$setArguments = @(
  "AZURE_SUBSCRIPTION_ID=$($desired.AZURE_SUBSCRIPTION_ID)",
  "FABRIC_CAPACITY_RG=$($desired.FABRIC_CAPACITY_RG)",
  "FABRIC_CAPACITY_NAME=$($desired.FABRIC_CAPACITY_NAME)"
)
az containerapp update `
  --name $env:API_CONTAINER_APP_NAME `
  --resource-group $env:AZURE_RESOURCE_GROUP `
  --set-env-vars $setArguments `
  --output none
if ($LASTEXITCODE -ne 0) {
  throw "Failed to restore Fabric capacity status settings."
}

Write-Host "Restored Fabric capacity status settings on $env:API_CONTAINER_APP_NAME." -ForegroundColor Green
