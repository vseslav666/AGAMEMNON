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

export type Host = {
  host_id?: number;
  ip_address: string;
  tacacs_key: string;
  hostname?: string | null;
  description?: string | null;
};

export type HostCreatePayload = {
  ip_address: string;
  tacacs_key: string;
  hostname?: string;
  description?: string;
};

export type HostUpdatePayload = {
  tacacs_key?: string;
  hostname?: string;
  description?: string;
};

export type UserGroup = {
  group_id?: number;
  group_name: string;
  description?: string | null;
};

export type UserGroupCreatePayload = {
  group_name: string;
  description?: string;
};

export type UserGroupMemberPayload = {
  username: string;
  group_name: string;
};

export type UserGroupMemberRecord = {
  username: string;
  group_name: string;
};

export type HostGroup = {
  group_id?: number;
  group_name: string;
  tacacs_key?: string | null;
  description?: string | null;
};

export type HostGroupCreatePayload = {
  group_name: string;
  tacacs_key?: string;
  description?: string;
};

export type HostGroupMemberPayload = {
  ip_address: string;
  group_name: string;
};

export type HostGroupMemberRecord = {
  ip_address: string;
  group_name: string;
};

export type Policy = {
  policy_id?: number;
  user_group_id?: number;
  host_group_id?: number;
  user_group_name: string;
  host_group_name: string;
  priv_lvl: number;
  allow_access: boolean;
};

export type PolicyCreatePayload = {
  user_group_name: string;
  host_group_name: string;
  priv_lvl: number;
  allow_access: boolean;
};

export type GeneratedFileMeta = {
  file: "users" | "hosts" | "host_groups";
  records: number;
};

export type GenerateConfigResponse = {
  success: boolean;
  path: string;
  files: GeneratedFileMeta[];
  file_contents: {
    users: string;
    hosts: string;
    host_groups: string;
  };
};
