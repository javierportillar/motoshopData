import { cookies } from "next/headers";

const TOKEN_COOKIE = "motoshop_token";
const REFRESH_COOKIE = "motoshop_refresh";

export function getServerToken(): string | null {
  const cookieStore = cookies();
  return cookieStore.get(TOKEN_COOKIE)?.value ?? null;
}

export function getServerRefreshToken(): string | null {
  const cookieStore = cookies();
  return cookieStore.get(REFRESH_COOKIE)?.value ?? null;
}
