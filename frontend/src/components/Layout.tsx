import { useQuery } from "@tanstack/react-query";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  Banknote,
  Boxes,
  Building2,
  Cable,
  Calculator,
  ChevronDown,
  CircleDollarSign,
  ClipboardCheck,
  ArrowLeftRight,
  Bell,
  BookMarked,
  FileSignature,
  FileText,
  FolderOpen,
  GitBranch,
  HandCoins,
  KeyRound,
  Layers,
  LayoutDashboard,
  Library,
  LogOut,
  Mail,
  MapPin,
  Menu,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  ScrollText,
  ShieldCheck,
  ShieldOff,
  Stamp,
  SlidersHorizontal,
  Timer,
  Unlock,
  UserRound,
  UsersRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { CurrentUser, Paginated, Tenant } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { hasAnyPerm } from "@/auth/permissions";
import { PageLoading } from "@/components/PageLoading";
import {
  PERM_ADMIN_AGENCIES,
  PERM_ADMIN_ALERTS,
  PERM_ADMIN_AUDIT,
  PERM_ADMIN_CBS_REF,
  PERM_ADMIN_CIRCUITS,
  PERM_ADMIN_CONNECTORS,
  PERM_ADMIN_CONTRACTS,
  PERM_ADMIN_DELEGATIONS,
  PERM_ADMIN_POLICY,
  PERM_ADMIN_CONFIGURATION,
  PERM_ADMIN_PRODUCTS,
  PERM_ADMIN_REFERENTIALS,
  PERM_ADMIN_ROLES,
  PERM_ADMIN_USERS,
  isFinflowAdmin,
  PERM_CLIENTS,
  PERM_COLLECTIONS,
  PERM_CREDITS,
  PERM_DATIONS,
  PERM_FORMALIZATIONS,
  PERM_DASHBOARD,
  PERM_DOCUMENTS,
  PERM_GUARANTEES,
  PERM_LEGAL_PARTIES_MANAGE,
  PERM_PRODUCTS,
  PERM_RELEASES,
  PERM_SIMULATOR,
  PERM_SURETIES,
  PERM_TASKS,
} from "@/auth/routePerms";
import { useTenantBranding } from "@/hooks/useTenantBranding";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Si défini, le lien n'apparaît que si l'utilisateur a au moins une permission. */
  anyOf?: readonly string[];
  /** Réservé aux comptes niveau Groupe. */
  groupOnly?: boolean;
  /** Administrateur filiale ou groupe. */
  finflowAdmin?: boolean;
  /** Cible alternative selon les droits (ex. catalogue vs paramétrage). */
  resolveTo?: (user: CurrentUser | null) => string;
}

interface AdminGroup {
  id: string;
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

const NAV_ITEMS: NavItem[] = [
  {
    to: "/",
    label: "Tableau de bord",
    icon: LayoutDashboard,
    anyOf: PERM_DASHBOARD,
  },
  {
    to: "/dossiers",
    label: "Dossiers de crédit",
    icon: FileText,
    anyOf: PERM_CREDITS,
  },
  {
    to: "/prets",
    label: "Prêts",
    icon: Banknote,
    anyOf: PERM_CREDITS,
  },
  {
    to: "/recouvrement",
    label: "Recouvrement",
    icon: CircleDollarSign,
    anyOf: PERM_COLLECTIONS,
  },
  {
    to: "/taches",
    label: "Mes validations",
    icon: ClipboardCheck,
    anyOf: PERM_TASKS,
  },
  { to: "/clients", label: "Clients", icon: UserRound, anyOf: PERM_CLIENTS },
  {
    to: "/cautions",
    label: "Cautions",
    icon: HandCoins,
    anyOf: PERM_SURETIES,
  },
  {
    to: "/garanties",
    label: "Garanties",
    icon: ShieldCheck,
    anyOf: PERM_GUARANTEES,
  },
  {
    to: "/formalisations",
    label: "Formalisations",
    icon: Stamp,
    anyOf: PERM_FORMALIZATIONS,
  },
  {
    to: "/dations",
    label: "Dations",
    icon: Unlock,
    anyOf: PERM_DATIONS,
  },
  {
    to: "/mains-levees",
    label: "Mains levées",
    icon: ShieldOff,
    anyOf: PERM_RELEASES,
  },
  {
    to: "/documents",
    label: "GED",
    icon: FolderOpen,
    anyOf: PERM_DOCUMENTS,
  },
  {
    to: "/simulateur",
    label: "Simulateur",
    icon: Calculator,
    anyOf: PERM_SIMULATOR,
  },
];

const ADMIN_GROUPS: AdminGroup[] = [
  {
    id: "org",
    label: "Organisation",
    icon: Building2,
    items: [
      { to: "/admin/filiales", label: "Filiales", icon: Building2 },
      {
        to: "/admin/consolidation",
        label: "Consolidation Groupe",
        icon: Layers,
        groupOnly: true,
        anyOf: PERM_DASHBOARD,
      },
      {
        to: "/admin/agences",
        label: "Agences",
        icon: MapPin,
        anyOf: PERM_ADMIN_AGENCIES,
      },
    ],
  },
  {
    id: "access",
    label: "Accès",
    icon: KeyRound,
    items: [
      {
        to: "/admin/utilisateurs",
        label: "Utilisateurs",
        icon: UsersRound,
        anyOf: PERM_ADMIN_USERS,
      },
      {
        to: "/admin/roles",
        label: "Rôles & droits",
        icon: KeyRound,
        anyOf: PERM_ADMIN_ROLES,
      },
      {
        to: "/admin/delegations",
        label: "Délégations",
        icon: ArrowLeftRight,
        anyOf: PERM_ADMIN_DELEGATIONS,
      },
    ],
  },
  {
    id: "catalog",
    label: "Catalogue",
    icon: Package,
    items: [
      {
        to: "/produits",
        label: "Produits",
        icon: Boxes,
        anyOf: [...PERM_PRODUCTS, ...PERM_ADMIN_PRODUCTS],
        resolveTo: (user) =>
          isFinflowAdmin(user) && hasAnyPerm(user, PERM_ADMIN_PRODUCTS)
            ? "/admin/produits"
            : "/produits",
      },
      {
        to: "/admin/referentiels-cbs",
        label: "Référentiels CBS",
        icon: BookMarked,
        anyOf: PERM_ADMIN_CBS_REF,
      },
      {
        to: "/admin/verification-situation",
        label: "Vérification de situation",
        icon: ClipboardCheck,
        finflowAdmin: true,
      },
      {
        to: "/admin/referentiels-metier",
        label: "Référentiels métier",
        icon: Library,
        anyOf: PERM_ADMIN_REFERENTIALS,
      },
      {
        to: "/admin/contrats",
        label: "Modèles de contrats",
        icon: FileSignature,
        anyOf: PERM_ADMIN_CONTRACTS,
      },
      {
        to: "/admin/politique-credit",
        label: "Politique crédit",
        icon: SlidersHorizontal,
        anyOf: PERM_ADMIN_POLICY,
      },
      { to: "/admin/configuration", label: "Centre de configuration", icon: SlidersHorizontal, anyOf: PERM_ADMIN_CONFIGURATION, finflowAdmin: true },
    ],
  },
  {
    id: "process",
    label: "Processus",
    icon: GitBranch,
    items: [
      {
        to: "/admin/circuits",
        label: "Circuits d'approbation",
        icon: GitBranch,
        anyOf: PERM_ADMIN_CIRCUITS,
      },
      {
        to: "/admin/tranches-recouvrement",
        label: "Tranches recouvrement",
        icon: CircleDollarSign,
        finflowAdmin: true,
      },
      {
        to: "/admin/regles-escalade",
        label: "Règles d'escalade",
        icon: Timer,
        finflowAdmin: true,
      },
      {
        to: "/admin/intervenants-juridiques",
        label: "Intervenants juridiques",
        icon: Scale,
        anyOf: PERM_LEGAL_PARTIES_MANAGE,
      },
    ],
  },
  {
    id: "integrations",
    label: "Intégrations",
    icon: Cable,
    items: [
      {
        to: "/admin/connecteurs",
        label: "Connecteurs CBS",
        icon: Cable,
        anyOf: PERM_ADMIN_CONNECTORS,
      },
      {
        to: "/admin/alertes",
        label: "Alertes e-mail",
        icon: Bell,
        anyOf: PERM_ADMIN_ALERTS,
      },
    ],
  },
  {
    id: "supervision",
    label: "Supervision",
    icon: ScrollText,
    items: [
      {
        to: "/admin/audit",
        label: "Audit",
        icon: ScrollText,
        anyOf: PERM_ADMIN_AUDIT,
      },
    ],
  },
];

function itemMatchesPath(item: NavItem, pathname: string, resolvedTo: string) {
  const targets = new Set([item.to, resolvedTo]);
  if (item.to === "/produits" || resolvedTo === "/admin/produits") {
    targets.add("/produits");
    targets.add("/admin/produits");
  }
  return [...targets].some(
    (t) => pathname === t || (t !== "/" && pathname.startsWith(`${t}/`)),
  );
}

function canSeeNavItem(item: NavItem, user: CurrentUser | null) {
  if (item.to.startsWith("/admin/") && !["/admin/audit", "/admin/consolidation", "/admin/intervenants-juridiques", "/admin/delegations", "/admin/roles", "/admin/alertes"].includes(item.to) && !isFinflowAdmin(user)) return false;
  if (item.to === "/admin/filiales" && !user?.is_group_level) return false;
  if (item.groupOnly && !user?.is_group_level) return false;
  if (item.finflowAdmin && !isFinflowAdmin(user)) return false;
  if (item.anyOf && !hasAnyPerm(user, item.anyOf)) return false;
  return true;
}

function NavItems({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate?: () => void;
}) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          title={item.label}
          className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          onClick={onNavigate}
        >
          <span className="nav-icon">
            <item.icon />
          </span>
          <span className="nav-label">{item.label}</span>
        </NavLink>
      ))}
    </>
  );
}

function AdminGroupsNav({
  groups,
  user,
  collapsed,
  onNavigate,
}: {
  groups: AdminGroup[];
  user: CurrentUser | null;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const location = useLocation();
  const groupRefs = useRef(new Map<string, HTMLDivElement>());
  const [openIds, setOpenIds] = useState<string[]>(() =>
    groups
      .filter((g) =>
        g.items.some((item) =>
          itemMatchesPath(
            item,
            location.pathname,
            item.resolveTo?.(user) ?? item.to,
          ),
        ),
      )
      .map((g) => g.id),
  );

  useEffect(() => {
    setOpenIds((prev) => {
      const extra = groups
        .filter((g) =>
          g.items.some((item) =>
            itemMatchesPath(
              item,
              location.pathname,
              item.resolveTo?.(user) ?? item.to,
            ),
          ),
        )
        .map((g) => g.id);
      if (extra.every((id) => prev.includes(id))) return prev;
      return [...new Set([...prev, ...extra])];
    });
  }, [groups, location.pathname, user]);

  function toggle(id: string) {
    setOpenIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function positionFlyout(element: HTMLDivElement) {
    const nav = element.closest(".nav");
    const panel = element.querySelector<HTMLElement>(".nav-group-items");
    if (!nav || !panel) return;
    const anchor = element.getBoundingClientRect();
    const viewport = nav.getBoundingClientRect();
    const height = Math.min(panel.scrollHeight || 300, window.innerHeight - 16);
    element.style.setProperty("--nav-flyout-top", `${Math.max(8, Math.min(anchor.top, window.innerHeight - height - 8))}px`);
    element.style.setProperty("--nav-flyout-left", `${anchor.right - 1}px`);
    element.style.setProperty("--nav-flyout-visibility", anchor.bottom <= viewport.top || anchor.top >= viewport.bottom ? "hidden" : "visible");
  }

  useEffect(() => {
    const first = groupRefs.current.values().next().value;
    const nav = first?.closest(".nav");
    const sidebar = first?.closest(".sidebar");
    const reposition = () => groupRefs.current.forEach(positionFlyout);
    reposition();
    nav?.addEventListener("scroll", reposition, { passive: true });
    window.addEventListener("resize", reposition);
    sidebar?.addEventListener("transitionend", reposition);
    return () => {
      nav?.removeEventListener("scroll", reposition);
      window.removeEventListener("resize", reposition);
      sidebar?.removeEventListener("transitionend", reposition);
    };
  }, [groups, openIds, collapsed]);

  return (
    <>
      {groups.map((group) => {
        const GroupIcon = group.icon;
        const open = openIds.includes(group.id);
        const groupActive = group.items.some((item) =>
          itemMatchesPath(
            item,
            location.pathname,
            item.resolveTo?.(user) ?? item.to,
          ),
        );
        return (
          <div
            key={group.id}
            ref={(element) => { if (element) groupRefs.current.set(group.id, element); else groupRefs.current.delete(group.id); }}
            onMouseEnter={(event) => positionFlyout(event.currentTarget)}
            onFocus={(event) => positionFlyout(event.currentTarget)}
            className={`nav-group${open ? " open" : ""}${
              groupActive ? " has-active" : ""
            }`}
          >
            <button
              type="button"
              className="nav-group-toggle"
              onClick={() => toggle(group.id)}
              aria-expanded={open}
              title={group.label}
            >
              <span className="nav-icon">
                <GroupIcon />
              </span>
              <span className="nav-label">{group.label}</span>
              <ChevronDown className="nav-group-chevron" size={14} />
            </button>
            <div className="nav-group-items">
              {group.items.map((item) => {
                const to = item.resolveTo?.(user) ?? item.to;
                const Icon = item.icon;
                return (
                  <NavLink
                    key={`${item.to}:${to}`}
                    to={to}
                    title={item.label}
                    className={({ isActive }) =>
                      `nav-link nav-sublink${isActive ? " active" : ""}`
                    }
                    onClick={onNavigate}
                  >
                    <span className="nav-icon">
                      <Icon />
                    </span>
                    <span className="nav-label">{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        );
      })}
    </>
  );
}

function TenantSwitcher() {
  const { activeTenant, setActiveTenant } = useAuth();
  const { data } = useQuery({
    queryKey: ["tenants"],
    queryFn: async () => (await api.get<Paginated<Tenant>>("/tenants/")).data,
  });

  return (
    <div className="input-icon tenant-switcher-wrap">
      <Building2 />
      <select
        className="tenant-switcher"
        style={{ paddingLeft: 38 }}
        value={activeTenant ?? ""}
        onChange={(e) => setActiveTenant(e.target.value || null)}
      >
        <option value="">Groupe (consolidé)</option>
        {data?.results.map((t) => (
          <option key={t.id} value={t.id}>
            {t.code} — {t.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function initials(user: {
  first_name?: string;
  last_name?: string;
  username: string;
}) {
  const a = user.first_name?.[0] ?? user.username[0];
  const b = user.last_name?.[0] ?? user.username[1] ?? "";
  return (a + b).toUpperCase();
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Bonjour";
  if (h < 18) return "Bon après-midi";
  return "Bonsoir";
}

type SessionUser = {
  first_name?: string;
  last_name?: string;
  username: string;
  email?: string;
  is_group_level?: boolean;
  roles?: string[];
};

function UserMenu({
  user,
  logout,
}: {
  user: SessionUser;
  logout: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const fullName =
    `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim() || user.username;

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className={`user-menu${open ? " open" : ""}`} ref={ref}>
      <button
        type="button"
        className="user-chip"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="avatar">{initials(user)}</span>
        <span className="user-meta">
          <span className="user-name">{fullName}</span>
          <span className="user-role">
            {user.is_group_level ? "Niveau Groupe" : "Filiale"}
          </span>
        </span>
        <ChevronDown className="chevron" size={16} />
      </button>

      {open && (
        <div className="user-menu-panel" role="menu">
          <div className="user-menu-header">
            <span className="avatar lg">{initials(user)}</span>
            <div>
              <div className="umh-name">{fullName}</div>
              {user.email && (
                <div className="umh-email">
                  <Mail size={12} />
                  {user.email}
                </div>
              )}
            </div>
          </div>
          <div className="user-menu-tags">
            <span className="scope-pill sm">
              <ShieldCheck size={13} />
              {user.is_group_level ? "Niveau Groupe" : "Espace filiale"}
            </span>
            {user.roles?.slice(0, 2).map((r) => (
              <span key={r} className="role-tag">
                {r}
              </span>
            ))}
          </div>
          <button
            type="button"
            className="user-menu-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate("/profil");
            }}
          >
            <UserRound size={16} />
            Mon profil
          </button>
          <button
            type="button"
            className="user-menu-item danger"
            role="menuitem"
            onClick={logout}
          >
            <LogOut size={16} />
            Déconnexion
          </button>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const { logoUrl, tenantName, isLoading: brandingLoading } = useTenantBranding();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebar-collapsed") === "1",
  );
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMobileNavOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [mobileNavOpen]);

  const navItems = NAV_ITEMS.filter((item) => canSeeNavItem(item, user));
  const adminGroups = useMemo(
    () =>
      ADMIN_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter((item) => canSeeNavItem(item, user)),
      })).filter((group) => group.items.length > 0),
    [user],
  );

  const closeMobileNav = () => setMobileNavOpen(false);

  if (brandingLoading) return <div className="centered-loader">Chargement…</div>;

  return (
    <div
      className={`app-shell${collapsed ? " sidebar-collapsed" : ""}${
        mobileNavOpen ? " mobile-nav-open" : ""
      }`}
    >
      {mobileNavOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Fermer le menu"
          onClick={closeMobileNav}
        />
      )}

      <aside className="sidebar">
        <div className="brand">
          <img src={logoUrl} alt={tenantName} className="brand-logo" />
          <span className="brand-name">Financial Workflow</span>
          <button
            type="button"
            className="sidebar-close-mobile"
            onClick={closeMobileNav}
            aria-label="Fermer le menu"
          >
            <X size={18} />
          </button>
        </div>
        <nav className="nav">
          <NavItems items={navItems} onNavigate={closeMobileNav} />
          {adminGroups.length > 0 && (
            <>
              <div className="nav-section">Administration</div>
              <AdminGroupsNav
                groups={adminGroups}
                user={user}
                collapsed={collapsed}
                onNavigate={closeMobileNav}
              />
            </>
          )}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="sidebar-toggle desktop-only"
              onClick={() => setCollapsed((v) => !v)}
              aria-label={
                collapsed ? "Déployer le menu" : "Réduire le menu"
              }
              title={collapsed ? "Déployer le menu" : "Réduire le menu"}
            >
              {collapsed ? (
                <PanelLeftOpen size={18} />
              ) : (
                <PanelLeftClose size={18} />
              )}
            </button>
            <button
              type="button"
              className="sidebar-toggle mobile-only"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Ouvrir le menu"
              title="Ouvrir le menu"
            >
              <Menu size={18} />
            </button>
            {user?.is_group_level ? (
              <TenantSwitcher />
            ) : (
              <span className="scope-pill">
                <Building2 size={16} />
                Espace filiale
              </span>
            )}
          </div>
          <div className="topbar-right">
            {user && (
              <span className="greeting">
                {greeting()},{" "}
                <strong>{user.first_name || user.username}</strong>
              </span>
            )}
            <span className="topbar-divider" />
            {user && <UserMenu user={user} logout={logout} />}
          </div>
        </header>
        <main className="content">
          <Suspense fallback={<PageLoading />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
