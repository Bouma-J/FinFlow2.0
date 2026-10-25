import type { CurrentUser } from "@/api/types";
import { hasAnyPerm } from "@/auth/permissions";

/** Permissions minimales pour afficher / accéder aux modules métier. */

export const PERM_CLIENTS = ["clients.view_client"] as const;
export const PERM_CLIENTS_CHANGE = ["clients.change_client"] as const;
export const PERM_CLIENTS_DELETE = ["clients.delete_client"] as const;
export const PERM_CREDITS = ["credits.view_creditapplication"] as const;
export const PERM_CREDIT_CREATE = ["credits.add_creditapplication"] as const;
export const PERM_CREDITS_CHANGE = ["credits.change_creditapplication"] as const;
export const PERM_PRODUCTS = ["catalog.view_creditproduct"] as const;
export const PERM_GUARANTEES = ["guarantees.view_guarantee"] as const;
export const PERM_GUARANTEES_ADD = ["guarantees.add_guarantee"] as const;
export const PERM_GUARANTEES_CHANGE = ["guarantees.change_guarantee"] as const;
export const PERM_SURETIES = ["sureties.view_surety"] as const;
export const PERM_TASKS = ["workflow.view_approvaltask"] as const;
export const PERM_SIMULATOR = ["credits.view_creditapplication"] as const;
export const PERM_RELEASES = [
  "guarantees.view_guaranteereleaserequest",
  "guarantees.initiate_guaranteereleaserequest",
] as const;
export const PERM_DATIONS = [
  "guarantees.view_dationrequest",
  "guarantees.initiate_dationrequest",
] as const;
export const PERM_FORMALIZATIONS = [
  "guarantees.view_guaranteeformalizationrequest",
  "guarantees.initiate_guaranteeformalizationrequest",
] as const;
export const PERM_COLLECTIONS = ["collections.view_collectioncase"] as const;
export const PERM_LEGAL_PARTIES = ["collections.view_legalparty"] as const;
/** Gérer le référentiel cabinets / huissiers (pas seulement le consulter). */
export const PERM_LEGAL_PARTIES_MANAGE = [
  "collections.change_legalparty",
] as const;
export const PERM_LITIGATION = ["collections.view_litigationfile"] as const;
export const PERM_DOCUMENTS = ["documents.view_document"] as const;
export const PERM_DASHBOARD = ["reporting.view_dashboard"] as const;

/** Hub après-vente : au moins un module ML / dation / formalisation / recouvrement. */
export const PERM_AFTER_SALES = [
  ...PERM_RELEASES,
  ...PERM_DATIONS,
  ...PERM_FORMALIZATIONS,
  ...PERM_COLLECTIONS,
] as const;

/** Admin — modules récents (en plus de is_staff). */
export const PERM_ADMIN_ALERTS = [
  "notifications.view_tenantnotificationsettings",
  "notifications.change_tenantnotificationsettings",
  "tenants.change_tenant",
] as const;
export const PERM_ADMIN_DELEGATIONS = [
  "accounts.view_delegation",
  "accounts.add_delegation",
  "accounts.change_delegation",
] as const;
export const PERM_ADMIN_CIRCUITS = [
  "workflow.view_workflowdefinition",
] as const;
export const PERM_ADMIN_CONTRACTS = [
  "contracts.view_contracttemplate",
  "contracts.add_contracttemplate",
  "contracts.change_contracttemplate",
] as const;
export const PERM_ADMIN_REFERENTIALS = [
  "catalog.view_rejectreason",
  "catalog.view_checklistitem",
  "credits.view_analysisthreshold",
  "documents.view_documentcategory",
] as const;
export const PERM_ADMIN_USERS = [
  "accounts.view_user",
] as const;
export const PERM_ADMIN_ROLES = ["accounts.view_tenantrole"] as const;
export const PERM_ADMIN_AGENCIES = [
  "tenants.view_agency",
] as const;
export const PERM_ADMIN_PRODUCTS = [
  "catalog.view_creditproduct",
] as const;
export const PERM_ADMIN_CBS_REF = [
  "catalog.view_currency",
  "catalog.view_loanperiodicity",
  "catalog.view_repaymentmethod",
  "catalog.view_financingobject",
  "catalog.view_servicepoint",
  "catalog.view_cbsmanager",
] as const;
export const PERM_ADMIN_CONNECTORS = [
  "corebanking.view_corebankingconnector",
] as const;
export const PERM_ADMIN_POLICY = [
  "credits.view_creditinstructionpolicy",
  "credits.change_creditinstructionpolicy",
] as const;
export const PERM_ADMIN_CONFIGURATION = ["configuration.view_configurationprofile"] as const;
export const PERM_ADMIN_COLLECTION_TRANCHES = [
  "collections.view_collectiontranche",
] as const;
export const PERM_ADMIN_COLLECTION_ESCALATION_RULES = [
  "collections.view_collectionescalationrule",
] as const;
export const PERM_ADMIN_AUDIT = ["audit.view_auditlog"] as const;

export const FILIALE_ADMIN_ROLE = "Administrateur filiale";
export const CONTROLE_PERMANENT_ROLES = [
  "Responsable contrôle interne",
  "Assistant Contrôle Interne",
] as const;

export function isFinflowAdmin(user: {
  is_superuser?: boolean;
  is_group_level?: boolean;
  is_staff?: boolean;
  roles?: string[];
  capabilities?: string[];
} | null | undefined): boolean {
  if (!user) return false;
  if (user.is_superuser || (user.is_group_level && user.is_staff)) return true;
  return Boolean(user.capabilities?.includes("tenant_admin"));
}

export function isControlePermanent(user: {
  roles?: string[];
  capabilities?: string[];
} | null | undefined): boolean {
  return Boolean(
    user?.capabilities?.includes("internal_control"),
  );
}

const HOME_CANDIDATES: { path: string; anyOf: readonly string[] }[] = [
  { path: "/", anyOf: PERM_DASHBOARD },
  { path: "/taches", anyOf: PERM_TASKS },
  { path: "/dossiers", anyOf: PERM_CREDITS },
  { path: "/recouvrement", anyOf: PERM_COLLECTIONS },
  { path: "/clients", anyOf: PERM_CLIENTS },
  { path: "/garanties", anyOf: PERM_GUARANTEES },
  { path: "/cautions", anyOf: PERM_SURETIES },
  { path: "/formalisations", anyOf: PERM_FORMALIZATIONS },
  { path: "/dations", anyOf: PERM_DATIONS },
  { path: "/mains-levees", anyOf: PERM_RELEASES },
  { path: "/documents", anyOf: PERM_DOCUMENTS },
];

/** Première page métier autorisée (login / retour mot de passe). */
export function homePath(user: CurrentUser | null | undefined): string {
  for (const candidate of HOME_CANDIDATES) {
    if (hasAnyPerm(user, candidate.anyOf)) return candidate.path;
  }
  return "/profil";
}
