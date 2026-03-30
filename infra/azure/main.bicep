// Azure Container Apps deployment for FutureSelf.
//
// Uses system-assigned managed identity for:
//   - Pulling images from ACR (AcrPull role)
//   - Authenticating to Azure AI Foundry (Cognitive Services OpenAI User role)
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file infra/azure/main.bicep \
//     --parameters containerImage=<acr>.azurecr.io/futureself:latest \
//                  acrName=<acr> \
//                  azureFoundryEndpoint=https://<account>.services.ai.azure.com \
//                  foundryAccountName=<account>

@description('Name of the Container Apps Environment')
param environmentName string = 'futureself-env'

@description('Name of the Container App')
param appName string = 'futureself'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Container image to deploy (e.g. myacr.azurecr.io/futureself:latest)')
param containerImage string

@description('Name of the Azure Container Registry (without .azurecr.io)')
param acrName string

@description('Azure AI Foundry endpoint URL (e.g. https://<account>.services.ai.azure.com)')
param azureFoundryEndpoint string

@description('Name of the Cognitive Services account backing Foundry')
param foundryAccountName string

@description('Application Insights connection string (optional)')
@secure()
param appInsightsConnectionString string = ''

// ---- Existing resources (looked up, not created) ----
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryAccountName
}

// ---- Log Analytics Workspace ----
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ---- Container Apps Environment ----
resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---- Container App (with system-assigned managed identity) ----
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: concat([
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
      ], appInsightsConnectionString != '' ? [
        { name: 'appinsights-conn', value: appInsightsConnectionString }
      ] : [])
    }
    template: {
      containers: [
        {
          name: appName
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            { name: 'FUTURESELF_LLM_PROVIDER', value: 'azure_foundry' }
            { name: 'AZURE_FOUNDRY_ENDPOINT', value: azureFoundryEndpoint }
          ], appInsightsConnectionString != '' ? [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-conn' }
          ] : [])
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

// ---- Role assignments for the Container App's managed identity ----

// AcrPull — allows the Container App to pull images from ACR
@description('AcrPull built-in role ID')
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, acr.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services OpenAI User — allows the Container App to call Foundry inference
@description('Cognitive Services OpenAI User built-in role ID')
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource foundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, foundryAccount.id, cognitiveServicesOpenAIUserRoleId)
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output principalId string = containerApp.identity.principalId
