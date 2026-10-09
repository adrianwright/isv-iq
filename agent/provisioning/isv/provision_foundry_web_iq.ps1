<#
.SYNOPSIS
  Provision isolated Foundry IQ and Web IQ knowledge bases for the ISV renewal scenario.
.DESCRIPTION
  Uploads data/isv/foundry_docs to an explicit storage account, creates an Azure Blob knowledge
  source and renewal knowledge base, creates a web knowledge source and external-signal knowledge
  base, and smoke-tests both retrieval paths. It never discovers or defaults to unrelated resources.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Subscription,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ResourceGroup,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$FoundryAccount,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$SearchService,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$SearchResourceGroup,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$StorageAccount,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Container,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ChatDeployment,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$ChatModel,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$EmbeddingDeployment,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$KnowledgeSourceName,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$KnowledgeBaseName,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$WebKnowledgeSourceName,
  [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$WebKnowledgeBaseName,
  [string]$Location = "eastus2",
  [string]$DocsDirectory = "",
  [string]$ApiVersion = "2026-05-01-preview"
)

$ErrorActionPreference = "Stop"
az account set --subscription $Subscription | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Failed to select Azure subscription $Subscription."
}
$repo = (Resolve-Path "$PSScriptRoot\..\..\..").Path
if (-not $DocsDirectory) {
  $DocsDirectory = Join-Path $repo "data\isv\foundry_docs"
}
if (-not (Test-Path $DocsDirectory -PathType Container)) {
  throw "ISV Foundry document directory not found: $DocsDirectory"
}
$documents = @(Get-ChildItem $DocsDirectory -Filter *.md)
if ($documents.Count -lt 5) {
  throw "Expected at least five ISV Foundry documents in $DocsDirectory."
}

function Get-SearchHeaders {
  $token = az account get-access-token --scope "https://search.azure.com/.default" `
    --query accessToken -o tsv --only-show-errors
  if ($LASTEXITCODE -ne 0 -or -not $token) {
    throw "Failed to acquire an Azure AI Search token."
  }
  return @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
}

$searchEndpoint = "https://$SearchService.search.windows.net"
$tags = @("project=microsoft-iq-isv", "scenario=customer-renewal", "env=poc")

Write-Host "1) Validate Foundry and Search resources" -ForegroundColor Cyan
$foundry = az cognitiveservices account show -n $FoundryAccount -g $ResourceGroup -o json |
  ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $foundry.kind -ne "AIServices") {
  throw "$FoundryAccount must be an existing AIServices account."
}
$search = az search service show -n $SearchService -g $SearchResourceGroup -o json |
  ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $search.id) {
  throw "Azure AI Search service $SearchService was not found."
}
foreach ($deployment in @($ChatDeployment, $EmbeddingDeployment)) {
  az cognitiveservices account deployment show -n $FoundryAccount -g $ResourceGroup `
    --deployment-name $deployment --only-show-errors | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Required model deployment $deployment does not exist on $FoundryAccount."
  }
}
Write-Host "   Foundry and Search resources verified" -ForegroundColor Green

Write-Host "2) Upload isolated ISV knowledge corpus" -ForegroundColor Cyan
if (-not (az storage account show -n $StorageAccount -g $ResourceGroup 2>$null)) {
  az storage account create -n $StorageAccount -g $ResourceGroup -l $Location `
    --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false `
    --min-tls-version TLS1_2 --tags $tags | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create storage account $StorageAccount."
  }
}
$storageId = az storage account show -n $StorageAccount -g $ResourceGroup `
  --query id -o tsv --only-show-errors
$searchPrincipalId = az search service show -n $SearchService -g $SearchResourceGroup `
  --query identity.principalId -o tsv --only-show-errors
$armToken = az account get-access-token --resource https://management.azure.com/ `
  --query accessToken -o tsv --only-show-errors
$tokenPayload = $armToken.Split(".")[1].Replace("-", "+").Replace("_", "/")
while ($tokenPayload.Length % 4) { $tokenPayload += "=" }
$operatorId = (
  [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($tokenPayload)) |
    ConvertFrom-Json
).oid
if (-not $storageId -or -not $searchPrincipalId -or -not $operatorId) {
  throw "Could not resolve storage, Search identity, or signed-in operator IDs."
}
az role assignment create --assignee-object-id $searchPrincipalId `
  --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" `
  --scope $storageId --only-show-errors | Out-Null
az role assignment create --assignee-object-id $operatorId `
  --assignee-principal-type User --role "Storage Blob Data Contributor" `
  --scope $storageId --only-show-errors | Out-Null
$connectionString = "ResourceId=$storageId;"
Start-Sleep 15
az storage container create -n $Container --account-name $StorageAccount `
  --auth-mode login --only-show-errors | Out-Null
foreach ($document in $documents) {
  az storage blob upload --account-name $StorageAccount --auth-mode login `
    -c $Container -f $document.FullName -n $document.Name --overwrite --only-show-errors |
    Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload $($document.Name)."
  }
}
Write-Host "   uploaded $($documents.Count) synthetic documents" -ForegroundColor Green

Write-Host "3) Provision ISV Foundry IQ knowledge source and knowledge base" -ForegroundColor Cyan
$foundryUri = "https://$FoundryAccount.openai.azure.com"
$foundryKey = az cognitiveservices account keys list -n $FoundryAccount -g $ResourceGroup `
  --query key1 -o tsv --only-show-errors
$knowledgeSource = @{
  name = $KnowledgeSourceName
  kind = "azureBlob"
  description = "Synthetic contract, support, pricing, product, and renewal knowledge for Microsoft IQ for ISVs."
  azureBlobParameters = @{
    connectionString = $connectionString
    containerName = $Container
    ingestionParameters = @{
      contentExtractionMode = "minimal"
      embeddingModel = @{
        kind = "azureOpenAI"
        azureOpenAIParameters = @{
          resourceUri = $foundryUri
          deploymentId = $EmbeddingDeployment
          apiKey = $foundryKey
          modelName = "text-embedding-3-large"
        }
      }
      chatCompletionModel = @{
        kind = "azureOpenAI"
        azureOpenAIParameters = @{
          resourceUri = $foundryUri
          deploymentId = $ChatDeployment
          apiKey = $foundryKey
          modelName = $ChatModel
        }
      }
    }
  }
} | ConvertTo-Json -Depth 12
Invoke-RestMethod -Method Put -Headers (Get-SearchHeaders) `
  -Uri "$searchEndpoint/knowledgesources/$KnowledgeSourceName`?api-version=$ApiVersion" `
  -Body $knowledgeSource | Out-Null

$knowledgeBase = @{
  name = $KnowledgeBaseName
  description = "Customer renewal and expansion policy grounding for Microsoft IQ for ISVs."
  retrievalInstructions = "Retrieve contract terms, premium-support obligations, strategic renewal pricing approvals, AI Automation qualification guidance, and at-risk renewal recovery playbooks. Preserve account and renewal IDs such as ACC-1001 and REN-1001."
  answerInstructions = "Answer only from retrieved documents and cite every source. Distinguish policy from customer facts. Never promise pricing, service credits, roadmap dates, or commercial commitments. State when human approval is required."
  outputMode = "answerSynthesis"
  knowledgeSources = @(@{ name = $KnowledgeSourceName })
  models = @(@{
    kind = "azureOpenAI"
    azureOpenAIParameters = @{
      resourceUri = $foundryUri
      deploymentId = $ChatDeployment
      apiKey = $foundryKey
      modelName = $ChatModel
    }
  })
  retrievalReasoningEffort = @{ kind = "medium" }
} | ConvertTo-Json -Depth 12
Invoke-RestMethod -Method Put -Headers (Get-SearchHeaders) `
  -Uri "$searchEndpoint/knowledgebases/$KnowledgeBaseName`?api-version=$ApiVersion" `
  -Body $knowledgeBase | Out-Null

Write-Host "4) Provision ISV Web IQ search fallback" -ForegroundColor Cyan
$webSource = @{
  name = $WebKnowledgeSourceName
  kind = "web"
  description = "Current public leadership, strategy, and competitive context for ISV account intelligence."
} | ConvertTo-Json
Invoke-RestMethod -Method Put -Headers (Get-SearchHeaders) `
  -Uri "$searchEndpoint/knowledgesources/$WebKnowledgeSourceName`?api-version=$ApiVersion" `
  -Body $webSource | Out-Null

$webBase = @{
  name = $WebKnowledgeBaseName
  description = "External account, leadership, investment, and competitive grounding for Microsoft IQ for ISVs."
  retrievalInstructions = "Find current public facts about customer leadership changes, strategic investment, company priorities, and competing workflow automation offerings."
  answerInstructions = "Cite source URLs, distinguish verified public facts from inference, and do not make unsupported claims about private customer intent."
  outputMode = "answerSynthesis"
  knowledgeSources = @(@{ name = $WebKnowledgeSourceName })
  models = @(@{
    kind = "azureOpenAI"
    azureOpenAIParameters = @{
      resourceUri = $foundryUri
      deploymentId = $ChatDeployment
      apiKey = $foundryKey
      modelName = $ChatModel
    }
  })
  retrievalReasoningEffort = @{ kind = "low" }
} | ConvertTo-Json -Depth 12
Invoke-RestMethod -Method Put -Headers (Get-SearchHeaders) `
  -Uri "$searchEndpoint/knowledgebases/$WebKnowledgeBaseName`?api-version=$ApiVersion" `
  -Body $webBase | Out-Null

Write-Host "5) Smoke-test both knowledge bases" -ForegroundColor Cyan
Start-Sleep 20
foreach ($test in @(
  @{
    Name = $KnowledgeBaseName
    Question = "For renewal REN-1001, what approvals govern a three-year proposal and service-credit recommendation?"
  },
  @{
    Name = $WebKnowledgeBaseName
    Question = "What current public leadership, AI investment, and competitive signals are relevant to Contoso Unified School District?"
  }
)) {
  $body = @{
    messages = @(@{
      role = "user"
      content = @(@{ type = "text"; text = $test.Question })
    })
  } | ConvertTo-Json -Depth 8
  $result = Invoke-RestMethod -Method Post -Headers (Get-SearchHeaders) `
    -Uri "$searchEndpoint/knowledgebases/$($test.Name)/retrieve?api-version=$ApiVersion" `
    -Body $body
  $referenceCount = @($result.references).Count
  if ($referenceCount -eq 0) {
    throw "Knowledge base $($test.Name) returned no grounded references."
  }
  Write-Host "   $($test.Name): $referenceCount references" -ForegroundColor Green
}

Write-Host "Provisioned isolated ISV Foundry IQ and Web IQ search fallback." -ForegroundColor Green
