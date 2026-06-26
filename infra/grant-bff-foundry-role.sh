#!/usr/bin/env bash
# Grant the BFF Container App's managed identity invoke rights on the Foundry
# hosted agent (spec §11). Run this ONCE, with credentials that have Owner or
# User Access Administrator on the Foundry account — the deploy workflow attempts
# the same grant but will skip it if its CI principal lacks that permission.
#
# Usage:
#   RG=<resource-group> \
#   FOUNDRY_RESOURCE_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>" \
#   ./infra/grant-bff-foundry-role.sh
#
# Optional: APP=futureself (Container App name; default below).
set -euo pipefail

APP="${APP:-futureself}"
: "${RG:?Set RG to the Container App's resource group}"
: "${FOUNDRY_RESOURCE_ID:?Set FOUNDRY_RESOURCE_ID to the Foundry account (or project) ARM id}"

# "Azure AI User" / "Foundry User" — reader on the project/account + data-plane
# actions (agent invocation). Pinned by GUID to survive the display-name rename.
ROLE_ID="53ca6127-db72-4b80-b1b0-d745d6d5456d"

echo "Ensuring system-assigned identity on Container App '$APP'..."
PRINCIPAL_ID=$(az containerapp identity assign -n "$APP" -g "$RG" \
  --system-assigned --query principalId -o tsv)
echo "  principalId: $PRINCIPAL_ID"

echo "Granting Foundry invoke role on $FOUNDRY_RESOURCE_ID ..."
az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "$ROLE_ID" \
  --scope "$FOUNDRY_RESOURCE_ID"

echo "Done. The BFF can now call the hosted agent with its managed identity."
