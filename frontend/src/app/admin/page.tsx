"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
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
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { Alert } from "@/components/common/alert";
import { ConfirmDelete } from "@/components/common/confirm-delete";
import { DataTable } from "@/components/common/data-table";
import { EntityModal } from "@/components/common/entity-modal";
import { ApiError, api } from "@/lib/api/client";
import type {
  AuthMode,
  Vendor,
  VendorCreatePayload,
  GenerateConfigResponse,
  Device,
  DeviceCreatePayload,
  DeviceGroup,
  DeviceGroupCreatePayload,
  Profile,
  ProfileCreatePayload,
  TacacsLogLevel,
  TacacsLogEvent,
  TacacsLogLine,
  TotpProfile,
  User,
  UserCreatePayload,
} from "@/lib/types/tacacs";

type SectionKey =
  | "dashboard"
  | "users"
  | "vendors"
  | "devices"
  | "deviceGroups"
  | "policies"
  | "settings";

type ThemeMode = "dark" | "light";
type GroupAccessMode = "read-only" | "read-write";

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

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim();
}

function hasAnyWhitespace(value: string): boolean {
  return /\s/.test(value);
}

function ensureNoSpaces(field: string, value: string): void {
  if (hasAnyWhitespace(value)) {
    throw new Error(`${field} must not contain spaces`);
  }
}

function IconDashboard() {
  return <LayoutDashboard className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconUsers() {
  return <Users className="h-4 w-4" strokeWidth={2} aria-hidden="true" />;
}

function IconDevices() {
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

type SearchableOption = {
  value: string;
  label: string;
};

function SearchableSelect({
  value,
  options,
  placeholder,
  disabled,
  onChange,
}: {
  value: string;
  options: SearchableOption[];
  placeholder: string;
  disabled?: boolean;
  onChange: (nextValue: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const selectedLabel = useMemo(
    () => options.find((option) => option.value === value)?.label ?? "",
    [options, value],
  );

  const filteredOptions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return options;
    return options.filter((option) => option.label.toLowerCase().includes(normalized));
  }, [options, query]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const openDropdown = () => {
    if (disabled) return;
    setIsOpen(true);
    setQuery("");
  };

  return (
    <div ref={rootRef} className="relative">
      <input
        ref={inputRef}
        value={isOpen ? query : selectedLabel}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={openDropdown}
        onClick={openDropdown}
        onChange={(event) => {
          if (!isOpen) setIsOpen(true);
          setQuery(event.target.value);
        }}
        className="glass-input glass-focus w-full rounded-xl px-3 py-2 pr-9 text-sm disabled:cursor-not-allowed disabled:opacity-60"
      />
      {isOpen && !disabled && (
        <div className="glass-panel absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-xl p-1">
          {filteredOptions.length === 0 && (
            <div className="glass-muted px-2 py-1.5 text-xs">No matches</div>
          )}
          {filteredOptions.map((option) => (
            <button
              key={`${option.value}-${option.label}`}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
                setQuery("");
              }}
              className="glass-focus glass-btn-secondary block w-full cursor-pointer rounded-lg px-2 py-1.5 text-left text-sm"
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
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
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceGroups, setDeviceGroups] = useState<DeviceGroup[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const [loading, setLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState<string>(new Date().toLocaleString());
  const [logLines, setLogLines] = useState<TacacsLogLine[]>([]);
  const [logEvents, setLogEvents] = useState<TacacsLogEvent[]>([]);
  const [logSearch, setLogSearch] = useState("");
  const [logLoading, setLogLoading] = useState(false);
  const [logRefreshing, setLogRefreshing] = useState(false);
  const [logError, setLogError] = useState("");
  const [logMissing, setLogMissing] = useState(false);
  const [logFingerprint, setLogFingerprint] = useState("");

  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "dark";
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [openDeviceMenu, setOpenDeviceMenu] = useState(false);

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

  const [deviceModalOpen, setDeviceModalOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [deviceModalError, setDeviceModalError] = useState<string>("");
  const [deleteDeviceTarget, setDeleteDeviceTarget] = useState<Device | null>(null);
  const [deviceForm, setDeviceForm] = useState<DeviceCreatePayload>({
    ip_address: "",
    tacacs_key: "",
    hostname: "",
    vendor_name: "",
    description: "",
  });

  const [userSelectedGroups, setUserSelectedGroups] = useState<string[]>([]);
  const [userInitialGroups, setUserInitialGroups] = useState<string[]>([]);
  const [userInitialGroupModes, setUserInitialGroupModes] = useState<Record<string, GroupAccessMode>>({});
  const [userSelectedGroupModes, setUserSelectedGroupModes] = useState<Record<string, GroupAccessMode>>({});

  const [deviceGroupModalOpen, setDeviceGroupModalOpen] = useState(false);
  const [editingDeviceGroup, setEditingDeviceGroup] = useState<DeviceGroup | null>(null);
  const [deleteDeviceGroupTarget, setDeleteDeviceGroupTarget] = useState<DeviceGroup | null>(null);
  const [deviceGroupForm, setDeviceGroupForm] = useState<DeviceGroupCreatePayload>({
    group_name: "",
    tacacs_key: "",
    description: "",
  });
  const [deviceCurrentGroup, setDeviceCurrentGroup] = useState<string>("");
  const [deviceSelectedGroup, setDeviceSelectedGroup] = useState<string>("");
  const [deviceInitialGroups, setDeviceInitialGroups] = useState<string[]>([]);
  const [deviceGroupsByIp, setDeviceGroupsByIp] = useState<Record<string, string>>({});

  const [userGroupCandidate, setUserGroupCandidate] = useState("");
  const [userGroupAccessMode, setUserGroupAccessMode] = useState<GroupAccessMode>("read-only");
  const [userSelectedProfile, setUserSelectedProfile] = useState<string>("");
  const [userProfileCandidate, setUserProfileCandidate] = useState<string>("");
  const [deviceGroupCandidate, setDeviceGroupCandidate] = useState("");

  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [deleteProfileTarget, setDeleteProfileTarget] = useState<Profile | null>(null);
  const [profileModalError, setProfileModalError] = useState<string>("");
  const [profileForm, setProfileForm] = useState<ProfileCreatePayload>({
    profile_name: "",
    profile_body: "",
    description: "",
    is_active: true,
  });

  const [vendorModalOpen, setVendorModalOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState<Vendor | null>(null);
  const [deleteVendorTarget, setDeleteVendorTarget] = useState<Vendor | null>(null);
  const [vendorForm, setVendorForm] = useState<VendorCreatePayload>({
    vendor_name: "",
    description: "",
  });

  const loadUsers = async () => {
    const result = await api.users.list();
    setUsers(result.data ?? []);
  };

  const loadVendors = async () => {
    const result = await api.vendors.list();
    setVendors(result.data ?? []);
  };

  const loadDevices = async () => {
    const result = await api.devices.list();
    setDevices(result.data ?? []);
  };

  const loadDeviceGroups = async () => {
    const result = await api.deviceGroups.list();
    setDeviceGroups(result.data ?? []);
  };

  const loadProfiles = async () => {
    const result = await api.profiles.list();
    setProfiles(result.data ?? []);
  };

  const loadDeviceGroupSummary = async () => {
    const result = await api.deviceGroups.members.list();
    const map: Record<string, string> = {};
    for (const row of result.data ?? []) {
      if (!map[row.ip_address]) {
        map[row.ip_address] = row.group_name;
      }
    }
    setDeviceGroupsByIp(map);
  };

  const loadTacacsLogs = useCallback(
    async (background = false) => {
      if (background) {
        setLogRefreshing(true);
      } else if (logLines.length === 0) {
        setLogLoading(true);
      }
      try {
        const result = await api.logs.tacacs(200);
        const nextLines = result.lines ?? [];
        const nextFingerprint = nextLines
          .map((line) => `${line.id}|${line.timestamp ?? ""}|${line.message ?? ""}`)
          .join("\n");

        if (nextFingerprint !== logFingerprint) {
          setLogLines(nextLines);
          setLogFingerprint(nextFingerprint);
        }
        setLogEvents(result.events ?? []);
        setLogMissing(result.missing);
        setLogError("");
      } catch (error) {
        setLogError(getErrorMessage(error));
      } finally {
        if (background) {
          setLogRefreshing(false);
        } else {
          setLogLoading(false);
        }
      }
    },
    [logFingerprint, logLines.length],
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    setGlobalError("");
    try {
      await Promise.all([
        loadUsers(),
        loadVendors(),
        loadDevices(),
        loadDeviceGroups(),
        loadProfiles(),
        loadDeviceGroupSummary(),
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

      const apply = result.apply;
      if (apply) {
        if (apply.validated && apply.reloaded) {
          setApplyStatus(`Validated and reloaded. Generated in ${result.path}. ${summary}`);
        } else {
          const validationError =
            apply.validation?.stderr || apply.validation?.stdout || apply.error || "TACACS config validation failed";
          throw new Error(validationError);
        }
      } else {
        setApplyStatus(`Generated in ${result.path}. ${summary}`);
      }

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
    if (activeSection !== "dashboard") return;

    void loadTacacsLogs(false);
    const interval = setInterval(() => {
      void loadTacacsLogs(true);
    }, 5000);

    return () => clearInterval(interval);
  }, [activeSection, loadTacacsLogs]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const sectionTitle = useMemo(() => {
    const labels: Record<SectionKey, string> = {
      dashboard: "Dashboard",
      users: "Users",
      vendors: "Vendor Profiles",
      devices: "Devices",
      deviceGroups: "Device Groups",
      policies: "Policies",
      settings: "Settings",
    };
    return labels[activeSection];
  }, [activeSection]);

  const sectionIcon = useMemo(() => {
    const map: Record<SectionKey, ReactNode> = {
      dashboard: <IconDashboard />,
      users: <IconUsers />,
      vendors: <IconDevices />,
      devices: <IconDevices />,
      deviceGroups: <IconDevices />,
      policies: <IconPolicy />,
      settings: <IconSettings />,
    };
    return map[activeSection];
  }, [activeSection]);

  const filteredLogLines = useMemo(() => {
    const query = logSearch.trim().toLowerCase();
    if (!query) return logLines;
    return logLines.filter((line) => {
      const haystack = `${line.timestamp ?? ""} ${line.host ?? ""} ${line.session ?? ""} ${line.message ?? ""}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [logLines, logSearch]);

  const authCharts = useMemo(() => {
    const buckets = new Map<
      string,
      {
        label: string;
        success: number;
        fail: number;
        deny: number;
        permit: number;
        authzSuccess: number;
        authzFail: number;
      }
    >();
    const successUsers = new Map<string, number>();
    const successDevices = new Map<string, number>();
    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    const parseEventDate = (event: TacacsLogEvent): Date | null => {
      if (!event.timestamp) return null;
      const hhmmss = event.timestamp.slice(0, 8);
      const today = new Date();
      const parsed = new Date(
        `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}T${hhmmss}`,
      );
      if (!Number.isNaN(parsed.getTime())) return parsed;
      return null;
    };

    const bucketLabel = (date: Date) =>
      `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

    for (const event of logEvents) {
      const lineDate = parseEventDate(event);
      if (!lineDate || lineDate < weekAgo || lineDate > now) continue;

      const label = bucketLabel(lineDate);

      if (!buckets.has(label)) {
        buckets.set(label, { label, success: 0, fail: 0, deny: 0, permit: 0, authzSuccess: 0, authzFail: 0 });
      }

      const entry = buckets.get(label)!;
      const isSuccess = event.result === "success";
      const isFail = event.result === "failure";
      const isAuthorizationEvent = event.kind === "authorization";
      const isAuthzSuccess = isAuthorizationEvent && isSuccess;
      const isAuthzFail = isAuthorizationEvent && isFail;
      const message = event.message.toLowerCase();
      const isDeny = message.includes("deny");
      const isPermit = message.includes("permit") || message.includes("pass");

      if (isSuccess) entry.success += 1;
      if (isFail) entry.fail += 1;
      if (isDeny) entry.deny += 1;
      if (isPermit) entry.permit += 1;
      if (isAuthzSuccess) entry.authzSuccess += 1;
      if (isAuthzFail) entry.authzFail += 1;

      if (isSuccess) {
        const user = event.username || event.session_id || "unknown-user";
        const device = event.remote_addr || event.host || "unknown-device";
        successUsers.set(user, (successUsers.get(user) ?? 0) + 1);
        successDevices.set(device, (successDevices.get(device) ?? 0) + 1);
      }
    }

    const trend = [...buckets.values()].sort((a, b) => a.label.localeCompare(b.label));
    const topUsers = [...successUsers.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, value]) => ({ name, value }));

    const topDevices = [...successDevices.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, value]) => ({ name, value }));

    return {
      trend,
      authorization: trend,
      topUsers,
      topDevices,
    };
  }, [logEvents]);

  const userGroupBaseNames = useMemo(() => {
    const unique = new Set<string>();
    for (const group of deviceGroups) unique.add(group.group_name);
    return [...unique].sort((a, b) => a.localeCompare(b));
  }, [deviceGroups]);

  const levelRowClass = (level: TacacsLogLevel) => {
    switch (level) {
      case "error":
        return "log-row-base log-row-error";
      case "warn":
        return "log-row-base log-row-warn";
      case "info":
        return "log-row-base log-row-info";
      case "debug":
        return "log-row-base log-row-debug";
      default:
        return "log-row-base";
    }
  };

  const formatGroupWithAccess = useCallback((groupName: string, mode?: GroupAccessMode) => {
    const suffix = mode === "read-write" ? "_rw" : "_ro";
    return `${groupName}${suffix}`;
  }, []);

  const openCreateUser = () => {
    setEditingUser(null);
    setUserForm({ username: "", password: "", full_name: "", description: "", is_active: true });
    setUserPasswordConfirm("");
    setUserModalError("");
    resetUserAuthState("password");
    setUserSelectedGroups([]);
    setUserInitialGroups([]);
    setUserInitialGroupModes({});
    setUserSelectedGroupModes({});
    setUserGroupCandidate("");
    setUserGroupAccessMode("read-only");
    setUserSelectedProfile("");
    setUserProfileCandidate("");
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
    setUserInitialGroupModes({});
    setUserSelectedGroupModes({});
    setUserGroupCandidate("");
    setUserGroupAccessMode("read-only");
    setUserSelectedProfile("");
    setUserProfileCandidate("");
    setUserModalOpen(true);
    void hydrateUserAuthState(user.username);
    void (async () => {
      try {
        const [groupResult, profileResult] = await Promise.all([
          api.userGroups.members.list({ username: user.username }),
          api.profiles.userMembers.list({ username: user.username }),
        ]);

        const groupRows = groupResult.data ?? [];
        const groups = groupRows.map((row) => row.group_name);
        const modes: Record<string, GroupAccessMode> = {};
        for (const row of groupRows) {
          modes[row.group_name] = row.ro_rw === 1 ? "read-write" : "read-only";
        }
        setUserSelectedGroups(groups);
        setUserInitialGroups(groups);
        setUserInitialGroupModes(modes);
        setUserSelectedGroupModes(modes);
        setUserGroupCandidate("");
        setUserGroupAccessMode("read-only");

        const assignedProfile = (profileResult.data ?? [])[0]?.profile_name ?? "";
        setUserSelectedProfile(assignedProfile);
        setUserProfileCandidate(assignedProfile || "");
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
      const username = normalizeText(userForm.username);
      if (!username) throw new Error("Username is required");
      ensureNoSpaces("Username", username);
      const usernameTaken = users.some(
        (user) => user.username.toLowerCase() === username.toLowerCase(),
      );
      if (usernameTaken) throw new Error("User with this username already exists");

      if (userAuthMode === "password" && !normalizeText(userForm.password)) {
        throw new Error("Password is required in password mode");
      }
      if (userAuthMode === "password" && userForm.password !== userPasswordConfirm) {
        throw new Error("Password confirmation does not match");
      }

      const payload: UserCreatePayload = {
        username,
        password:
          userAuthMode === "totp"
            ? normalizeText(userForm.password) || generateBootstrapPassword()
            : userForm.password,
        full_name: normalizeText(userForm.full_name),
        description: normalizeText(userForm.description),
        is_active: userForm.is_active,
      };

      const created = await api.users.create(payload);
      setEditingUser(created.user);
      setUserSelectedGroups([]);
      setUserInitialGroups([]);
      setUserInitialGroupModes({});
      setUserSelectedGroupModes({});
      setUserGroupCandidate("");
      setUserGroupAccessMode("read-only");
      setUserSelectedProfile("");
      setUserProfileCandidate("");

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
      const username = normalizeText(userForm.username);
      if (!username) throw new Error("Username is required");
      ensureNoSpaces("Username", username);
      const usernameTaken = users.some(
        (user) =>
          user.username.toLowerCase() === username.toLowerCase() &&
          (!editingUser || user.username !== editingUser.username),
      );
      if (usernameTaken) throw new Error("User with this username already exists");

      if (!editingUser && userAuthMode === "password" && !normalizeText(userForm.password)) {
        throw new Error("Password is required in password mode");
      }
      if (editingUser && userAuthMode === "password" && userInitialAuthMode === "totp" && !normalizeText(userForm.password)) {
        throw new Error("Password is required when switching from TOTP to password mode");
      }
      if (userAuthMode === "password") {
        const requiresPassword = !editingUser || userInitialAuthMode === "totp";
        const hasEnteredPassword = normalizeText(userForm.password).length > 0;
        if ((requiresPassword || hasEnteredPassword) && userForm.password !== userPasswordConfirm) {
          throw new Error("Password confirmation does not match");
        }
      }

      if (editingUser) {
        await api.users.update(editingUser.username, {
          password: normalizeText(userForm.password) || undefined,
          full_name: normalizeText(userForm.full_name),
          description: normalizeText(userForm.description),
          is_active: userForm.is_active,
        });

        const selected = new Set(userSelectedGroups);
        const initial = new Set(userInitialGroups);
        const toAdd = [...selected].filter((group) => !initial.has(group));
        const toUpdateMode = [...selected].filter(
          (group) => initial.has(group) && userInitialGroupModes[group] !== userSelectedGroupModes[group],
        );
        const toRemove = [...initial].filter((group) => !selected.has(group));
        await Promise.all([
          ...toAdd.map((group_name) =>
            api.userGroups.members.add({
              username: editingUser.username,
              group_name,
              ro_rw: userSelectedGroupModes[group_name] === "read-write" ? 1 : 0,
            }),
          ),
          ...toUpdateMode.map((group_name) =>
            api.userGroups.members.add({
              username: editingUser.username,
              group_name,
              ro_rw: userSelectedGroupModes[group_name] === "read-write" ? 1 : 0,
            }),
          ),
          ...toRemove.map((group_name) =>
            api.userGroups.members.remove({ username: editingUser.username, group_name }),
          ),
        ]);

        const currentProfileResult = await api.profiles.userMembers.list({ username: editingUser.username });
        const currentProfiles = (currentProfileResult.data ?? []).map((row) => row.profile_name);
        const profilesToRemove = currentProfiles.filter((profile_name) => profile_name !== userSelectedProfile);
        const shouldAddProfile = Boolean(userSelectedProfile) && !currentProfiles.includes(userSelectedProfile);

        await Promise.all([
          ...profilesToRemove.map((profile_name) =>
            api.profiles.userMembers.remove({ username: editingUser.username, profile_name }),
          ),
          ...(shouldAddProfile
            ? [api.profiles.userMembers.add({ username: editingUser.username, profile_name: userSelectedProfile })]
            : []),
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
          username,
          password:
            userAuthMode === "totp"
              ? normalizeText(userForm.password) || generateBootstrapPassword()
              : userForm.password,
          full_name: normalizeText(userForm.full_name),
          description: normalizeText(userForm.description),
          is_active: userForm.is_active,
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

  const openCreateDevice = () => {
    setEditingDevice(null);
    setDeviceModalError("");
    setDeviceForm({ ip_address: "", tacacs_key: "", hostname: "", vendor_name: "", description: "" });
    setDeviceCurrentGroup("");
    setDeviceSelectedGroup("");
    setDeviceInitialGroups([]);
    setDeviceGroupCandidate("");
    setDeviceModalOpen(true);
  };

  const openEditDevice = (device: Device) => {
    setEditingDevice(device);
    setDeviceModalError("");
    setDeviceForm({
      ip_address: device.ip_address,
      tacacs_key: device.tacacs_key,
      hostname: device.hostname ?? "",
      vendor_name: device.vendor_name ?? "",
      description: device.description ?? "",
    });
    setDeviceCurrentGroup("");
    setDeviceSelectedGroup("");
    setDeviceInitialGroups([]);
    setDeviceGroupCandidate("");
    setDeviceModalOpen(true);
    void (async () => {
      try {
        const result = await api.deviceGroups.members.list({ ip_address: device.ip_address });
        const groups = (result.data ?? []).map((row) => row.group_name);
        const firstGroup = groups[0] ?? "";
        setDeviceInitialGroups(groups);
        setDeviceCurrentGroup(firstGroup);
        setDeviceSelectedGroup(firstGroup);
        setDeviceGroupCandidate(firstGroup);
      } catch (error) {
        setGlobalError(getErrorMessage(error));
      }
    })();
  };

  const createDeviceAndContinue = async () => {
    if (editingDevice) return;
    setDeviceModalError("");
    try {
      const ipAddress = normalizeText(deviceForm.ip_address);
      const hostname = normalizeText(deviceForm.hostname);
      const vendorName = normalizeText(deviceForm.vendor_name);
      if (!ipAddress) throw new Error("IP address is required");
      if (!isStrictIpv4(ipAddress)) throw new Error("IP address must be a valid IPv4 address");
      const ipTaken = devices.some((device) => device.ip_address === ipAddress);
      if (ipTaken) throw new Error("Device with this IP already exists");
      if (!vendorName) throw new Error("Vendor profile is required");
      if (hostname) ensureNoSpaces("Hostname", hostname);
      ensureNoSpaces("Vendor profile", vendorName);

      const payload: DeviceCreatePayload = {
        ip_address: ipAddress,
        tacacs_key: normalizeText(deviceForm.tacacs_key),
        hostname,
        vendor_name: vendorName,
        description: normalizeText(deviceForm.description),
      };

      const created = await api.devices.create(payload);
      setEditingDevice(created.device);
      setDeviceInitialGroups([]);
      setDeviceCurrentGroup("");
      setDeviceSelectedGroup("");
      setDeviceGroupCandidate("");

      await loadDevices();
      await loadDeviceGroupSummary();
    } catch (error) {
      setDeviceModalError(getErrorMessage(error));
    }
  };

  const saveDevice = async () => {
    setDeviceModalError("");
    try {
      const ipAddress = normalizeText(deviceForm.ip_address);
      const hostname = normalizeText(deviceForm.hostname);
      const vendorName = normalizeText(deviceForm.vendor_name);
      const tacacsKey = normalizeText(deviceForm.tacacs_key);
      const description = normalizeText(deviceForm.description);
      if (!ipAddress) throw new Error("IP address is required");
      if (!isStrictIpv4(ipAddress)) throw new Error("IP address must be a valid IPv4 address");
      const ipTaken = devices.some(
        (device) =>
          device.ip_address === ipAddress &&
          (!editingDevice || device.ip_address !== editingDevice.ip_address),
      );
      if (ipTaken) throw new Error("Device with this IP already exists");
      if (!vendorName) throw new Error("Vendor profile is required");
      if (hostname) ensureNoSpaces("Hostname", hostname);
      ensureNoSpaces("Vendor profile", vendorName);

      if (editingDevice) {
        await api.devices.update(editingDevice.ip_address, {
          new_ip_address: ipAddress,
          tacacs_key: tacacsKey,
          hostname,
          vendor_name: vendorName,
          description,
        });

        const groupsToRemove = deviceInitialGroups.filter((group_name) => group_name !== deviceSelectedGroup);
        await Promise.all(
          groupsToRemove.map((group_name) =>
            api.deviceGroups.members.remove({
              ip_address: ipAddress,
              group_name,
            }),
          ),
        );

        if (deviceSelectedGroup && !deviceInitialGroups.includes(deviceSelectedGroup)) {
          await api.deviceGroups.members.add({
            ip_address: ipAddress,
            group_name: deviceSelectedGroup,
          });
        }
      } else {
        await api.devices.create({
          ip_address: ipAddress,
          tacacs_key: tacacsKey,
          hostname,
          vendor_name: vendorName,
          description,
        });
      }

      await loadDevices();
      await loadDeviceGroupSummary();
      setDeviceModalOpen(false);
    } catch (error) {
      setDeviceModalError(getErrorMessage(error));
    }
  };

  const deleteDevice = async () => {
    if (!deleteDeviceTarget) return;
    setGlobalError("");
    try {
      await api.devices.delete(deleteDeviceTarget.ip_address);
      await loadDevices();
      setDeleteDeviceTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateDeviceGroup = () => {
    setEditingDeviceGroup(null);
    setDeviceGroupForm({ group_name: "", tacacs_key: "", description: "" });
    setDeviceGroupModalOpen(true);
  };

  const openEditDeviceGroup = (group: DeviceGroup) => {
    setEditingDeviceGroup(group);
    setDeviceGroupForm({
      group_name: group.group_name,
      tacacs_key: group.tacacs_key ?? "",
      description: group.description ?? "",
    });
    setDeviceGroupModalOpen(true);
  };

  const saveDeviceGroup = async () => {
    setGlobalError("");
    try {
      const groupName = normalizeText(deviceGroupForm.group_name);
      if (!groupName) throw new Error("Group name is required");
      ensureNoSpaces("Group name", groupName);
      const tacacsKey = normalizeText(deviceGroupForm.tacacs_key);
      const description = normalizeText(deviceGroupForm.description);

      if (editingDeviceGroup) {
        await api.deviceGroups.update(editingDeviceGroup.group_name, {
          group_name: editingDeviceGroup.group_name,
          tacacs_key: tacacsKey,
          description,
        });
      } else {
        await api.deviceGroups.create({
          group_name: groupName,
          tacacs_key: tacacsKey,
          description,
        });
      }

      await loadDeviceGroups();
      setDeviceGroupModalOpen(false);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const deleteDeviceGroup = async () => {
    if (!deleteDeviceGroupTarget) return;
    setGlobalError("");
    try {
      await api.deviceGroups.delete(deleteDeviceGroupTarget.group_name);
      await loadDeviceGroups();
      await loadDeviceGroupSummary();
      setDeleteDeviceGroupTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateProfile = () => {
    setEditingProfile(null);
    setProfileModalError("");
    setProfileForm({
      profile_name: "",
      profile_body: "",
      description: "",
      is_active: true,
    });
    setProfileModalOpen(true);
  };

  const openEditProfile = (profile: Profile) => {
    setEditingProfile(profile);
    setProfileModalError("");
    setProfileForm({
      profile_name: profile.profile_name,
      profile_body: profile.profile_body,
      description: profile.description ?? "",
      is_active: profile.is_active,
    });
    setProfileModalOpen(true);
  };

  const saveProfile = async () => {
    setProfileModalError("");
    try {
      const profileName = normalizeText(profileForm.profile_name);
      if (!profileName) throw new Error("Profile name is required");
      ensureNoSpaces("Profile name", profileName);
      if (!profileForm.profile_body.trim()) throw new Error("Profile body is required");
      const description = normalizeText(profileForm.description);

      if (editingProfile) {
        await api.profiles.update(editingProfile.profile_name, {
          profile_body: profileForm.profile_body,
          description,
          is_active: profileForm.is_active,
        });
      } else {
        await api.profiles.create({
          profile_name: profileName,
          profile_body: profileForm.profile_body,
          description,
          is_active: profileForm.is_active,
        });
      }

      await loadProfiles();
      setProfileModalOpen(false);
    } catch (error) {
      setProfileModalError(getErrorMessage(error));
    }
  };

  const deleteProfile = async () => {
    if (!deleteProfileTarget) return;
    setGlobalError("");
    try {
      await api.profiles.delete(deleteProfileTarget.profile_name);
      await loadProfiles();
      setDeleteProfileTarget(null);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const openCreateVendor = () => {
    setEditingVendor(null);
    setVendorForm({ vendor_name: "", description: "" });
    setVendorModalOpen(true);
  };

  const openEditVendor = (vendor: Vendor) => {
    setEditingVendor(vendor);
    setVendorForm({
      vendor_name: vendor.vendor_name,
      description: vendor.description ?? "",
    });
    setVendorModalOpen(true);
  };

  const saveVendor = async () => {
    setGlobalError("");
    try {
      const vendorName = normalizeText(vendorForm.vendor_name);
      if (!vendorName) throw new Error("Vendor name is required");
      ensureNoSpaces("Vendor name", vendorName);
      const description = normalizeText(vendorForm.description);

      if (editingVendor) {
        await api.vendors.update(editingVendor.vendor_name, {
          vendor_name: editingVendor.vendor_name,
          description,
        });
      } else {
        await api.vendors.create({
          vendor_name: vendorName,
          description,
        });
      }

      await loadVendors();
      setVendorModalOpen(false);
    } catch (error) {
      setGlobalError(getErrorMessage(error));
    }
  };

  const deleteVendor = async () => {
    if (!deleteVendorTarget) return;
    setGlobalError("");
    try {
      await api.vendors.delete(deleteVendorTarget.vendor_name);
      await loadVendors();
      setDeleteVendorTarget(null);
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
          <Link
            href="/admin"
            className="glass-focus mb-3 block w-full rounded-lg"
            aria-label="Open dashboard"
            onClick={() => setActiveSection("dashboard")}
          >
            <Image
              src={theme === "dark" ? "/irit-200-75-dark.svg" : "/irit-200-75.svg"}
              alt="IRIT company logo"
              width={140}
              height={53}
              unoptimized
              className="h-auto w-full"
            />
          </Link>
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
              onClick={() => setActiveSection("users")}
              className={`glass-focus glass-btn inline-flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm transition ${
                activeSection === "users" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
              }`}
            >
              <IconUsers />
              Tacacs Users
            </button>

            <button
              type="button"
              onClick={() => setOpenDeviceMenu((prev) => !prev)}
              className="glass-focus glass-btn inline-flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm transition"
            >
              <span className="inline-flex items-center gap-2">
                <IconDevices />
                Tacacs Devices
              </span>
              <IconChevron open={openDeviceMenu} />
            </button>
            {openDeviceMenu && (
              <div className="ml-3 space-y-1">
                <button
                  type="button"
                  onClick={() => setActiveSection("devices")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "devices" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Devices
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection("deviceGroups")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "deviceGroups" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Device Groups
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection("vendors")}
                  className={`glass-focus glass-btn w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                    activeSection === "vendors" ? "glass-btn" : "glass-muted opacity-90 hover:opacity-100"
                  }`}
                >
                  Vendor Profiles
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
              Policy Profiles
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
              {activeSection === "devices" && (
                <button
                  type="button"
                  onClick={openCreateDevice}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add device
                </button>
              )}
              {activeSection === "vendors" && (
                <button
                  type="button"
                  onClick={openCreateVendor}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add vendor profile
                </button>
              )}
              {activeSection === "deviceGroups" && (
                <button
                  type="button"
                  onClick={openCreateDeviceGroup}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add device group
                </button>
              )}
              {activeSection === "policies" && (
                <button
                  type="button"
                  onClick={openCreateProfile}
                  className="glass-btn-primary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium transition"
                >
                  Add profile
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
                    <p className="glass-muted text-xs uppercase tracking-wide">Devices summary</p>
                    <p className="glass-title mt-2 text-3xl font-semibold">{devices.length}</p>
                    <p className="glass-muted mt-1 text-sm">Total devices</p>
                  </div>
                  <div className="glass-panel rounded-2xl p-4">
                    <p className="glass-muted text-xs uppercase tracking-wide">Current time</p>
                    <p className="glass-title mt-2 text-xl font-semibold">{currentTime}</p>
                    <p className="glass-muted mt-1 text-sm">Server dashboard clock</p>
                  </div>
                </div>

                <div className="glass-panel rounded-2xl p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="glass-title text-base font-semibold">Authentication & Authorization Analytics</p>
                      <p className="glass-muted text-xs">Charts for last 7 days</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    <div className="glass-soft rounded-xl p-3">
                      <p className="glass-muted mb-2 text-xs uppercase tracking-wide">Authentication Stats</p>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={authCharts.trend} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid-stroke)" />
                            <XAxis dataKey="label" tick={{ fill: "var(--chart-axis-text)", fontSize: 11 }} />
                            <YAxis tick={{ fill: "var(--chart-axis-text)", fontSize: 11 }} allowDecimals={false} />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="success" name="success authn" stroke="#22c55e" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="fail" name="failed authn" stroke="#f472b6" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    <div className="glass-soft rounded-xl p-3">
                      <p className="glass-muted mb-2 text-xs uppercase tracking-wide">Authorization Stats</p>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={authCharts.authorization} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid-stroke)" />
                            <XAxis dataKey="label" tick={{ fill: "var(--chart-axis-text)", fontSize: 11 }} />
                            <YAxis tick={{ fill: "var(--chart-axis-text)", fontSize: 11 }} allowDecimals={false} />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="authzSuccess" name="success authz" stroke="#22c55e" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="authzFail" name="failed authz" stroke="#f472b6" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    <div className="glass-soft rounded-xl p-3">
                      <p className="glass-muted mb-2 text-xs uppercase tracking-wide">Top 5 Active Users (success only)</p>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={authCharts.topUsers}
                              cx="50%"
                              cy="50%"
                              innerRadius={55}
                              outerRadius={92}
                              paddingAngle={3}
                              dataKey="value"
                              nameKey="name"
                            >
                              {authCharts.topUsers.map((entry, index) => (
                                <Cell
                                  key={`user-pie-${entry.name}`}
                                  fill={["#38bdf8", "#22c55e", "#a78bfa", "#f59e0b", "#f472b6"][index % 5]}
                                />
                              ))}
                            </Pie>
                            <Tooltip />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    <div className="glass-soft rounded-xl p-3">
                      <p className="glass-muted mb-2 text-xs uppercase tracking-wide">Top 5 Used Devices (success only)</p>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={authCharts.topDevices}
                              cx="50%"
                              cy="50%"
                              innerRadius={55}
                              outerRadius={92}
                              paddingAngle={3}
                              dataKey="value"
                              nameKey="name"
                            >
                              {authCharts.topDevices.map((entry, index) => (
                                <Cell
                                  key={`device-pie-${entry.name}`}
                                  fill={["#a78bfa", "#38bdf8", "#22c55e", "#f59e0b", "#f472b6"][index % 5]}
                                />
                              ))}
                            </Pie>
                            <Tooltip />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="glass-panel rounded-2xl p-4">
                  <div className="flex flex-col gap-3 border-b border-[var(--glass-soft-border)] pb-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="glass-title text-base font-semibold">TACACS log stream</p>
                      <p className="glass-muted text-xs">
                        Last 200 lines from <code>/var/log/tac_plus-ng/tac_plus-ng.log</code>
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        placeholder="Search logs"
                        value={logSearch}
                        onChange={(event) => setLogSearch(event.target.value)}
                        className="glass-input glass-focus w-56 rounded-xl px-3 py-2 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => void loadTacacsLogs(false)}
                        className="glass-btn glass-focus inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm"
                      >
                        <IconRefresh />
                        Refresh
                      </button>
                    </div>
                  </div>

                  {logRefreshing && (
                    <div className="mt-3 text-xs">
                      <span className="status-success-text">Auto-refreshing…</span>
                    </div>
                  )}

                  {logLoading && <p className="glass-muted mt-3 text-sm">Loading logs...</p>}
                  {logError && <Alert message={logError} variant="error" />}
                  {!logLoading && logMissing && <Alert message="Log file is not available yet" variant="info" />}
                  {!logLoading && !logError && !logMissing && filteredLogLines.length === 0 && (
                    <p className="glass-muted mt-3 text-sm">No log lines match current filter.</p>
                  )}

                  {!logLoading && !logError && !logMissing && filteredLogLines.length > 0 && (
                    <div className="log-stream mt-3 max-h-[28rem] overflow-auto rounded-xl p-2">
                      <div className="space-y-1 font-mono text-xs">
                        {filteredLogLines.map((line) => (
                          <div
                            key={line.id}
                            className={`rounded-md px-2 py-1.5 whitespace-pre-wrap break-words ${levelRowClass(line.level)}`}
                            title={line.raw}
                          >
                            {line.raw || line.message}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
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

            {activeSection === "devices" && (
              <DataTable
                enableControls
                rows={devices}
                emptyText="No devices"
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
                    header: "Device Group",
                    render: (row) => deviceGroupsByIp[row.ip_address] ?? "—",
                    getSortValue: (row) => deviceGroupsByIp[row.ip_address] ?? "",
                    getSearchValue: (row) => deviceGroupsByIp[row.ip_address] ?? "",
                  },
                  {
                    key: "vendor",
                    header: "Vendor Profile",
                    render: (row) => row.vendor_name ?? "—",
                    getSortValue: (row) => row.vendor_name ?? "",
                    getSearchValue: (row) => row.vendor_name ?? "",
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
                        () => openEditDevice(row),
                        () => setDeleteDeviceTarget(row),
                      ),
                  },
                ]}
              />
            )}


            {activeSection === "vendors" && (
              <DataTable
                enableControls
                rows={vendors}
                emptyText="No vendor profiles"
                columns={[
                  {
                    key: "name",
                    header: "Vendor Profile",
                    render: (row) => row.vendor_name,
                    getSortValue: (row) => row.vendor_name,
                    getSearchValue: (row) => row.vendor_name,
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
                        () => openEditVendor(row),
                        () => setDeleteVendorTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "deviceGroups" && (
              <DataTable
                enableControls
                rows={deviceGroups}
                emptyText="No device groups"
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
                        () => openEditDeviceGroup(row),
                        () => setDeleteDeviceGroupTarget(row),
                      ),
                  },
                ]}
              />
            )}

            {activeSection === "policies" && (
              <DataTable
                enableControls
                rows={profiles}
                emptyText="No profiles"
                columns={[
                  {
                    key: "name",
                    header: "Profile",
                    render: (row) => row.profile_name,
                    getSortValue: (row) => row.profile_name,
                    getSearchValue: (row) => row.profile_name,
                  },
                  {
                    key: "active",
                    header: "Active",
                    render: (row) => (row.is_active ? "Yes" : "No"),
                    sortable: false,
                    getSearchValue: (row) => (row.is_active ? "yes active" : "no disabled"),
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
                        () => openEditProfile(row),
                        () => setDeleteProfileTarget(row),
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
        actions={
          <button
            type="button"
            onClick={saveUser}
            disabled={userSubmitting || userAuthLoading}
            className="glass-btn-primary glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-70"
          >
            {userSubmitting ? "Saving..." : editingUser ? "Save" : "Create"}
          </button>
        }
        onClose={() => {
          if (userSubmitting) return;
          setUserPasswordConfirm("");
          setUserModalOpen(false);
        }}
      >
        <div className="max-h-[90vh] space-y-3 overflow-y-auto pr-1">
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

              <div className="space-y-2">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Profiles</p>
                {editingUser ? (
                  <>
                    <div className="grid gap-2">
                      <SearchableSelect
                        value={userProfileCandidate}
                        onChange={(nextProfile) => {
                          setUserProfileCandidate(nextProfile);
                          setUserSelectedProfile(nextProfile);
                        }}
                        placeholder="Search profile"
                        options={[
                          { value: "", label: "No profile" },
                          ...profiles.map((profile) => ({
                            value: profile.profile_name,
                            label: profile.profile_name,
                          })),
                        ]}
                      />
                    </div>
                  </>
                ) : (
                  <p className="glass-muted text-xs">Create user first, then assign profile.</p>
                )}

                <div className="assigned-groups-panel rounded-xl p-3">
                  <p className="glass-muted mb-2 text-[10px] uppercase tracking-wide">Assigned profile</p>
                  <div className="flex flex-wrap gap-2">
                    {userSelectedProfile ? (
                      <div className="assigned-chip">
                        <TruncatedLabel text={userSelectedProfile} className="assigned-chip-label" />
                        {editingUser && (
                          <button
                            type="button"
                            onClick={() => setUserSelectedProfile("")}
                            className="assigned-chip-remove glass-focus"
                            aria-label={`Remove ${userSelectedProfile}`}
                            title={`Remove ${userSelectedProfile}`}
                          >
                            ×
                          </button>
                        )}
                      </div>
                    ) : (
                      <span className="glass-muted text-xs">No profile selected</span>
                    )}
                  </div>
                </div>
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
                <p className="glass-muted text-xs uppercase tracking-wide">Device groups</p>
                <span className="assigned-count-badge">{userSelectedGroups.length}</span>
              </div>
              <div className="space-y-2">
                {editingUser ? (
                  <>
                    <div className="grid gap-2">
                      <SearchableSelect
                        value={userGroupCandidate}
                        onChange={(nextGroup) => {
                          setUserGroupCandidate(nextGroup);
                          const targetGroup = nextGroup.trim();
                          if (!targetGroup) return;

                          const existingMode = userSelectedGroupModes[targetGroup];
                          if (existingMode) {
                            setUserGroupAccessMode(existingMode);
                          } else {
                            setUserSelectedGroupModes((prev) => ({
                              ...prev,
                              [targetGroup]: userGroupAccessMode,
                            }));
                          }

                          setUserSelectedGroups((prev) =>
                            prev.includes(targetGroup) ? prev : [...prev, targetGroup],
                          );
                        }}
                        placeholder="Search group"
                        options={[
                          { value: "", label: "Select device group" },
                          ...userGroupBaseNames.map((groupName) => ({
                            value: groupName,
                            label: groupName,
                          })),
                        ]}
                      />
                    </div>
                    <div className="mt-1 inline-flex items-center gap-3">
                      <span className="glass-muted text-xs">read-only</span>
                      <Switch.Root
                        checked={userGroupAccessMode === "read-write"}
                        onCheckedChange={(checked) => {
                          const nextMode: GroupAccessMode = checked ? "read-write" : "read-only";
                          setUserGroupAccessMode(nextMode);

                          const targetGroup = userGroupCandidate.trim();
                          if (!targetGroup) return;

                          setUserSelectedGroups((prev) =>
                            prev.includes(targetGroup) ? prev : [...prev, targetGroup],
                          );
                          setUserSelectedGroupModes((prev) => ({
                            ...prev,
                            [targetGroup]: nextMode,
                          }));
                        }}
                        aria-label="Toggle device group access mode"
                        className="status-switch-root glass-focus"
                      >
                        <Switch.Thumb className="status-switch-thumb" />
                      </Switch.Root>
                      <span className="glass-muted text-xs">read-write</span>
                    </div>
                  </>
                ) : (
                  <p className="glass-muted text-xs">Create user first, then assign groups.</p>
                )}
              </div>

              <div className="mt-1 pt-3">
                <div className="assigned-groups-panel rounded-xl p-3">
                  <p className="glass-muted mb-2 text-[10px] uppercase tracking-wide">Assigned groups</p>
                  <div className="flex flex-wrap gap-2">
                    {userSelectedGroups.length === 0 && (
                      <span className="glass-muted text-xs">No groups assigned</span>
                    )}
                    {userSelectedGroups.map((groupName) => (
                      <div key={groupName} className="assigned-chip">
                        <TruncatedLabel
                          text={formatGroupWithAccess(groupName, userSelectedGroupModes[groupName])}
                          className="assigned-chip-label"
                        />
                        {editingUser && (
                          <button
                            type="button"
                            onClick={() => {
                              setUserSelectedGroups((prev) => prev.filter((group) => group !== groupName));
                              setUserSelectedGroupModes((prev) => {
                                const next = { ...prev };
                                delete next[groupName];
                                return next;
                              });
                            }}
                            className="assigned-chip-remove glass-focus"
                            aria-label={`Remove ${formatGroupWithAccess(groupName, userSelectedGroupModes[groupName])}`}
                            title={`Remove ${formatGroupWithAccess(groupName, userSelectedGroupModes[groupName])}`}
                          >
                            ×
                          </button>
                        )}
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
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingDevice ? "Edit device" : "Create device"}
        open={deviceModalOpen}
        actions={
          <button
            type="button"
            onClick={saveDevice}
            className="glass-btn-primary glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            {editingDevice ? "Save" : "Create"}
          </button>
        }
        onClose={() => {
          setDeviceModalError("");
          setDeviceModalOpen(false);
        }}
      >
        <div className="space-y-3">
          {deviceModalError && <Alert message={deviceModalError} variant="error" />}
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="space-y-3">
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Hostname</p>
                <input
                  placeholder="Hostname"
                  value={deviceForm.hostname ?? ""}
                  onChange={(event) => setDeviceForm((prev) => ({ ...prev, hostname: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">IP address</p>
                <input
                  placeholder="IP address"
                  value={deviceForm.ip_address}
                  onChange={(event) => setDeviceForm((prev) => ({ ...prev, ip_address: event.target.value }))}
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
                  value={deviceForm.tacacs_key}
                  onChange={(event) => setDeviceForm((prev) => ({ ...prev, tacacs_key: event.target.value }))}
                  className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Vendor Profile</p>
                <SearchableSelect
                  value={deviceForm.vendor_name ?? ""}
                  onChange={(nextVendor) => setDeviceForm((prev) => ({ ...prev, vendor_name: nextVendor }))}
                  placeholder="Search vendor profile"
                  options={[
                    { value: "", label: "No vendor" },
                    ...vendors.map((vendor) => ({
                      value: vendor.vendor_name,
                      label: vendor.vendor_name,
                    })),
                  ]}
                />
              </div>
              <div className="space-y-1">
                <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
                <textarea
                  placeholder="Description"
                  value={deviceForm.description ?? ""}
                  onChange={(event) => setDeviceForm((prev) => ({ ...prev, description: event.target.value }))}
                  className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="glass-soft h-full space-y-3 rounded-xl p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="glass-muted text-xs uppercase tracking-wide">Device group</p>
                <span className="assigned-count-badge">{deviceSelectedGroup ? 1 : 0}</span>
              </div>
              <div className="space-y-2">
                <div className="grid gap-2">
                  <SearchableSelect
                    value={deviceGroupCandidate}
                    disabled={!editingDevice}
                    onChange={(nextGroup) => {
                      setDeviceGroupCandidate(nextGroup);
                      if (!editingDevice) return;
                      setDeviceSelectedGroup(nextGroup);
                    }}
                    placeholder="Search group"
                    options={[
                      { value: "", label: "No group" },
                      ...deviceGroups.map((group) => ({
                        value: group.group_name,
                        label: group.group_name,
                      })),
                    ]}
                  />
                </div>
                {!editingDevice && (
                  <p className="glass-muted text-xs">Create device first, then assign group.</p>
                )}
              </div>

              <div className="mt-1 pt-3">
                <div className="assigned-groups-panel rounded-xl p-3">
                  <p className="glass-muted mb-2 text-[10px] uppercase tracking-wide">Assigned group</p>
                  <div className="flex flex-wrap gap-2">
                    {deviceSelectedGroup ? (
                      <div className="assigned-chip">
                        <TruncatedLabel text={deviceSelectedGroup} className="assigned-chip-label" />
                        <button
                          type="button"
                          onClick={() => setDeviceSelectedGroup("")}
                          className="assigned-chip-remove glass-focus"
                          aria-label={`Remove ${deviceSelectedGroup}`}
                          title={`Remove ${deviceSelectedGroup}`}
                        >
                          ×
                        </button>
                      </div>
                    ) : (
                      <span className="glass-muted text-xs">No group selected</span>
                    )}
                  </div>
                  {editingDevice && deviceCurrentGroup && (
                    <p className="glass-muted mt-2 text-xs">
                      Current group in DB: <span className="glass-title font-medium">{deviceCurrentGroup}</span>
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {!editingDevice && (
              <button
                type="button"
                onClick={createDeviceAndContinue}
                className="glass-btn-secondary glass-focus cursor-pointer rounded-xl px-3 py-2 text-sm font-medium"
              >
                Create and continue
              </button>
            )}
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingDeviceGroup ? "Edit device group" : "Create device group"}
        open={deviceGroupModalOpen}
        actions={
          <button
            type="button"
            onClick={saveDeviceGroup}
            className="glass-btn-primary glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            Save
          </button>
        }
        onClose={() => setDeviceGroupModalOpen(false)}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Group name</p>
            <input
              placeholder="Group name"
              value={deviceGroupForm.group_name}
              disabled={Boolean(editingDeviceGroup)}
              onChange={(event) => setDeviceGroupForm((prev) => ({ ...prev, group_name: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">TACACS key</p>
            <input
              placeholder="TACACS key"
              value={deviceGroupForm.tacacs_key ?? ""}
              onChange={(event) => setDeviceGroupForm((prev) => ({ ...prev, tacacs_key: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
            <textarea
              placeholder="Description"
              value={deviceGroupForm.description ?? ""}
              onChange={(event) => setDeviceGroupForm((prev) => ({ ...prev, description: event.target.value }))}
              className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
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
        open={Boolean(deleteDeviceTarget)}
        title="Delete device"
        description={`Delete device ${deleteDeviceTarget?.ip_address ?? ""}?`}
        onCancel={() => setDeleteDeviceTarget(null)}
        onConfirm={deleteDevice}
      />

      <ConfirmDelete
        open={Boolean(deleteVendorTarget)}
        title="Delete vendor profile"
        description={`Delete vendor profile ${deleteVendorTarget?.vendor_name ?? ""}?`}
        onCancel={() => setDeleteVendorTarget(null)}
        onConfirm={deleteVendor}
      />

      <ConfirmDelete
        open={Boolean(deleteDeviceGroupTarget)}
        title="Delete device group"
        description={`Delete device group ${deleteDeviceGroupTarget?.group_name ?? ""}?`}
        onCancel={() => setDeleteDeviceGroupTarget(null)}
        onConfirm={deleteDeviceGroup}
      />

      <EntityModal
        title="Generated TACACS files"
        open={applyPreviewOpen}
        onClose={() => setApplyPreviewOpen(false)}
      >
        <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
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
            <p className="glass-muted text-[10px] uppercase tracking-wide">user_groups</p>
            <textarea
              readOnly
              value={applyPreview?.user_groups ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">devices</p>
            <textarea
              readOnly
              value={applyPreview?.devices ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">profiles</p>
            <textarea
              readOnly
              value={applyPreview?.profiles ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[10px] uppercase tracking-wide">ruleset</p>
            <textarea
              readOnly
              value={applyPreview?.ruleset ?? ""}
              className="glass-input glass-focus min-h-40 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingVendor ? "Edit vendor profile" : "Create vendor profile"}
        open={vendorModalOpen}
        actions={
          <button
            type="button"
            onClick={saveVendor}
            className="glass-btn-primary glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            Save
          </button>
        }
        onClose={() => setVendorModalOpen(false)}
      >
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Vendor name</p>
            <input
              placeholder="Vendor profile name"
              value={vendorForm.vendor_name}
              disabled={Boolean(editingVendor)}
              onChange={(event) => setVendorForm((prev) => ({ ...prev, vendor_name: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
            <textarea
              placeholder="Description"
              value={vendorForm.description ?? ""}
              onChange={(event) => setVendorForm((prev) => ({ ...prev, description: event.target.value }))}
              className="glass-input glass-focus min-h-20 w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>
        </div>
      </EntityModal>

      <EntityModal
        title={editingProfile ? "Edit profile" : "Create profile"}
        open={profileModalOpen}
        actions={
          <button
            type="button"
            onClick={saveProfile}
            className="glass-btn-primary glass-focus cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium"
          >
            Save
          </button>
        }
        onClose={() => setProfileModalOpen(false)}
      >
        <div className="space-y-3">
          {profileModalError && <Alert message={profileModalError} variant="error" />}

          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Profile name</p>
            <input
              placeholder="Profile name"
              value={profileForm.profile_name}
              disabled={Boolean(editingProfile)}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, profile_name: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Profile body (tac_plus-ng syntax)</p>
            <textarea
              placeholder="service = exec {\n\tpriv-lvl = 15\n}"
              value={profileForm.profile_body}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, profile_body: event.target.value }))}
              className="glass-input glass-focus min-h-36 w-full rounded-xl px-3 py-2 font-mono text-xs"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Description</p>
            <input
              placeholder="Description"
              value={profileForm.description ?? ""}
              onChange={(event) => setProfileForm((prev) => ({ ...prev, description: event.target.value }))}
              className="glass-input glass-focus w-full rounded-xl px-3 py-2 text-sm"
            />
          </div>

          <div className="space-y-1">
            <p className="glass-muted text-[8px] uppercase tracking-wide">Status</p>
            <div className="inline-flex items-center gap-3">
              <Switch.Root
                checked={profileForm.is_active}
                onCheckedChange={(checked) => setProfileForm((prev) => ({ ...prev, is_active: checked }))}
                aria-label="Toggle profile status"
                className="status-switch-root glass-focus"
              >
                <Switch.Thumb className="status-switch-thumb" />
              </Switch.Root>
              <span className={`text-sm font-medium ${profileForm.is_active ? "status-success-text" : "status-warn-text"}`}>
                {profileForm.is_active ? "Active" : "Disabled"}
              </span>
            </div>
          </div>

        </div>
      </EntityModal>

      <ConfirmDelete
        open={Boolean(deleteProfileTarget)}
        title="Delete profile"
        description={`Delete profile ${deleteProfileTarget?.profile_name ?? ""}?`}
        onCancel={() => setDeleteProfileTarget(null)}
        onConfirm={deleteProfile}
      />
    </div>
  );
}
