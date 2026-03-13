import type {
  ApiEnvelope,
  DeviceGroupMemberPayload,
  DeviceGroupMemberRecord,
  Device,
  DeviceCreatePayload,
  DeviceGroup,
  DeviceGroupCreatePayload,
  DeviceUpdatePayload,
  Profile,
  ProfileCreatePayload,
  ProfileUpdatePayload,
  User,
  UserCreatePayload,
  UserProfileMemberPayload,
  UserProfileMemberRecord,
  UserGroupMemberPayload,
  UserGroupMemberRecord,
  TotpConfigPayload,
  TotpProfile,
  Vendor,
  VendorCreatePayload,
  GenerateConfigResponse,
  UserUpdatePayload,
  TacacsLogResponse,
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

  vendors: {
    list: () => request<{ success: boolean; data: Vendor[] }>("/vendors"),
    get: (vendorName: string) =>
      request<{ success: boolean; vendor: Vendor }>(`/vendors/${encodeURIComponent(vendorName)}`),
    create: (payload: VendorCreatePayload) =>
      request<{ success: boolean; vendor: Vendor }>("/vendors", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (vendorName: string, payload: VendorCreatePayload) =>
      request<{ success: boolean; vendor: Vendor }>(`/vendors/${encodeURIComponent(vendorName)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (vendorName: string) =>
      request<void>(`/vendors/${encodeURIComponent(vendorName)}`, {
        method: "DELETE",
      }),
  },

  devices: {
    list: () => request<{ success: boolean; data: Device[] }>("/devices"),
    get: (ipAddress: string) =>
      request<{ success: boolean; device: Device }>(`/devices/${encodeURIComponent(ipAddress)}`),
    create: (payload: DeviceCreatePayload) =>
      request<{ success: boolean; device: Device }>("/devices", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (ipAddress: string, payload: DeviceUpdatePayload) =>
      request<{ success: boolean; device: Device }>(`/devices/${encodeURIComponent(ipAddress)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (ipAddress: string) =>
      request<void>(`/devices/${encodeURIComponent(ipAddress)}`, {
        method: "DELETE",
      }),
  },

  userGroups: {
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

  deviceGroups: {
    list: () => request<{ success: boolean; data: DeviceGroup[] }>("/device-groups"),
    get: (groupName: string) =>
      request<{ success: boolean; group: DeviceGroup }>(`/device-groups/${encodeURIComponent(groupName)}`),
    create: (payload: DeviceGroupCreatePayload) =>
      request<{ success: boolean; group: DeviceGroup }>("/device-groups", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (groupName: string, payload: DeviceGroupCreatePayload) =>
      request<{ success: boolean; group: DeviceGroup }>(`/device-groups/${encodeURIComponent(groupName)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    delete: (groupName: string) =>
      request<void>(`/device-groups/${encodeURIComponent(groupName)}`, {
        method: "DELETE",
      }),

    members: {
      list: (params?: { ip_address?: string; group_name?: string }) => {
        const query = new URLSearchParams();
        if (params?.ip_address) query.set("ip_address", params.ip_address);
        if (params?.group_name) query.set("group_name", params.group_name);
        const suffix = query.toString() ? `?${query.toString()}` : "";
        return request<{ success: boolean; data: DeviceGroupMemberRecord[] }>(`/device-group-members${suffix}`);
      },
      add: (payload: DeviceGroupMemberPayload) =>
        request<{ success: boolean; member: DeviceGroupMemberRecord | null }>("/device-group-members", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      remove: (payload: DeviceGroupMemberPayload) =>
        request<void>("/device-group-members", {
          method: "DELETE",
          body: JSON.stringify(payload),
        }),
    },
  },

  profiles: {
    list: () => request<{ success: boolean; data: Profile[] }>("/profiles"),
    get: (profileName: string) =>
      request<{ success: boolean; profile: Profile }>(`/profiles/${encodeURIComponent(profileName)}`),
    create: (payload: ProfileCreatePayload) =>
      request<{ success: boolean; profile: Profile }>("/profiles", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (profileName: string, payload: ProfileUpdatePayload) =>
      request<{ success: boolean; profile: Profile }>(`/profiles/${encodeURIComponent(profileName)}`, {
        method: "PUT",
        body: JSON.stringify({
          profile_name: profileName,
          profile_body: payload.profile_body,
          description: payload.description,
          is_active: payload.is_active,
        }),
      }),
    delete: (profileName: string) =>
      request<void>(`/profiles/${encodeURIComponent(profileName)}`, {
        method: "DELETE",
      }),

    userMembers: {
      list: (params?: { username?: string; profile_name?: string }) => {
        const query = new URLSearchParams();
        if (params?.username) query.set("username", params.username);
        if (params?.profile_name) query.set("profile_name", params.profile_name);
        const suffix = query.toString() ? `?${query.toString()}` : "";
        return request<{ success: boolean; data: UserProfileMemberRecord[] }>(`/user-profile-members${suffix}`);
      },
      add: (payload: UserProfileMemberPayload) =>
        request<{ success: boolean; member: UserProfileMemberRecord | null }>("/user-profile-members", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      remove: (payload: UserProfileMemberPayload) =>
        request<void>("/user-profile-members", {
          method: "DELETE",
          body: JSON.stringify(payload),
        }),
    },
  },

  config: {
    generate: () =>
      request<GenerateConfigResponse>("/generate-config/", {
        method: "POST",
      }),
  },

  logs: {
    tacacs: (limit = 200) =>
      request<TacacsLogResponse>(`/logs/tacacs?limit=${encodeURIComponent(String(limit))}`),
  },
};

export { ApiError };
