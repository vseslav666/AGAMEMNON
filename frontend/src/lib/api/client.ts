import type {
  ApiEnvelope,
  HostGroupMemberPayload,
  HostGroupMemberRecord,
  Host,
  HostCreatePayload,
  HostGroup,
  HostGroupCreatePayload,
  HostUpdatePayload,
  Policy,
  PolicyCreatePayload,
  User,
  UserCreatePayload,
  UserGroupMemberPayload,
  UserGroupMemberRecord,
  UserGroup,
  UserGroupCreatePayload,
  TotpConfigPayload,
  TotpProfile,
  GenerateConfigResponse,
  UserUpdatePayload,
} from "@/lib/types/tacacs";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const rawText = await response.text();
  let body: ApiEnvelope<T> | Record<string, unknown>;
  try {
    body = rawText ? (JSON.parse(rawText) as ApiEnvelope<T> | Record<string, unknown>) : {};
  } catch (parseError) {
    console.error("[api.request] failed to parse JSON", {
      path,
      status: response.status,
      rawText,
      parseError,
    });
    throw new ApiError(`Invalid JSON response (status ${response.status})`, response.status);
  }

  if (!response.ok) {
    const detail =
      (body as { detail?: string }).detail ??
      (body as { error?: string }).error ??
      `Request failed with status ${response.status}`;
    throw new ApiError(detail, response.status);
  }

  if ((body as ApiEnvelope<T>).success === false) {
    const message =
      (body as ApiEnvelope<T>).error ??
      (body as ApiEnvelope<T>).reason ??
      "Operation failed";
    throw new ApiError(message, response.status);
  }

  return body as T;
}

export const api = {
  users: {
    list: () => request<{ success: boolean; data: User[] }>("/users"),
    get: (username: string) => request<{ success: boolean; user: User }>(`/users/${username}`),
    create: (payload: UserCreatePayload) =>
      request<{ success: boolean; user: User }>("/users", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (username: string, payload: UserUpdatePayload) =>
      request<{ success: boolean; user: User }>(`/users/${username}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (username: string) =>
      request<void>(`/users/${username}`, {
        method: "DELETE",
      }),

    totp: {
      get: (username: string) =>
        request<{ success: boolean; totp: TotpProfile }>(`/users/${encodeURIComponent(username)}/totp`),
      createOrUpdate: (username: string, payload: TotpConfigPayload) =>
        request<{ success: boolean; totp: TotpProfile; secret: string; otp_uri: string }>(
          `/users/${encodeURIComponent(username)}/totp`,
          {
            method: "POST",
            body: JSON.stringify(payload),
          },
        ),
      delete: (username: string) =>
        request<void>(`/users/${encodeURIComponent(username)}/totp`, {
          method: "DELETE",
        }),
      disable: (username: string) =>
        request<{ success: boolean; totp: TotpProfile }>(`/users/${encodeURIComponent(username)}/totp/disable`, {
          method: "POST",
        }),
    },
  },

  hosts: {
    list: () => request<{ success: boolean; data: Host[] }>("/hosts"),
    get: (ipAddress: string) =>
      request<{ success: boolean; host: Host }>(`/hosts/${encodeURIComponent(ipAddress)}`),
    create: (payload: HostCreatePayload) =>
      request<{ success: boolean; host: Host }>("/hosts", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (ipAddress: string, payload: HostUpdatePayload) =>
      request<{ success: boolean; host: Host }>(`/hosts/${encodeURIComponent(ipAddress)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (ipAddress: string) =>
      request<void>(`/hosts/${encodeURIComponent(ipAddress)}`, {
        method: "DELETE",
      }),
  },

  userGroups: {
    list: () => request<{ success: boolean; data: UserGroup[] }>("/user-groups"),
    get: (groupName: string) =>
      request<{ success: boolean; group: UserGroup }>(`/user-groups/${encodeURIComponent(groupName)}`),
    create: (payload: UserGroupCreatePayload) =>
      request<{ success: boolean; group: UserGroup }>("/user-groups", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (groupName: string, payload: UserGroupCreatePayload) =>
      request<{ success: boolean; group: UserGroup }>(`/user-groups/${encodeURIComponent(groupName)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (groupName: string) =>
      request<void>(`/user-groups/${encodeURIComponent(groupName)}`, {
        method: "DELETE",
      }),

    members: {
      list: (params?: { username?: string; group_name?: string }) => {
        const query = new URLSearchParams();
        if (params?.username) query.set("username", params.username);
        if (params?.group_name) query.set("group_name", params.group_name);
        const suffix = query.toString() ? `?${query.toString()}` : "";
        return request<{ success: boolean; data: UserGroupMemberRecord[] }>(`/user-group-members${suffix}`);
      },
      add: (payload: UserGroupMemberPayload) =>
        request<{ success: boolean; member: UserGroupMemberRecord | null }>("/user-group-members", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      remove: (payload: UserGroupMemberPayload) =>
        request<void>("/user-group-members", {
          method: "DELETE",
          body: JSON.stringify(payload),
        }),
    },
  },

  hostGroups: {
    list: () => request<{ success: boolean; data: HostGroup[] }>("/host-groups"),
    get: (groupName: string) =>
      request<{ success: boolean; group: HostGroup }>(`/host-groups/${encodeURIComponent(groupName)}`),
    create: (payload: HostGroupCreatePayload) =>
      request<{ success: boolean; group: HostGroup }>("/host-groups", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (groupName: string, payload: HostGroupCreatePayload) =>
      request<{ success: boolean; group: HostGroup }>(`/host-groups/${encodeURIComponent(groupName)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (groupName: string) =>
      request<void>(`/host-groups/${encodeURIComponent(groupName)}`, {
        method: "DELETE",
      }),

    members: {
      list: (params?: { ip_address?: string; group_name?: string }) => {
        const query = new URLSearchParams();
        if (params?.ip_address) query.set("ip_address", params.ip_address);
        if (params?.group_name) query.set("group_name", params.group_name);
        const suffix = query.toString() ? `?${query.toString()}` : "";
        return request<{ success: boolean; data: HostGroupMemberRecord[] }>(`/host-group-members${suffix}`);
      },
      add: (payload: HostGroupMemberPayload) =>
        request<{ success: boolean; member: HostGroupMemberRecord | null }>("/host-group-members", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      remove: (payload: HostGroupMemberPayload) =>
        request<void>("/host-group-members", {
          method: "DELETE",
          body: JSON.stringify(payload),
        }),
    },
  },

  policies: {
    list: () => request<{ success: boolean; data: Policy[] }>("/policies"),
    get: (policyId: number) => request<{ success: boolean; policy: Policy }>(`/policies/${policyId}`),
    create: (payload: PolicyCreatePayload) =>
      request<{ success: boolean; policy: Policy }>("/policies", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    delete: (policyId: number) =>
      request<void>(`/policies/${policyId}`, {
        method: "DELETE",
      }),
  },

  config: {
    generate: () =>
      request<GenerateConfigResponse>("/generate-config/", {
        method: "POST",
      }),
  },
};

export { ApiError };
