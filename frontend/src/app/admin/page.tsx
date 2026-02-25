"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import * as Switch from "@radix-ui/react-switch";
import {
  LayoutDashboard,
  Users,
  Server,
  ShieldCheck,
  Settings,
  ChevronRight,
  Sun,
  Moon,
  RefreshCw,
  Pencil,
  Trash2,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Alert } from "@/components/common/alert";
import { ConfirmDelete } from "@/components/common/confirm-delete";
import { DataTable } from "@/components/common/data-table";
import { EntityModal } from "@/components/common/entity-modal";
import { ApiError, api } from "@/lib/api/client";
import type {
  AuthMode,
  GenerateConfigResponse,
  Host,
  HostCreatePayload,
  HostGroup,
  HostGroupCreatePayload,
  Policy,
  PolicyCreatePayload,
  TotpProfile,
  User,
  UserCreatePayload,
  UserGroup,
  UserGroupCreatePayload,
} from "@/lib/types/tacacs";

type SectionKey =
  | "dashboard"
  | "users"
  | "userGroups"
  | "hosts"
  | "hostGroups"
  | "policies"
  | "settings";

type ThemeMode = "dark" | "light";

const THEME_STORAGE_KEY = "tacacs_theme";

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unknown error";
}

function isStrictIpv4(value: string): boolean {
  const octet = "(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)";
  const ipv4Regex = new RegExp(`^${octet}\\.${octet}\\.${octet}\\.${octet}$`);
  return ipv4Regex.test(value);
}

function IconDashboard() {
  return <LayoutDashboard className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconUsers() {
  return <Users className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconHosts() {
  return <Server className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconPolicy() {
  return <ShieldCheck className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconSettings() {
  return <Settings className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconChevron({ open }: { open: boolean }) {
  return <ChevronRight aria-hidden="true" className={`h-4 w-4 transition-transform ${open ? "rotate-90" : ""}`} strokeWidth={2} />;
}

function IconRefresh() {
  return <RefreshCw className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconEdit() {
  return <Pencil className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />;
}

function IconDelete() {
  return <Trash2 className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />;
}

function TruncatedLabel({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [isTruncated, setIsTruncated] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const checkTruncation = () => {
      setIsTruncated(element.scrollWidth > element.clientWidth);
    };

    checkTruncation();

    const observer = new ResizeObserver(() => {
      checkTruncation();
    });
    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [text]);

  return (
    <span ref={ref} className={className} title={isTruncated ? text : undefined}>
      {text}
    </span>
  );
}

export default function AdminPage() {
  const [activeSection, setActiveSection] = useState<SectionKey>("dashboard");
  const [globalError, setGlobalError] = useState<string>("");
  const [applyStatus, setApplyStatus] = useState<string>("");
  const [applyInProgress, setApplyInProgress] = useState(false);
  const [applyPreviewOpen, setApplyPreviewOpen] = useState(false);
  const [applyPreview, setApplyPreview] = useState<GenerateConfigResponse["file_contents"] | null>(null);

  const [users, setUsers] = useState<User[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [userGroups, setUserGroups] = useState<UserGroup[]>([]);
  const [hostGroups, setHostGroups] = useState<HostGroup[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);

  const [loading, setLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState<string>(new Date().toLocaleString());

  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "dark";
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [openUserMenu, setOpenUserMenu] = useState(false);
  const [openHostMenu, setOpenHostMenu] = useState(false);

  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [deleteUserTarget, setDeleteUserTarget] = useState<User | null>(null);
  const [userAuthMode, setUserAuthMode] = useState<AuthMode>("password");
  const [userInitialAuthMode, setUserInitialAuthMode] = useState<AuthMode>("password");
  const [userTotpProfile, setUserTotpProfile] = useState<TotpProfile | null>(null);
  const [userTotpUri, setUserTotpUri] = useState<string>("");
  const [userAuthLoading, setUserAuthLoading] = useState(false);
  const [userAuthInlineError, setUserAuthInlineError] = useState<string>("");
  const [userModalError, setUserModalError] = useState<string>("");
  const [userPasswordConfirm, setUserPasswordConfirm] = useState<string>("");
  const [totpPreparedUsername, setTotpPreparedUsername] = useState<string>("");
  const [userSubmitting, setUserSubmitting] = useState(false);
  const [userForm, setUserForm] = useState<UserCreatePayload>({
    username: "",
    password: "",
    full_name: "",
    description: "",
    is_active: true,
  });

  const generateBootstrapPassword = () => {
    const randomPart = Math.random().toString(36).slice(2, 14);
    const timePart = Date.now().toString(36);
    return `totp-${randomPart}-${timePart}`;
  };

  const buildTotpUriFromProfile = (username: string, secret: string) => {
    const issuer = "tacacs-plus";
    const label = `${issuer}:${username}`;
    const params = new URLSearchParams({
      secret,
      issuer,
      digits: "6",
      period: "30",
    });
    return `otpauth://totp/${encodeURIComponent(label)}?${params.toString()}`;
  };

  const resetUserAuthState = (mode: AuthMode = "password") => {
    setUserAuthMode(mode);
    setUserInitialAuthMode(mode);
    setUserTotpProfile(null);
    setUserTotpUri("");
    setUserAuthLoading(false);
    setUserAuthInlineError("");
    setTotpPreparedUsername("");
  };

  const handleUserAuthModeChange = useCallback(
    async (nextMode: AuthMode) => {
      if (userAuthLoading || userSubmitting) return;
      setUserAuthInlineError("");

      if (nextMode === "password") {
        setUserAuthMode("password");
        return;
      }

      setUserAuthMode("totp");
      const username = userForm.username.trim();
      if (!username) {
        setUserAuthInlineError("Enter username before enabling TOTP");
        return;
      }

      if (!editingUser) {
        setUserAuthInlineError("Use Create or Create and continue to generate TOTP for a new user");
        return;
      }

      if (totpPreparedUsername === username && userTotpProfile?.totp_secret) {
        return;
      }

      setUserAuthLoading(true);
      try {
        const totpResult = await api.users.totp.createOrUpdate(username, {
          is_enabled: true,
        });
        setUserTotpProfile(totpResult.totp);
        setUserTotpUri(totpResult.otp_uri);
        setUserInitialAuthMode("totp");
        setTotpPreparedUsername(username);
      } catch (error) {
        setGlobalError(getErrorMessage(error));
      } finally {
        setUserAuthLoading(false);
      }
    },
    [
      editingUser,
      totpPreparedUsername,
      userAuthLoading,
      userForm.username,
      userSubmitting,
      userTotpProfile?.totp_secret,
    ],
  );

  const hydrateUserAuthState = useCallback(async (username: string) => {
    setUserAuthLoading(true);
    try {
      const result = await api.users.totp.get(username);
      const profile = result.totp;
      if (profile.is_enabled && profile.totp_secret) {
        setUserAuthMode("totp");
        setUserInitialAuthMode("totp");
        setUserTotpProfile(profile);
        setUserTotpUri(buildTotpUriFromProfile(username, profile.totp_secret));
      } else {
        resetUserAuthState("password");
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        resetUserAuthState("password");
      } else {
        setGlobalError(getErrorMessage(error));
        resetUserAuthState("password");
      }
    } finally {
      setUserAuthLoading(false);
    }
  }, []);

  const [hostModalOpen, setHostModalOpen] = useState(false);
  const [editingHost, setEditingHost] = useState<Host | null>(null);
  const [hostModalError, setHostModalError] = useState<string>("");
  const [deleteHostTarget, setDeleteHostTarget] = useState<Host | null>(null);
  const [hostForm, setHostForm] = useState<HostCreatePayload>({
    ip_address: "",
    tacacs_key: "",
    hostname: "",
    description: "",
  });

  const [userGroupModalOpen, setUserGroupModalOpen] = useState(false);
  const [editingUserGroup, setEditingUserGroup] = useState<UserGroup | null>(null);
  const [deleteUserGroupTarget, setDeleteUserGroupTarget] = useState<UserGroup | null>(null);
  const [userGroupForm, setUserGroupForm] = useState<UserGroupCreatePayload>({
    group_name: "",
    description: "",
  });
  const [userSelectedGroups, setUserSelectedGroups] = useState<string[]>([]);
  const [userInitialGroups, setUserInitialGroups] = useState<string[]>([]);

  const [hostGroupModalOpen, setHostGroupModalOpen] = useState(false);
  const [editingHostGroup, setEditingHostGroup] = useState<HostGroup | null>(null);
  const [deleteHostGroupTarget, setDeleteHostGroupTarget] = useState<HostGroup | null>(null);
  const [hostGroupForm, setHostGroupForm] = useState<HostGroupCreatePayload>({
    group_name: "",
    tacacs_key: "",
    description: "",
  });
  const [hostCurrentGroup, setHostCurrentGroup] = useState<string>("");
  const [hostSelectedGroup, setHostSelectedGroup] = useState<string>("");
  const [hostInitialGroups, setHostInitialGroups] = useState<string[]>([]);
  const [hostGroupsByIp, setHostGroupsByIp] = useState<Record<string, string>>({});

  const [userGroupSearch, setUserGroupSearch] = useState("");
  const [userGroupCandidate, setUserGroupCandidate] = useState("");
  const [hostGroupSearch, setHostGroupSearch] = useState("");
  const [hostGroupCandidate, setHostGroupCandidate] = useState("");

  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<Policy | null>(null);
  const [deletePolicyTarget, setDeletePolicyTarget] = useState<Policy | null>(null);
  const [policyForm, setPolicyForm] = useState<PolicyCreatePayload>({
    user_group_name: "",
    host_group_name: "",
    priv_lvl: 1,
    allow_access: true,
  });

  const loadUsers = async () => {
    const result = await api.users.list();
    setUsers(result.data ?? []);
  };

  const loadHosts = async () => {
    const result = await api.hosts.list();
    setHosts(result.data ?? []);
  };

  const loadUserGroups = async () => {
    const result = await api.userGroups.list();
    setUserGroups(result.data ?? []);
  };

  const loadHostGroups = async () => {
    const result = await api.hostGroups.list();
    setHostGroups(result.data ?? []);
  };

  const loadPolicies = async () => {
    const result = await api.policies.list();
    setPolicies(result.data ?? []);
  };

  const loadHostGroupSummary = async () => {
    const result = await api.hostGroups.members.list();
    const map: Record<string, string> = {};
    for (const row of result.data ?? []) {
      if (!map[row.ip_address]) {
        map[row.ip_address] = row.group_name;
      }
    }
    setHostGroupsByIp(map);
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    setGlobalError("");
    try {
      await Promise.all([
        loadUsers(),
        loadHosts(),
        loadUserGroups(),
        loadHostGroups(),
        loadPolicies(),
        loadHostGroupSummary(),
      ]);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  const applyConfig = async () => {
    if (applyInProgress) return;
    setGlobalError("");
    setApplyStatus("");
    setApplyPreviewOpen(false);
    setApplyPreview(null);
    setApplyInProgress(true);
    try {
      const result = await api.config.generate();
      const summary = (result.files ?? [])
        .map((item) => `${item.file}: ${item.records}`)
        .join(", ");
      setApplyStatus(`Generated in ${result.path}. ${summary}`);
      setApplyPreview(result.file_contents);
      setApplyPreviewOpen(true);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    } finally {
      setApplyInProgress(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date().toLocaleString()), 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const sectionTitle = useMemo(() => {
    const labels: Record<SectionKey, string> = {
      dashboard: "Dashboard",
      users: "Users",
      userGroups: "User Groups",
      hosts: "Hosts",
      hostGroups: "Host Groups",
      policies: "Policies",
      settings: "Settings",
    };
    return labels[activeSection];
  }, [activeSection]);

  const sectionIcon = useMemo(() => {
    const map: Record<SectionKey, ReactNode> = {
      dashboard: <IconDashboard />,
      users: <IconUsers />,
      userGroups: <IconUsers />,
      hosts: <IconHosts />,
      hostGroups: <IconHosts />,
      policies: <IconPolicy />,
      settings: <IconSettings />,
    };
    return map[activeSection];
  }, [activeSection]);

  const openCreateUser = () => {
    setEditingUser(null);
    setUserForm({ username: "", password: "", full_name: "", description: "", is_active: true });
    setUserPasswordConfirm("");
    setUserModalError("");
    resetUserAuthState("password");
    setUserSelectedGroups([]);
    setUserInitialGroups([]);
    setUserGroupSearch("");
    setUserGroupCandidate("");
    setUserModalOpen(true);
  };

  const openEditUser = (user: User) => {
    setEditingUser(user);
    setUserModalError("");
    setUserPasswordConfirm("");
    setUserForm({
      username: user.username,
      password: "",
      full_name: user.full_name ?? "",
      description: user.description ?? "",
      is_active: user.is_active,
    });
    resetUserAuthState("password");
    setUserSelectedGroups([]);
    setUserInitialGroups([]);
    setUserGroupSearch("");
    setUserGroupCandidate("");
    setUserModalOpen(true);
    void hydrateUserAuthState(user.username);
    void (async () => {
      try {
        const result = await api.userGroups.members.list({ username: user.username });
        const groups = (result.data ?? []).map((row) => row.group_name);
        setUserSelectedGroups(groups);
        setUserInitialGroups(groups);
        const firstAvailable = userGroups.find((group) => !groups.includes(group.group_name))?.group_name ?? "";
        setUserGroupCandidate(firstAvailable);
      } catch (error) {
        setGlobalError(getErrorMessage(error));
      }
    })();
  };

  const createUserAndContinue = async () => {
    if (userSubmitting || editingUser) return;
    setUserModalError("");
    setUserSubmitting(true);
    try {
      const username = userForm.username.trim();
      if (!username) throw new Error("Username is required");
      const usernameTaken = users.some(
        (user) => user.username.toLowerCase() === username.toLowerCase(),
      );
      if (usernameTaken) throw new Error("User with this username already exists");

      if (userAuthMode === "password" && !userForm.password.trim()) {
        throw new Error("Password is required in password mode");
      }
      if (userAuthMode === "password" && userForm.password !== userPasswordConfirm) {
        throw new Error("Password confirmation does not match");
      }

      const payload: UserCreatePayload = {
        ...userForm,
        password:
          userAuthMode === "totp"
            ? userForm.password.trim() || generateBootstrapPassword()
            : userForm.password,
      };

      const created = await api.users.create(payload);
      setEditingUser(created.user);
      setUserSelectedGroups([]);
      setUserInitialGroups([]);
      setUserGroupSearch("");
      setUserGroupCandidate(userGroups[0]?.group_name ?? "");

      if (userAuthMode === "totp") {
        const totpResult = await api.users.totp.createOrUpdate(created.user.username, {
          is_enabled: true,
        });
        setUserTotpProfile(totpResult.totp);
        setUserTotpUri(totpResult.otp_uri);
        setUserInitialAuthMode("totp");
      }

      await loadUsers();
    } catch (error) {
      setUserModalError(getErrorMessage(error));
    } finally {
      setUserSubmitting(false);
    }
  };

  const saveUser = async () => {
    if (userSubmitting) return;
    setUserModalError("");
    setUserSubmitting(true);
    try {
      const username = userForm.username.trim();
      if (!username) throw new Error("Username is required");
      const usernameTaken = users.some(
        (user) =>
          user.username.toLowerCase() === username.toLowerCase() &&
          (!editingUser || user.username !== editingUser.username),
      );
      if (usernameTaken) throw new Error("User with this username already exists");

      if (!editingUser && userAuthMode === "password" && !userForm.password.trim()) {
        throw new Error("Password is required in password mode");
      }
      if (editingUser && userAuthMode === "password" && userInitialAuthMode === "totp" && !userForm.password.trim()) {
        throw new Error("Password is required when switching from TOTP to password mode");
      }
      if (userAuthMode === "password") {
        const requiresPassword = !editingUser || userInitialAuthMode === "totp";
        const hasEnteredPassword = userForm.password.trim().length > 0;
        if ((requiresPassword || hasEnteredPassword) && userForm.password !== userPasswordConfirm) {
          throw new Error("Password confirmation does not match");
        }
      }

      if (editingUser) {
        await api.users.update(editingUser.username, {
          password: userForm.password.trim() || undefined,
          full_name: userForm.full_name || undefined,
          description: userForm.description || undefined,
          is_active: userForm.is_active,
        });

        const selected = new Set(userSelectedGroups);
        const initial = new Set(userInitialGroups);
        const toAdd = [...selected].filter((group) => !initial.has(group));
        const toRemove = [...initial].filter((group) => !selected.has(group));

        await Promise.all([
          ...toAdd.map((group_name) =>
            api.userGroups.members.add({ username: editingUser.username, group_name }),
          ),
          ...toRemove.map((group_name) =>
            api.userGroups.members.remove({ username: editingUser.username, group_name }),
          ),
        ]);

        if (userAuthMode === "totp" && userInitialAuthMode !== "totp") {
          const totpResult = await api.users.totp.createOrUpdate(editingUser.username, {
            is_enabled: true,
          });
          setUserTotpProfile(totpResult.totp);
          setUserTotpUri(totpResult.otp_uri);
          setUserInitialAuthMode("totp");
        }

        if (userAuthMode === "password" && userInitialAuthMode === "totp") {
          try {
            await api.users.totp.delete(editingUser.username);
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 404)) {
              throw error;
            }
          }
          resetUserAuthState("password");
        }
      } else {
        const payload: UserCreatePayload = {
          ...userForm,
          password:
            userAuthMode === "totp"
              ? userForm.password.trim() || generateBootstrapPassword()
              : userForm.password,
        };

        await api.users.create(payload);

        if (userAuthMode === "totp") {
          const totpResult = await api.users.totp.createOrUpdate(userForm.username, {
            is_enabled: true,
          });
          setUserTotpProfile(totpResult.totp);
          setUserTotpUri(totpResult.otp_uri);
          setUserInitialAuthMode("totp");
        }
      }

      await loadUsers();
      if (editingUser || userAuthMode === "password") {
        setUserModalOpen(false);
      }
    } catch (error) {
      setUserModalError(getErrorMessage(error));
    } finally {
      setUserSubmitting(false);
    }
  };

  const deleteUser = async () => {
    if (!deleteUserTarget) return;
    setGlobalError("");
    try {
      await api.users.delete(deleteUserTarget.username);
      await loadUsers();
      setDeleteUserTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateHost = () => {
    setEditingHost(null);
    setHostModalError("");
    setHostForm({ ip_address: "", tacacs_key: "", hostname: "", description: "" });
    setHostCurrentGroup("");
    setHostSelectedGroup("");
    setHostInitialGroups([]);
    setHostGroupSearch("");
    setHostGroupCandidate("");
    setHostModalOpen(true);
  };

  const openEditHost = (host: Host) => {
    setEditingHost(host);
    setHostModalError("");
    setHostForm({
      ip_address: host.ip_address,
      tacacs_key: host.tacacs_key,
      hostname: host.hostname ?? "",
      description: host.description ?? "",
    });
    setHostCurrentGroup("");
    setHostSelectedGroup("");
    setHostInitialGroups([]);
    setHostGroupSearch("");
    setHostGroupCandidate("");
    setHostModalOpen(true);
    void (async () => {
      try {
        const result = await api.hostGroups.members.list({ ip_address: host.ip_address });
        const groups = (result.data ?? []).map((row) => row.group_name);
        const firstGroup = groups[0] ?? "";
        setHostInitialGroups(groups);
        setHostCurrentGroup(firstGroup);
        setHostSelectedGroup(firstGroup);
        setHostGroupCandidate(firstGroup);
        setHostGroupSearch(firstGroup);
      } catch (error) {
        setGlobalError(getErrorMessage(error));
      }
    })();
  };

  const createHostAndContinue = async () => {
    if (editingHost) return;
    setHostModalError("");
    try {
      const ipAddress = hostForm.ip_address.trim();
      if (!ipAddress) throw new Error("IP address is required");
      if (!isStrictIpv4(ipAddress)) throw new Error("IP address must be a valid IPv4 address");

      const created = await api.hosts.create(hostForm);
      setEditingHost(created.host);
      setHostInitialGroups([]);
      setHostCurrentGroup("");
      setHostSelectedGroup("");
      setHostGroupSearch("");
      setHostGroupCandidate(hostGroups[0]?.group_name ?? "");

      await loadHosts();
      await loadHostGroupSummary();
    } catch (error) {
      setHostModalError(getErrorMessage(error));
    }
  };

  const saveHost = async () => {
    setHostModalError("");
    try {
      const ipAddress = hostForm.ip_address.trim();
      if (!ipAddress) throw new Error("IP address is required");
      if (!isStrictIpv4(ipAddress)) throw new Error("IP address must be a valid IPv4 address");

      if (editingHost) {
        await api.hosts.update(editingHost.ip_address, {
          tacacs_key: hostForm.tacacs_key,
          hostname: hostForm.hostname || undefined,
          description: hostForm.description || undefined,
        });

        const groupsToRemove = hostInitialGroups.filter((group_name) => group_name !== hostSelectedGroup);
        await Promise.all(
          groupsToRemove.map((group_name) =>
            api.hostGroups.members.remove({
              ip_address: editingHost.ip_address,
              group_name,
            }),
          ),
        );

        if (hostSelectedGroup && !hostInitialGroups.includes(hostSelectedGroup)) {
          await api.hostGroups.members.add({
            ip_address: editingHost.ip_address,
            group_name: hostSelectedGroup,
          });
        }
      } else {
        await api.hosts.create(hostForm);
      }

      await loadHosts();
      await loadHostGroupSummary();
      setHostModalOpen(false);
    } catch (error) {
      setHostModalError(getErrorMessage(error));
    }
  };

  const deleteHost = async () => {
    if (!deleteHostTarget) return;
    setGlobalError("");
    try {
      await api.hosts.delete(deleteHostTarget.ip_address);
      await loadHosts();
      setDeleteHostTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateUserGroup = () => {
    setEditingUserGroup(null);
    setUserGroupForm({ group_name: "", description: "" });
    setUserGroupModalOpen(true);
  };

  const openEditUserGroup = (group: UserGroup) => {
    setEditingUserGroup(group);
    setUserGroupForm({ group_name: group.group_name, description: group.description ?? "" });
    setUserGroupModalOpen(true);
  };

  const saveUserGroup = async () => {
    setGlobalError("");
    try {
      if (!userGroupForm.group_name.trim()) throw new Error("Group name is required");

      if (editingUserGroup) {
        await api.userGroups.update(editingUserGroup.group_name, {
          group_name: editingUserGroup.group_name,
          description: userGroupForm.description || undefined,
        });
      } else {
        await api.userGroups.create(userGroupForm);
      }

      await loadUserGroups();
      setUserGroupModalOpen(false);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const deleteUserGroup = async () => {
    if (!deleteUserGroupTarget) return;
    setGlobalError("");
    try {
      await api.userGroups.delete(deleteUserGroupTarget.group_name);
      await loadUserGroups();
      setDeleteUserGroupTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateHostGroup = () => {
    setEditingHostGroup(null);
    setHostGroupForm({ group_name: "", tacacs_key: "", description: "" });
    setHostGroupModalOpen(true);
  };

  const openEditHostGroup = (group: HostGroup) => {
    setEditingHostGroup(group);
    setHostGroupForm({
      group_name: group.group_name,
      tacacs_key: group.tacacs_key ?? "",
      description: group.description ?? "",
    });
    setHostGroupModalOpen(true);
  };

  const saveHostGroup = async () => {
    setGlobalError("");
    try {
      if (!hostGroupForm.group_name.trim()) throw new Error("Group name is required");

      if (editingHostGroup) {
        await api.hostGroups.update(editingHostGroup.group_name, {
          group_name: editingHostGroup.group_name,
          tacacs_key: hostGroupForm.tacacs_key || undefined,
          description: hostGroupForm.description || undefined,
        });
      } else {
        await api.hostGroups.create(hostGroupForm);
      }

      await loadHostGroups();
      setHostGroupModalOpen(false);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const deleteHostGroup = async () => {
    if (!deleteHostGroupTarget) return;
    setGlobalError("");
    try {
      await api.hostGroups.delete(deleteHostGroupTarget.group_name);
      await loadHostGroups();
      await loadHostGroupSummary();
      setDeleteHostGroupTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreatePolicy = () => {
    setEditingPolicy(null);
    setPolicyForm({
      user_group_name: userGroups[0]?.group_name ?? "",
      host_group_name: hostGroups[0]?.group_name ?? "",
      priv_lvl: 1,
      allow_access: true,
    });
    setPolicyModalOpen(true);
  };

  const openEditPolicy = (policy: Policy) => {
    setEditingPolicy(policy);
    setPolicyForm({
      user_group_name: policy.user_group_name,
      host_group_name: policy.host_group_name,
      priv_lvl: policy.priv_lvl,
      allow_access: policy.allow_access,
    });
    setPolicyModalOpen(true);
  };

  const savePolicy = async () => {
    setGlobalError("");
    try {
      if (!policyForm.user_group_name) throw new Error("User group is required");
      if (!policyForm.host_group_name) throw new Error("Host group is required");
      if (policyForm.priv_lvl < 0 || policyForm.priv_lvl > 15) {
        throw new Error("Privilege level must be between 0 and 15");
      }

      if (editingPolicy?.policy_id) {
        await api.policies.delete(editingPolicy.policy_id);
      }

      await api.policies.create(policyForm);
      await loadPolicies();
      setPolicyModalOpen(false);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const deletePolicy = async () => {
    if (!deletePolicyTarget?.policy_id) return;
    setGlobalError("");
    try {
      await api.policies.delete(deletePolicyTarget.policy_id);
      await loadPolicies();
      setDeletePolicyTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const renderActionButtons = (
    onEdit: () => void,
    onDelete: () => void,
    editLabel = "Edit",
  ) => (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={onEdit}
        aria-label={editLabel}
        title={editLabel}
        className="glass-btn glass-focus inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg text-xs transition"
      >
        <IconEdit />
      </button>
      <button
        type="button"
        onClick={onDelete}
        aria-label="Delete"
        title="Delete"
        className="glass-btn-danger glass-focus inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg text-xs transition"
      >
        <IconDelete />
      </button>
    </div>
  );

  return (
    <div className="min-h-screen p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 lg:flex-row">
        <aside className="glass-panel w-full rounded-2xl p-4 lg:w-72 lg:self-start">
          <h1 className="glass-title tacacs-brand-title mb-1 text-lg font-semibold tracking-wide">TACACS Admin</h1>
          <p className="glass-muted mb-3 text-xs">Control panel</p>

          <nav className="space-y-2">
            <button
              type="button"
              onClick={() => setActiveSection("dashboard")}
              className={`glass-focus glass-btn inline-flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
                activeSection === "dashboard" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
              }`}
            >
              <IconDashboard />
              Dashboard
            </button>

            <button
              type="button"
              onClick={() => setOpenUserMenu((prev) => !prev)}
              className="glass-focus glass-btn inline-flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition"
            >
              <span className="inline-flex items-center gap-2">
                <IconUsers />
                Tacacs Users
              </span>
              <IconChevron open={openUserMenu} />
            </button>
            {openUserMenu && (
              <div className="ml-3 space-y-1">
                <button
                  type="button"
                  onClick={() => setActiveSection("users")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "users" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Users
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection("userGroups")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "userGroups" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  User Groups
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setOpenHostMenu((prev) => !prev)}
              className="glass-focus glass-btn inline-flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition"
            >
              <span className="inline-flex items-center gap-2">
                <IconHosts />
                Tacacs Hosts
              </span>
              <IconChevron open={openHostMenu} />
            </button>
            {openHostMenu && (
              <div className="ml-3 space-y-1">
                <button
                  type="button"
                  onClick={() => setActiveSection("hosts")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "hosts" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Hosts
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection("hostGroups")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "hostGroups" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Host Groups
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setActiveSection("policies")}
              className={`glass-focus glass-btn inline-flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
                activeSection === "policies" ? "" : "glass-muted opacity-90 hover:opacity-100"
              }`}
            >
              <IconPolicy />
              Policies
            </button>

            <button
              type="button"
              onClick={() => setActiveSection("settings")}
              className={`glass-focus glass-btn inline-flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
                activeSection === "settings" ? "" : "glass-muted opacity-90 hover:opacity-100"
              }`}
            >
              <IconSettings />
              Settings
            </button>
          </nav>
        </aside>

        <main className="glass-panel flex-1 rounded-2xl p-4 sm:p-6">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="glass-title flex h-8 items-center gap-2 text-xl leading-none font-semibold tracking-tight">
                <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center leading-none">
                  {sectionIcon}
                </span>
                <span className="inline-flex items-center leading-none">{sectionTitle}</span>
              </h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={loadAll}
                aria-label="Refresh data"
                title="Refresh data"
                className="glass-btn glass-focus inline-flex cursor-pointer items-center justify-center rounded-xl p-2 text-sm transition"
              >
                <IconRefresh />
              </button>
              <button
                type="button"
                onClick={applyConfig}
                disabled={applyInProgress}
                className="apply-btn glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-70"
              >
                {applyInProgress ? "Applying..." : "APPLY"}
              </button>

              {activeSection === "users" && (
                <button
                  type="button"
                  onClick={openCreateUser}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add user
                </button>
              )}
              {activeSection === "hosts" && (
                <button
                  type="button"
                  onClick={openCreateHost}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add host
                </button>
              )}
              {activeSection === "userGroups" && (
                <button
                  type="button"
                  onClick={openCreateUserGroup}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add user group
                </button>
              )}
              {activeSection === "hostGroups" && (
                <button
                  type="button"
                  onClick={openCreateHostGroup}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add host group
                </button>
              )}
              {activeSection === "policies" && (
                <button
                  type="button"
                  onClick={openCreatePolicy}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add policy
                </button>
              )}
            </div>
          </div>

          {loading && <p className="glass-muted mb-3 text-sm">Loading...</p>}
          {globalError && <Alert message={globalError} variant="error" />}
          {applyStatus && <Alert message={applyStatus} variant="success" />}

          <div className="mt-4">
            {activeSection === "dashboard" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <div className="glass-panel rounded-2xl p-4">
                    <p className="glass-muted text-xs uppercase tracking-wide">Users summary</p>
                    <p className="glass-title mt-2 text-3xl font-semibold">{users.length}</p>
                    <p className="glass-muted mt-1 text-sm">Total users</p>
                  </div>
                  <div className="glass-panel rounded-2xl p-4">
                    <p className="glass-muted text-xs uppercase tracking-wide">Hosts summary</p>
                    <p className="glass-title mt-2 text-3xl font-semibold">{hosts.length}</p>
                    <p className="glass-muted mt-1 text-sm">Total hosts</p>
                  </div>
                  <div className="glass-panel rounded-2xl p-4">
                    <p className="glass-muted text-xs uppercase tracking-wide">Current time</p>
                    <p className="glass-title mt-2 text-xl font-semibold">{currentTime}</p>
                    <p className="glass-muted mt-1 text-sm">Server dashboard clock</p>
                  </div>
                </div>

              </div>
            )}

            {activeSection === "users" && (
              <DataTable
                enableControls
                rows={users}
                emptyText="No users"
                columns={[
                  {
                    key: "username",
                    header: "Username",
                    render: (row) => row.username,
                    getSortValue: (row) => row.username,
                    getSearchValue: (row) => row.username,
                  },
                  {
                    key: "description",
                    header: "Description",
                    sortable: false,
                    render: (row) => row.description ?? "—",
                    getSearchValue: (row) => row.description ?? "",
                  },
                  {
                    key: "active",
                    header: "Active",
                    render: (row) => (row.is_active ? "Yes" : "No"),
                    sortable: false,
                    getSearchValue: (row) => (row.is_active ? "yes active" : "no disabled"),
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    sortable: false,
                    getSearchValue: () => "",
                    render: (row) =>
                      renderActionButtons(
                        () => openEditUser(row),
                        () => setDeleteUserTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "hosts" && (
              <DataTable
                enableControls
                rows={hosts}
                emptyText="No hosts"
                columns={[
                  {
                    key: "name",
                    header: "Hostname",
                    render: (row) => row.hostname ?? "—",
                    getSortValue: (row) => row.hostname ?? "",
                    getSearchValue: (row) => row.hostname ?? "",
                  },
                  {
                    key: "ip",
                    header: "IP Address",
                    render: (row) => row.ip_address,
                    getSortValue: (row) => row.ip_address,
                    getSearchValue: (row) => row.ip_address,
                  },
                  {
                    key: "group",
                    header: "Host Group",
                    render: (row) => hostGroupsByIp[row.ip_address] ?? "—",
                    getSortValue: (row) => hostGroupsByIp[row.ip_address] ?? "",
                    getSearchValue: (row) => hostGroupsByIp[row.ip_address] ?? "",
                  },
                  {
                    key: "description",
                    header: "Description",
                    sortable: false,
                    render: (row) => row.description ?? "—",
                    getSearchValue: (row) => row.description ?? "",
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    sortable: false,
                    getSearchValue: () => "",
                    render: (row) =>
                      renderActionButtons(
                        () => openEditHost(row),
                        () => setDeleteHostTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "userGroups" && (
              <DataTable
                enableControls
                rows={userGroups}
                emptyText="No user groups"
                columns={[
                  {
                    key: "name",
                    header: "Group",
                    render: (row) => row.group_name,
                    getSortValue: (row) => row.group_name,
                    getSearchValue: (row) => row.group_name,
                  },
                  {
                    key: "description",
                    header: "Description",
                    sortable: false,
                    render: (row) => row.description ?? "—",
                    getSearchValue: (row) => row.description ?? "",
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    sortable: false,
                    getSearchValue: () => "",
                    render: (row) =>
                      renderActionButtons(
                        () => openEditUserGroup(row),
                        () => setDeleteUserGroupTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "hostGroups" && (
              <DataTable
                enableControls
                rows={hostGroups}
                emptyText="No host groups"
                columns={[
                  {
                    key: "name",
                    header: "Group",
                    render: (row) => row.group_name,
                    getSortValue: (row) => row.group_name,
                    getSearchValue: (row) => row.group_name,
                  },
                  {
                    key: "description",
                    header: "Description",
                    sortable: false,
                    render: (row) => row.description ?? "—",
                    getSearchValue: (row) => row.description ?? "",
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    sortable: false,
                    getSearchValue: () => "",
                    render: (row) =>
                      renderActionButtons(
                        () => openEditHostGroup(row),
                        () => setDeleteHostGroupTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "policies" && (
              <DataTable
                rows={policies}
                emptyText="No policies"
                columns={[
                  { key: "id", header: "ID", render: (row) => row.policy_id ?? "—" },
                  { key: "ug", header: "User Group", render: (row) => row.user_group_name },
                  { key: "hg", header: "Host Group", render: (row) => row.host_group_name },
                  { key: "lvl", header: "Priv", render: (row) => row.priv_lvl },
                  { key: "allow", header: "Allow", render: (row) => (row.allow_access ? "Yes" : "No") },
                  {
                    key: "actions",
                    header: "Actions",
                    render: (row) =>
                      renderActionButtons(
                        () => openEditPolicy(row),
                        () => setDeletePolicyTarget(row),
                        "Recreate",
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "settings" && (
              <div className="max-w-xl space-y-4">
                <div className="glass-soft rounded-2xl p-4">
                  <p className="glass-muted text-xs uppercase tracking-wide">Appearance</p>
                  <div className="mt-3 flex items-center gap-3">
                    <Moon
                      className={`h-4 w-4 transition-colors ${theme === "dark" ? "text-sky-100" : "glass-muted"}`}
                      strokeWidth={2}
                      aria-hidden="true"
                    />
                    <Switch.Root
                      checked={theme === "light"}
                      onCheckedChange={(checked) => setTheme(checked ? "light" : "dark")}
                      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                      className="theme-switch-root glass-focus"
                    >
                      <Switch.Thumb className="theme-switch-thumb" />
                    </Switch.Root>
                    <Sun
                      className={`h-4 w-4 transition-colors ${theme === "light" ? "text-amber-600" : "glass-muted"}`}
                      strokeWidth={2}
                      aria-hidden="true"
                    />
                    <span className="glass-title text-sm font-medium">
                      {theme === "light" ? "Light theme" : "Dark theme"}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      <EntityModal
        title={editingUser ? "Edit user" : "Create user"}
        open={userModalOpen}
        onClose={() => {
          if (userSubmitting) return;
          setUserPasswordConfirm("");
          setUserModalOpen(false);
        }}
      >
        <div className="space-y-3">
          {userModalError && <Alert message={userModalError} variant="error" />}
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="space-y-3">
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Username</p>
                <input
                  placeholder="Username"
                  value={userForm.username}
                  disabled={Boolean(editingUser)}
                  onChange={(event) => setUserForm((prev) => ({ ...prev, username: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>

              <div className="glass-soft space-y-2 rounded-xl p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="glass-muted text-xs uppercase tracking-wide">Authentication mode</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleUserAuthModeChange("password")}
                      disabled={userAuthLoading || userSubmitting}
                      className={`glass-focus rounded-lg px-3 py-1.5 text-sm transition ${
                        userAuthMode === "password" ? "glass-btn" : "glass-btn-secondary"
                      } ${userAuthLoading || userSubmitting ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                    >
                      Password
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleUserAuthModeChange("totp")}
                      disabled={userAuthLoading || userSubmitting}
                      className={`glass-focus rounded-lg px-3 py-1.5 text-sm transition ${
                        userAuthMode === "totp" ? "glass-btn" : "glass-btn-secondary"
                      } ${userAuthLoading || userSubmitting ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                    >
                      TOTP
                    </button>
                  </div>
                </div>
                {userAuthInlineError && <p className="status-warn-text text-xs">{userAuthInlineError}</p>}
                {userAuthLoading && <p className="glass-muted text-xs">Loading auth mode…</p>}
              </div>

              {userAuthMode === "password" && (
                <div className="space-y-3">
                  <div className="space-y-1">
                    <p className="glass-muted text-[8px] uppercase tracking-wide">Password</p>
                    <input
                      type="password"
                      placeholder={editingUser ? "New password" : "Password"}
                      value={userForm.password}
                      onChange={(event) => setUserForm((prev) => ({ ...prev, password: event.target.value }))}
                      className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <p className="glass-muted text-[8px] uppercase tracking-wide">Confirm password</p>
                    <input
                      type="password"
                      placeholder="Confirm password"
                      value={userPasswordConfirm}
                      onChange={(event) => setUserPasswordConfirm(event.target.value)}
                      className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}

              {userAuthMode === "totp" && (
                <div className="status-chip-success space-y-2 rounded-xl p-3">
                  <p className="status-success-text text-xs font-medium tracking-wide uppercase">
                    TOTP secret
                  </p>
                  <input
                    value={userTotpProfile?.totp_secret ?? "Will be generated immediately after selecting TOTP"}
                    readOnly
                    className="glass-input glass-focus w-full rounded-xl px-3 py-2 font-mono text-xs"
                  />
                  {userTotpUri && (
                    <div className="space-y-2">
                      <div className="mx-auto w-fit rounded-xl border border-white/15 bg-white p-2">
                        <QRCodeSVG
                          value={userTotpUri}
                          size={164}
                          level="M"
                          marginSize={2}
                          title={`TOTP QR for ${userForm.username || "user"}`}
                          bgColor="#ffffff"
                          fgColor="#0f172a"
                        />
                      </div>
                      <textarea
                        value={userTotpUri}
                        readOnly
                        className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 font-mono text-[11px]"
                      />
                    </div>
                  )}
                  {editingUser && !userTotpProfile?.totp_secret && (
                    <p className="glass-muted text-xs">TOTP is being prepared. Secret will appear here.</p>
                  )}
                  {!editingUser && (
                    <p className="glass-muted text-xs">Enter username and choose TOTP to generate secret immediately.</p>
                  )}
                </div>
              )}

              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Full name</p>
                <input
                  placeholder="Full name"
                  value={userForm.full_name ?? ""}
                  onChange={(event) => setUserForm((prev) => ({ ...prev, full_name: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>

              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
                <input
                  placeholder="Description"
                  value={userForm.description ?? ""}
                  onChange={(event) => setUserForm((prev) => ({ ...prev, description: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>

              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Status</p>
                <div className="inline-flex items-center gap-3">
                  <Switch.Root
                    checked={userForm.is_active}
                    onCheckedChange={(checked) => setUserForm((prev) => ({ ...prev, is_active: checked }))}
                    aria-label="Toggle user status"
                    className="status-switch-root glass-focus"
                  >
                    <Switch.Thumb className="status-switch-thumb" />
                  </Switch.Root>
                  <span className={`text-sm font-medium ${userForm.is_active ? "status-success-text" : "status-warn-text"}`}>
                    {userForm.is_active ? "Active" : "Disabled"}
                  </span>
                </div>
              </div>
            </div>

            <div className="glass-soft h-full space-y-3 rounded-xl p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="glass-muted text-xs uppercase tracking-wide">User groups</p>
                <span className="assigned-count-badge">{userSelectedGroups.length}</span>
              </div>
              <div className="space-y-2">
                <div className="relative">
                  <input
                    placeholder="Search group"
                    value={userGroupSearch}
                    disabled={!editingUser}
                    onChange={(event) => {
                      const value = event.target.value;
                      setUserGroupSearch(value);
                      const normalized = value.trim().toLowerCase();
                      const first = userGroups.find(
                        (group) =>
                          !userSelectedGroups.includes(group.group_name) &&
                          group.group_name.toLowerCase().includes(normalized),
                      );
                      setUserGroupCandidate(first?.group_name ?? "");
                    }}
                    className="glass-input glass-focus w-full rounded-xl px-3 py-2 pr-9 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  {userGroupSearch.trim().length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        setUserGroupSearch("");
                        const first = userGroups.find(
                          (group) => !userSelectedGroups.includes(group.group_name),
                        );
                        setUserGroupCandidate(first?.group_name ?? "");
                      }}
                      aria-label="Clear group search"
                      title="Clear group search"
                      disabled={!editingUser}
                      className="glass-btn-secondary glass-focus absolute top-1/2 right-1 inline-flex h-7 w-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      ×
                    </button>
                  )}
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <select
                    value={userGroupCandidate}
                    disabled={!editingUser}
                    onChange={(event) => setUserGroupCandidate(event.target.value)}
                    className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <option value="">Select user group</option>
                    {userGroups
                      .filter(
                        (group) =>
                          !userSelectedGroups.includes(group.group_name) &&
                          group.group_name.toLowerCase().includes(userGroupSearch.trim().toLowerCase()),
                      )
                      .map((group) => (
                        <option key={group.group_name} value={group.group_name}>
                          {group.group_name}
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      if (!editingUser) return;
                      if (!userGroupCandidate) return;
                      if (userSelectedGroups.includes(userGroupCandidate)) return;
                      setUserSelectedGroups((prev) => [...prev, userGroupCandidate]);
                      setUserGroupCandidate("");
                      setUserGroupSearch("");
                    }}
                    disabled={!editingUser || !userGroupCandidate}
                    className="glass-btn-secondary accent-outline-btn glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Add
                  </button>
                </div>
                {!editingUser && (
                  <p className="glass-muted text-xs">Create user first, then assign groups.</p>
                )}
              </div>

              <div className="mt-1 border-t border-[var(--glass-soft-border)] pt-3">
                <div className="assigned-groups-panel rounded-xl p-3">
                  <p className="glass-muted mb-2 text-[10px] uppercase tracking-wide">Assigned groups</p>
                  <div className="flex flex-wrap gap-2">
                    {userSelectedGroups.length === 0 && (
                      <span className="glass-muted text-xs">No groups assigned</span>
                    )}
                    {userSelectedGroups.map((groupName) => (
                      <div key={groupName} className="assigned-chip">
                        <TruncatedLabel text={groupName} className="assigned-chip-label" />
                        <button
                          type="button"
                          onClick={() => setUserSelectedGroups((prev) => prev.filter((group) => group !== groupName))}
                          className="assigned-chip-remove glass-focus"
                          aria-label={`Remove ${groupName}`}
                          title={`Remove ${groupName}`}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {!editingUser && (
              <button
                type="button"
                onClick={createUserAndContinue}
                disabled={userSubmitting || userAuthLoading}
                className="glass-btn-secondary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-70"
              >
                {userSubmitting ? "Creating..." : "Create and continue"}
              </button>
            )}
            <button
              type="button"
              onClick={saveUser}
              disabled={userSubmitting || userAuthLoading}
              className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-70"
            >
              {userSubmitting ? "Saving..." : editingUser ? "Save" : "Create"}
            </button>
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingHost ? "Edit host" : "Create host"}
        open={hostModalOpen}
        onClose={() => {
          setHostModalError("");
          setHostModalOpen(false);
        }}
      >
        <div className="space-y-3">
          {hostModalError && <Alert message={hostModalError} variant="error" />}
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="space-y-3">
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Hostname</p>
                <input
                  placeholder="Hostname"
                  value={hostForm.hostname ?? ""}
                  onChange={(event) => setHostForm((prev) => ({ ...prev, hostname: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">IP address</p>
                <input
                  placeholder="IP address"
                  value={hostForm.ip_address}
                  disabled={Boolean(editingHost)}
                  onChange={(event) => setHostForm((prev) => ({ ...prev, ip_address: event.target.value }))}
                  inputMode="numeric"
                  pattern="(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)(?:\\.(?:25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)){3}"
                  title="Enter valid IPv4 address (example: 192.168.1.10)"
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">TACACS key</p>
                <input
                  placeholder="TACACS key"
                  value={hostForm.tacacs_key}
                  onChange={(event) => setHostForm((prev) => ({ ...prev, tacacs_key: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
                <textarea
                  placeholder="Description"
                  value={hostForm.description ?? ""}
                  onChange={(event) => setHostForm((prev) => ({ ...prev, description: event.target.value }))}
                  className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="glass-soft h-full space-y-3 rounded-xl p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="glass-muted text-xs uppercase tracking-wide">Host group</p>
                <span className="assigned-count-badge">{hostSelectedGroup ? 1 : 0}</span>
              </div>
              <div className="space-y-2">
                <div className="relative">
                  <input
                    placeholder="Search group"
                    value={hostGroupSearch}
                    disabled={!editingHost}
                    onChange={(event) => {
                      const value = event.target.value;
                      setHostGroupSearch(value);
                      const normalized = value.trim().toLowerCase();
                      const first = hostGroups.find((group) =>
                        group.group_name.toLowerCase().includes(normalized),
                      );
                      setHostGroupCandidate(first?.group_name ?? "");
                    }}
                    className="glass-input glass-focus w-full rounded-xl px-3 py-2 pr-9 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  {hostGroupSearch.trim().length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        setHostGroupSearch("");
                        setHostGroupCandidate(hostGroups[0]?.group_name ?? "");
                      }}
                      aria-label="Clear group search"
                      title="Clear group search"
                      disabled={!editingHost}
                      className="glass-btn-secondary glass-focus absolute top-1/2 right-1 inline-flex h-7 w-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-sm disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      ×
                    </button>
                  )}
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <select
                    value={hostGroupCandidate}
                    disabled={!editingHost}
                    onChange={(event) => setHostGroupCandidate(event.target.value)}
                    className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <option value="">No group</option>
                    {hostGroups
                      .filter((group) =>
                        group.group_name.toLowerCase().includes(hostGroupSearch.trim().toLowerCase()),
                      )
                      .map((group) => (
                        <option key={group.group_name} value={group.group_name}>
                          {group.group_name}
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      if (!editingHost) return;
                      setHostSelectedGroup(hostGroupCandidate);
                    }}
                    disabled={!editingHost}
                    className="glass-btn-secondary accent-outline-btn glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Select
                  </button>
                </div>
                {!editingHost && (
                  <p className="glass-muted text-xs">Create host first, then assign group.</p>
                )}
              </div>

              <div className="mt-1 border-t border-[var(--glass-soft-border)] pt-3">
                <div className="assigned-groups-panel rounded-xl p-3">
                  <p className="glass-muted mb-2 text-[10px] uppercase tracking-wide">Assigned group</p>
                  <div className="flex flex-wrap gap-2">
                    {hostSelectedGroup ? (
                      <div className="assigned-chip">
                        <TruncatedLabel text={hostSelectedGroup} className="assigned-chip-label" />
                        <button
                          type="button"
                          onClick={() => setHostSelectedGroup("")}
                          className="assigned-chip-remove glass-focus"
                          aria-label={`Remove ${hostSelectedGroup}`}
                          title={`Remove ${hostSelectedGroup}`}
                        >
                          ×
                        </button>
                      </div>
                    ) : (
                      <span className="glass-muted text-xs">No group selected</span>
                    )}
                  </div>
                  {editingHost && hostCurrentGroup && (
                    <p className="glass-muted mt-2 text-xs">
                      Current group in DB: <span className="glass-title font-medium">{hostCurrentGroup}</span>
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {!editingHost && (
              <button
                type="button"
                onClick={createHostAndContinue}
                className="glass-btn-secondary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
              >
                Create and continue
              </button>
            )}
            <button
              type="button"
              onClick={saveHost}
              className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
            >
              {editingHost ? "Save" : "Create"}
            </button>
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingUserGroup ? "Edit user group" : "Create user group"}
        open={userGroupModalOpen}
        onClose={() => setUserGroupModalOpen(false)}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Group name</p>
            <input
              placeholder="Group name"
              value={userGroupForm.group_name}
              disabled={Boolean(editingUserGroup)}
              onChange={(event) => setUserGroupForm((prev) => ({ ...prev, group_name: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
            <textarea
              placeholder="Description"
              value={userGroupForm.description ?? ""}
              onChange={(event) => setUserGroupForm((prev) => ({ ...prev, description: event.target.value }))}
              className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <button
            type="button"
            onClick={saveUserGroup}
            className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
          >
            Save
          </button>
        </div>
      </EntityModal>

      <EntityModal
        title={editingHostGroup ? "Edit host group" : "Create host group"}
        open={hostGroupModalOpen}
        onClose={() => setHostGroupModalOpen(false)}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Group name</p>
            <input
              placeholder="Group name"
              value={hostGroupForm.group_name}
              disabled={Boolean(editingHostGroup)}
              onChange={(event) => setHostGroupForm((prev) => ({ ...prev, group_name: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">TACACS key</p>
            <input
              placeholder="TACACS key"
              value={hostGroupForm.tacacs_key ?? ""}
              onChange={(event) => setHostGroupForm((prev) => ({ ...prev, tacacs_key: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
            <textarea
              placeholder="Description"
              value={hostGroupForm.description ?? ""}
              onChange={(event) => setHostGroupForm((prev) => ({ ...prev, description: event.target.value }))}
              className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <button
            type="button"
            onClick={saveHostGroup}
            className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
          >
            Save
          </button>
        </div>
      </EntityModal>

      <EntityModal
        title={editingPolicy ? "Recreate policy" : "Create policy"}
        open={policyModalOpen}
        onClose={() => setPolicyModalOpen(false)}
      >
        <div className="space-y-3">
          <select
            value={policyForm.user_group_name}
            onChange={(event) => setPolicyForm((prev) => ({ ...prev, user_group_name: event.target.value }))}
            className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
          >
            <option value="">
              Select user group
            </option>
            {userGroups.map((group) => (
              <option key={group.group_name} value={group.group_name}>
                {group.group_name}
              </option>
            ))}
          </select>

          <select
            value={policyForm.host_group_name}
            onChange={(event) => setPolicyForm((prev) => ({ ...prev, host_group_name: event.target.value }))}
            className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
          >
            <option value="">
              Select host group
            </option>
            {hostGroups.map((group) => (
              <option key={group.group_name} value={group.group_name}>
                {group.group_name}
              </option>
            ))}
          </select>

          <input
            type="number"
            min={0}
            max={15}
            value={policyForm.priv_lvl}
            onChange={(event) => setPolicyForm((prev) => ({ ...prev, priv_lvl: Number(event.target.value) }))}
            className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
          />

          <label className="glass-muted flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={policyForm.allow_access}
              onChange={(event) => setPolicyForm((prev) => ({ ...prev, allow_access: event.target.checked }))}
            />
            Allow access
          </label>

          <button
            type="button"
            onClick={savePolicy}
            className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
          >
            Save
          </button>
        </div>
      </EntityModal>

      <ConfirmDelete
        open={Boolean(deleteUserTarget)}
        title="Delete user"
        description={`Delete user ${deleteUserTarget?.username ?? ""}?`}
        onCancel={() => setDeleteUserTarget(null)}
        onConfirm={deleteUser}
      />

      <ConfirmDelete
        open={Boolean(deleteHostTarget)}
        title="Delete host"
        description={`Delete host ${deleteHostTarget?.ip_address ?? ""}?`}
        onCancel={() => setDeleteHostTarget(null)}
        onConfirm={deleteHost}
      />

      <ConfirmDelete
        open={Boolean(deleteUserGroupTarget)}
        title="Delete user group"
        description={`Delete user group ${deleteUserGroupTarget?.group_name ?? ""}?`}
        onCancel={() => setDeleteUserGroupTarget(null)}
        onConfirm={deleteUserGroup}
      />

      <ConfirmDelete
        open={Boolean(deleteHostGroupTarget)}
        title="Delete host group"
        description={`Delete host group ${deleteHostGroupTarget?.group_name ?? ""}?`}
        onCancel={() => setDeleteHostGroupTarget(null)}
        onConfirm={deleteHostGroup}
      />

      <ConfirmDelete
        open={Boolean(deletePolicyTarget)}
        title="Delete policy"
        description={`Delete policy #${deletePolicyTarget?.policy_id ?? ""}?`}
        onCancel={() => setDeletePolicyTarget(null)}
        onConfirm={deletePolicy}
      />

      <EntityModal
        title="Generated TACACS files"
        open={applyPreviewOpen}
        onClose={() => setApplyPreviewOpen(false)}
      >
        <div className="space-y-3">
          <p className="glass-muted text-sm">
            Files are generated and saved to <code>/etc/tac_plus-ng</code>.
          </p>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">users</p>
            <textarea
              readOnly
              value={applyPreview?.users ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">hosts</p>
            <textarea
              readOnly
              value={applyPreview?.hosts ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">host_groups</p>
            <textarea
              readOnly
              value={applyPreview?.host_groups ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>
        </div>
      </EntityModal>
    </div>
  );
}
