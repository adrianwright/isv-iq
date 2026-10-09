targetScope = 'resourceGroup'

@description('Azure region for new proof-of-concept resources.')
param location string = resourceGroup().location

@description('Tenant for Key Vault and managed-identity auth.')
param tenantId string

@description('API container image. azd deploy replaces this placeholder with the built ISV API image.')
param apiContainerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Port exposed by the API container.')
param apiContainerPort int = 8000

@description('Log Analytics workspace name.')
param logAnalyticsName string

@description('Application Insights component name.')
param appInsightsName string

@description('Container Apps managed environment name.')
param containerAppsEnvironmentName string

@description('Azure region for the Container Apps environment and API.')
param containerAppsLocation string = location

@description('Container App for the FastAPI backend.')
param apiContainerAppName string

@description('Static Web App for the React/Vite UI.')
param staticWebAppName string

@description('Azure region for the Static Web App resource.')
param staticWebAppLocation string = location

@description('Azure Container Registry for azd-built API images.')
param containerRegistryName string = take(toLower('msiqisv${uniqueString(resourceGroup().id)}acr'), 50)

@description('Key Vault for future app secrets. Prefer managed identity and avoid storing keys.')
param keyVaultName string = take(toLower('msiqisv${uniqueString(resourceGroup().id)}kv'), 24)

@description('User-assigned managed identity shared by the API and role assignments.')
param managedIdentityName string

@description('Existing Azure AI Search resource group. Referenced only; not recreated.')
param existingSearchResourceGroupName string

@description('Existing Azure AI Search service. Referenced only; not recreated.')
param existingSearchServiceName string

@description('Foundry IQ knowledge base name created by agent/provisioning.')
param isvFoundryKbName string

@description('Web knowledge base name used by live web search.')
param isvWebKbName string

@description('Native Microsoft Web IQ REST endpoint.')
param isvWebIqEndpoint string = 'https://api.microsoft.ai/v3/search/web'

@description('Existing Key Vault secret containing the native Web IQ evaluation API key.')
param isvWebIqApiKeySecretName string

@description('Optional Azure AI Search endpoint override. When empty, derived from existingSearchServiceName.')
param searchEndpoint string = ''

@description('Fabric workspace ID used by the API when live Fabric is enabled.')
param isvFabricWorkspaceId string

@description('Fabric Data Agent ID used by the API when live Fabric is enabled.')
param isvFabricDataAgentId string

@description('Resource group of the backing Fabric capacity used for the optional status indicator.')
param fabricCapacityResourceGroup string

@description('Backing Fabric capacity resource name used for the optional status indicator.')
param fabricCapacityName string

@description('Application client ID for the confidential Work IQ OBO registration.')
param workIqClientId string

@description('Application client ID for the operator-provided public SPA registration.')
param webClientId string

@description('Exact audience accepted by the Microsoft IQ for ISVs API access-token validator.')
param apiAudience string

@description('Delegated scope claim required by protected API endpoints.')
param apiRequiredScope string = 'access_as_user'

@description('Fully qualified delegated API scope requested by the SPA.')
param webApiScope string

@description('Existing exportable Key Vault certificate secret read by the API managed identity.')
param workIqClientCertificateSecretName string

@description('Work IQ A2A v1.0 gateway endpoint.')
param workIqEndpoint string = 'https://workiq.svc.cloud.microsoft/a2a/'

@description('Work IQ delegated resource scope used for OBO.')
param workIqScope string = 'api://workiq.svc.cloud.microsoft/.default'

@description('Enable live Work IQ integration. Disabled by default to preserve mock fallback behavior.')
param useLiveIsvWork bool = false

@description('Tags applied to every taggable new resource.')
param tags object = {
  project: 'microsoft-iq-isv'
  scenario: 'renewal-expansion'
  env: 'poc'
}

var effectiveSearchEndpoint = empty(searchEndpoint) ? 'https://${existingSearchServiceName}.search.windows.net' : searchEndpoint

resource deployedKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

module identity 'modules/identity.bicep' = {
  name: 'msiqisv-identity'
  params: {
    location: location
    managedIdentityName: managedIdentityName
    tags: tags
  }
}

module observability 'modules/observability.bicep' = {
  name: 'msiqisv-observability'
  params: {
    location: location
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
    tags: tags
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'msiqisv-keyvault'
  params: {
    location: location
    tenantId: tenantId
    keyVaultName: keyVaultName
    apiPrincipalId: identity.outputs.principalId
    roleAssignmentSeed: managedIdentityName
    tags: tags
  }
}

module apps 'modules/apps.bicep' = {
  name: 'msiqisv-apps'
  params: {
    location: location
    containerAppsLocation: containerAppsLocation
    containerAppsEnvironmentName: containerAppsEnvironmentName
    apiContainerAppName: apiContainerAppName
    apiContainerImage: apiContainerImage
    apiContainerPort: apiContainerPort
    staticWebAppName: staticWebAppName
    staticWebAppLocation: staticWebAppLocation
    containerRegistryName: containerRegistryName
    logAnalyticsCustomerId: observability.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: observability.outputs.logAnalyticsSharedKey
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    identityResourceId: identity.outputs.identityId
    identityPrincipalId: identity.outputs.principalId
    identityClientId: identity.outputs.clientId
    isvSearchEndpoint: effectiveSearchEndpoint
    isvFoundryKbName: isvFoundryKbName
    isvWebKbName: isvWebKbName
    isvWebIqEndpoint: isvWebIqEndpoint
    isvWebIqApiKey: deployedKeyVault.getSecret(isvWebIqApiKeySecretName)
    isvFabricWorkspaceId: isvFabricWorkspaceId
    isvFabricDataAgentId: isvFabricDataAgentId
    azureSubscriptionId: subscription().subscriptionId
    fabricCapacityResourceGroup: fabricCapacityResourceGroup
    fabricCapacityName: fabricCapacityName
    tenantId: tenantId
    apiAudience: apiAudience
    apiRequiredScope: apiRequiredScope
    workIqClientId: workIqClientId
    workIqClientCertificatePfx: deployedKeyVault.getSecret(workIqClientCertificateSecretName)
    workIqClientCertificateSecretName: workIqClientCertificateSecretName
    workIqEndpoint: workIqEndpoint
    workIqScope: workIqScope
    useLiveIsvWork: useLiveIsvWork
    keyVaultUri: keyVault.outputs.keyVaultUri
    tags: tags
  }
}

module searchRole 'modules/search-role.bicep' = {
  name: 'msiqisv-api-search-reader'
  scope: resourceGroup(subscription().subscriptionId, existingSearchResourceGroupName)
  params: {
    searchServiceName: existingSearchServiceName
    principalId: identity.outputs.principalId
    roleAssignmentSeed: managedIdentityName
  }
}

output apiUrl string = apps.outputs.apiUrl
output staticWebAppName string = staticWebAppName
output applicationInsightsConnectionString string = observability.outputs.appInsightsConnectionString
output managedIdentityClientId string = identity.outputs.clientId
output AZURE_MANAGED_IDENTITY_NAME string = managedIdentityName
output keyVaultUri string = keyVault.outputs.keyVaultUri
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = apps.outputs.containerRegistryEndpoint
output API_URL string = apps.outputs.apiUrl
output WEB_URL string = apps.outputs.staticWebAppUrl
output VITE_API_BASE_URL string = apps.outputs.apiUrl
output VITE_ENTRA_TENANT_ID string = tenantId
output VITE_ENTRA_CLIENT_ID string = webClientId
output VITE_API_SCOPE string = webApiScope
