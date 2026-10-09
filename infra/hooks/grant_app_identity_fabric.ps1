[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Require-EnvironmentValue {
  param([Parameter(Mandatory)][string]$Name)
  $value = [Environment]::GetEnvironmentVariable($Name, "Process")
  if ([string]::IsNullOrWhiteSpace($value)) {
    throw "Required azd environment variable '$Name' is not set."
  }
  return $value
}

$subscription = Require-EnvironmentValue "AZURE_SUBSCRIPTION_ID"
$resourceGroup = Require-EnvironmentValue "AZURE_RESOURCE_GROUP"
$identityName = Require-EnvironmentValue "AZURE_MANAGED_IDENTITY_NAME"
$workspaceId = Require-EnvironmentValue "ISV_FABRIC_WORKSPACE_ID"
$capacityResourceGroup = Require-EnvironmentValue "FABRIC_CAPACITY_RESOURCE_GROUP"
$capacityName = Require-EnvironmentValue "FABRIC_CAPACITY_NAME"

az account set --subscription $subscription | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Failed to select Azure subscription $subscription."
}

$principalId = az identity show -n $identityName -g $resourceGroup --query principalId -o tsv
if ($LASTEXITCODE -ne 0 -or -not $principalId) {
  throw "Managed identity $identityName was not found in resource group $resourceGroup."
}

$fabricToken = az account get-access-token --scope "https://api.fabric.microsoft.com/.default" `
  --query accessToken -o tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or -not $fabricToken) {
  throw "Failed to acquire a Microsoft Fabric access token."
}

$headers = @{ Authorization = "Bearer $fabricToken"; "Content-Type" = "application/json" }
$assignmentsUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/roleAssignments"
$assignmentUri = "$assignmentsUri/$principalId"
$body = @{
  principal = @{ id = $principalId; type = "ServicePrincipal" }
  role = "Member"
} | ConvertTo-Json
$membershipConfirmed = $false
for ($attempt = 0; $attempt -lt 5; $attempt++) {
  try {
    Invoke-RestMethod -Headers $headers -Uri $assignmentUri | Out-Null
    $membershipConfirmed = $true
    break
  } catch {
    if ($attempt -lt 4) {
      Start-Sleep (2 * ($attempt + 1))
    }
  }
}
if ($membershipConfirmed) {
  Write-Host "$identityName already has Fabric workspace access." -ForegroundColor DarkGray
} else {
  Invoke-RestMethod -Method Post -Headers $headers -Uri $assignmentsUri -Body $body | Out-Null
  Write-Host "Granted $identityName Member on Fabric workspace $workspaceId." -ForegroundColor Green
}

$capacityScope = (
  "/subscriptions/$subscription/resourceGroups/$capacityResourceGroup" +
  "/providers/Microsoft.Fabric/capacities/$capacityName"
)
$readerAssignment = az role assignment list --assignee-object-id $principalId `
  --scope $capacityScope --role Reader --query "[0].id" -o tsv
if ($LASTEXITCODE -ne 0) {
  throw "Failed to inspect Reader access on Fabric capacity $capacityName."
}
if (-not $readerAssignment) {
  az role assignment create --assignee-object-id $principalId `
    --assignee-principal-type ServicePrincipal --role Reader --scope $capacityScope `
    --only-show-errors | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to grant Reader on Fabric capacity $capacityName."
  }
  Write-Host "Granted $identityName Reader on Fabric capacity $capacityName." -ForegroundColor Green
} else {
  Write-Host "$identityName already has Reader on Fabric capacity $capacityName." -ForegroundColor DarkGray
}
