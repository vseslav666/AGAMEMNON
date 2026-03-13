export type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: string;
  reason?: string;
  [key: string]: unknown;
};

export type User = {
  user_id?: number;
  username: string;
  password_hash?: string;
  full_name?: string | null;
  description?: string | null;
  is_active: boolean;
};

export type UserCreatePayload = {
  username: string;
  password: string;
  full_name?: string;
  description?: string;
  is_active: boolean;
};

export type UserUpdatePayload = {
  password?: string;
  full_name?: string;
  description?: string;
  is_active?: boolean;
};

export type AuthMode = "password" | "totp";

export type TotpConfigPayload = {
  issuer?: string;
  digits?: number;
  period?: number;
  is_enabled?: boolean;
};

export type TotpProfile = {
  id?: number;
  user_id?: number;
  totp_secret: string;
  is_enabled: boolean;
  created_at?: string;
  last_used_at?: string | null;
};

export type Vendor = {
  vendor_id?: number;
  vendor_name: string;
  description?: string | null;
};

export type VendorCreatePayload = {
  vendor_name: string;
  description?: string;
};

export type Device = {
  device_id?: number;
  ip_address: string;
  tacacs_key: string;
  hostname?: string | null;
  vendor_id?: number | null;
  vendor_name?: string | null;
  description?: string | null;
};

export type DeviceCreatePayload = {
  ip_address: string;
  tacacs_key: string;
  hostname?: string;
  vendor_name: string;
  description?: string;
};

export type DeviceUpdatePayload = {
  new_ip_address?: string;
  tacacs_key?: string;
  hostname?: string;
  vendor_name?: string;
  description?: string;
};

export type UserGroupMemberPayload = {
  username: string;
  group_name: string;
  ro_rw?: number;
};

export type UserGroupMemberRecord = {
  username: string;
  group_name: string;
  ro_rw?: number;
};

export type DeviceGroup = {
  group_id?: number;
  group_name: string;
  tacacs_key?: string | null;
  description?: string | null;
};

export type DeviceGroupCreatePayload = {
  group_name: string;
  tacacs_key?: string;
  description?: string;
};

export type DeviceGroupMemberPayload = {
  ip_address: string;
  group_name: string;
};

export type DeviceGroupMemberRecord = {
  ip_address: string;
  group_name: string;
};

export type Profile = {
  profile_id?: number;
  profile_name: string;
  profile_body: string;
  description?: string | null;
  is_active: boolean;
};

export type ProfileCreatePayload = {
  profile_name: string;
  profile_body: string;
  description?: string;
  is_active: boolean;
};

export type ProfileUpdatePayload = {
  profile_body: string;
  description?: string;
  is_active: boolean;
};

export type UserProfileMemberPayload = {
  username: string;
  profile_name: string;
};

export type UserProfileMemberRecord = {
  username: string;
  profile_name: string;
};

export type GeneratedFileMeta = {
  file: "users" | "user_groups" | "devices" | "profiles" | "ruleset";
  records: number;
};

export type GenerateApplyResult = {
  success: boolean;
  validated: boolean;
  reloaded: boolean;
  message?: string;
  error?: string;
  validation?: {
    command: string;
    exit_code: number | null;
    stdout?: string;
    stderr?: string;
    ok: boolean;
  };
};

export type GenerateConfigResponse = {
  success: boolean;
  path: string;
  files: GeneratedFileMeta[];
  apply?: GenerateApplyResult;
  file_contents: {
    users: string;
    user_groups: string;
    devices: string;
    profiles: string;
    ruleset: string;
  };
};

export type TacacsLogLevel = "error" | "warn" | "info" | "debug" | "unknown";

export type TacacsLogLine = {
  id: number;
  raw: string;
  message: string;
  timestamp: string | null;
  session: string | null;
  host: string | null;
  level: TacacsLogLevel;
};

export type TacacsEventKind = "authentication" | "authorization" | "accounting";
export type TacacsEventResult = "success" | "failure" | "unknown";

export type TacacsLogEvent = {
  id: number;
  line_id: number;
  timestamp: string | null;
  session: string | null;
  session_id: string | null;
  host: string | null;
  kind: TacacsEventKind;
  result: TacacsEventResult;
  message: string;
  username: string | null;
  remote_addr: string | null;
  port: string | null;
  attrs: Record<string, string>;
};

export type TacacsLogResponse = {
  success: boolean;
  file_path: string;
  limit: number;
  total_lines: number;
  missing: boolean;
  generated_at: string;
  lines: TacacsLogLine[];
  events: TacacsLogEvent[];
};
